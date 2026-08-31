# YSYX Engineering Journal Skill Specification

**中文名：一生一芯工程学习日志**
**状态：V0.1 Core 已批准实现；VM Git integration、生产部署与权限变更仍未批准。**
**课程版本：v24.07**

## 1. Problem Statement

“一生一芯”D/C 阶段是长期、工程导向的学习过程。现有零散笔记难以同时承担真实轨迹回顾、结业复习、官方记录整理、组会素材和 Bug 复盘；反过来，重型日报或打卡系统又会挤占真正写代码、调试和理解的时间。

YSYX Engineering Journal 是 Autumn 中的一个窄域 Skill：用三问访谈收集用户亲自确认的事实，再用确定性文件处理把这些事实保存为 Markdown 与小型 JSON 状态。它不是技术代做器、学习打卡器、通用第二记忆系统，或任意 Git/SSH 通道。

## 2. User Goals

- 低负担记录 D1--D6、C1--C5 的真实学习与调试轨迹。
- 保留 AI-assisted engineering 的协作痕迹，同时不掩盖用户独立完成的核心能力。
- 在需要时从事实日志生成最近两周总结、D/C 复习材料和未来组会素材。
- 清楚显示阶段、当前任务、未解决项及官方 mandatory task 的确定性进度。
- 把一生一芯官方自动 tracing 与用户认可的 Git manual checkpoint 明确区分。

## 3. Non-goals

V0.1 明确不做数据库、Vector DB、embedding、RAG、自动终端截图、命令级录像、streak/打卡压力、云同步、复杂多 Agent、Dashboard、PPT/PDF、官方格式导出或任意远程 shell。

本 Skill 不分析“为何 DiffTest 的 CSR 状态失配”等复杂技术问题；它只保存用户或另一个经授权技术分析流程已经确认的结论。它也不把模型主观估计渲染成 D1 `57%` 一类假精确进度。

## 4. Existing Autumn Compatibility

本设计遵守当前 Autumn 的既有边界：OpenClaw 原生能力优先，Router Lite 不是新服务，Hermes 通路保持冻结，Windows Runner 不允许 raw shell，Git 网络与 destructive Git 均受现有 authority 限制。现有 `deadline-manager` 证明了适合复用的模式：Skill 只约束对话与调用，固定 Node helper 负责 schema 校验、锁、原子写入与机器可读输出。

YSYX 的运行时数据不放入 Autumn 通用 `memory/`：那一层用于近期上下文与稳定偏好，检索/注入规则也不同。学习日志应是独立的、可由用户审阅的业务数据域。仓库仅未来跟踪 Skill/helper 源码与测试；运行时日志、state、生成物和 VM 凭据都保持 device-local、默认不提交。

## 5. Core Integrity Rules

### 5.1 Facts belong to the user

下列结论只能来自用户本人明确陈述，或来自本轮真实、受控工具输出；模型不得补造：实际完成、真正理解、问题现象、Bug 根因、测试 PASS、任务完成状态。

模型可以把口语压缩成书面语、去重、按既有事实分类、补充当前日期/已有 Git 元数据，并在缺少会改变事实含义时只追问一到两个关键问题。模型不得从“改了 MUL”推断“理解了乘法器”，不得把“看起来像”写为“根因已确认”，不得为了模板完整虚构测试、步骤或进度。

### 5.2 Provenance and wording

- 用户确认的事实可直接写入日志，例如“用户确认 `cpu-tests` 中 MUL/MULH 通过”。
- 受控 helper 的只读结果可写入 `Git` 段，并标注为观察值。
- 未确认内容只允许出现在“待确认/未解决”，不可进入“今天完成”“真正理解”或 `done`。
- `not_started`、`in_progress`、`done` 是状态词；除非已导入并验证官方 mandatory 清单，不显示比例或百分比。

## 6. UX / Conversation Flow

Skill 应识别下列自然语言意图：

