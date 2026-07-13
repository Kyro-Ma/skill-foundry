<p align="right">
  <a href="./README.md">English</a> | <a href="./README_ch.md">简体中文</a>
</p>

# SkillFoundry
Clawhub Account:
![ClawHub dashboard: office and document skills](2026-07-13.png)

**Find real demand. Build the right skills. Publish with proof.**

SkillFoundry is a demand-driven skill factory for AI products, agent marketplaces, internal automation libraries, and workflow teams. It discovers what users are already asking for, proves demand with live evidence, scores each opportunity, removes duplicates, generates complete skill packages, reviews them, and prepares them for ClawHub or GitHub publishing.

Instead of guessing what to build next, SkillFoundry turns public demand signals into a repeatable production pipeline.

## Why We Built It

Most skill libraries grow from intuition:

- someone notices a problem,
- someone writes a helper,
- someone uploads it,
- and only later do we discover whether people actually wanted it.

That approach is slow and noisy. It creates duplicate skills, vague names, weak documentation, and packages that look useful but have no demand behind them.

SkillFoundry reverses the process.

It starts with the market: public questions, feature requests, issue threads, community posts, and popular ClawHub patterns. Then it asks:

1. Are real users repeatedly asking for this?
2. Is there enough evidence across multiple sources?
3. Can this become a practical, local-friendly skill?
4. Is it different enough from existing ideas?
5. Can it be packaged, documented, reviewed, and published?

Only high-confidence ideas move forward.

## What We Did

We built an end-to-end pipeline that:

- scans public demand sources,
- pulls ClawHub popularity signals,
- turns noisy posts into structured requirements,
- scores opportunities on a 100-point scale,
- keeps only ideas above the acceptance threshold,
- deduplicates repeated ideas,
- generates skill implementation plans,
- creates complete bilingual skill folders,
- reviews generated packages,
- publishes reviewed output when configured,
- and writes a human-readable catalog for every run.

The result is not just a list of ideas. It is a production system for deciding what skills are worth building.

## Launch Proof

After uploading generated skills to ClawHub, the dashboard screenshots below show visible published entries accumulating downloads within a few days.

Across the three provided ClawHub dashboard screenshots, the visible cards add up to **1,612 total downloads**.

> This total is calculated from the download counts visible in the screenshots. It counts visible dashboard cards as shown, including separate published entries with the same display name.

![ClawHub dashboard: office and document skills](assets/clawhub-dashboard-office-skills.png)

![ClawHub dashboard: general generated skills](assets/clawhub-dashboard-general-skills.png)

![ClawHub dashboard: renamed and updated skills](assets/clawhub-dashboard-renamed-skills.png)

## Component Overview

SkillFoundry is built from ten main components.

### 1. Source Discovery

The discovery layer scans public sources that expose real user needs:

- Hacker News for Ask HN posts and tool requests.
- GitHub Issues for feature requests, enhancement requests, bug-fix requests, and implementation gaps.
- V2EX, Gitee, Juejin, CSDN, OSChina, and SegmentFault for China-accessible developer and maker signals.
- ClawHub public skill listings for popular existing skill patterns.

Example:

A GitHub issue asking for OpenAPI documentation, a Hacker News thread about reviewing generated code, and a ClawHub skill with strong usage can all become signals for a new skill opportunity.

### 2. Candidate Extraction

Raw posts are noisy. SkillFoundry filters for phrases and patterns that sound like real jobs-to-be-done:

- "I need..."
- "How do I..."
- "Any tool..."
- "Feature request"
- "Recommend..."
- "需求"
- "如何"
- "怎么"
- "有没有"

It avoids pure news, hiring posts, advertisements, and one-off announcements.

Example:

An issue titled `test(unit): add tests for db modules` is generalized into a broader market requirement:

> Teams need repeatable help adding useful unit tests and raising test coverage for existing codebases.

### 3. Evidence Corroboration

SkillFoundry does not build from a single post. Every serious requirement needs multiple signals.

The default gate requires at least **3 separate evidence items**. The system also reports how many source families support the idea, such as GitHub, Hacker News, V2EX, or ClawHub.

Example:

`unit-test-coverage-helper` reached 12 evidence items across 2 source families. It was accepted, but its score was capped because the evidence did not span at least 3 source families.

### 4. Demand Scoring

Every requirement is scored out of 100:

- **70 points** for demand strength.
- **30 points** for implementation feasibility.

Demand strength considers evidence count, source diversity, and community or professional signal. Feasibility considers whether the skill can run on ordinary local hardware and be expressed as a practical workflow, checklist, script, template, or small automation.

