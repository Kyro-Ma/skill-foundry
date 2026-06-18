#!/usr/bin/env python3
"""Discover recent user needs online and turn them into reviewed Codex skills."""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import dataclasses
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


UTC = dt.timezone.utc
MAX_WORKERS = 10
USER_AGENT = "skill-demand-agent/1.0 (+https://openai.com/codex)"
SIMILARITY_DEDUPE_THRESHOLD = 0.72
CLAW_HUB_SKILLS_API = "https://clawhub.ai/api/v1/skills"
CLAW_HUB_SKILL_PAGE = "https://clawhub.ai/skills/{slug}"
CLAW_HUB_MIN_DOWNLOADS = 100_000
CLAW_HUB_POPULAR_LIMIT = 100

ASCII_TRANSLATION = str.maketrans(
    {
        "\u00a0": " ",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
        "\u2212": "-",
    }
)

NEED_PATTERNS = [
    r"\bi need\b",
    r"\bwe need\b",
    r"\blooking for\b",
    r"\bhow do i\b",
    r"\bhow can i\b",
    r"\bwhat('s| is) the best way\b",
    r"\bany tool\b",
    r"\btool for\b",
    r"\brecommend\b",
    r"\bsuggest\b",
    r"\bstruggl(?:e|ing)\b",
    r"\bwish there (?:was|were)\b",
    r"\bcan someone help\b",
    r"\bfeature request\b",
    r"\benhancement\b",
    r"需求",
    r"如何",
    r"怎么",
    r"求推荐",
    r"有没有",
    r"报错",
    r"优化",
    r"改进",
    r"支持",
]

EXCLUDE_PATTERNS = [
    r"\bwho is hiring\b",
    r"\bmonthly hiring\b",
    r"\bshow hn\b",
    r"\blaunched\b",
    r"\bpress release\b",
    r"\bgiveaway\b",
]

STOPWORDS = {
    "a",
    "about",
    "after",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "best",
    "but",
    "by",
    "can",
    "could",
    "do",
    "does",
    "enhancement",
    "feat",
    "feature",
    "for",
    "from",
    "get",
    "getting",
    "good",
    "have",
    "help",
    "how",
    "i",
    "in",
    "into",
    "is",
    "it",
    "me",
    "my",
    "need",
    "new",
    "of",
    "on",
    "or",
    "our",
    "please",
    "recommend",
    "request",
    "should",
    "some",
    "that",
    "the",
    "this",
    "to",
    "tool",
    "use",
    "using",
    "want",
    "way",
    "we",
    "what",
    "when",
    "where",
    "which",
    "with",
    "without",
    "you",
    "your",
}

PREFIX_WORDS = {
    "ask",
    "hn",
    "feature",
    "request",
    "enhancement",
    "feat",
    "fr",
    "issue",
}

CLAW_HUB_GENERIC_TERMS = {
    "agent",
    "agents",
    "clawhub",
    "clawdhub",
    "clawdbot",
    "download",
    "downloads",
    "latest",
    "popular",
    "skill",
    "skills",
    "version",
}

CATEGORY_KEYWORDS = {
    "work-productivity": {
        "meeting",
        "email",
        "calendar",
        "project",
        "team",
        "manager",
        "workflow",
        "client",
        "report",
        "sales",
        "crm",
        "freelance",
        "job",
    },
    "software-and-data": {
        "code",
        "api",
        "python",
        "javascript",
        "database",
        "sql",
        "github",
        "bug",
        "deploy",
        "server",
        "data",
        "spreadsheet",
    },
    "learning-and-research": {
        "learn",
        "study",
        "course",
        "research",
        "paper",
        "school",
        "student",
        "teacher",
        "explain",
        "notes",
    },
    "creative-and-content": {
        "write",
        "video",
        "image",
        "design",
        "music",
        "story",
        "blog",
        "content",
        "social",
        "presentation",
    },
    "personal-happiness": {
        "habit",
        "health",
        "fitness",
        "sleep",
        "family",
        "relationship",
        "fun",
        "hobby",
        "travel",
        "mood",
        "stress",
    },
    "business-and-operations": {
        "business",
        "invoice",
        "customer",
        "support",
        "marketing",
        "startup",
        "pricing",
        "inventory",
        "finance",
    },
}

DEMAND_THEMES = [
    {
        "theme_id": "unit-test-coverage",
        "summary": "Teams need repeatable help adding useful unit tests and raising test coverage for existing codebases.",
        "audience": "software maintainers, QA engineers, open-source contributors, and product teams who need confidence that changes do not break existing behavior",
        "category": "software-and-data",
        "keywords": ["unit tests", "test coverage", "testing", "regression", "quality"],
        "queries": ["unit tests", "test coverage", "add tests"],
    },
    {
        "theme_id": "api-documentation-openapi",
        "summary": "Backend and platform teams need practical help generating, improving, and validating OpenAPI or Swagger documentation for REST APIs.",
        "audience": "API developers, backend teams, developer-experience teams, and maintainers who must make services understandable to other engineers",
        "category": "software-and-data",
        "keywords": ["openapi", "swagger", "api documentation", "rest api", "developer experience"],
        "queries": ["OpenAPI documentation", "Swagger REST API", "API docs"],
    },
    {
        "theme_id": "responsive-ui-fixes",
        "summary": "Product teams need reliable workflows for fixing mobile responsiveness, navigation layout, and cross-device UI issues.",
        "audience": "frontend developers, designers, startup teams, and maintainers responsible for making web interfaces usable on phones and desktop screens",
        "category": "creative-and-content",
        "keywords": ["mobile responsive", "responsive design", "navbar", "layout", "frontend"],
        "queries": ["mobile responsive navbar", "responsive design issue", "mobile layout fix"],
    },
    {
        "theme_id": "clear-error-messages",
        "summary": "Users and support teams need clearer error messages that explain what failed, why it failed, and what action to take next.",
        "audience": "application developers, support teams, SaaS operators, and users who lose time when vague errors block troubleshooting",
        "category": "work-productivity",
        "keywords": ["error messages", "debugging", "user feedback", "support", "troubleshooting"],
        "queries": ["better error messages", "unclear error message", "debugging error message"],
    },
    {
        "theme_id": "local-ai-consumer-hardware",
        "summary": "Builders need guidance for running useful AI and LLM workflows locally on consumer CPU or family GPU hardware without depending on cloud-only systems.",
        "audience": "developers, researchers, privacy-conscious users, hobbyists, and small teams who want local AI workflows on ordinary home machines",
        "category": "software-and-data",
        "keywords": ["local llm", "consumer gpu", "cpu inference", "llama.cpp", "privacy"],
        "queries": ["local LLM consumer GPU", "llama.cpp CPU", "run AI locally"],
    },
    {
        "theme_id": "document-formatting-automation",
        "summary": "Knowledge workers need practical help automating document formatting, find-and-replace, styles, and Word-like editing tasks.",
        "audience": "office workers, legal and operations teams, students, and documentation maintainers who repeatedly clean up structured documents",
        "category": "work-productivity",
        "keywords": ["microsoft word", "document formatting", "find replace", "styles", "automation"],
        "queries": ["Microsoft Word replace formatting", "Word paragraph styles", "document formatting automation"],
    },
    {
        "theme_id": "network-troubleshooting-home-office",
        "summary": "Remote workers and technically curious households need local diagnostic workflows for network issues such as bufferbloat, router problems, and latency.",
        "audience": "remote workers, gamers, home-office users, and small teams who need to diagnose internet quality with consumer networking hardware",
        "category": "general-help",
        "keywords": ["bufferbloat", "router", "modem", "latency", "network troubleshooting"],
        "queries": ["bufferbloat modem router", "home network latency", "router troubleshooting"],
    },
    {
        "theme_id": "product-idea-validation",
        "summary": "Founders and builders need a repeatable way to turn rough product ideas into validated plans, prototypes, and user-facing positioning.",
        "audience": "solo founders, product managers, makers, and small teams who need to test whether a product idea is worth building before spending heavily",
        "category": "business-and-operations",
        "keywords": ["product idea", "validation", "prototype", "saas", "startup"],
        "queries": ["product idea validation", "validate SaaS idea", "prototype product idea"],
    },
]

OFFICE_DEMAND_THEMES = [
    {
        "theme_id": "word-docx-formatting-repair",
        "summary": "Word users and document automation teams need reliable help repairing DOCX formatting, styles, numbering, section breaks, comments, tracked changes, and OOXML compatibility issues.",
        "audience": "knowledge workers, legal and operations teams, documentation maintainers, and developers automating Microsoft Word or DOCX files",
        "category": "work-productivity",
        "keywords": ["microsoft word", "docx", "ooxml", "styles", "numbering", "track changes"],
        "queries": [
            "Microsoft Word DOCX styles numbering issue",
            "python-docx OOXML track changes comments",
            "Word section break formatting automation",
        ],
        "targeted_query_limit": 2,
    },
    {
        "theme_id": "excel-xlsx-formula-data-automation",
        "summary": "Excel users and analysts need practical help fixing XLSX formulas, Power Query refreshes, pivot tables, VBA macros, workbook corruption, and repeatable data cleanup workflows.",
        "audience": "analysts, finance and operations teams, spreadsheet-heavy small businesses, and developers automating Excel workbooks",
        "category": "software-and-data",
        "keywords": ["microsoft excel", "xlsx", "formula", "power query", "vba", "pivot table"],
        "queries": [
            "Microsoft Excel formula Power Query issue",
            "openpyxl xlsx pivot table vba automation",
            "Excel workbook corruption data cleanup",
        ],
        "targeted_query_limit": 2,
    },
    {
        "theme_id": "powerpoint-pptx-layout-export-automation",
        "summary": "PowerPoint users and presentation builders need repeatable help generating, repairing, and exporting PPTX decks with reliable slide layouts, charts, images, speaker notes, and template fidelity.",
        "audience": "presentation designers, consultants, educators, analysts, and developers who build or repair PowerPoint decks programmatically",
        "category": "creative-and-content",
        "keywords": ["microsoft powerpoint", "pptx", "slide layout", "chart export", "python-pptx", "speaker notes"],
        "queries": [
            "PowerPoint PPTX slide layout chart export issue",
            "python-pptx template speaker notes automation",
            "PowerPoint image export layout problem",
        ],
        "targeted_query_limit": 2,
    },
    {
        "theme_id": "word-template-mail-merge-automation",
        "summary": "Word template owners need practical help automating mail merge, content controls, merge fields, document properties, and repeatable DOCX template assembly without breaking formatting.",
        "audience": "administrative teams, legal operations, HR teams, and developers who maintain Word templates or mail-merge document workflows",
        "category": "work-productivity",
        "keywords": ["word mail merge", "docx template", "content controls", "merge fields", "document properties"],
        "queries": [
            "Word mail merge content controls DOCX template issue",
            "python-docx merge fields document properties automation",
        ],
        "targeted_query_limit": 2,
    },
    {
        "theme_id": "excel-report-chart-export-workflow",
        "summary": "Excel report builders need dependable help producing charts, dashboards, conditional formatting, print areas, and PDF or image exports from XLSX workbooks.",
        "audience": "analysts, finance teams, operations teams, and developers who generate recurring Excel reports",
        "category": "software-and-data",
        "keywords": ["excel chart", "dashboard", "conditional formatting", "print area", "export pdf"],
        "queries": [
            "Excel chart dashboard conditional formatting export PDF issue",
            "openpyxl chart print area image export xlsx",
        ],
        "targeted_query_limit": 2,
    },
    {
        "theme_id": "powerpoint-template-master-placeholder-fix",
        "summary": "PowerPoint template maintainers need help repairing slide masters, placeholders, fonts, theme colors, chart links, and branded PPTX layouts that break during automated deck generation.",
        "audience": "brand teams, consultants, presentation operations teams, and developers working with PowerPoint templates",
        "category": "creative-and-content",
        "keywords": ["powerpoint template", "slide master", "placeholder", "theme colors", "chart links"],
        "queries": [
            "PowerPoint slide master placeholder theme colors issue",
            "python-pptx template placeholder chart links",
        ],
        "targeted_query_limit": 2,
    },
    {
        "theme_id": "office-openxml-vba-python-automation",
        "summary": "Office automation builders need dependable workflows for moving data and content across Word, Excel, and PowerPoint using Open XML, VBA, Python libraries, and template-driven pipelines.",
        "audience": "developers, analysts, consultants, and operations teams building repeatable Microsoft Office document, spreadsheet, and presentation workflows",
        "category": "software-and-data",
        "keywords": ["office automation", "open xml", "vba", "python-docx", "openpyxl", "python-pptx"],
        "queries": [
            "Office automation Open XML VBA Python docx xlsx pptx",
            "python-docx openpyxl python-pptx workflow",
            "Microsoft Office template automation issue",
        ],
        "targeted_query_limit": 2,
    },
]