| 用户意图 | 处理 |
| --- | --- |
| “记录一下一生一芯”“今天 D1 学了两个小时……” | 当日记录流程 |
| “我现在做到哪里了？” | 当前进度 |
| “查看最近学习日志” | 最近日志 |
| “整理最近两周组会内容” | 两周总结 |
| “把 D 阶段复习一下” | D 阶段复习汇总 |
| “把 C 阶段复习一下” | C 阶段复习汇总 |

### 6.1 Daily flow

1. helper 读取 `state.json`，以 Asia/Shanghai 日期确定当天；读取上一条日志的“下一步”，将其作为可编辑默认目标。
2. Autumn 在正常情况下只问三个主要问题：

   1. “今天学了多久？主要做到哪里了？”
   2. “今天最值得以后记住的一个理解、发现或者坑是什么？”
   3. “现在还有什么没解决？下次准备做什么？”

   单条用户消息已覆盖的问题不重复问。
3. 若用户描述了具有复盘价值的 Bug，才追问缺失的关键字段：现象、定位、根因、修复、验证。简单报错、未确认猜测或没有价值的 Bug 不强制五段式。
4. Skill 把用户已确认答案提交给固定 helper。helper 校验日期、分钟数、stage、枚举和 JSON，渲染日志，更新状态与轻量索引。
5. Autumn 自然回报已记录的简短摘要；若存在稳定节点，可另外提出 checkpoint 建议，但绝不在同一请求中自行提交。

日期默认取当前 Asia/Shanghai 日期；用户说“补记 9 月 2 日”时才写指定过去日期。重复日期不静默覆盖：默认加载并更新同日草稿/记录，显示合并摘要；对已存在的用户段落必须显式确认才重写。

### 6.2 Default goal inheritance

上一学习日的非空“下一步”会成为下一学习日的 `目标` 默认建议，例如“继续实现 DIV。”。它只是可编辑提示；用户改写、取消或说“今天换做 ELF”时以用户当前事实为准。没有上一条下一步时不编造目标。

### 6.3 Read and synthesis flows

- **当前进度**：展示 current stage/task/goal、D/C milestone 状态、已验证 mandatory 的确定性计数、未解决项、最近学习日和最近 manual checkpoint。
- **最近日志**：默认列最近 10 条，日期、阶段、时长、完成摘要、下一步；按请求打开单日全文。
- **两周总结**：以今天（或用户指定截止日）向前含当日的 14 个自然日为窗口；只聚合已有日志中的时长、完成事实、概念、Bug、开放项、checkpoint。没有学习日只写“该窗口无记录”，不制造连续性评价。
- **D/C 复习**：按对应阶段筛选事实，输出概念、已确认问题案例、测试/验证事实、mandatory 进度和仍开放项；不能把未记录内容补成讲义。

## 7. Example Conversation A -- Ordinary Learning Day

> Autumn：上次下一步是“继续实现 RV32IM 指令”。今天学了多久？主要做到哪里了？
>
> 用户：1 小时 45 分，继续写 NEMU 的 RV32M，MUL、MULH、MULHSU 都实现了，cpu-tests 这些用例过了。
>
> Autumn：今天最值得以后记住的一个理解、发现或者坑是什么？
>
> 用户：高半部分不是拿低 32 位右移，得按有符号/无符号把 64 位乘积先算对再取高位。
>
> Autumn：现在还有什么没解决？下次准备做什么？
>
> 用户：DIV 还没开始，下次继续实现 DIV。
>
> Autumn：记下了：D1，1h45min；MUL/MULH/MULHSU 的已确认实现与测试结果，以及高半乘法的理解。下次默认目标是“继续实现 DIV”。

生成的日志：

```markdown
# 2026-09-02｜D1｜1h45min

## 目标

继续实现 RV32IM 指令。

## 今天完成

- 实现 NEMU 的 RV32M：MUL、MULH、MULHSU。
- 用户确认：上述 cpu-tests 用例通过。

## 今天真正理解的东西

高半乘法不能通过低 32 位结果右移得到；应先按有符号/无符号语义得到正确的 64 位乘积，再取高位。

## 遇到的问题


## Git

- branch: （未查询）
- 当前状态: （未查询）
- manual checkpoint: （未查询）
- recent trace: （未查询）

## 下一步

继续实现 DIV。
```

