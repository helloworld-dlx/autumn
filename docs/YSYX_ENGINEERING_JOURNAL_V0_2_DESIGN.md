# YSYX Engineering Journal V0.2

## Review & Visualization

状态：V0.2A 本地实现完成并经 synthetic fixture 验证；尚未部署 Pi、未读取真实 D1 数据、未启用 Web serving。

V0.1 的目标是“低负担记录真实学习过程”；V0.2 的目标是“快速理解和复盘自己的长期学习轨迹”。它不替代学习、不评价学习表现，也不自动补全课程内容。

## 1. Hard boundaries

- 现有三问 write flow 冻结，不能添加固定的第四个 Git/commit 问题。
- `logs/*.md` 与 `state.json` 仍是 canonical data；`reviews/*.md` 是用户回答 closure review 后的 canonical review artifact。
- Dashboard 永远是由上述文件确定性生成的只读视图，不能回写或成为事实来源。
- 不引入 Database、SQLite、Vector DB、RAG、backend service、React server、cloud sync、streak、生产力评分、掌握度百分比、同周压力比较或 achievement badge。
- 概念、Bug、理解、验证和未解决项必须可追溯到真实 Journal。Dashboard 不读取课程讲义来生成“应该掌握”的知识。
- D6 仍标为 optional；阶段状态只有 `not_started`、`in_progress`、`done`。没有 verified mandatory mapping 时不显示百分比。

## 2. Information architecture

| 页面 | 用户在回答什么 | 仅使用的事实 |
| --- | --- | --- |
| Overview | 我现在做到哪了？ | current stage/substage/task/goal、milestone、聚合时长/天数、未解决项、最后学习日、用户确认 checkpoint、下一 milestone |
| Timeline | 我是怎样走到这里的？ | 每日 log 的日期、substage、时长、完成/理解/Bug/下一步摘要和原日志全文 |
| Review | 某一 substage 当时真正学到了什么、踩了什么坑？ | 该 substage 日志、closure review、验证文字、未解决项、checkpoint suggestion/confirmation |
| Stats | 历史投入和记录分布如何？ | 按 substage/周聚合时长、学习日、concept、Bug、未解决项、用户确认 checkpoint 计数 |

### 2.1 Overview

显示 current stage/substage、current task、current goal / next step、learning days、total time、last learning date、unresolved count、last user-confirmed checkpoint 和 next milestone。D/C 路线只显示三态，例如 `D1 done → D2 in_progress → D3 not_started`。

“last user-confirmed checkpoint” 只来自 `last_manual_git_checkpoint`；suggestion 不是 checkpoint 成功事实。

### 2.2 Timeline

每个 learning day 显示 date、substage、duration，以及“今天完成 / 真正理解 / Bug / 下一步”的短摘要。默认折叠；点击后展示该日志全文。过滤必须是确定性的：substage（D1…C5）、type（all / concept / bug / unresolved）、date range 与 plain-text keyword search。搜索 `mulh` 必须只返回真实文本包含 `mulh`（按明确的大小写无关匹配实现）的记录；不用 embedding。

### 2.3 Review

选择 D1…C5 后，按以下顺序显示：Timeline summary、用户真实记录的 concepts、Bug Casebook、unresolved items、validation/test facts、manual checkpoint records/suggestions。每个条目必须回链到 learning date 和原日志；Bug 只展示已有的现象、定位、原因、修复、验证，缺失字段保持缺失。

### 2.4 Stats

仅显示 learning time by substage、weekly learning time、learning days by substage、recorded concepts 数、Bug cases 数、unresolved count、user-confirmed manual checkpoints。图表是历史回顾，不带排名、目标线、颜色惩罚或绩效结论。

## 3. Substage closure

用户明确说“D1 完成了”等 closure 时，先完成 milestone/state/log 写入；之后的 checkpoint eligibility 是 strong signal，不能被 closure flow 漏掉。推荐 UX：