CHINA_DISCOVERY_QUERIES = [
    "单元测试",
    "测试覆盖率",
    "OpenAPI 文档",
    "Swagger 接口文档",
    "移动端 响应式 导航栏",
    "错误提示 优化",
    "本地 大模型 GPU",
    "产品验证",
    "自动化 工作流",
    "用户需求 工具",
]

GITEE_DISCOVERY_QUERIES = [
    "功能 需求",
    "希望 支持",
    "建议 增加",
    "用户 需求",
]

OFFICE_CHINA_DISCOVERY_QUERIES = [
    "Microsoft Word DOCX formatting automation",
    "Microsoft Excel XLSX formula Power Query",
    "PowerPoint PPTX layout export automation",
    "Office Open XML VBA Python automation",
]

OFFICE_GITEE_DISCOVERY_QUERIES = [
    "Word DOCX issue",
    "Excel XLSX issue",
    "PowerPoint PPTX issue",
    "Office automation",
]

MIN_REQUIRED_EVIDENCE = 3
DEFAULT_SCORE_THRESHOLD = 90


def demand_themes_for_profile(theme_profile: str) -> list[dict[str, Any]]:
    if theme_profile == "office":
        return OFFICE_DEMAND_THEMES
    return DEMAND_THEMES


def china_queries_for_profile(theme_profile: str) -> list[str]:
    if theme_profile == "office":
        return OFFICE_CHINA_DISCOVERY_QUERIES
    return CHINA_DISCOVERY_QUERIES


def gitee_queries_for_profile(theme_profile: str) -> list[str]:
    if theme_profile == "office":
        return OFFICE_GITEE_DISCOVERY_QUERIES
    return GITEE_DISCOVERY_QUERIES


@dataclasses.dataclass(frozen=True)
class SourceItem:
    source: str
    title: str
    body: str
    url: str
    created_at: str
    raw_score: float
    tags: list[str]


@dataclasses.dataclass(frozen=True)
class Requirement:
    requirement_id: str
    summary: str
    audience: str
    category: str
    evidence: list[dict[str, str]]
    keywords: list[str]
    score: float
    demand_score: int
    feasibility_score: int
    evidence_count: int
    source_count: int
    scoring_rationale: list[str]


@dataclasses.dataclass(frozen=True)
class SkillPlan:
    skill_name: str
    display_name: str
    requirement: Requirement
    how_it_meets_need: str
    implementation_steps: list[str]
    validation_checks: list[str]
    outputs: list[str]
    trigger_sentences: list[str]
    keywords: list[str]


@dataclasses.dataclass(frozen=True)
class ReviewResult:
    skill_name: str
    passed: bool
    score: int
    findings: list[str]
    path: str


def utc_now() -> dt.datetime:
    return dt.datetime.now(tz=UTC)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def ascii_safe(value: str) -> str:
    text = value.translate(ASCII_TRANSLATION)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", errors="ignore").decode("ascii", errors="ignore")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def safe_filename(value: str, default: str = "skill") -> str:
    words = re.findall(r"[a-z0-9]+", value.lower())
    words = [w for w in words if w not in STOPWORDS]
    slug = "-".join(words[:7]) or default
    slug = re.sub(r"-+", "-", slug).strip("-")[:56].strip("-")
    return slug or default