## 8. Example Conversation B -- Important Bug and Checkpoint

> Autumn：今天学了多久？主要做到哪里了？
>
> 用户：2 小时 20 分，D1 的 DIV/DIVU 已完成，cpu-tests 都过了。
>
> Autumn：最值得记住的理解或坑是什么？
>
> 用户：一开始把负数除法按 C 的 unsigned 算了，RISC-V 的 DIV 要按有符号语义，余数符号也跟被除数。
>
> Autumn：这个 Bug 值得复盘。我只补问五点：现象、怎么定位、确认的根因、修复、如何验证？
>
> 用户：`div-test` 的负数 case 错；对照参考结果和指令语义定位；根因就是扩展前用了 uint32_t；改成先 sign-extend 到 int64_t；负数和除零的 `cpu-tests` 都过了。
>
> Autumn：现在还有什么没解决？下次准备做什么？
>
> 用户：暂时没有，准备整理 RV32M 再进下一块。
>
> Autumn：已记录。只读 Git 信息显示当前工作树有这次实现的改动，最近 manual checkpoint 之前没有新的稳定提交。DIV/DIVU 已由你确认通过，适合作为稳定节点。建议：
>
> `checkpoint: D1 RV32M DIV and DIVU cpu-tests pass`
>
> 将暂存这次列出的文件并创建该 checkpoint。是否提交？
>
> 用户：提交。
>
> Autumn：仅在此第二轮明确确认后调用 `ysyx_git_checkpoint`；成功结果才写入 state 的 `last_manual_git_checkpoint`。失败则如实报告，不称已保存。

生成的日志（Git 段仅在 helper 成功读到或提交到后填入）：

```markdown
# 2026-09-04｜D1｜2h20min

## 目标

继续实现 DIV。

## 今天完成

- 完成 DIV、DIVU。
- 用户确认：相关 cpu-tests 通过，包含负数与除零用例。

## 今天真正理解的东西

DIV 使用有符号语义；余数符号跟随被除数，不能把负数路径按 unsigned 处理。

## 遇到的问题

### div-test 负数 case 错

现象：`div-test` 的负数 case 错。

定位：对照参考结果与指令语义。

原因：确认在扩展前使用了 `uint32_t`。

修复：先 sign-extend 到 `int64_t` 后执行有符号除法路径。

验证：用户确认负数与除零的 cpu-tests 通过。

## Git

- branch: `pa0`（helper 观察值）
- 当前状态: 已由 helper 在建议时读取；具体文件仅在确认界面展示。
- manual checkpoint: `abc1234 checkpoint: D1 RV32M DIV and DIVU cpu-tests pass`（仅 checkpoint 成功后写入）
- recent trace: `unavailable`（未验证官方 tracing provider）

## 下一步

整理 RV32M，再进入下一块。
```

## 9. Markdown Log Schema

路径为 `ysyx-learning/logs/YYYY-MM-DD.md`，编码 UTF-8、LF 换行、每个日期一个文件。固定标题与二级段落使 helper 可确定性解析；正文保持用户可读，而不是把原始会话或模型思考写入文件。

必需段落为 `目标`、`今天完成`、`今天真正理解的东西`、`遇到的问题`、`Git`、`下一步`。内容可为空：无重要 Bug 时“遇到的问题”留空或一句短说明；没有 Git 查询也只写“未查询”。禁止为了填满字段补内容。

Bug 小节仅在用户确认其价值和事实后出现，结构为 `### 标题`、`现象`、`定位`、`原因`、`修复`、`验证`。缺失字段直接省略或写“尚未确认”，绝不由模型补全。

日志元信息不使用会污染正文的 AI 过程记录。运行时 state 保存“来源为用户/工具”的最小标记；日后若需要导出可追溯性，再单独设计，不在 V0.1 加哈希或事件日志。

## 10. state.json Schema

运行时 canonical 状态位于 `ysyx-learning/state.json`。数字用整数分钟存储，展示时由 helper 格式化为小时/分钟；因此不会因浮点数产生不一致。未知字段拒绝，升级只能通过显式 `schema_version` migration。