> D1 已完成。我先记下阶段状态。这也是一个很适合做 manual Git checkpoint 的节点：`checkpoint: complete D1 RV32IM NEMU`。Autumn 当前未连接你的 Linux VM，因此这里只是提醒，你需要在 VM 中手动执行。要不要顺手做一个很短的 D1 阶段复盘？只需回答 2 个问题。

checkpoint 后才邀请、绝不强制 closure review；用户可说稍后再做。默认最多问：

1. D1 最值得留下的 2～3 个收获是什么？
2. 还有什么感觉不牢、以后值得回来看的？
3. 如果重新做一次，这一阶段哪里会做得不一样？（optional）

Autumn 可提示已有日志曾出现的事实，供用户选择，但不能替用户断言“三大收获”。收集完成后生成 `ysyx-learning/reviews/D1-closure.md`：阶段时间（开始、结束、learning days、total time）、最重要收获、仍不牢处、重做一次、关键日志、关键 Bugs、Checkpoint。前两节主要以本次 closure 回答为准；关联条目都带日期链接/引用。未回答的段落留空或不生成，不编造。

## 4. Static generation proposal

建议未来实现一个确定性 builder：

```text
logs/*.md + state.json + reviews/*.md
              ↓
core/pi/helpers/ysyx_dashboard.mjs
              ↓
ysyx-learning/dashboard.html
```

输出一个 self-contained static HTML：内联/打包 CSS、嵌入 derived JSON、无 backend API、无 runtime database、无外部 CDN，离线可用；若成本低，支持 desktop/mobile 与 light/dark。生成器只读 canonical files，解析失败要报告受影响文件，不能修复、覆盖或臆造内容。

在 A（每次 `journal_record` 成功后 rebuild）、B（用户请求 Dashboard 时 rebuild）和 C（两者结合）之间，推荐 **A**：数据规模小、结果立即更新，且 artifact 是 cheap derived data。builder failure 绝不能使 Journal 写入失败：返回“日志已保存，Dashboard 暂未更新”，保留可重试/按需 rebuild 的入口。C 仅在日后证据显示需要 self-healing 时再考虑；不为假想失败增加服务或后台任务。

`dashboard.html` 是 device-local derived artifact，默认不进 Git，也不能写入测试 fixture、开发日志或 GitHub。未来以真实 Pi D1 data 只读验收时，验收脚本/报告仅可输出聚合和必要断言，不能复制原日志正文。

## 5. Production and privacy boundary

V0.2 第一阶段只生成本地 `dashboard.html`，不是公网网站。若用户随后确认会频繁使用，应优先复用已有 Tailscale / private Serve / existing web bridge，在单独 deployment subphase 提供只读 `/ysyx/` 路径；不开放 public internet、不新建 generic file server、不开放 SSH、不从零创建 auth framework。

真实 D1 是未来的只读验收样本：验证 timeline、total time、learning days、日志来源 concepts、Bug、unresolved、D1 done、以及（若 production state 如此）D2 in_progress；不得生成额外课程知识、假进度，或把真实 Journal 写进 Git/fixture/dev log。

## 6. Future generalization / portability

长期可考虑拆分为 `generic journal core + ysyx profile + autumn adapter + other agent adapters`，最终再评估独立 GitHub repo。当前继续留在 Autumn repo：先以真实 YSYX 使用找出真正稳定的 generic boundary，避免过早抽象或迁移。

## 7. Phased implementation and acceptance

推荐小步顺序：

1. **V0.2A**：只实现 dashboard data model、deterministic static builder 和 HTML；用 synthetic fixtures 测试，不读取/写入真实 D1。
2. **V0.2B**：实现 optional stage closure interview、`reviews/*.md` 和 Review page integration。
3. **V0.2C**：Pi 部署、备份和真实 D1 read-only acceptance；只有另行批准时评估 private web access。

成功标准：用户打开 Dashboard 后 30 秒内能回答“我现在做到哪里”“D1 怎么一路完成”“D1 真正理解过什么”“D1 哪些 Bug 值得复习”“下一步做什么”。同时必须保证：不污染 canonical data、不生成假学习事实/进度、不泄露真实日志到 GitHub、Dashboard 损坏可由 canonical files 重建、V0.1 写入流程继续正常。