def md_escape(value: str) -> str:
    return value.replace("|", "\\|").strip()


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def http_json(url: str, timeout: int = 4, headers: dict[str, str] | None = None) -> Any:
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/plain,*/*",
    }
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = response.read().decode("utf-8", errors="replace")
    return json.loads(payload)


def http_text(url: str, timeout: int = 4, headers: dict[str, str] | None = None) -> str:
    request_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_html_links(source: str, html_text: str, base_url: str, limit: int) -> list[SourceItem]:
    items: list[SourceItem] = []
    seen: set[str] = set()
    for match in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html_text, flags=re.I | re.S):
        href, title_html = match.groups()
        title = clean_text(title_html)
        if any(noise in title.lower() for noise in ["登录", "注册", "搜本站", "bing", "google", "关于我们"]):
            continue
        if len(title) < 8 or excluded(title):
            continue
        url = urllib.parse.urljoin(base_url, html.unescape(href))
        if url in seen or url.startswith("javascript:"):
            continue
        seen.add(url)
        items.append(
            SourceItem(
                source=source,
                title=title[:180],
                body="",
                url=url,
                created_at=utc_now().isoformat(),
                raw_score=1.0,
                tags=[source],
            )
        )
        if len(items) >= limit:
            break
    return items


def source_family(source: str) -> str:
    if source.startswith("hacker-news"):
        return "hacker-news"
    if source.startswith("github"):
        return "github"
    if source.startswith("gitee"):
        return "gitee"
    if source.startswith("v2ex"):
        return "v2ex"
    if source.startswith("juejin"):
        return "juejin"
    if source.startswith("csdn"):
        return "csdn"
    if source.startswith("oschina"):
        return "oschina"
    if source.startswith("segmentfault"):
        return "segmentfault"
    if source.startswith("clawhub"):
        return "clawhub"
    return source.split("-", 1)[0]


def unique_source_items(items: list[SourceItem], limit: int = 12) -> list[SourceItem]:
    seen_urls: set[str] = set()
    unique: list[SourceItem] = []
    for item in sorted(items, key=lambda value: value.raw_score, reverse=True):
        if excluded(item.title):
            continue
        key = item.url or f"{item.source}:{item.title}"
        if key in seen_urls:
            continue
        seen_urls.add(key)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def item_matches_terms(item: SourceItem, terms: list[str]) -> bool:
    haystack = f"{item.title} {item.body} {' '.join(item.tags)}".lower()
    token_hits = 0
    for term in terms:
        normalized = term.lower()
        if " " in normalized:
            if normalized in haystack:
                return True
            continue
        if re.search(rf"\b{re.escape(normalized)}\b", haystack):
            token_hits += 1
    return token_hits >= 2


def parse_created(value: Any) -> dt.datetime:
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        try:
            parsed = dt.datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            return utc_now()
    return utc_now()


def parse_clawhub_timestamp(value: Any) -> dt.datetime:
    if isinstance(value, (int, float)):
        timestamp = float(value)
    elif isinstance(value, str) and value.strip().isdigit():
        timestamp = float(value.strip())
    else:
        return parse_created(value)
    if timestamp > 10_000_000_000:
        timestamp /= 1000
    return dt.datetime.fromtimestamp(timestamp, tz=UTC)


def int_stat(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def clawhub_skill_terms(text: str, tags: list[str] | None = None, limit: int = 8) -> list[str]:
    terms = extract_keywords(text, tags or [], limit=limit + 8)
    filtered = [
        term
        for term in terms
        if term not in CLAW_HUB_GENERIC_TERMS
        and not term.startswith("download")
        and not re.fullmatch(r"\d+", term)
    ]
    return filtered[:limit]


def fetch_hacker_news(days: int, limit: int) -> list[SourceItem]:
    since = int((utc_now() - dt.timedelta(days=days)).timestamp())
    params = {
        "tags": "ask_hn",
        "hitsPerPage": str(min(max(limit, 20), 100)),
        "numericFilters": f"created_at_i>{since}",
    }
    url = "https://hn.algolia.com/api/v1/search_by_date?" + urllib.parse.urlencode(params)
    data = http_json(url)
    items: list[SourceItem] = []
    for hit in data.get("hits", []):
        title = clean_text(hit.get("title") or hit.get("story_title"))
        if not title:
            continue
        object_id = hit.get("objectID") or hit.get("story_id")
        item_url = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
        created = parse_created(hit.get("created_at"))
        body = clean_text(hit.get("story_text") or hit.get("comment_text"))
        raw_score = float(hit.get("points") or 0) + float(hit.get("num_comments") or 0) * 0.7
        items.append(
            SourceItem(
                source="hacker-news-ask-hn",
                title=title,
                body=body,
                url=item_url,
                created_at=created.isoformat(),
                raw_score=raw_score,
                tags=["ask-hn"],
            )
        )
    return items


def fetch_hacker_news_query(query: str, days: int, limit: int) -> list[SourceItem]:
    since = int((utc_now() - dt.timedelta(days=days)).timestamp())
    params = {
        "query": query,
        "hitsPerPage": str(min(max(limit, 5), 30)),
        "numericFilters": f"created_at_i>{since}",
    }
    url = "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(params)
    data = http_json(url)
    items: list[SourceItem] = []
    for hit in data.get("hits", []):
        title = clean_text(hit.get("title") or hit.get("story_title"))
        if not title:
            continue
        object_id = hit.get("objectID") or hit.get("story_id")
        item_url = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
        created = parse_created(hit.get("created_at"))
        body = clean_text(hit.get("story_text") or hit.get("comment_text"))
        raw_score = float(hit.get("points") or 0) + float(hit.get("num_comments") or 0) * 0.7
        items.append(
            SourceItem(
                source="hacker-news-search",
                title=title,
                body=body,
                url=item_url,
                created_at=created.isoformat(),
                raw_score=raw_score,
                tags=["hn-search", safe_filename(query)],
            )
        )
    return items


def fetch_juejin_query(query: str, days: int, limit: int) -> list[SourceItem]:
    payload = {
        "id_type": 2,
        "key_word": query,
        "search_type": 0,
        "cursor": "0",
        "limit": str(min(max(limit, 3), 20)),
    }
    req = urllib.request.Request(
        "https://api.juejin.cn/search_api/v1/search",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=6) as response:
        data = json.loads(response.read().decode("utf-8", errors="replace"))
    since = utc_now() - dt.timedelta(days=days)
    items: list[SourceItem] = []
    for entry in data.get("data") or []:
        model = entry.get("result_model", {}) if isinstance(entry, dict) else {}
        info = model.get("article_info", {}) if isinstance(model, dict) else {}
        title = clean_text(info.get("title"))
        if not title:
            continue
        created = parse_created(int(info.get("ctime") or 0)) if str(info.get("ctime") or "").isdigit() else utc_now()
        if created < since and days <= 60:
            continue
        article_id = info.get("article_id") or model.get("article_id")
        url = f"https://juejin.cn/post/{article_id}" if article_id else "https://juejin.cn/search"
        body = clean_text(info.get("brief_content"))
        raw_score = float(info.get("view_count") or 0) / 200 + float(info.get("digg_count") or 0) + float(info.get("comment_count") or 0) * 0.5
        items.append(
            SourceItem(
                source="juejin-search",
                title=title,
                body=body,
                url=url,
                created_at=created.isoformat(),
                raw_score=raw_score,
                tags=["juejin", safe_filename(query)],
            )
        )
    return items


def fetch_csdn_query(query: str, days: int, limit: int) -> list[SourceItem]:
    params = {
        "q": query,
        "t": "all",
        "p": "1",
        "s": "0",
        "tm": "0",
        "lv": "-1",
        "ft": "0",
        "l": "",
        "u": "",
    }
    url = "https://so.csdn.net/api/v3/search?" + urllib.parse.urlencode(params)
    data = http_json(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    since = utc_now() - dt.timedelta(days=days)
    items: list[SourceItem] = []
    for entry in data.get("result_vos", [])[: min(max(limit, 3), 30)]:
        title = clean_text(entry.get("title") or entry.get("name") or entry.get("description"))
        if not title:
            continue
        created = parse_created(entry.get("created_at"))
        if created < since and days <= 60:
            continue
        article_id = entry.get("articleid") or entry.get("id")
        url = entry.get("url") or entry.get("search_url") or (f"https://blog.csdn.net/article/details/{article_id}" if article_id else "https://so.csdn.net")
        body = clean_text(entry.get("description") or entry.get("body"))
        raw_score = float(str(entry.get("digg") or "0").strip() or 0)
        tags = [tag.strip() for tag in str(entry.get("language") or "").split(",") if tag.strip()][:6]
        items.append(
            SourceItem(
                source="csdn-search",
                title=title[:180],
                body=body,
                url=url,
                created_at=created.isoformat(),
                raw_score=raw_score,
                tags=["csdn", safe_filename(query), *tags],
            )
        )
    return items


def fetch_v2ex_topics(days: int, limit: int) -> list[SourceItem]:
    since = utc_now() - dt.timedelta(days=days)
    endpoints = [
        ("v2ex-latest", "https://www.v2ex.com/api/topics/latest.json"),
        ("v2ex-hot", "https://www.v2ex.com/api/topics/hot.json"),
    ]
    items: list[SourceItem] = []
    seen: set[str] = set()
    for source, url in endpoints:
        data = http_json(url, timeout=8, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        for topic in data[: min(max(limit, 10), 60)]:
            title = clean_text(topic.get("title"))
            if not title:
                continue
            created = parse_created(topic.get("created"))
            if created < since and days <= 60:
                continue
            item_url = topic.get("url") or f"https://www.v2ex.com/t/{topic.get('id')}"
            if item_url in seen:
                continue
            seen.add(item_url)
            node = topic.get("node") or {}
            body = clean_text(topic.get("content") or topic.get("content_rendered"))
            items.append(
                SourceItem(
                    source=source,
                    title=title[:180],
                    body=body,
                    url=item_url,
                    created_at=created.isoformat(),
                    raw_score=float(topic.get("replies") or 0) + 1.0,
                    tags=["v2ex", clean_text(node.get("name") or node.get("title"))],
                )
            )
            if len(items) >= limit:
                return items
    return items


def fetch_gitee_issues_query(query: str, days: int, limit: int) -> list[SourceItem]:
    params = {
        "q": query,
        "page": "1",
        "per_page": str(min(max(limit, 3), 20)),
    }
    url = "https://gitee.com/api/v5/search/issues?" + urllib.parse.urlencode(params)
    data = http_json(url, timeout=8, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    since = utc_now() - dt.timedelta(days=days)
    items: list[SourceItem] = []
    for issue in data if isinstance(data, list) else []:
        title = clean_text(issue.get("title"))
        if not title:
            continue
        created = parse_created(issue.get("created_at") or issue.get("updated_at"))
        if created < since and days <= 60:
            continue
        repo = issue.get("repository") or {}
        repo_name = clean_text(repo.get("full_name") or repo.get("human_name"))
        labels = issue.get("labels") or []
        label_names = [clean_text(label.get("name")) for label in labels if isinstance(label, dict)]
        items.append(
            SourceItem(
                source="gitee-issues",
                title=title[:180],
                body=clean_text(issue.get("body"))[:1200],
                url=issue.get("html_url") or issue.get("url") or "https://gitee.com",
                created_at=created.isoformat(),
                raw_score=float(issue.get("comments") or 0) + 2.0,
                tags=["gitee", safe_filename(query), repo_name, *label_names[:4]],
            )
        )
    return items


def fetch_oschina_query(query: str, days: int, limit: int) -> list[SourceItem]:
    params = {"q": query, "scope": "blog"}
    url = "https://www.oschina.net/search?" + urllib.parse.urlencode(params)
    text = http_text(url)
    return extract_html_links("oschina-search", text, "https://www.oschina.net", min(max(limit, 3), 20))


def fetch_segmentfault_query(query: str, days: int, limit: int) -> list[SourceItem]:
    params = {"q": query}
    url = "https://segmentfault.com/search?" + urllib.parse.urlencode(params)
    text = http_text(url)
    return extract_html_links("segmentfault-search", text, "https://segmentfault.com", min(max(limit, 3), 20))


def fetch_clawhub_popular_skills(min_downloads: int, limit: int) -> list[SourceItem]:
    if limit <= 0:
        return []
    items: list[SourceItem] = []
    cursor = ""
    stop_after_page = False
    max_pages = 5
    for _page in range(max_pages):
        page_limit = min(max(limit - len(items), 5), 100)
        params = {
            "sort": "downloads",
            "limit": str(page_limit),
        }
        if cursor:
            params["cursor"] = cursor
        data = http_json(
            CLAW_HUB_SKILLS_API + "?" + urllib.parse.urlencode(params),
            timeout=12,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        page_items = data.get("items", []) if isinstance(data, dict) else []
        if not page_items:
            break
        for skill in page_items:
            if not isinstance(skill, dict):
                continue
            stats = skill.get("stats") or {}
            downloads = int_stat(stats.get("downloads"))
            if downloads < min_downloads:
                stop_after_page = True
                break
            slug = clean_text(skill.get("slug"))
            display_name = clean_text(skill.get("displayName") or slug)
            if not slug or not display_name:
                continue
            summary = clean_text(skill.get("summary") or skill.get("description"))[:900]
            latest = skill.get("latestVersion") or {}
            changelog = clean_text(latest.get("changelog"))[:700]
            installs = int_stat(stats.get("installsAllTime"))
            current_installs = int_stat(stats.get("installsCurrent"))
            stars = int_stat(stats.get("stars"))
            comments = int_stat(stats.get("comments"))
            term_text = f"{display_name} {summary} {changelog}"
            terms = clawhub_skill_terms(term_text, [safe_filename(display_name)], limit=8)
            title = f"Popular Clawhub skill demand: {display_name} has {downloads:,} downloads"
            body_parts = [
                f"Users need reliable {display_name}-style agent support because this Clawhub skill has strong adoption.",
                f"Existing skill summary: {summary}" if summary else "",
                (
                    "Idea angles: fix bugs or brittle setup, improve safety, privacy, reliability, and docs, "
                    "or create an adjacent skill for a related workflow after understanding what the popular skill does."
                ),
                (
                    f"Clawhub stats: {downloads:,} downloads, {installs:,} all-time installs, "
                    f"{current_installs:,} current installs, {stars:,} stars, {comments:,} comments."
                ),
                f"Latest version notes: {changelog}" if changelog else "",
            ]
            raw_score = downloads / 5000 + installs / 200 + current_installs / 250 + stars / 100 + comments
            items.append(
                SourceItem(
                    source="clawhub-popular-skill",
                    title=title[:180],
                    body=" ".join(part for part in body_parts if part),
                    url=CLAW_HUB_SKILL_PAGE.format(slug=urllib.parse.quote(slug, safe="")),
                    created_at=parse_clawhub_timestamp(skill.get("updatedAt") or skill.get("createdAt")).isoformat(),
                    raw_score=raw_score,
                    tags=[*terms, "clawhub", "popular-skill", "downloads-100k-plus", slug],
                )
            )
            if len(items) >= limit:
                stop_after_page = True
                break
        cursor = str(data.get("nextCursor") or "") if isinstance(data, dict) else ""
        if stop_after_page or not cursor:
            break
        time.sleep(0.05)
    return items


def fetch_china_sources(days: int, per_source_limit: int, theme_profile: str = "default") -> list[SourceItem]:
    queries = china_queries_for_profile(theme_profile)[:4]
    items: list[SourceItem] = []
    try:
        items.extend(fetch_v2ex_topics(days, per_source_limit))
    except Exception:
        pass
    china_history_days = max(days, 365)
    per_query_limit = max(2, min(5, per_source_limit // max(len(queries), 1)))
    for query in queries:
        for fetcher in [fetch_juejin_query, fetch_csdn_query]:
            try:
                items.extend(fetcher(query, china_history_days, per_query_limit))
            except Exception:
                continue
            time.sleep(0.05)
    for query in gitee_queries_for_profile(theme_profile)[:2]:
        try:
            items.extend(fetch_gitee_issues_query(query, china_history_days, max(3, per_query_limit)))
        except Exception:
            continue
        time.sleep(0.05)
    return items

def fetch_github_issues(days: int, limit: int) -> list[SourceItem]:
    since = (utc_now() - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    queries = [
        f'is:issue is:open label:enhancement created:>={since}',
        f'is:issue is:open "feature request" created:>={since}',
        f'is:issue is:open "would be nice" created:>={since}',
    ]
    items: list[SourceItem] = []
    for query in queries:
        params = {
            "q": query,
            "sort": "created",
            "order": "desc",
            "per_page": str(min(max(limit // len(queries), 10), 50)),
        }
        url = "https://api.github.com/search/issues?" + urllib.parse.urlencode(params)
        data = http_json(url, headers={"Accept": "application/vnd.github+json"})
        for entry in data.get("items", []):
            title = clean_text(entry.get("title"))
            body = clean_text(entry.get("body"))[:800]
            if not title:
                continue
            created = parse_created(entry.get("created_at"))
            labels = [label.get("name", "") for label in entry.get("labels", []) if isinstance(label, dict)]
            raw_score = float(entry.get("comments") or 0) * 0.6
            items.append(
                SourceItem(
                    source="github-issues",
                    title=title,
                    body=body,
                    url=str(entry.get("html_url") or ""),
                    created_at=created.isoformat(),
                    raw_score=raw_score,
                    tags=[label for label in labels if label][:6],
                )
            )
        time.sleep(0.5)
    return items


def fetch_github_issues_query(query: str, days: int, limit: int) -> list[SourceItem]:
    since = (utc_now() - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    search_query = f'is:issue is:open created:>={since} "{query}"'
    params = {
        "q": search_query,
        "sort": "updated",
        "order": "desc",
        "per_page": str(min(max(limit, 5), 30)),
    }
    url = "https://api.github.com/search/issues?" + urllib.parse.urlencode(params)
    data = http_json(url, headers={"Accept": "application/vnd.github+json"})
    items: list[SourceItem] = []
    for entry in data.get("items", []):
        title = clean_text(entry.get("title"))
        body = clean_text(entry.get("body"))[:800]
        if not title:
            continue
        created = parse_created(entry.get("created_at"))
        labels = [label.get("name", "") for label in entry.get("labels", []) if isinstance(label, dict)]
        raw_score = float(entry.get("comments") or 0) * 0.6
        items.append(
            SourceItem(
                source="github-issues",
                title=title,
                body=body,
                url=str(entry.get("html_url") or ""),
                created_at=created.isoformat(),
                raw_score=raw_score,
                tags=[label for label in labels if label][:6],
            )
        )
    return items


def discover_online(
    days: int,
    per_source_limit: int,
    theme_profile: str = "default",
    include_clawhub_popular: bool = True,
    clawhub_min_downloads: int = CLAW_HUB_MIN_DOWNLOADS,
    clawhub_popular_limit: int = CLAW_HUB_POPULAR_LIMIT,
) -> tuple[list[SourceItem], list[str]]:
    fetchers = [
        ("hacker-news-ask-hn", lambda: fetch_hacker_news(days, per_source_limit)),
        ("github-issues", lambda: fetch_github_issues(days, per_source_limit)),
        ("china-friendly-sources", lambda: fetch_china_sources(days, per_source_limit, theme_profile)),
    ]
    if include_clawhub_popular and theme_profile == "default":
        fetchers.append(
            (
                "clawhub-popular-skills",
                lambda: fetch_clawhub_popular_skills(clawhub_min_downloads, clawhub_popular_limit),
            )
        )
    items: list[SourceItem] = []
    errors: list[str] = []
    for name, fetcher in fetchers:
        try:
            found = fetcher()
            items.extend(found)
            errors.append(f"{name}: fetched {len(found)} items")
        except Exception as exc:  # noqa: BLE001 - keep discovery resilient across public endpoints.
            errors.append(f"{name}: failed with {type(exc).__name__}: {exc}")
    return items, errors


def keyword_hits(text: str) -> int:
    lower = text.lower()
    return sum(1 for pattern in NEED_PATTERNS if re.search(pattern, lower))


def excluded(text: str) -> bool:
    lower = text.lower()
    return any(re.search(pattern, lower) for pattern in EXCLUDE_PATTERNS)


def infer_category(text: str, tags: list[str]) -> str:
    haystack = " ".join([text.lower(), " ".join(tags).lower()])
    scores: dict[str, int] = {}
    for category, words in CATEGORY_KEYWORDS.items():
        scores[category] = sum(1 for word in words if re.search(rf"\b{re.escape(word)}\b", haystack))
    best_category, best_score = max(scores.items(), key=lambda item: item[1])
    return best_category if best_score > 0 else "general-help"


def infer_audience(item: SourceItem, category: str) -> str:
    source = item.source
    if "github" in source:
        return "maintainers and users asking for software improvements"
    if "stackoverflow" in source or category == "software-and-data":
        return "developers, analysts, and technical users"
    if "workplace" in source or category == "work-productivity":
        return "professionals and teams trying to improve work outcomes"
    if category == "personal-happiness":
        return "people looking for practical support in daily life"
    if category == "creative-and-content":
        return "creators and communicators"
    if category == "business-and-operations":
        return "operators, founders, and small business owners"
    return "people asking for help online"


def extract_keywords(text: str, tags: list[str], limit: int = 8) -> list[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", text.lower())
    ranked: list[str] = []
    for token in list(tags) + tokens:
        normalized = re.sub(r"[^a-z0-9-]", "", token.lower())
        if not normalized or normalized in STOPWORDS:
            continue
        if normalized not in ranked:
            ranked.append(normalized)
        if len(ranked) >= limit:
            break
    return ranked


def requirement_score(item: SourceItem) -> float:
    combined = f"{item.title} {item.body[:500]}"
    hits = keyword_hits(combined)
    source_boost = (
        3.5
        if "clawhub" in item.source
        else 3.0
        if "ask-hn" in item.source
        else 2.8
        if any(name in item.source for name in ["gitee", "v2ex", "juejin", "csdn", "oschina", "segmentfault"])
        else 2.0
    )
    question_boost = 1.2 if "?" in item.title or item.title.lower().startswith(("how ", "what ", "why ", "can ")) else 0
    body_boost = min(len(item.body) / 400, 1.5)
    return hits * 4 + source_boost + question_boost + body_boost + min(item.raw_score, 40) / 10


def normalize_requirement_key(text: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    tokens = [token for token in tokens if token not in STOPWORDS and token not in PREFIX_WORDS]
    return " ".join(tokens[:12])


def to_requirement(item: SourceItem) -> Requirement | None:
    combined = f"{item.title} {item.body[:500]}"
    title_words = re.findall(r"\w+", item.title)
    if len(title_words) < 4 or len(item.title) > 220 or excluded(combined):
        return None
    if len(re.sub(r"[^A-Za-z0-9]", "", item.title)) < 12:
        return None
    if keyword_hits(combined) == 0 and "?" not in item.title:
        return None
    category = infer_category(combined, item.tags)
    keywords = extract_keywords(combined, item.tags)
    key = normalize_requirement_key(item.title) or item.title.lower()
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    evidence = [
        {
            "source": item.source,
            "title": item.title,
            "url": item.url,
            "created_at": item.created_at,
        }
    ]
    summary = item.title.rstrip(" .")
    return Requirement(
        requirement_id=digest,
        summary=f"Single-source signal: {summary}",
        audience=infer_audience(item, category),
        category=category,
        evidence=evidence,
        keywords=keywords,
        score=min(50.0, requirement_score(item)),
        demand_score=20,
        feasibility_score=25,
        evidence_count=1,
        source_count=1,
        scoring_rationale=[
            "This is a single-source signal and is not eligible for implementation until corroborated.",
            "The idea may still seed broader demand searches.",
        ],
    )


def build_dynamic_themes(items: list[SourceItem], limit: int = 6) -> list[dict[str, Any]]:
    seeds: list[Requirement] = []
    for item in sorted(items, key=requirement_score, reverse=True):
        requirement = to_requirement(item)
        if requirement is None or len(requirement.keywords) < 3:
            continue
        seeds.append(requirement)
        if len(seeds) >= limit:
            break
    themes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for seed in seeds:
        terms = [keyword for keyword in seed.keywords if keyword not in PREFIX_WORDS][:6]
        key = " ".join(terms[:4])
        if not key or key in seen:
            continue
        seen.add(key)
        phrase = action_phrase(seed.summary.replace("Single-source signal:", "").strip())
        themes.append(
            {
                "theme_id": f"dynamic-{seed.requirement_id}",
                "summary": f"People repeatedly need a practical, repeatable way to handle {phrase}.",
                "audience": (
                    f"{seed.audience}, especially users who need a reusable workflow instead of a one-off answer"
                ),
                "category": seed.category,
                "keywords": terms,
                "queries": [phrase, key],
            }
        )
    return themes


def clawhub_skill_label(item: SourceItem) -> str:
    match = re.match(r"Popular Clawhub skill demand: (.+?) has [\d,]+ downloads", item.title)
    if match:
        return match.group(1).strip()
    title = item.title.replace("Popular Clawhub skill demand:", "").strip()
    return re.sub(r"\s+has\s+[\d,]+\s+downloads.*$", "", title, flags=re.I).strip() or title


def build_clawhub_popular_skill_themes(items: list[SourceItem]) -> list[dict[str, Any]]:
    themes: list[dict[str, Any]] = []
    seen: set[str] = set()
    popular_items = [item for item in items if source_family(item.source) == "clawhub"]
    for item in sorted(popular_items, key=lambda value: value.raw_score, reverse=True):
        label = clawhub_skill_label(item)
        skill_key = safe_filename(label, "clawhub-skill")
        if skill_key in seen:
            continue
        seen.add(skill_key)
        terms = clawhub_skill_terms(f"{label} {item.body}", item.tags, limit=8)
        if not terms:
            terms = [skill_key.replace("-", " ")]
        query_terms = " ".join(terms[:4]) or label
        themes.append(
            {
                "theme_id": f"clawhub-popular-{skill_key}",
                "origin": "clawhub-popular-skill",
                "summary": (
                    f"Agent users show strong demand for {label}-style workflows on Clawhub. "
                    "They need practical help fixing bugs, hardening setup and safety, improving reliability, "
                    "or creating adjacent skills inspired by the same job-to-be-done."
                ),
                "audience": (
                    "AI-agent users, skill authors, maintainers, and teams who want proven popular skill patterns "
                    "adapted into more reliable or adjacent workflows"
                ),
                "category": infer_category(f"{label} {item.body}", item.tags),
                "keywords": list(dict.fromkeys([*terms, "bug fix", "setup", "reliability", "adjacent workflow"]))[:10],
                "queries": [
                    query_terms,
                    f"{label} skill setup bug feature request",
                ],
                "targeted_query_limit": 1,
            }
        )
    return themes


def fetch_targeted_theme_evidence(theme: dict[str, Any], days: int, per_source_limit: int) -> tuple[list[SourceItem], list[str]]:
    items: list[SourceItem] = []
    notes: list[str] = []
    query_limit = max(1, int(theme.get("targeted_query_limit", 1)))
    for query in theme["queries"][:query_limit]:
        query_items: list[SourceItem] = []
        fetchers = [
            ("hacker-news-search", lambda q=query: fetch_hacker_news_query(q, days, max(5, per_source_limit // 8))),
            ("github-issues-search", lambda q=query: fetch_github_issues_query(q, days, max(5, per_source_limit // 8))),
            ("juejin-search", lambda q=query: fetch_juejin_query(q, days, max(5, per_source_limit // 8))),
            ("csdn-search", lambda q=query: fetch_csdn_query(q, days, max(5, per_source_limit // 8))),
            ("oschina-search", lambda q=query: fetch_oschina_query(q, days, max(5, per_source_limit // 8))),
            ("segmentfault-search", lambda q=query: fetch_segmentfault_query(q, days, max(5, per_source_limit // 8))),
        ]
        for name, fetcher in fetchers:
            try:
                found = fetcher()
                query_items.extend(found)
                notes.append(f"{theme['theme_id']} / {name} / {query}: fetched {len(found)} items")
            except Exception as exc:  # noqa: BLE001 - targeted enrichment should continue across sources.
                notes.append(f"{theme['theme_id']} / {name} / {query}: failed with {type(exc).__name__}: {exc}")
            time.sleep(0.05)
        items.extend(query_items)
    return items, notes


def local_feasibility_score(theme: dict[str, Any]) -> tuple[int, list[str]]:
    text = " ".join([theme["summary"], " ".join(theme["keywords"]), " ".join(theme["queries"])]).lower()
    heavy_patterns = [
        "train a large model",
        "fine tune large",
        "cluster",
        "kubernetes production",
        "enterprise-only",
        "requires paid api",
        "datacenter",
    ]
    if any(pattern in text for pattern in heavy_patterns):
        return 12, ["Feasibility is low because the theme may require cloud-scale or enterprise-only infrastructure."]
    gpu_patterns = ["local llm", "llama", "consumer gpu", "cpu inference", "ai locally"]
    if any(pattern in text for pattern in gpu_patterns):
        return 28, ["Implementation can be designed for local CPU or family GPU workflows with small models and no cloud-only dependency."]
    return 30, ["Implementation is a documentation, workflow, code, or analysis skill that can run on ordinary CPU hardware."]


def requirement_scoring_agent(
    theme: dict[str, Any],
    evidence_items: list[SourceItem],
    min_evidence: int,
) -> Requirement:
    evidence_items = unique_source_items(evidence_items, limit=12)
    evidence_count = len(evidence_items)
    source_count = len({source_family(item.source) for item in evidence_items})
    raw_strength = sum(min(max(item.raw_score, 0), 30) for item in evidence_items)
    professional_signal = 8 if theme["category"] in {"software-and-data", "work-productivity", "business-and-operations"} else 5
    demand_score = min(70, evidence_count * 8 + source_count * 12 + int(min(raw_strength, 80) / 10) + professional_signal)
    feasibility_score, feasibility_notes = local_feasibility_score(theme)
    total_score = demand_score + feasibility_score
    rationale = [
        f"Evidence count: {evidence_count}; required minimum: {min_evidence}.",
        f"Distinct source families: {source_count}; sources: {', '.join(sorted({source_family(item.source) for item in evidence_items})) or 'none'}.",
        f"Demand score: {demand_score}/70 based on corroboration, source diversity, and professional/community signal.",
        f"Local feasibility score: {feasibility_score}/30.",
        *feasibility_notes,
    ]
    if theme.get("origin") == "clawhub-popular-skill":
        rationale.append(
            "Clawhub-derived idea: popularity is only a seed signal; this idea is scored by the same 100-point requirement scorer and must meet the implementation threshold."
        )
    if evidence_count < min_evidence:
        total_score = min(total_score, 80)
        rationale.append("Score capped because the requirement does not appear at least three times.")
    if source_count < min_evidence:
        total_score = min(total_score, 90)
        rationale.append("Score capped because corroborating evidence does not come from at least three different source families.")
    digest = hashlib.sha1(theme["theme_id"].encode("utf-8")).hexdigest()[:10]
    evidence = [
        {
            "source": item.source,
            "title": item.title,
            "url": item.url,
            "created_at": item.created_at,
        }
        for item in evidence_items
    ]
    summary = (
        f"Validated demand: {theme['summary']} This requirement is supported by {evidence_count} "
        f"separate online signals across {source_count} source families, so it represents broader demand "
        f"rather than a single isolated request."
    )
    return Requirement(
        requirement_id=digest,
        summary=summary,
        audience=theme["audience"],
        category=theme["category"],
        evidence=evidence,
        keywords=list(dict.fromkeys([theme["category"], *theme["keywords"]]))[:10],
        score=float(total_score),
        demand_score=demand_score,
        feasibility_score=feasibility_score,
        evidence_count=evidence_count,
        source_count=source_count,
        scoring_rationale=rationale,
    )


def requirement_meets_acceptance(requirement: Requirement, threshold: int, min_evidence: int) -> bool:
    return requirement.score >= threshold and requirement.evidence_count >= min_evidence


def extract_requirements(
    items: list[SourceItem],
    max_ideas: int,
    days: int,
    per_source_limit: int,
    min_evidence: int,
    theme_profile: str = "default",
) -> tuple[list[Requirement], list[str]]:
    notes: list[str] = []
    configured_themes = demand_themes_for_profile(theme_profile)
    clawhub_themes = build_clawhub_popular_skill_themes(items) if theme_profile == "default" else []
    dynamic_themes = build_dynamic_themes(items, limit=2) if theme_profile == "default" else []
    themes = [*configured_themes, *clawhub_themes, *dynamic_themes]
    requirements: list[Requirement] = []
    for theme in themes:
        matching_items = [item for item in items if item_matches_terms(item, theme["keywords"])]
        current_unique = unique_source_items(matching_items, limit=12)
        current_source_count = len({source_family(item.source) for item in current_unique})
        if len(current_unique) < min_evidence or current_source_count < min_evidence:
            targeted_items, targeted_notes = fetch_targeted_theme_evidence(theme, days, per_source_limit)
            notes.extend(targeted_notes)
            matching_items.extend(targeted_items)
        requirement = requirement_scoring_agent(theme, matching_items, min_evidence)
        requirements.append(requirement)
    requirements = sorted(requirements, key=lambda req: req.score, reverse=True)
    if max_ideas > 0:
        requirements = requirements[: max(max_ideas * 2, max_ideas)]
    return requirements, notes


def similarity_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", ascii_safe(text).lower())
    return {
        token
        for token in tokens
        if len(token) >= 3 and token not in STOPWORDS and token not in PREFIX_WORDS and token not in NAME_NOISE_WORDS
    }


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def requirement_similarity_text(requirement: Requirement) -> str:
    return " ".join(
        [
            action_phrase(requirement.summary),
            requirement.audience,
            " ".join(requirement.keywords),
            requirement.category,
        ]
    )


def requirement_strength(requirement: Requirement) -> tuple[float, int, int, int, int]:
    return (
        requirement.score,
        requirement.evidence_count,
        requirement.source_count,
        requirement.demand_score,
        requirement.feasibility_score,
    )


def requirements_are_similar(left: Requirement, right: Requirement) -> tuple[bool, str]:
    left_base = searchable_skill_base(left)
    right_base = searchable_skill_base(right)
    if left_base == right_base:
        return True, f"same functional skill name `{left_base}`"

    left_tokens = similarity_tokens(requirement_similarity_text(left))
    right_tokens = similarity_tokens(requirement_similarity_text(right))
    similarity = jaccard_similarity(left_tokens, right_tokens)
    if left.category == right.category and similarity >= SIMILARITY_DEDUPE_THRESHOLD:
        return True, f"{similarity:.0%} overlapping requirement/function tokens"

    return False, ""


def dedupe_requirements(requirements: list[Requirement]) -> tuple[list[Requirement], list[str], set[str]]:
    kept: list[Requirement] = []
    notes: list[str] = []
    removed_ids: set[str] = set()
    for candidate in sorted(requirements, key=requirement_strength, reverse=True):
        duplicate_of: Requirement | None = None
        reason = ""
        for existing in kept:
            similar, reason = requirements_are_similar(candidate, existing)
            if similar:
                duplicate_of = existing
                break
        if duplicate_of is None:
            kept.append(candidate)
            continue
        removed_ids.add(candidate.requirement_id)
        notes.append(
            "[dedupe-agent] removed duplicate requirement "
            f"`{candidate.requirement_id}` ({searchable_skill_base(candidate)}) because it is similar to "
            f"`{duplicate_of.requirement_id}` ({searchable_skill_base(duplicate_of)}): {reason}. "
            "Kept the stronger representative by score, evidence count, and source diversity."
        )
    return kept, notes, removed_ids


def dedupe_plans(plans: list[SkillPlan]) -> tuple[list[SkillPlan], list[str], set[str]]:
    kept: list[SkillPlan] = []
    notes: list[str] = []
    removed_ids: set[str] = set()
    for candidate in sorted(plans, key=lambda plan: requirement_strength(plan.requirement), reverse=True):
        duplicate_of: SkillPlan | None = None
        reason = ""
        for existing in kept:
            similar, reason = requirements_are_similar(candidate.requirement, existing.requirement)
            same_base = re.sub(r"-\d+$", "", candidate.skill_name) == re.sub(r"-\d+$", "", existing.skill_name)
            if same_base or similar:
                duplicate_of = existing
                reason = reason or f"same generated skill function `{re.sub(r'-\d+$', '', candidate.skill_name)}`"
                break
        if duplicate_of is None:
            kept.append(candidate)
            continue
        removed_ids.add(candidate.requirement.requirement_id)
        notes.append(
            "[dedupe-agent] removed duplicate skill plan "
            f"`{candidate.skill_name}` because it overlaps `{duplicate_of.skill_name}`: {reason}. "
            "Only one skill per repeated function is implemented and published."
        )
    return kept, notes, removed_ids


def action_phrase(summary: str) -> str:
    text = clean_text(summary).rstrip("?")
    text = re.sub(r"(?i)^validated demand:\s*", "", text)
    text = text.split(" This requirement is supported", 1)[0]
    text = text.split(" This requirement has", 1)[0]
    text = text.split(" It represents", 1)[0]
    text = re.sub(r"(?i)^ask hn:\s*", "", text)
    text = re.sub(r"(?i)^\s*(\[(feature request|feature|enhancement|feat|fr)\]|(feature request|feature|enhancement|feat|fr))\s*:?\s*-?\s*", "", text)
    text = re.sub(r"(?i)^\s*(feature request|feature|enhancement|feat|fr)\s*:?\s*-?\s*", "", text)
    text = re.sub(r"(?i)^(how do i|how can i|what is the best way to|what's the best way to)\s+", "", text)
    text = re.sub(r"(?i)^(i need|we need|looking for|recommend|suggest)\s+", "", text)
    text = re.sub(r"\s+", " ", text)
    text = text[:120].strip(" .")
    return text or summary[:120]


SEARCHABLE_NAME_RULES: list[tuple[str, list[str]]] = [
    ("office-openxml-automation-helper", ["moving data and content across word, excel, and powerpoint", "office automation", "open xml", "python-docx openpyxl python-pptx", "office document"]),
    ("word-mail-merge-template-helper", ["word mail merge", "content controls", "merge fields", "docx template assembly"]),
    ("excel-chart-report-export-helper", ["excel report builders", "excel chart", "dashboard", "conditional formatting", "print area", "export pdf"]),
    ("powerpoint-template-master-fixer", ["powerpoint template", "slide masters", "slide master", "placeholders", "theme colors", "chart links"]),
    ("word-docx-formatting-repair-helper", ["word docx formatting", "microsoft word", "track changes", "section break", "ooxml compatibility"]),
    ("excel-xlsx-formula-cleanup-helper", ["microsoft excel", "power query", "pivot table", "xlsx formulas", "openpyxl"]),
    ("powerpoint-pptx-layout-export-helper", ["microsoft powerpoint", "pptx", "python-pptx", "speaker notes", "slide layout"]),
    ("unit-test-coverage-helper", ["unit test", "test coverage", "regression"]),
    ("openapi-docs-generator", ["openapi", "swagger", "api documentation", "rest api"]),
    ("mobile-responsive-layout-fixer", ["mobile responsive", "responsive design", "navbar", "layout", "frontend"]),
    ("error-message-improver", ["error message", "clearer error", "debugging", "troubleshooting"]),
    ("local-llm-setup-advisor", ["local llm", "consumer gpu", "family gpu", "cpu inference", "ai and llm workflows locally", "llama.cpp", "privacy"]),
    ("document-formatting-automation-helper", ["microsoft word", "document formatting", "find replace", "styles"]),
    ("home-network-troubleshooter", ["bufferbloat", "router", "modem", "latency", "network troubleshooting"]),
    ("product-validation-planner", ["product idea", "help for a product", "validation", "prototype", "saas", "startup"]),
    ("nextcloud-integration-helper", ["nextcloud"]),
    ("llm-api-provider-integration-helper", ["response api", "minimax", "api provider"]),
    ("bun-migration-advisor", ["migrating away bun", "bun"]),
    ("workflow-planner-simplifier", ["adaptive planner", "workflow phases", "planner"]),
    ("remote-llama-server-setup", ["remote llama", "llama cpp", "llama.cpp"]),
    ("linked-list-practice-helper", ["linked list"]),
    ("blockly-block-builder", ["blockly"]),
    ("audio-waveform-track-toggle", ["waveform", "track names"]),
    ("phone-verification-helper", ["telephone", "phone verification"]),
    ("document-tab-settings-helper", ["tab settings", "paragraphs"]),
    ("word-alternative-advisor", ["replace microsoft word"]),
    ("contract-clause-review-helper", ["clause", "developments relating"]),
    ("qemu-graphical-client-fixer", ["qemu", "graphical client", "serial"]),
    ("stereoscopic-3d-support-helper", ["stereoscopic", "3d"]),
    ("javascript-blog-access-helper", ["blog", "heavy javascript"]),
    ("status-message-rule-helper", ["profile status", "status message", "rules event"]),
    ("toml-model-override-helper", ["toml", "model overrides"]),
    ("housing-dispute-help-planner", ["furnished apartments", "landing dispute"]),
    ("usa-business-migration-planner", ["emigrating", "usa", "starting business"]),
    ("shell-editing-workflow-helper", ["edit write shell", "write shell"]),
]


NAME_NOISE_WORDS = STOPWORDS | {
    "ask",
    "hn",
    "ask-hn",
    "feature",
    "request",
    "enhancement",
    "feat",
    "fr",
    "add",
    "support",
    "help",
    "people",
    "repeatedly",
    "practical",
    "repeatable",
    "handle",
    "teams",
    "users",
    "need",
    "needs",
    "validated",
    "demand",
    "single",
    "source",
    "signal",
    "general",
    "gssocapproved",
    "typefeature",
    "mentorpankajsingh34",
    "based",
    "selected",
    "existing",
    "issues",
    "found",
    "happy",
    "answer",
    "questions",
    "com",
    "high",
    "quality",
    "ready",
}


def readable_slug_from_text(text: str, default: str = "workflow-helper") -> str:
    words = re.findall(r"[a-z0-9]+", ascii_safe(text).lower())
    chosen: list[str] = []
    for word in words:
        if word in NAME_NOISE_WORDS:
            continue
        if word not in chosen:
            chosen.append(word)
        if len(chosen) >= 4:
            break
    if not chosen:
        return default
    return "-".join(chosen)


def searchable_skill_base(requirement: Requirement) -> str:
    text = " ".join(
        [
            requirement.summary,
            requirement.audience,
            " ".join(requirement.keywords),
        ]
    ).lower()
    for slug, phrases in SEARCHABLE_NAME_RULES:
        if any(phrase in text for phrase in phrases):
            return slug

    suffix_by_category = {
        "software-and-data": "developer-helper",
        "work-productivity": "workflow-helper",
        "learning-and-research": "learning-helper",
        "creative-and-content": "content-helper",
        "personal-happiness": "life-helper",
        "business-and-operations": "business-planner",
        "general-help": "help-workflow",
    }
    topic = readable_slug_from_text(" ".join(requirement.keywords) + " " + action_phrase(requirement.summary))
    suffix = suffix_by_category.get(requirement.category, "workflow-helper")
    if topic.endswith(suffix) or topic in suffix:
        return topic[:58].strip("-") or suffix
    return safe_filename(f"{topic} {suffix}", default=suffix)[:58].strip("-")


def build_skill_name(requirement: Requirement, used: set[str]) -> str:
    base = searchable_skill_base(requirement)[:58].strip("-") or "workflow-helper"
    candidate = base
    counter = 2
    while candidate in used:
        suffix = f"-{counter}"
        candidate = (base[: 63 - len(suffix)].strip("-") + suffix).strip("-")
        counter += 1
    used.add(candidate)
    return candidate


def title_case_from_slug(slug: str) -> str:
    small = {"and", "or", "for", "to", "with", "in", "on"}
    acronyms = {
        "ai": "AI",
        "api": "API",
        "cpu": "CPU",
        "gpu": "GPU",
        "llm": "LLM",
        "qemu": "QEMU",
        "ui": "UI",
        "usa": "USA",
        "toml": "TOML",
        "3d": "3D",
    }
    words = []
    for index, word in enumerate(slug.split("-")):
        words.append(acronyms.get(word, word if index > 0 and word in small else word.capitalize()))
    return " ".join(words)


def plan_for_requirement(requirement: Requirement, used_names: set[str]) -> SkillPlan:
    skill_name = build_skill_name(requirement, used_names)
    display_name = title_case_from_slug(skill_name)
    phrase = action_phrase(requirement.summary)
    keywords = requirement.keywords[:]
    if requirement.category not in keywords:
        keywords.insert(0, requirement.category)
    trigger_sentences = [
        f"Help me {phrase}.",
        f"I need a practical workflow for {phrase}.",
        f"Use ${skill_name} to handle {phrase}.",
    ]
    how_it_meets_need = (
        f"Transforms the live request into a repeatable workflow that clarifies the user's context, "
        f"produces a concrete deliverable, checks the result against the original need, and keeps execution feasible on ordinary CPU or family GPU hardware."
    )
    category_step = {
        "work-productivity": "Create a concise work plan, template, automation outline, or decision aid that reduces manual coordination.",
        "software-and-data": "Inspect technical constraints, propose implementation steps, and include test or verification commands when code or data is involved.",
        "learning-and-research": "Break the topic into teachable chunks, gather trustworthy references, and produce a study or research artifact.",
        "creative-and-content": "Define the creative brief, generate options, and refine the strongest output against audience and tone.",
        "personal-happiness": "Favor small, low-friction actions that improve daily life while respecting the user's constraints and preferences.",
        "business-and-operations": "Turn the operational problem into a repeatable process, checklist, template, or lightweight analysis.",
    }.get(requirement.category, "Convert the request into a practical plan and useful output.")
    implementation_steps = [
        "Restate the user's outcome, constraints, available inputs, and success criteria.",
        category_step,
        "Ask only for missing information that materially changes the output; otherwise make reasonable assumptions and continue.",
        "Keep the implementation local-hardware friendly: prefer scripts, templates, checklists, and small-model or CPU-safe workflows over cloud-only or large-training approaches.",
        "Produce the requested artifact, workflow, checklist, analysis, code change, or decision support.",
        "Validate the output against the success criteria and list any remaining risks or follow-up work.",
    ]
    validation_checks = [
        "The output directly addresses the discovered requirement.",
        "The user can act on the result without reading the original source post.",
        "Assumptions, limits, and required inputs are visible.",
        "The final response includes a short usage or next-step note when helpful.",
    ]
    outputs = [
        "A tailored answer or artifact for the user's immediate situation.",
        "A reusable checklist or workflow when the task is repeatable.",
        "A verification note showing how the result was checked.",
    ]
    return SkillPlan(
        skill_name=skill_name,
        display_name=display_name,
        requirement=requirement,
        how_it_meets_need=how_it_meets_need,
        implementation_steps=implementation_steps,
        validation_checks=validation_checks,
        outputs=outputs,
        trigger_sentences=trigger_sentences,
        keywords=keywords[:10],
    )


def wrapped_lines(prefix: str, value: str, width: int = 88) -> str:
    lines = textwrap.wrap(value, width=width, subsequent_indent="  ")
    if not lines:
        return prefix
    return prefix + lines[0] + ("\n" + "\n".join("  " + line for line in lines[1:]) if len(lines) > 1 else "")


def render_skill_md(plan: SkillPlan) -> str:
    req = plan.requirement
    description = (
        f"Help users with {req.summary}. Use when a user asks for {', '.join(plan.keywords[:5])}, "
        f"or needs a practical workflow, artifact, checklist, analysis, or implementation support for this requirement."
    )
    steps = "\n".join(f"{index}. {step}" for index, step in enumerate(plan.implementation_steps, start=1))
    checks = "\n".join(f"- {check}" for check in plan.validation_checks)
    triggers = "\n".join(f"- `{trigger}`" for trigger in plan.trigger_sentences)
    keywords = ", ".join(f"`{keyword}`" for keyword in plan.keywords)
    outputs = "\n".join(f"- {output}" for output in plan.outputs)
    return f"""---
name: {plan.skill_name}
description: >-
  {description}
---

# {plan.display_name}

## Requirement

Use this skill to help {req.audience} with:

> {req.summary}

Demand score: {int(req.score)}/100 (`{req.demand_score}/70` demand, `{req.feasibility_score}/30` local feasibility).
Evidence: {req.evidence_count} signals across {req.source_count} source families.

Read `references/requirement-plan.md` when source evidence, planning details, or review criteria are needed.

## Workflow

{steps}

## Expected Outputs

{outputs}

## Validation

{checks}

## Triggers

Keywords: {keywords}

Example trigger sentences:

{triggers}
"""


def zh_category_label(category: str) -> str:
    labels = {
        "work-productivity": "工作与效率",
        "software-and-data": "软件与数据",
        "learning-and-research": "学习与研究",
        "creative-and-content": "创意与内容",
        "personal-happiness": "个人幸福感",
        "business-and-operations": "业务与运营",
        "general-help": "通用帮助",
    }
    return labels.get(category, category)


def zh_category_step(category: str) -> str:
    steps = {
        "work-productivity": "创建简洁的工作计划、模板、自动化思路或决策辅助，减少手动协调。",
        "software-and-data": "检查技术限制，提出实现步骤，并在涉及代码或数据时包含测试或验证方法。",
        "learning-and-research": "把主题拆成可学习的模块，收集可信参考，并产出学习或研究材料。",
        "creative-and-content": "明确创意简报，生成多个方案，并根据受众和语气打磨最强输出。",
        "personal-happiness": "优先选择低摩擦的小行动，在尊重用户限制和偏好的前提下改善日常体验。",
        "business-and-operations": "把运营问题转化为可复用流程、检查清单、模板或轻量分析。",
    }
    return steps.get(category, "把请求转化为实用计划和可执行输出。")


def render_skill_md_zh(plan: SkillPlan) -> str:
    req = plan.requirement
    description = (
        f"帮助用户处理“{req.summary}”。当用户提出 {', '.join(plan.keywords[:5])}，"
        f"或需要围绕该需求获得实用流程、产物、检查清单、分析或实现支持时使用。"
    )
    steps = [
        "重新说明用户想要的结果、限制、已有输入和成功标准。",
        zh_category_step(req.category),
        "只有当缺失信息会明显改变输出时才提问；否则先做合理假设并继续推进。",
        "保持本地硬件友好：优先使用脚本、模板、检查清单、小模型或 CPU 可承受的流程，避免依赖云端专用资源或大规模训练。",
        "产出用户需要的文档、流程、清单、分析、代码修改或决策支持。",
        "对照成功标准检查结果，并列出剩余风险或后续事项。",
    ]
    step_lines = "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1))
    checks = [
        "输出直接回应发现的原始需求。",
        "用户不需要阅读原始来源帖子也能采取行动。",
        "假设、限制和所需输入清晰可见。",
        "在有帮助时，最终回复包含简短的使用说明或下一步建议。",
    ]
    check_lines = "\n".join(f"- {check}" for check in checks)
    outputs = [
        "针对用户当前情境的定制回答或产物。",
        "当任务可复用时，提供检查清单或工作流程。",
        "说明结果如何被检查的验证备注。",
    ]
    output_lines = "\n".join(f"- {output}" for output in outputs)
    triggers = "\n".join(f"- `{trigger}`" for trigger in plan.trigger_sentences)
    keywords = ", ".join(f"`{keyword}`" for keyword in plan.keywords)
    return f"""---
name: {plan.skill_name}
description: >-
  {description}
---

# {plan.display_name}

## 需求

使用这个技能帮助以下用户群体：{req.audience}

> {req.summary}

需求评分：{int(req.score)}/100（需求强度 `{req.demand_score}/70`，本地可执行性 `{req.feasibility_score}/30`）。
证据：{req.evidence_count} 条信号，覆盖 {req.source_count} 个来源类型。

如需查看来源证据、执行计划或评审标准，请阅读 `references/requirement-plan.md`。

## 工作流程

{step_lines}

## 预期输出

{output_lines}

## 验证

{check_lines}

## 触发方式

关键词：{keywords}

示例触发句：

{triggers}
"""


def render_readme_md(plan: SkillPlan) -> str:
    req = plan.requirement
    evidence = "\n".join(
        f"- {entry['source']}: [{md_escape(entry['title'])}]({entry['url']})"
        for entry in req.evidence
    )
    triggers = "\n".join(f"- `{trigger}`" for trigger in plan.trigger_sentences)
    keywords = ", ".join(f"`{keyword}`" for keyword in plan.keywords)
    return f"""# {plan.display_name}

## Requirement

{req.summary}

Audience: {req.audience}

Category: `{req.category}`

Demand score: {int(req.score)}/100

Evidence coverage: {req.evidence_count} signals across {req.source_count} source families.

## Evidence

{evidence}

## How This Skill Meets The Requirement

{plan.how_it_meets_need}

## Usage

Keywords: {keywords}

Trigger sentences:

{triggers}

## Files

- `SKILL.md`: English Codex-valid skill instructions.
- `SKILL.zh-CN.md`: Chinese skill instructions.
- `README.md`: English user-facing guide.
- `README.zh-CN.md`: Chinese user-facing guide.
"""


def render_readme_md_zh(plan: SkillPlan) -> str:
    req = plan.requirement
    evidence = "\n".join(
        f"- {entry['source']}：[{md_escape(entry['title'])}]({entry['url']})"
        for entry in req.evidence
    )
    triggers = "\n".join(f"- `{trigger}`" for trigger in plan.trigger_sentences)
    keywords = ", ".join(f"`{keyword}`" for keyword in plan.keywords)
    return f"""# {plan.display_name}

## 需求

{req.summary}

目标用户：{req.audience}

分类：`{zh_category_label(req.category)}`

需求评分：{int(req.score)}/100

证据覆盖：{req.evidence_count} 条信号，覆盖 {req.source_count} 个来源类型。

## 来源证据

{evidence}

## 这个技能如何满足需求

{plan.how_it_meets_need}

## 使用方式

关键词：{keywords}

触发句：

{triggers}

## 文件

- `SKILL.md`：英文版 Codex 有效技能说明。
- `SKILL.zh-CN.md`：中文版技能说明。
- `README.md`：英文版用户说明。
- `README.zh-CN.md`：中文版用户说明。
"""


def render_requirement_plan(plan: SkillPlan) -> str:
    req = plan.requirement
    evidence_lines = "\n".join(
        f"- {entry['source']} ({entry['created_at']}): [{md_escape(entry['title'])}]({entry['url']})"
        for entry in req.evidence
    )
    steps = "\n".join(f"{index}. {step}" for index, step in enumerate(plan.implementation_steps, start=1))
    checks = "\n".join(f"- {check}" for check in plan.validation_checks)
    triggers = "\n".join(f"- {trigger}" for trigger in plan.trigger_sentences)
    outputs = "\n".join(f"- {output}" for output in plan.outputs)
    keywords = ", ".join(plan.keywords)
    return f"""# Requirement Plan

## Live Requirement

{req.summary}

## Audience

{req.audience}

## Category

{req.category}

## Requirement Score

Total: {int(req.score)}/100

Demand: {req.demand_score}/70

Local feasibility: {req.feasibility_score}/30

Evidence coverage: {req.evidence_count} signals across {req.source_count} source families.

Scoring rationale:

{chr(10).join(f"- {line}" for line in req.scoring_rationale)}

## Evidence

{evidence_lines}

## How The Skill Meets The Requirement

{plan.how_it_meets_need}

## Executable Implementation Plan

{steps}

## Expected Outputs

{outputs}

## Review Criteria

{checks}

## Usage Signals

Keywords: {keywords}

Trigger sentences:

{triggers}
"""


def render_openai_yaml(plan: SkillPlan) -> str:
    short = f"Helps with {action_phrase(plan.requirement.summary)}."
    if len(short) > 64:
        short = short[:61].rstrip(" .,") + "..."
    if len(short) < 25:
        short = f"Helps users with {plan.requirement.category} needs."
    default_prompt = f"Use ${plan.skill_name} to help me {action_phrase(plan.requirement.summary)}."
    return f"""interface:
  display_name: {yaml_quote(plan.display_name)}
  short_description: {yaml_quote(short)}
  default_prompt: {yaml_quote(default_prompt)}

policy:
  allow_implicit_invocation: true
"""


def implement_skill(plan: SkillPlan, output_dir: Path) -> Path:
    skill_dir = output_dir / plan.skill_name
    refs_dir = skill_dir / "references"
    agents_dir = skill_dir / "agents"
    refs_dir.mkdir(parents=True, exist_ok=True)
    agents_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(render_skill_md(plan), encoding="utf-8", newline="\n")
    (skill_dir / "SKILL.zh-CN.md").write_text(render_skill_md_zh(plan), encoding="utf-8", newline="\n")
    (skill_dir / "README.md").write_text(render_readme_md(plan), encoding="utf-8", newline="\n")
    (skill_dir / "README.zh-CN.md").write_text(render_readme_md_zh(plan), encoding="utf-8", newline="\n")
    (refs_dir / "requirement-plan.md").write_text(render_requirement_plan(plan), encoding="utf-8", newline="\n")
    (agents_dir / "openai.yaml").write_text(render_openai_yaml(plan), encoding="utf-8", newline="\n")
    return skill_dir


def read_frontmatter(skill_md: str) -> dict[str, str]:
    if not skill_md.startswith("---"):
        return {}
    end = skill_md.find("\n---", 3)
    if end == -1:
        return {}
    block = skill_md[3:end].strip()
    result: dict[str, str] = {}
    current_key = ""
    for line in block.splitlines():
        if not line.strip():
            continue
        if re.match(r"^[a-zA-Z_][\w-]*:", line):
            key, value = line.split(":", 1)
            current_key = key.strip()
            result[current_key] = value.strip().strip('"')
        elif current_key:
            result[current_key] = (result[current_key] + " " + line.strip()).strip()
    return result


def locate_quick_validate() -> Path | None:
    candidate = Path.home() / ".codex" / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"
    return candidate if candidate.exists() else None


def official_validate(skill_dir: Path) -> tuple[bool, str]:
    validator = locate_quick_validate()
    if validator is None:
        return True, "quick_validate.py not found; internal review used"
    try:
        proc = subprocess.run(
            [sys.executable, str(validator), str(skill_dir)],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "PYTHONUTF8": "1"},
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - validation should report, not crash the run.
        return False, f"quick_validate.py failed to run: {exc}"
    output = (proc.stdout + "\n" + proc.stderr).strip()
    return proc.returncode == 0, output


def review_skill(plan: SkillPlan, skill_dir: Path) -> ReviewResult:
    findings: list[str] = []
    score = 0
    skill_md_path = skill_dir / "SKILL.md"
    skill_zh_path = skill_dir / "SKILL.zh-CN.md"
    readme_path = skill_dir / "README.md"
    readme_zh_path = skill_dir / "README.zh-CN.md"
    plan_path = skill_dir / "references" / "requirement-plan.md"
    openai_path = skill_dir / "agents" / "openai.yaml"
    for required in [skill_md_path, skill_zh_path, readme_path, readme_zh_path, plan_path, openai_path]:
        if required.exists():
            score += 1
        else:
            findings.append(f"Missing {required.name}")
    skill_md = skill_md_path.read_text(encoding="utf-8") if skill_md_path.exists() else ""
    frontmatter = read_frontmatter(skill_md)
    if frontmatter.get("name") == plan.skill_name:
        score += 1
    else:
        findings.append("SKILL.md frontmatter name does not match the planned skill name")
    if frontmatter.get("description") and any(keyword in frontmatter.get("description", "").lower() for keyword in plan.keywords[:5]):
        score += 1
    else:
        findings.append("Description does not clearly include planned keywords")
    for section in ["## Requirement", "## Workflow", "## Validation", "## Triggers"]:
        if section in skill_md:
            score += 1
        else:
            findings.append(f"Missing {section} section")
    skill_zh = skill_zh_path.read_text(encoding="utf-8") if skill_zh_path.exists() else ""
    if plan.requirement.summary in skill_zh and f"${plan.skill_name}" in skill_zh and len(skill_zh) > 500:
        score += 1
    else:
        findings.append("SKILL.zh-CN.md is missing Chinese requirement or workflow content")
    readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    if "## Requirement" in readme and "## Usage" in readme and f"${plan.skill_name}" in readme:
        score += 1
    else:
        findings.append("README.md is missing English requirement or usage content")
    readme_zh = readme_zh_path.read_text(encoding="utf-8") if readme_zh_path.exists() else ""
    if plan.requirement.summary in readme_zh and f"${plan.skill_name}" in readme_zh and len(readme_zh) > 400:
        score += 1
    else:
        findings.append("README.zh-CN.md is missing Chinese requirement or usage content")
    plan_text = plan_path.read_text(encoding="utf-8") if plan_path.exists() else ""
    if plan.requirement.summary in plan_text:
        score += 1
    else:
        findings.append("Requirement plan does not include the original requirement")
    if "## Executable Implementation Plan" in plan_text and "## Review Criteria" in plan_text:
        score += 1
    else:
        findings.append("Requirement plan is missing implementation or review criteria")
    openai_text = openai_path.read_text(encoding="utf-8") if openai_path.exists() else ""
    if f"${plan.skill_name}" in openai_text:
        score += 1
    else:
        findings.append("agents/openai.yaml default prompt does not mention the skill")
    validate_ok, validate_output = official_validate(skill_dir)
    if validate_ok:
        score += 1
    else:
        findings.append(validate_output or "quick_validate.py reported a failure")
    passed = not findings
    return ReviewResult(
        skill_name=plan.skill_name,
        passed=passed,
        score=score,
        findings=findings,
        path=str(skill_dir),
    )


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")


def dataclass_to_dicts(values: list[Any]) -> list[dict[str, Any]]:
    return [dataclasses.asdict(value) for value in values]


def command_exists(command: str) -> bool:
    return bool(shutil.which(command))


def publish_to_clawhub(skill_dirs: list[Path], cli: str, version: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if not command_exists(cli):
        return [
            {
                "target": "clawhub",
                "status": "skipped",
                "reason": f"{cli!r} CLI was not found. Install it and run `clawhub login` first.",
            }
        ]
    for skill_dir in skill_dirs:
        command = [cli, "skill", "publish", str(skill_dir)]
        if version:
            command.extend(["--version", version])
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        results.append(
            {
                "target": "clawhub",
                "skill": skill_dir.name,
                "path": str(skill_dir),
                "status": "published" if result.returncode == 0 else "failed",
                "returncode": result.returncode,
                "stdout": result.stdout.strip()[-1200:],
                "stderr": result.stderr.strip()[-1200:],
            }
        )
    return results


def github_token() -> str:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def github_request(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"message": body}
        return exc.code, parsed


def github_file_sha(repo: str, branch: str, remote_path: str, token: str) -> str | None:
    api_base = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    encoded_path = urllib.parse.quote(remote_path.replace("\\", "/"), safe="/")
    url = f"{api_base}/repos/{repo}/contents/{encoded_path}?ref={urllib.parse.quote(branch)}"
    status, body = github_request("GET", url, token)
    if status == 200 and isinstance(body, dict):
        sha = body.get("sha")
        return str(sha) if sha else None
    if status == 404:
        return None
    message = body.get("message", body) if isinstance(body, dict) else body
    raise RuntimeError(f"GitHub lookup failed for {remote_path}: HTTP {status}: {message}")


def github_put_file(repo: str, branch: str, remote_path: str, local_path: Path, token: str, message: str) -> dict[str, Any]:
    api_base = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    encoded_path = urllib.parse.quote(remote_path.replace("\\", "/"), safe="/")
    url = f"{api_base}/repos/{repo}/contents/{encoded_path}"
    payload: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(local_path.read_bytes()).decode("ascii"),
        "branch": branch,
    }
    sha = github_file_sha(repo, branch, remote_path, token)
    if sha:
        payload["sha"] = sha
    status, body = github_request("PUT", url, token, payload)
    if status not in {200, 201}:
        api_message = body.get("message", body) if isinstance(body, dict) else body
        raise RuntimeError(f"GitHub upload failed for {remote_path}: HTTP {status}: {api_message}")
    return {
        "path": remote_path,
        "status": "updated" if status == 200 else "created",
        "url": body.get("content", {}).get("html_url") if isinstance(body, dict) else "",
    }


def collect_publish_files(skill_root: Path, run_dir: Path, output_root: Path, run_id: str) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for path in sorted(skill_root.rglob("*")):
        if path.is_file():
            files.append((path, f"generated_skills/{run_id}/{path.relative_to(skill_root).as_posix()}"))
    for path, remote_name in [
        (output_root / "SKILLS_CATALOG.md", "SKILLS_CATALOG.md"),
        (run_dir / "SCORING_REPORT.md", "SCORING_REPORT.md"),
        (run_dir / "metadata.json", "metadata.json"),
        (run_dir / "publish_manifest.json", "publish_manifest.json"),
    ]:
        if path.exists():
            files.append((path, remote_name))
    return files


def publish_to_github(repo: str, branch: str, prefix: str, files: list[tuple[Path, str]], run_id: str) -> list[dict[str, Any]]:
    token = github_token()
    if not repo:
        return [
            {
                "target": "github",
                "status": "skipped",
                "reason": "No GitHub repository was configured. Use `--publish-github-repo owner/repo`.",
            }
        ]
    if "/" not in repo:
        return [
            {
                "target": "github",
                "status": "skipped",
                "reason": f"GitHub repository must be in owner/repo form, got {repo!r}.",
            }
        ]
    if not token:
        return [
            {
                "target": "github",
                "status": "skipped",
                "repo": repo,
                "reason": "Set GITHUB_TOKEN or GH_TOKEN with repository contents write permission.",
            }
        ]
    clean_prefix = prefix.strip("/").replace("\\", "/")
    results: list[dict[str, Any]] = []
    message = f"Publish skill-demand-agent run {run_id}"
    for local_path, remote_name in files:
        remote_path = f"{clean_prefix}/{run_id}/{remote_name}" if clean_prefix else f"{run_id}/{remote_name}"
        try:
            uploaded = github_put_file(repo, branch, remote_path, local_path, token, message)
            uploaded.update({"target": "github", "repo": repo, "branch": branch, "local_path": str(local_path)})
            results.append(uploaded)
        except Exception as exc:
            results.append(
                {
                    "target": "github",
                    "repo": repo,
                    "branch": branch,
                    "local_path": str(local_path),
                    "path": remote_path,
                    "status": "failed",
                    "reason": str(exc),
                }
            )
    return results


def write_publish_manifest(
    path: Path,
    run_id: str,
    generated_at: str,
    skill_dirs: list[Path],
    publish_results: list[dict[str, Any]],
    catalog_path: Path,
) -> None:
    write_json(
        path,
        {
            "run_id": run_id,
            "generated_at": generated_at,
            "catalog": str(catalog_path),
            "skills": [str(skill_dir) for skill_dir in skill_dirs],
            "targets": {
                "clawhub_dashboard": "https://clawhub.ai/dashboard",
                "github_repositories": "https://github.com/Kyro-Ma?tab=repositories",
            },
            "results": publish_results,
        },
    )


def render_catalog(
    run_id: str,
    generated_at: str,
    requirements: list[Requirement],
    plans: list[SkillPlan],
    reviews: list[ReviewResult],
    discovery_notes: list[str],
    skill_root: Path,
) -> str:
    review_by_name = {review.skill_name: review for review in reviews}
    summary_rows = [
        "| Skill | Score | Evidence | Category | Requirement | Review |",
        "| --- | ---: | ---: | --- | --- | --- |",
    ]
    for plan in plans:
        review = review_by_name.get(plan.skill_name)
        status = "pass" if review and review.passed else "needs attention"
        summary_rows.append(
            f"| `{plan.skill_name}` | {int(plan.requirement.score)} | {plan.requirement.evidence_count}/{plan.requirement.source_count} | "
            f"{md_escape(plan.requirement.category)} | {md_escape(plan.requirement.summary[:120])} | {status} |"
        )
    sections: list[str] = []
    for index, plan in enumerate(plans, start=1):
        review = review_by_name.get(plan.skill_name)
        evidence = "\n".join(
            f"- {entry['source']}: [{md_escape(entry['title'])}]({entry['url']})"
            for entry in plan.requirement.evidence
        )
        triggers = "\n".join(f"- `{trigger}`" for trigger in plan.trigger_sentences)
        keywords = ", ".join(f"`{keyword}`" for keyword in plan.keywords)
        review_text = "Passed all checks." if review and review.passed else "; ".join(review.findings if review else ["Review missing"])
        relative_path = skill_root / plan.skill_name
        scoring = "\n".join(f"- {line}" for line in plan.requirement.scoring_rationale)
        sections.append(
            f"""## {index}. {plan.display_name}

- Skill folder: `{relative_path}`
- Docs: `SKILL.md`, `SKILL.zh-CN.md`, `README.md`, `README.zh-CN.md`
- Requirement: {plan.requirement.summary}
- Audience: {plan.requirement.audience}
- Category: `{plan.requirement.category}`
- Keywords: {keywords}
- Score: {int(plan.requirement.score)}/100
- Evidence coverage: {plan.requirement.evidence_count} signals across {plan.requirement.source_count} source families

### Evidence

{evidence}

### Requirement Check

{scoring}

### How This Skill Meets The Requirement

{plan.how_it_meets_need}

### How To Use

{triggers}

### Review

{review_text}
"""
        )
    notes = "\n".join(f"- {note}" for note in discovery_notes)
    return f"""# Skill Demand Agent Catalog

Generated: {generated_at}

Run ID: `{run_id}`

## Discovery Notes

{notes}

## Summary

Discovered {len(requirements)} requirements and generated {len(plans)} skills.

{chr(10).join(summary_rows)}

{chr(10).join(sections)}
"""


def render_scoring_report(
    run_id: str,
    requirements: list[Requirement],
    threshold: int,
    min_evidence: int,
    selected_requirement_ids: set[str] | None = None,
    deduped_requirement_ids: set[str] | None = None,
) -> str:
    rows = [
        "| Score | Evidence | Sources | Category | Requirement | Decision |",
        "| ---: | ---: | ---: | --- | --- | --- |",
    ]
    sections: list[str] = []
    for index, requirement in enumerate(sorted(requirements, key=lambda req: req.score, reverse=True), start=1):
        accepted = requirement_meets_acceptance(requirement, threshold, min_evidence)
        if not accepted:
            decision = "reject"
        elif deduped_requirement_ids and requirement.requirement_id in deduped_requirement_ids:
            decision = "deduplicate"
        elif selected_requirement_ids is not None and requirement.requirement_id not in selected_requirement_ids:
            decision = "eligible, not selected"
        else:
            decision = "implement"
        rows.append(
            f"| {int(requirement.score)} | {requirement.evidence_count} | {requirement.source_count} | "
            f"{md_escape(requirement.category)} | {md_escape(requirement.summary[:110])} | {decision} |"
        )
        evidence = "\n".join(
            f"- {entry['source']}: [{md_escape(entry['title'])}]({entry['url']})"
            for entry in requirement.evidence
        )
        rationale = "\n".join(f"- {line}" for line in requirement.scoring_rationale)
        sections.append(
            f"""## {index}. {decision.upper()} - {int(requirement.score)}/100

Requirement: {requirement.summary}

Audience: {requirement.audience}

Category: `{requirement.category}`

Evidence: {requirement.evidence_count} signals across {requirement.source_count} source families.

### Rationale

{rationale}

### Sources

{evidence}
"""
        )
    return f"""# Requirement Scoring Report

Run ID: `{run_id}`

Threshold: {threshold}

Minimum evidence: {min_evidence} separate source signals.

## Decisions

{chr(10).join(rows)}

{chr(10).join(sections)}
"""


def parse_args() -> argparse.Namespace:
    workspace_default = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Discover live user needs and generate reviewed Codex skills.")
    parser.add_argument("--days", type=int, default=14, help="Lookback window for online discovery.")
    parser.add_argument("--per-source-limit", type=int, default=60, help="Approximate source fetch limit.")
    parser.add_argument("--max-ideas", type=int, default=10, help="Number of ideas to implement. Use 0 for all.")
    parser.add_argument("--max-workers", type=int, default=10, help="Parallel skill agents, capped at 10.")
    parser.add_argument("--theme-profile", choices=["default", "office"], default="default", help="Discovery theme profile to use.")
    parser.add_argument("--score-threshold", type=int, default=DEFAULT_SCORE_THRESHOLD, help="Only implement requirements scoring at least this high.")
    parser.add_argument("--min-evidence", type=int, default=MIN_REQUIRED_EVIDENCE, help="Minimum corroborating evidence items required.")
    parser.add_argument("--max-search-rounds", type=int, default=3, help="How many times to broaden online search when no requirement passes.")
    parser.add_argument("--no-clawhub-popular", action="store_true", help="Disable Clawhub popular-skill discovery seeds.")
    parser.add_argument("--clawhub-min-downloads", type=int, default=CLAW_HUB_MIN_DOWNLOADS, help="Minimum Clawhub downloads for popular-skill idea seeds.")
    parser.add_argument("--clawhub-popular-limit", type=int, default=CLAW_HUB_POPULAR_LIMIT, help="Maximum Clawhub popular skills to fetch before scoring.")
    parser.add_argument("--output-root", type=Path, default=workspace_default, help="Workspace output directory.")
    parser.add_argument("--run-id", default="", help="Optional deterministic run id.")
    parser.add_argument("--publish-clawhub", action="store_true", help="Publish reviewed skills to ClawHub with `clawhub skill publish`.")
    parser.add_argument("--clawhub-cli", default="clawhub", help="ClawHub CLI command name or absolute path.")
    parser.add_argument("--clawhub-version", default="", help="Optional version to pass to `clawhub skill publish --version`.")
    parser.add_argument("--publish-github-repo", default=os.environ.get("SKILL_DEMAND_GITHUB_REPO", ""), help="GitHub repository in owner/repo form for publishing generated skills.")
    parser.add_argument("--publish-github-branch", default=os.environ.get("SKILL_DEMAND_GITHUB_BRANCH", "main"), help="GitHub branch to update when publishing.")
    parser.add_argument("--publish-github-prefix", default=os.environ.get("SKILL_DEMAND_GITHUB_PREFIX", "skill-demand-agent-runs"), help="Repository folder prefix for published run artifacts.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.days < 1:
        raise SystemExit("--days must be at least 1")
    if args.clawhub_min_downloads < 0:
        raise SystemExit("--clawhub-min-downloads must not be negative")
    if args.clawhub_popular_limit < 0:
        raise SystemExit("--clawhub-popular-limit must not be negative")
    max_workers = max(1, min(args.max_workers, MAX_WORKERS))
    output_root = args.output_root.resolve()
    run_id = args.run_id or utc_now().strftime("%Y%m%d-%H%M%S")
    generated_at = utc_now().isoformat()
    run_dir = output_root / "runs" / run_id
    skill_root = output_root / "generated_skills" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    skill_root.mkdir(parents=True, exist_ok=True)

    all_items: list[SourceItem] = []
    discovery_notes: list[str] = []
    scoring_notes: list[str] = []
    requirements: list[Requirement] = []
    eligible_requirements: list[Requirement] = []
    deduped_requirement_ids: set[str] = set()
    for round_index in range(max(1, args.max_search_rounds)):
        round_days = args.days if round_index == 0 else args.days * (round_index + 2)
        round_limit = args.per_source_limit if round_index == 0 else args.per_source_limit * (round_index + 1)
        print(
            f"[discover] round {round_index + 1}: searching online sources for the last {round_days} days "
            f"(theme profile: {args.theme_profile})"
        )
        items, round_notes = discover_online(
            round_days,
            round_limit,
            args.theme_profile,
            not args.no_clawhub_popular,
            args.clawhub_min_downloads,
            args.clawhub_popular_limit,
        )
        all_items.extend(items)
        discovery_notes.extend([f"round {round_index + 1}: {note}" for note in round_notes])
        requirements, round_scoring_notes = extract_requirements(
            all_items,
            args.max_ideas,
            round_days,
            round_limit,
            args.min_evidence,
            args.theme_profile,
        )
        scoring_notes.extend([f"round {round_index + 1}: {note}" for note in round_scoring_notes])
        eligible_candidates = [
            requirement
            for requirement in requirements
            if requirement_meets_acceptance(requirement, args.score_threshold, args.min_evidence)
        ]
        eligible_requirements, round_dedupe_notes, round_deduped_ids = dedupe_requirements(eligible_candidates)
        deduped_requirement_ids.update(round_deduped_ids)
        scoring_notes.extend([f"round {round_index + 1}: {note}" for note in round_dedupe_notes])
        print(
            f"[score-agent] {len(eligible_candidates)} requirements scored >= {args.score_threshold} "
            f"with at least {args.min_evidence} corroborating evidence items"
        )
        if len(eligible_requirements) != len(eligible_candidates):
            print(
                f"[dedupe-agent] removed {len(eligible_candidates) - len(eligible_requirements)} repeated ideas; "
                f"{len(eligible_requirements)} unique requirements remain"
            )
        if eligible_requirements:
            break
        print("[score-agent] no requirement passed; broadening online search and trying other source queries")

    if not requirements:
        write_json(run_dir / "raw_items.json", [dataclasses.asdict(item) for item in all_items])
        write_json(run_dir / "discovery_notes.json", discovery_notes)
        raise SystemExit("No requirement-like items were discovered after expanded online search.")
    all_scored_requirements = requirements
    if not eligible_requirements:
        write_json(run_dir / "raw_items.json", [dataclasses.asdict(item) for item in all_items])
        write_json(run_dir / "requirements.json", dataclass_to_dicts(all_scored_requirements))
        write_json(run_dir / "discovery_notes.json", discovery_notes)
        write_json(run_dir / "scoring_notes.json", scoring_notes)
        catalog = render_catalog(run_id, generated_at, all_scored_requirements, [], [], discovery_notes + scoring_notes, skill_root)
        (output_root / "SKILLS_CATALOG.md").write_text(catalog, encoding="utf-8", newline="\n")
        (run_dir / "SCORING_REPORT.md").write_text(
            render_scoring_report(run_id, all_scored_requirements, args.score_threshold, args.min_evidence),
            encoding="utf-8",
            newline="\n",
        )
        raise SystemExit(
            f"No requirements scored >= {args.score_threshold} after {args.max_search_rounds} search rounds; no skills were implemented."
        )
    requirements, final_dedupe_notes, final_deduped_ids = dedupe_requirements(
        sorted(eligible_requirements, key=lambda req: req.score, reverse=True)
    )
    deduped_requirement_ids.update(final_deduped_ids)
    scoring_notes.extend(final_dedupe_notes)
    if args.max_ideas > 0:
        requirements = requirements[: args.max_ideas]

    used_names: set[str] = set()
    plans = [plan_for_requirement(requirement, used_names) for requirement in requirements]
    plans, plan_dedupe_notes, plan_deduped_ids = dedupe_plans(plans)
    requirements = [plan.requirement for plan in plans]
    deduped_requirement_ids.update(plan_deduped_ids)
    scoring_notes.extend(plan_dedupe_notes)

    print(f"[plan] selected {len(plans)} requirements over score threshold {args.score_threshold}")
    print(f"[implement] running up to {max_workers} parallel skill agents")
    implemented_paths: dict[str, Path] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(implement_skill, plan, skill_root): plan for plan in plans}
        for future in concurrent.futures.as_completed(futures):
            plan = futures[future]
            implemented_paths[plan.skill_name] = future.result()
            print(f"[implement] {plan.skill_name}")

    print("[review] checking generated skills against plans")
    reviews: list[ReviewResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(review_skill, plan, implemented_paths[plan.skill_name]): plan
            for plan in plans
        }
        for future in concurrent.futures.as_completed(futures):
            review = future.result()
            reviews.append(review)
            status = "pass" if review.passed else "needs attention"
            print(f"[review] {review.skill_name}: {status}")
    reviews.sort(key=lambda review: [plan.skill_name for plan in plans].index(review.skill_name))

    write_json(run_dir / "raw_items.json", [dataclasses.asdict(item) for item in all_items])
    write_json(run_dir / "requirements.json", dataclass_to_dicts(requirements))
    write_json(run_dir / "all_scored_requirements.json", dataclass_to_dicts(all_scored_requirements))
    write_json(run_dir / "plans.json", dataclass_to_dicts(plans))
    write_json(run_dir / "reviews.json", dataclass_to_dicts(reviews))
    write_json(run_dir / "discovery_notes.json", discovery_notes)
    write_json(run_dir / "scoring_notes.json", scoring_notes)
    (run_dir / "SCORING_REPORT.md").write_text(
        render_scoring_report(
            run_id,
            all_scored_requirements,
            args.score_threshold,
            args.min_evidence,
            {requirement.requirement_id for requirement in requirements},
            deduped_requirement_ids,
        ),
        encoding="utf-8",
        newline="\n",
    )
    write_json(
        run_dir / "metadata.json",
        {
            "run_id": run_id,
            "generated_at": generated_at,
            "days": args.days,
            "per_source_limit": args.per_source_limit,
            "max_ideas": args.max_ideas,
            "max_workers": max_workers,
            "theme_profile": args.theme_profile,
            "score_threshold": args.score_threshold,
            "min_evidence": args.min_evidence,
            "max_search_rounds": args.max_search_rounds,
            "clawhub_popular_enabled": not args.no_clawhub_popular,
            "clawhub_min_downloads": args.clawhub_min_downloads,
            "clawhub_popular_limit": args.clawhub_popular_limit,
            "skill_root": str(skill_root),
            "catalog": str(output_root / "SKILLS_CATALOG.md"),
            "dedupe": {
                "similarity_threshold": SIMILARITY_DEDUPE_THRESHOLD,
                "removed_requirement_ids": sorted(deduped_requirement_ids),
            },
            "publish": {
                "clawhub_enabled": args.publish_clawhub,
                "clawhub_cli": args.clawhub_cli,
                "clawhub_version": args.clawhub_version,
                "github_repo": args.publish_github_repo,
                "github_branch": args.publish_github_branch,
                "github_prefix": args.publish_github_prefix,
            },
            "discovery_notes": discovery_notes,
            "scoring_notes": scoring_notes,
        },
    )
    catalog = render_catalog(run_id, generated_at, requirements, plans, reviews, discovery_notes + scoring_notes, skill_root)
    (output_root / "SKILLS_CATALOG.md").write_text(catalog, encoding="utf-8", newline="\n")

    passed = sum(1 for review in reviews if review.passed)
    publish_results: list[dict[str, Any]] = []
    publishable_skill_dirs = [
        implemented_paths[review.skill_name]
        for review in reviews
        if review.passed and review.skill_name in implemented_paths
    ]
    manifest_path = run_dir / "publish_manifest.json"
    write_publish_manifest(
        manifest_path,
        run_id,
        generated_at,
        publishable_skill_dirs,
        publish_results,
        output_root / "SKILLS_CATALOG.md",
    )
    if args.publish_clawhub:
        print(f"[publish] publishing {len(publishable_skill_dirs)} skills to ClawHub")
        publish_results.extend(
            publish_to_clawhub(
                publishable_skill_dirs,
                args.clawhub_cli,
                args.clawhub_version,
            )
        )
    if args.publish_github_repo:
        print(f"[publish] uploading run artifacts to GitHub repo {args.publish_github_repo}")
        publish_files = collect_publish_files(skill_root, run_dir, output_root, run_id)
        publish_results.extend(
            publish_to_github(
                args.publish_github_repo,
                args.publish_github_branch,
                args.publish_github_prefix,
                publish_files,
                run_id,
            )
        )
    write_publish_manifest(
        manifest_path,
        run_id,
        generated_at,
        publishable_skill_dirs,
        publish_results,
        output_root / "SKILLS_CATALOG.md",
    )
    if args.publish_github_repo:
        token = github_token()
        if token:
            final_manifest_result = publish_to_github(
                args.publish_github_repo,
                args.publish_github_branch,
                args.publish_github_prefix,
                [(manifest_path, "publish_manifest.json")],
                run_id,
            )
            publish_results.extend(final_manifest_result)
            write_publish_manifest(
                manifest_path,
                run_id,
                generated_at,
                publishable_skill_dirs,
                publish_results,
                output_root / "SKILLS_CATALOG.md",
            )
    if publish_results:
        write_json(run_dir / "publish_results.json", publish_results)
        published = sum(1 for result in publish_results if result.get("status") in {"published", "created", "updated"})
        failed = sum(1 for result in publish_results if result.get("status") == "failed")
        skipped = sum(1 for result in publish_results if result.get("status") == "skipped")
        print(f"[publish] results: {published} published/updated, {failed} failed, {skipped} skipped")
    print(f"[done] wrote {output_root / 'SKILLS_CATALOG.md'}")
    print(f"[done] review passed {passed}/{len(reviews)} skills")
    return 0 if passed == len(reviews) else 1


if __name__ == "__main__":
    raise SystemExit(main())