```json
{
  "schema_version": 1,
  "course_version": "v24.07",
  "timezone": "Asia/Shanghai",
  "current_stage": "D",
  "current_substage": "D1",
  "current_task": "RV32IM NEMU",
  "current_goal": "继续实现 DIV。",
  "last_learning_date": "2026-09-02",
  "total_learning_days": 1,
  "total_learning_minutes": 105,
  "milestones": {
    "D1": { "label": "支持RV32IM的NEMU", "status": "in_progress" },
    "D2": { "label": "程序的机器级表示", "status": "not_started" },
    "D3": { "label": "AM运行时环境", "status": "not_started" },
    "D4": { "label": "用RTL实现迷你RISC-V处理器", "status": "not_started" },
    "D5": { "label": "设备和输入输出", "status": "not_started" },
    "D6": { "label": "D阶段流片准备（optional）", "status": "not_started" },
    "C1": { "label": "工具和基础设施", "status": "not_started" },
    "C2": { "label": "支持RV32E的单周期NPC", "status": "not_started" },
    "C3": { "label": "调试技巧", "status": "not_started" },
    "C4": { "label": "ELF文件和链接", "status": "not_started" },
    "C5": { "label": "异常处理和RT-Thread", "status": "not_started" }
  },
  "official_mandatory_task_mapping": {
    "source_status": "unverified",
    "source_name": null,
    "source_reference": null,
    "imported_at": null,
    "items": []
  },
  "last_manual_git_checkpoint": null,
  "unresolved_items": [],
  "indexes": { "tags": {}, "concepts": {}, "bugs": {} }
}
```

`status` 只能为 `not_started`、`in_progress`、`done`。变更为 `done` 必须来自用户明确完成声明或已验证的 official mandatory item，不能由连续日志次数推断。`official_mandatory_task_mapping.items` 的正式结构为 `{id, substage, title, mandatory, status, evidence_log_dates}`；只有 `source_status=verified` 且 `mandatory=true` 时才显示 `done/total`。当前官方清单与 tracing 的具体语义尚未核验，初始状态必须是 `unverified`。

`indexes` 仅是 V0.1 的小型反向索引：键为用户认可或从其原话做保守归一化的标签，值为日期数组；例如 `"div": ["2026-09-04"]`。它不是 embedding、知识图谱或“模型推测薄弱点”。

helper 对写入使用单目录锁、完整 schema 校验、同目录临时文件加 rename 的原子替换，沿用现有 Agenda 习惯。日志与 state 是两个文件，不能伪称跨文件事务：任一步失败即返回失败、不称记录成功；下次读取应检测日期/累计数不一致并要求确定性 reconcile，而不是靠模型猜补。

## 11. D/C Progress Model

阶段路线锁定为一生一芯 **v24.07** 的 D1--D6 与 C1--C5；不得按其他课程版本重命名或补任务。D6 必须显式标记“可选”，不以未完成 D6 阻塞 D 阶段必修结论，直到用户提供官方规则。

进度展示优先级：

1. milestone 状态；
2. 当前任务与下一目标；
3. 已验证 mandatory 的 `completed / total`；
4. 仍开放的问题。

当官方 mandatory 清单未确认，界面应写“官方 mandatory mapping：未导入/未验证”，而非为每阶段塞假百分比。导入必须记录来源名、版本/链接或用户提供文件标识、导入时间与逐项状态；Skill 不能从课程标题自行生成任务清单。

## 12. Skill Responsibilities

Skill 负责意图识别、三问访谈、最小必要追问、事实级文字整理、调用固定 helper、展示结果与 checkpoint 建议。它只能向 helper 传递结构化字段，不能直接编辑 `state.json` 或日志，也不能直接调用任意 Git/SSH 命令。

内部 helper（批准后才实现）应提供固定动作：`journal_context`、`journal_record`、`journal_progress`、`journal_recent`、`journal_summary`、`journal_review`。所有输入有严格 schema，所有输出为小型 JSON；总结和复习由 helper 确定性筛选日志，模型只负责把已选事实压缩为用户可读文本。

