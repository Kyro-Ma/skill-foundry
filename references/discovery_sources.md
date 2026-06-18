# Discovery Sources

The runner intentionally uses public endpoints that need no API key:

- Hacker News Algolia API for recent Ask HN needs and tool requests.
- GitHub issue search for current feature requests and enhancement requests.
- V2EX public latest/hot topic API for recent China-accessible developer and maker discussions.
- Gitee public issue search for China-accessible feature requests and enhancement requests.
- Juejin public search API for China-accessible developer articles and discussions.
- CSDN public search API for China-accessible technical articles and problem signals.
- OSChina public search pages for targeted China-accessible open-source and developer follow-up evidence.
- SegmentFault public search pages for targeted China-accessible Q&A and developer follow-up evidence.
- Clawhub public skill catalog API for popular skills above the configured download threshold.

Each run must attempt live network discovery. Do not replace live discovery with static fixtures unless adding an explicit test-only mode.

Clawhub popular-skill discovery is enabled by default for the normal theme profile. The default threshold is 100,000 downloads. Each popular skill should seed two kinds of ideas: bug-fix or hardening work for the existing skill pattern, and adjacent skill ideas created by understanding what the popular skill already does. These seeds still pass through the same corroboration, scoring, dedupe, planning, implementation, and review stages as other ideas. Do not implement a Clawhub-derived idea just because the source skill is popular; implement it only when its scored requirement reaches the configured score threshold, normally 90/100 or higher.

Use `--theme-profile office` when the run should focus on Microsoft Word, Excel, PowerPoint, DOCX/XLSX/PPTX, Open XML, VBA, and Python Office automation issues. That profile keeps the same public source families but changes the targeted themes and source queries to Office-related technical problems.

## Candidate Signals

Prioritize posts that sound like a person asking for help:

- "I need..."
- "looking for..."
- "how do I..."
- "any tool..."
- "best way to..."
- "recommend..."
- "wish there was..."
- "struggling with..."
- "需求"
- "如何"
- "怎么"
- "求推荐"
- "有没有"

Avoid pure news, hiring threads, advertisements, solved release notes, and posts without a user job-to-be-done.

## Planning Standard

For each accepted requirement, generate a skill plan with:

- Audience and situation.
- Requirement statement that is broader than one post title.
- At least three separate evidence source URLs.
- Requirement score of at least 90/100 before implementation.
- Implementation workflow.
- Expected outputs.
- Validation checks.
- Keywords and trigger sentences.

## Scoring Standard

Run the requirement scoring agent before implementation. It must mark:

- Demand strength out of 70, based on evidence count, source diversity, and professional/community need.
- Local feasibility out of 30, based on whether the implementation can be executed on ordinary CPU or family GPU hardware.

Only implement skills with total score `>= 90` and at least three separate evidence items. Source-family diversity should still be reported and reflected in the score rationale, but it is not a hard blocker once the idea reaches the score threshold. If none pass, broaden the search window and run targeted searches for other requirement themes. Stop after three search rounds if no idea reaches the threshold.

## Parallelism

Implement generated skills with a worker pool. The queue may contain any number of ideas, but `max_workers` must never exceed 10.
