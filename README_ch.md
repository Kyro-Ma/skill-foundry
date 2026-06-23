<p align="right">
  <a href="./README.md">English</a> | <strong>简体中文</strong>
</p>

# SkillFoundry

**发现真实需求。构建正确技能。带着证据发布。**

SkillFoundry 是一个面向 AI 产品、Agent 市场、内部自动化库和工作流团队的需求驱动型技能工厂。它会发现用户已经在公开场景中提出的真实需求，用实时证据证明需求存在，对每个机会进行评分，去除重复想法，生成完整技能包，完成审查，并准备发布到 ClawHub 或 GitHub。

与其凭感觉猜下一个该做什么技能，SkillFoundry 把公开需求信号转化为一条可重复运行的生产流水线。

## 为什么要做 SkillFoundry

大多数技能库的增长都来自直觉：

* 某个人发现了一个问题；
* 某个人写了一个辅助工具；
* 某个人把它上传；
* 直到后来才发现用户到底需不需要它。

这种方式慢，而且噪声很大。它容易产生重复技能、模糊命名、薄弱文档，以及看起来有用但没有真实需求支撑的技能包。

SkillFoundry 反过来做这件事。

它从市场出发：公开问题、功能请求、Issue 讨论、社区帖子，以及 ClawHub 上已经流行的技能模式。然后它会问：

1. 是否有真实用户反复提出这个需求？
2. 是否有足够多来自不同来源的证据？
3. 它能否变成一个实用、适合本地运行的技能？
4. 它是否与已有想法有足够区别？
5. 它能否被打包、写文档、审查并发布？

只有高置信度的想法才会继续进入下一步。

## 我们做了什么

我们构建了一条端到端流水线，可以：

* 扫描公开需求来源；
* 拉取 ClawHub 的流行度信号；
* 把噪声较高的帖子转化为结构化需求；
* 用 100 分制对机会进行评分；
* 只保留超过接受阈值的想法；
* 对重复想法进行去重；
* 生成技能实现计划；
* 创建完整的中英文技能文件夹；
* 审查生成的技能包；
* 在配置完成后发布审查通过的输出；
* 为每次运行生成一份人类可读的技能目录。

最终产物不只是一个想法列表，而是一套判断哪些技能值得构建的生产系统。

## 发布证明

将生成的技能上传到 ClawHub 后，下面的仪表盘截图显示，已发布条目在几天内开始获得可见下载量。

在提供的三张 ClawHub 仪表盘截图中，所有可见卡片合计共有 **1,612 次下载**。

> 该总数根据截图中可见的下载数量计算。统计范围包括截图中展示的可见仪表盘卡片；即使某些已发布条目显示名称相同，也按独立条目分别计入。

![ClawHub dashboard: office and document skills](assets/clawhub-dashboard-office-skills.png)

![ClawHub dashboard: general generated skills](assets/clawhub-dashboard-general-skills.png)

![ClawHub dashboard: renamed and updated skills](assets/clawhub-dashboard-renamed-skills.png)

## 组件概览

SkillFoundry 由十个主要组件组成。

### 1. 来源发现

发现层会扫描能够暴露真实用户需求的公开来源：

* Hacker News：Ask HN 帖子和工具请求；
* GitHub Issues：功能请求、增强请求、Bug 修复请求和实现缺口；
* V2EX、Gitee、掘金、CSDN、OSChina、SegmentFault：适合中国访问环境的开发者和创作者需求信号；
* ClawHub 公开技能列表：已有热门技能模式。

示例：

一个请求 OpenAPI 文档的 GitHub Issue、一条关于审查生成代码的 Hacker News 讨论，以及一个使用量较高的 ClawHub 技能，都可以成为新技能机会的信号。

### 2. 候选需求提取

原始帖子通常噪声很大。SkillFoundry 会筛选听起来像真实待完成任务的短语和模式，例如：

* “I need...”
* “How do I...”
* “Any tool...”
* “Feature request”
* “Recommend...”
* “需求”
* “如何”
* “怎么”
* “有没有”

它会避免纯新闻、招聘帖、广告和一次性公告。

示例：

一个标题为 `test(unit): add tests for db modules` 的 Issue 可以被泛化为更广泛的市场需求：

> 团队需要可重复的帮助，用于为现有代码库添加有价值的单元测试并提升测试覆盖率。

### 3. 证据交叉验证

SkillFoundry 不会根据单个帖子就决定构建技能。每个重要需求都需要多个信号支撑。

默认门槛要求至少有 **3 条独立证据**。系统还会报告该想法获得了多少来源家族的支持，例如 GitHub、Hacker News、V2EX 或 ClawHub。

示例：

`unit-test-coverage-helper` 获得了来自 2 个来源家族的 12 条证据。它被接受了，但因为证据没有覆盖至少 3 个来源家族，所以分数被设置了上限。

### 4. 需求评分

每个需求都会按 100 分制评分：

* **70 分**：需求强度；
* **30 分**：实现可行性。