## 13. Codex vs Autumn Responsibilities

| 责任 | Codex | Autumn |
| --- | --- | --- |
| Skill/helper/测试/HTML | 开发、维护、静态与单元测试 | 调用已部署版本 |
| 每日交互 | 不替用户填写事实 | 三问、必要追问、整理与确认表达 |
| 日志与状态 | 实现确定性校验/落盘 | 提交用户事实给 helper |
| Git helper | 实现协议、安全测试、维护固定 allowlist | 只读查询、建议 checkpoint、二次确认后调用 |
| 技术难题 | 可在用户授权的独立任务中协助分析 | 不把分析猜测写进 Journal |
| 复习/组会素材 | 实现确定性筛选和格式 | 按用户请求生成与交付 |

当前主要模型可能为 MiniMax M2.7，因此 Skill Prompt 必须使用有限状态、固定问题、固定字段、明确的“不知道就留空”、严格 JSON helper 输入和少量示例；不要求模型规划复杂工作流或判断技术真伪。

## 14. Git Tracing vs Manual Checkpoint

官方 auto tracing 是一生一芯开发过程的黑匣子，属于观察数据；manual checkpoint 是用户明确认可的稳定版本，属于用户意志动作。二者不能互相替代，不能用“有自动 tracing”推断“已 checkpoint”，也不能把 checkpoint 称为官方课程要求。

建议 checkpoint 的稳定节点包括：一条/一组指令测试通过、一个模块完成且验证通过、重要 Bug 修复并回归、重构前、进入新 PA 阶段前，或当天结束且代码稳定。编译成功但测试仍失败、按时长间隔、仅改动行数都不是建议理由。

建议格式为：`checkpoint: D1 RV32M multiply instructions pass cpu-tests`。它只是本项目约定。message 必须单行、长度受限、无控制字符；checkpoint 成功前不得写入 `last_manual_git_checkpoint`。

一生一芯 v24.07 / PA 已知机制是：成功编译后的 development tracing 会记录代码变化，官方读取命令为 `git log tracer-ysyx`。bug-free / stable 状态仍建议用户自行 local manual commit；官方建议流程为 `git add .` 后 `git commit --allow-empty`。但用户实际 VM 仓库中 `tracer-ysyx` 是否存在、是否正常工作，以及 author/branch/worktree 的具体行为仍须只读 recon 验证。不得把普通 `git log` 冒充 tracer-ysyx。

V0.1 provider 默认仍为 `unavailable`，在真实 VM integration 单独批准前不执行任何命令。

## 15. ysyx-git-helper API Proposal

该 helper 必须在 VM 内拥有唯一固定的已配置仓库根，不接受 repo path、shell、environment、remote、refspec 或任意命令。所有进程使用 argv 数组和 `shell=false`。Pi/Windows/VM transport 只可传递以下 JSON 协议。

### 15.1 `ysyx_git_status`

请求：`{}`。响应包含固定 repo 的 display path、branch、bounded working-tree 文件状态、`last_manual_checkpoint`、recent commits 和 `recent_tracing_activity`。status 不读取文件内容、不执行网络、不修改索引或工作树。

### 15.2 `ysyx_git_recent`

请求：`{"limit": 1..20}`。只返回受限字段的最近 commit/trace 元数据。没有已验证 tracing provider 时明确返回其不可用状态。

### 15.3 `ysyx_git_checkpoint`

checkpoint 分为两个明确 mode，且都必须先 `checkpoint_preview`、绑定短 TTL `confirmation_id` 与 tree fingerprint、再等待用户下一轮明确确认：

- `mark_current_state`：auto tracing 已记录代码时的稳定人工标记。paths 必须为空，只允许固定 `git commit --allow-empty -m <validated message>`；不执行 `git add`。
- `commit_changes`：仍有需要纳入 checkpoint 的明确工作树修改。paths 必须为经过 preview 的安全相对路径，只允许 `git add -- <paths>` 后 `git commit -m <validated message>`。