The default implementation threshold is **90/100**.

Example:

A Skill Vetter-style opportunity reached 100/100 because it combined strong ClawHub popularity with Hacker News and GitHub evidence around security, setup, and reliability.

### 5. Deduplication

Demand often repeats under different names. SkillFoundry removes same-function ideas before generating packages.

It uses similarity checks and planned skill names to keep only the strongest representative by:

- score,
- evidence count,
- source diversity,
- and functional uniqueness.

Example:

If two requirements both produce the same planned package name, only the stronger one survives.

### 6. Skill Planning

Accepted requirements become structured skill plans.

Each plan includes:

- skill name,
- display name,
- target audience,
- requirement summary,
- evidence links,
- implementation workflow,
- validation checks,
- expected outputs,
- trigger sentences,
- and keywords.

This planning step makes every generated package explain why it exists.

### 7. Parallel Generation

SkillFoundry generates multiple skill folders in parallel with a worker cap of 10.

Each generated folder includes:

- `SKILL.md`
- `SKILL.zh-CN.md`
- `README.md`
- `README.zh-CN.md`
- `references/requirement-plan.md`
- `agents/openai.yaml`

The output is ready for review, cataloging, and publishing.

### 8. Review

After generation, SkillFoundry checks each package against its plan.

The review checks:

- required files,
- frontmatter,
- naming consistency,
- required sections,
- bilingual documentation,
- trigger examples,
- requirement traceability,
- and optional official validation scripts when available.

Failures are not hidden. They are written into `reviews.json` and surfaced in `SKILLS_CATALOG.md`.

### 9. Publishing

SkillFoundry can publish reviewed skills to ClawHub and upload run artifacts to GitHub.

ClawHub publishing uses:

```bash
python scripts/run_skill_demand_agent.py --publish-clawhub
```

GitHub publishing uses:

```bash
python scripts/run_skill_demand_agent.py --publish-github-repo Kyro-Ma/<repo-name>
```

Publishing writes:

- `publish_manifest.json`
- `publish_results.json`

Each result records success, failure, or skipped status.

### 10. Catalog

Every run writes a catalog:

```text
SKILLS_CATALOG.md
```

The catalog is the operating dashboard for the run. It lists:

- generated skill names,
- scores,
- evidence counts,
- source coverage,
- requirements,
- keywords,
- trigger sentences,
- review status,
- and file locations.

This makes the output easy to inspect, share, and improve.

## Example Generated Skills

SkillFoundry has generated and published skills such as:

- `unit-test-coverage-helper`
- `openapi-docs-generator`
- `error-message-improver`
- `product-validation-planner`
- `mobile-responsive-layout-fixer`
- `local-llm-setup-advisor`
- `word-docx-formatting-repair-helper`
- `excel-xlsx-formula-cleanup-helper`
- `powerpoint-pptx-layout-export-helper`
- `workflow-planner-simplifier`

These are not random ideas. Each comes from discovered demand signals and a scoring gate.

## Quick Start

Run the full pipeline:

```bash
python scripts/run_skill_demand_agent.py --max-ideas 10 --max-workers 10
```

Run every accepted idea:

```bash
python scripts/run_skill_demand_agent.py --max-ideas 0
```

Use the Office-focused profile:

```bash
python scripts/run_skill_demand_agent.py --theme-profile office --max-ideas 10
```

Tune the acceptance gate:

```bash
python scripts/run_skill_demand_agent.py --score-threshold 90 --min-evidence 3 --max-search-rounds 3
```

## Outputs

SkillFoundry writes:

- `generated_skills/<run-id>/` for generated skill folders.
- `runs/<run-id>/raw_items.json` for discovered source items.
- `runs/<run-id>/requirements.json` for selected requirements.
- `runs/<run-id>/plans.json` for implementation plans.
- `runs/<run-id>/reviews.json` for package reviews.
- `runs/<run-id>/SCORING_REPORT.md` for scoring decisions.
- `runs/<run-id>/publish_manifest.json` for publishable outputs.
- `runs/<run-id>/publish_results.json` for publishing results.
- `SKILLS_CATALOG.md` for the latest human-readable catalog.

## Why It Matters

Skill creation is becoming cheaper. The hard question is no longer "can we generate a skill?"

The hard question is:

> Which skill is worth building next?

SkillFoundry answers that with evidence. It turns community demand into a measurable pipeline and gives teams a repeatable way to build the skills users already want.