需求强度会考虑证据数量、来源多样性，以及社区或专业场景信号。实现可行性会考虑该技能能否在普通本地硬件上运行，并能否被表达为实用工作流、检查清单、脚本、模板或小型自动化。

默认实现阈值为 **90/100**。

示例：

一个类似 Skill Vetter 的机会获得了 100/100 分，因为它结合了 ClawHub 的高热度，以及 Hacker News 和 GitHub 中围绕安全、配置和可靠性的证据。

### 5. 去重

需求经常会以不同名称重复出现。SkillFoundry 会在生成技能包之前去除功能相同的想法。

它会使用相似度检查和计划技能名称，只保留最强的代表项。判断依据包括：

* 分数；
* 证据数量；
* 来源多样性；
* 功能独特性。

示例：

如果两个需求最终生成了相同的计划包名，系统只会保留更强的那个。

### 6. 技能规划

被接受的需求会转化为结构化技能计划。

每个计划包含：

* 技能名称；
* 展示名称；
* 目标用户；
* 需求摘要；
* 证据链接；
* 实现工作流；
* 验证检查；
* 预期输出；
* 触发语句；
* 关键词。

这个规划步骤可以让每个生成的技能包都解释清楚：它为什么值得存在。

### 7. 并行生成

SkillFoundry 会以最多 10 个 worker 的并行方式生成多个技能文件夹。

每个生成文件夹包括：

* `SKILL.md`
* `SKILL.zh-CN.md`
* `README.md`
* `README.zh-CN.md`
* `references/requirement-plan.md`
* `agents/openai.yaml`

这些输出可以直接进入审查、目录生成和发布流程。

### 8. 审查

生成完成后，SkillFoundry 会根据对应计划检查每个技能包。

审查内容包括：

* 必需文件；
* frontmatter；
* 命名一致性；
* 必需章节；
* 双语文档；
* 触发示例；
* 需求可追溯性；
* 可选的官方验证脚本。

失败不会被隐藏。它们会写入 `reviews.json`，并在 `SKILLS_CATALOG.md` 中展示。

### 9. 发布

SkillFoundry 可以将审查后的技能发布到 ClawHub，并将运行产物上传到 GitHub。

发布到 ClawHub：

```bash
python scripts/run_skill_demand_agent.py --publish-clawhub
```

发布到 GitHub：

```bash
python scripts/run_skill_demand_agent.py --publish-github-repo Kyro-Ma/<repo-name>
```

发布过程会写入：

* `publish_manifest.json`
* `publish_results.json`

每条结果都会记录成功、失败或跳过状态。

### 10. 目录

每次运行都会生成目录：

```text
SKILLS_CATALOG.md
```

该目录是本次运行的人类可读操作面板。它会列出：

* 已生成技能名称；
* 分数；
* 证据数量；
* 来源覆盖情况；
* 需求；
* 关键词；
* 触发语句；
* 审查状态；
* 文件位置。

这让输出结果更容易检查、分享和改进。

## 示例生成技能

SkillFoundry 已经生成并发布过以下技能：

* `unit-test-coverage-helper`
* `openapi-docs-generator`
* `error-message-improver`
* `product-validation-planner`
* `mobile-responsive-layout-fixer`
* `local-llm-setup-advisor`
* `word-docx-formatting-repair-helper`
* `excel-xlsx-formula-cleanup-helper`
* `powerpoint-pptx-layout-export-helper`
* `workflow-planner-simplifier`

这些不是随机想法。每个技能都来自被发现的需求信号，并通过了评分门槛。

## 快速开始

运行完整流水线：

```bash
python scripts/run_skill_demand_agent.py --max-ideas 10 --max-workers 10
```

运行所有被接受的想法：

```bash
python scripts/run_skill_demand_agent.py --max-ideas 0
```

使用 Office 主题配置：

```bash
python scripts/run_skill_demand_agent.py --theme-profile office --max-ideas 10
```

调整接受门槛：

```bash
python scripts/run_skill_demand_agent.py --score-threshold 90 --min-evidence 3 --max-search-rounds 3
```

## 输出文件

SkillFoundry 会写入：

* `generated_skills/<run-id>/`：生成的技能文件夹；
* `runs/<run-id>/raw_items.json`：发现的原始来源条目；
* `runs/<run-id>/requirements.json`：筛选出的需求；
* `runs/<run-id>/plans.json`：实现计划；
* `runs/<run-id>/reviews.json`：技能包审查结果；
* `runs/<run-id>/SCORING_REPORT.md`：评分决策；
* `runs/<run-id>/publish_manifest.json`：可发布输出；
* `runs/<run-id>/publish_results.json`：发布结果；
* `SKILLS_CATALOG.md`：最新的人类可读目录。

## 为什么它重要

技能创建正在变得越来越便宜。真正困难的问题不再是：

> 我们能不能生成一个技能？

真正困难的问题是：

> 下一个值得构建的技能是什么？

SkillFoundry 用证据回答这个问题。它把社区需求转化为可衡量的流水线，让团队能够以可重复的方式构建用户已经想要的技能。