`commit_changes` 请求：

```json
{
  "confirmation_id": "one-time server-issued id",
  "message": "checkpoint: D1 RV32M DIV and DIVU cpu-tests pass",
  "mode": "commit_changes",
  "paths": ["nemu/src/isa/riscv32/inst.c"],
  "tree_fingerprint": "preview-bound value"
}
```

`confirmation_id` 由前一轮 `checkpoint_preview` 产生，短 TTL、单次消费，并绑定 message、paths 与当前 tree fingerprint。preview 必须把待暂存路径、状态摘要和建议 message 展示给用户；只有用户下一条明确“提交”才允许 Autumn 发送此请求。

helper 只执行对应 mode 的固定 argv。`paths` 不允许绝对路径、`..`、`.git`、NUL、glob 或 path escape；`commit_changes` 默认拒绝删除、重命名、typechange、子模块与 symlink 边界。需要这些特殊变更时 V0.1 应报告“请在 VM 内手工处理”，不扩权。`mark_current_state` 是唯一允许空 manual marker 的 mode，不能被模型偷偷切换。

显式禁止 `rm`、`reset --hard`、`clean`、`rebase`、`push --force`、`pull`、`fetch`、`clone`、任意 shell、任意路径、hooks bypass、config 覆盖和外网 Git。提交身份沿用 VM 已有 Git 配置，helper 不读取/返回凭据。

## 16. VM Connectivity Options and Security Analysis

| 方案 | 优点 | 主要风险/限制 | 结论 |
| --- | --- | --- | --- |
| VM 内固定 helper + 主机受控调用 | 最小协议、固定仓库、可经现有 Pi Bridge/Windows Runner 逐层授权；不需要通用远程登录 | 必须先核验 hypervisor 的 host-only 通道与认证 | **推荐目标架构** |
| SSH restricted command | Linux 原生、可远程调用；可用 forced-command key 限制为 helper | key 生命周期、端口暴露、转发/TTY/环境逃逸配置错误风险；仍须先验收 | 仅作为核验后备选 |
| 共享目录 + VM watcher/helper | 不需入站网络 | 请求重放、文件竞争、权限/路径混淆、延迟与 stale response 处理复杂 | 不推荐 V0.1 |
| 用户在 VM 内手动运行固定 helper | 权限最小、零新增网络攻击面 | 自动化低，需复制状态/确认 | **V0.1 连通性未核验时的安全降级** |

推荐链路为：`Autumn Skill → 受限 Pi Bridge action → 受限 Windows connector → host-only VM helper RPC → fixed Git argv`。VM helper 仅绑定 host-only interface 或等效 guest channel，使用双向认证、request nonce、短 TTL、重放保护和固定 JSON schema；Windows connector 也只允许三种 API 动作，不提供 `ssh`、`powershell` 或 guest command 参数。所有新 transport、端口、密钥保存位置和 hypervisor 机制都必须在批准后的只读 recon 后再定。

若 host-only 通道不可用，优先保持手动模式；不要为了自动化开放通用 SSH。SSH 备选只有在 forced command、禁用 TTY/转发/agent forwarding、固定用户与固定 helper、独立受限 key、审计和负向测试均通过后才可考虑。

## 17. Recommended Architecture and File Layout

运行时（Pi OpenClaw workspace，非本仓库、默认私有且不自动 Git 同步）：

```text
ysyx-learning/
├── state.json
├── logs/
│   └── YYYY-MM-DD.md
├── reviews/
├── meetings/
└── dashboard.html              # V0.2 以后才出现
```

未来源码位置遵循现有仓库布局：`core/pi/skills/ysyx-engineering-journal/SKILL.md`、`core/pi/helpers/ysyx_journal.mjs`、对应测试；Git adapter 放在独立的、按最终运行节点决定的受限目录。V0.1 不创建这些文件。本次只新增本 Spec，路径按用户要求采用 `docs/YSYX_ENGINEERING_JOURNAL_SPEC.md`，而非放入 `docs/current/` 或 `docs/architecture/`，因为它尚不是 Autumn 当前真相或冻结架构契约。

## 18. Version Boundaries

### V0.1

Skill、三问、Markdown、state.json、D/C milestone、Git status/checkpoint 建议与二次确认协议、两周总结、D/C 复习汇总。输出可按用户请求存为带日期的 `meetings/` 或 `reviews/` 文件，默认不覆盖既有用户生成物。

### V0.2

`dashboard.html`：四个简单页面（首页、进度、日志、复习），Timeline、D/C 路线、总时长、Bug/概念/任务过滤与 checkpoint 可视化。它只读取现有 JSON/Markdown，不引入数据库或生产力套件。

### V0.3

官方学习记录格式导出、2--4 页组会 PPT 草稿数据、D/C 结业考核模式、Mandatory Questions 索引，以及按需生成 `reviews/D-stage-review.md` 与 `reviews/C-stage-review.md`。这些是明确延期项目，不反向膨胀 V0.1。

## 19. Future Dashboard Direction

首页只显示当前 D/C 阶段、当前任务、学习日、总时长、最近记录、最近 checkpoint、下一里程碑。进度页列 D1--D6/C1--C5 的三态；日志页按日期 Timeline 并可按 stage/bug/concept 过滤；复习页聚合核心概念、Bug、mandatory、薄弱点（仅用户明确标注）和 checkpoint。禁止虚假进度、连续打卡压力及复杂工作台。

## 20. Acceptance Criteria for the Future Implementation

- 三问可创建普通日记录；无 Bug 时不出现伪造的 Bug 五段式。
- 用户未提供的理解、根因、PASS、完成状态不写入日志或 state。
- 下一日默认目标准确继承上一日志“下一步”，且可被用户覆盖。
- 时长、学习日和最近日期由 helper 确定性计算；重复日期与写入失败不静默覆盖或假报成功。
- milestone 只用三态；mandatory 比例仅来自已验证 mapping。
- 最近两周、D/C 复习的每项事实可追溯到日志日期；无记录时诚实为空。
- status/recent 不改变 VM 仓库；checkpoint 没有第二轮明确确认、expired/replayed confirmation、tree 改变或参数不匹配时必须拒绝。
- Git helper 的负向测试覆盖路径逃逸、`.git`、额外字段、换行 message、删除/重命名、网络 Git、shell 注入、重放、`mark_current_state` 与 `commit_changes` 的 mode 绑定。
- 不修改 Hermes、现有 Router、Runner 通用 Git policy、生产配置、SSH 或 Dashboard，除非后续单独授权。

## 21. Risks and Open Questions

1. 一生一芯 VM 的 hypervisor、host-only 网络、固定 repo path、Git worktree 布局和可用 guest channel尚未确认。
2. 官方 auto tracing 的真实来源、读取方式、隐私边界与是否会受 manual commit 影响尚未确认；不能猜。
3. D/C 官方 mandatory task 清单、D6 的结业地位、官方学习记录格式和 Mandatory Questions 来源尚未确认。
4. 需要用户确认运行时日志保留位置、备份策略及未来官方导出是否允许包含具体代码路径/commit hash。
5. Git checkpoint 若触发 Git hooks 或课程工具副作用，helper 必须先只读调查并默认保留 hook；禁止用 `--no-verify` 绕过。

## 22. Implementation Plan After Approval

1. **只读 recon**：确认 VM 连接能力、固定 repo 根、Git/trace 行为、mandatory 来源与现有运行时 workspace；不创建 key、不开放端口、不改仓库。
2. **本地实现**：新增 Skill、固定 journal helper、schema/lock/atomic-write 与 unit tests；先用临时 fixture，不接生产。
3. **Git adapter design verification**：在 VM fixture 或用户批准的测试 repo 验证 status/recent/preview/confirmation/negative cases；决定 host-only 或手动模式。
4. **受控部署与验收**：按 Autumn 既有流程备份、最小同步、静态测试和极少量真实 smoke；只在用户另行授权后执行。
5. **停止点**：V0.1 验收后停止；Dashboard、PPT、官方导出和任何扩权均另行批准。
