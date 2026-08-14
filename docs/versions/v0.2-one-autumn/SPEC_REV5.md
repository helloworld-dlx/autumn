AUTUMN

V0.2 · One Autumn

项目说明书 · Rev5

I can handle it.

| 版本 | Autumn V0.2 · One Autumn · Rev5 |

| --- | --- |

| 状态 | IMPLEMENTATION BASELINE / REPAIR A FROZEN / PHASE 2B-1 AUDIT STARTED / VOICE SCOPE UPDATED |

| 更新时间 | 2026-08-10 |

本文件面向实施与长期迭代；Rev5 在 Rev4 基线上正式提升 Phase 2C Portable Voice：Continuous Voice 成为 P0，Quick Voice 作为同一语音栈的单轮 fast path 保留；V0.3 继续承担 Wake Word、自然打断与 Voice/Eyes/Worker 融合。本次不重新裁决 Repair A/B，不包含真实 Token、HMAC Key、Feishu Secret 或私聊正文。

# 1. 版本定位

| 正式目标V0.2 不再追求“增加更多按钮”，而是让 D老师只面对一个 Autumn。Autumn 自己负责判断：亲自处理、调用 Hermes、交给 Direct Worker、OpenCode，还是 Codex。 |

| --- |

V0.1 已经证明 Pi 5 中枢、OpenClaw、飞书、Tailscale、Windows Runner、文件回传、Cron/Web 与白名单程序链路可稳定日用。V0.2 的任务是把这些“能用的零件”组织成一个统一的个人助手体验。

| 版本 | 主句 | 核心跃迁 | 一句话能力 | 状态 |

| --- | --- | --- | --- | --- |

| V0.1 · Afterglow | I can act. | 执行闭环 | 自然语言 → 工具 → 真实执行 → 飞书返回 | 已冻结 |

| V0.2 · One Autumn | I can handle it. | 统一调度 | 一个入口，自动选择 Hermes / Worker / OpenCode / Codex | 当前实施 |

| V0.3 · Presence | I am here. | 存在与感知 | 统一 Node、语音、视觉、Home/Dorm、专属控制端 | 规划 |

| V0.4 · Forge | I can build it. | 创造闭环 | EDA/FPGA/软件/实物实验室自动协作 | 预研 |

# 2. 已批准范围与当前进度

| 阶段 | 名称 | 状态 | 核心结果 |

| --- | --- | --- | --- |

| 2A | One Autumn | IN PROGRESS | Autumn ↔ Hermes；当前已推进至 Phase 2A-1B；Repair A 已 PASS / FROZEN |

| 2A-T | Token Hygiene Interlude | DEFERRED / REQUIRED | Phase 2A Final Acceptance + Freeze 后继续 Repair B；不阻塞当前 2A，原则上在 2B 扩张前完成 |

| 2B | Autumn Worker | IN PROGRESS / 2B-1 READ-ONLY AUDIT | 已进入 2B-1 只读审计；2B-2 next。General Worker + OpenCode + Codex + Authority Levels 继续按专项实施记录推进。 |

| 2C | Portable Companion Lite | PLANNED / VOICE P0 UPDATED | 手机轻联动；Continuous Voice P0（含 Quick Voice 单轮 fast path）；主动通知；不做完整原生 App。 |

当前执行点（2026-08-10）：已开始 Phase 2B-1 只读审计，下一步为 2B-2。本 Rev5 仅记录该执行位置；Phase 2A 与 Repair B 的最终验收状态仍以各自专项记录为准，不在本次 Voice 范围更新中反推或重裁决。

| 阶段纪律当前 Repair A frozen baseline：Autumn main = MiniMax-M2.7；Hermes default = MiniMax-M2.7；fallback=[]；DeepSeek V4 Flash 仅手动选择。Phase 2A 主线期间不为了省额度或追求峰值质量反复切 provider / fallback / subagent 模型。Repair B 保持 DEFERRED，不阻塞 2A。每次只改变一个关键变量。 |

| --- |

# 3. 核心架构：One Autumn

| D老师                           │                        Autumn                  唯一人格 / 默认入口                           │          ┌────────────────┼────────────────┐          │                │                │   OpenClaw Core      Hermes Core      Worker Router 工具/执行/调度       私人连续性            │ Web/Cron/Skills      深层陪伴               │          │                │        ┌───────┼────────┐          │                │      Direct  OpenCode  Codex          └────── Autumn 统一组织最终体验 ────┘ |

| --- |

Autumn 不是“等于 OpenClaw” ：OpenClaw 是主要运行核心，但 Autumn 是最上层统一身份、路由和体验。

Hermes 不被合并 ：保留自身 SOUL、memory 与独立飞书入口；V0.2 只建立受控的 Consult / Session 通路。

用户不用做路由 ：正常情况下只找 Autumn；只有用户明确要求或安全/隐私有必要时才暴露底层去向。

# 4. Phase 2A — One Autumn

## 4.1 Hermes Consult

Autumn 对情绪、私人连续性、长期关系背景等问题，可向 Hermes 发起单次咨询。

默认只传当前请求和“完成本次任务所需的最小上下文”；不把 Autumn 工作日志、项目文件或整段历史自动同步给 Hermes。

Hermes 返回建议后，默认由 Autumn 继续当前对话，用户不需要切换聊天窗口。

## 4.2 Hermes Session

用户明确希望深入聊时，可在 Autumn 入口进入临时 Hermes Session。

Session 结束后回到 Autumn；原 Hermes 私聊继续作为独立、私密、备用入口。

不得为了“统一入口”删除 Hermes 的独立人格和记忆优势。

## 4.3 Continuity Lite + Commitment Memory

| 记忆类型 | V0.2 处理方式 | 例子 |

| --- | --- | --- |

| 稳定记忆 | 沿用 workspace / OpenClaw / Hermes 各自长期信息 | 设备、偏好、长期规则 |

| Active Context | 只保留近期正在推进的事情 | PA、FPGA、Autumn 当前 Phase |

| Commitment Memory | 专门记录 Autumn 已承诺要跟进的事项 | “Codex 做完告诉我”“回学校再继续” |

| Hermes 私人记忆 | 仍由 Hermes 管理，不批量复制 | 私人连续性、情感历史 |

| 从 Amy-JARVIS 借鉴之一：Commitment / persistent daemon 思想Autumn 不只“记住事实”，还要记住自己答应了什么、哪些后台任务在等待、哪些事项需要在条件满足后回来找用户。V0.2 只做轻量实现，不建设复杂人生数据库。 |

| --- |

# 5. Phase 2B — Autumn Worker

| 核心变化从“一种能力写一个白名单程序”升级为“通用 Job 原语 + 智能 Worker”。不再为 7-Zip、Python、Node、Everything、OpenCode、Codex 各写一套独立业务系统。 |

| --- |

| Autumn Worker├── Direct Process Worker│   ├── Python / Node / Git / Everything / 7-Zip│   └── 普通已安装程序├── OpenCode Worker│   └── 中等智能任务 / 高频 Agent Loop└── Codex Worker    └── 高价值、复杂、长程任务统一 Job：submit → status → cancel → result |

| --- |

## 5.1 General Worker 最小接口

| 字段 | 目的 | 原则 |

| --- | --- | --- |

| executable | 直接启动可执行程序 | 优先 CreateProcess，不拼接任意 cmd 字符串 |

| arguments | 结构化参数 | 记录原始参数；执行前做风险判断 |

| cwd | 工作目录 | 必须落在授权任务范围 |

| timeout | 最长执行时间 | 超时可取消并返回状态 |

| write_scope | 允许写入范围 | D盘可读；写入按任务级授权 |

| network_policy | 联网策略 | Codex/OpenCode 可按任务配置 |

| risk_level | 权限等级 | 由运行时 Authority Engine 强制，不依赖模型自觉 |

## 5.2 Authority Levels（Amy-JARVIS 重点借鉴）

| 级别 | 典型行为 | 默认策略 |

| --- | --- | --- |

| L0 · Query | 状态、只读信息 | AUTO |

| L1 · Read/Open | 读文件、打开本地资源 | AUTO / 低风险 |

| L2 · Create/Process | 创建输出、运行普通程序 | 任务上下文决定，通常 AUTO |

| L3 · Workspace Write | 修改授权项目/工作区 | 任务开始时一次确认 |

| L4 · External Effect | 外部发送、联网产生副作用 | 每次明确确认 |

| L5 · System/Admin | 管理员、系统级设置 | 默认 DENY |

| Hard Deny | 删除类动作 | V0.2 继续不提供 |

执行权限由 Runner/Worker 运行时强制，而不是只写在 AGENTS.md 里。

新增 Emergency Stop：停止活动 Worker / Codex / OpenCode Job，并将新任务置为暂停。

任务授权尽量“一次授权一个范围”，减少 Codex 每一步都询问。

如果需要强保证“禁止删除”，必须依赖 sandbox / OS 文件权限 / 受限账户等运行时边界，而不是过滤 del/rm 字符串。

## 5.3 AI 资源与成本路由

| 模块 | 默认资源 | 升级/回退 | 设计理由 |

| --- | --- | --- | --- |

| Autumn 主 Agent | MiniMax-M2.7 | 规则触发 MiniMax-M3 Planner；无自动厂商 fallback | M2.7 负责日常理解、工具执行与统一回复；M3 留给真正复杂的规划/重规划 |

| Hermes 默认 | MiniMax-M2.7 | 复杂 Consult 可显式 M3；2A 后再 A/B M2-her | 优先发挥 Hermes 自身持久记忆与陪伴优势，不把“陪伴”简单等同于长期 M3 |

| M3 Planner | MiniMax-M3（按规则显式启动） | 正常每任务最多 1 次规划 + 真实冲突后 1 次 replan | 作为高级分析/风险判断资源，不承担所有日常工具点击 |

| Direct Worker | 不调用 LLM | — | 状态、压缩、确定性转换等动作不烧 token |

| OpenCode（2B 计划） | GPT-5.6 Luna（Plus）优先试用 | DeepSeek V4 Flash / Pro 手动或规则型备用 | 承担高频中档智能任务，避免继续占用 MiniMax 5h 池 |

| Codex（2B 计划） | GPT-5.6 Sol / Codex CLI | — | 高智商、高价值、长程工程任务 |

| 规划/架构 | GPT-5.6 Sol | — | 高智商决策优先交 GPT；不占 Autumn 常驻额度 |

| MiniMax 套餐与主模型裁决保留老用户 ¥29 套餐，不因 V0.2 开发期高负载立即升级。Repair A 已把 Autumn/Hermes 默认切至 M2.7；M3 仍允许，但作为规则触发的高级规划资源。先完成 2A，再观察 3–7 天真实日用：若 M2.7 路由/工具选择频繁需要纠正，或 M3 升级率过高，再重新评估默认模型与套餐。升级前应先确认老用户 ¥29 档能否恢复。 |

| --- |

## 5.4 OpenCode 与 Codex 分工

| 任务 | 优先 Worker |

| --- | --- |

| 压缩、打开程序、确定性转换 | Direct |

| 整理文件副本、普通脚本、小型修改 | OpenCode |

| 普通 Coding / 数据处理，需要自主迭代但成本敏感 | OpenCode |

| 核心仓库审查、复杂 Debug、大型修改 | Codex |

| Autumn Runner/Bridge 核心安全改动 | Codex + GPT 规划 |

Clash Verge 作为 Codex Worker 的基础运行环境：Worker 启动前检查代理可用性，可在用户批准后自动启动 Clash Verge；不自动改节点、订阅、规则或代理配置。

# 6. Phase 2C — Portable Companion Lite

主力设备：Xiaomi 15（Android）。优先 Tasker / PWA / 飞书现有能力，不开发原生 App。

V0.1 已完成 Windows → Feishu → 手机文件链路；V0.2 2C 重点新增快捷入口、Portable Continuous Voice（含 Quick Voice fast path）、打开 App/URL、剪贴板和有限通知。

手机只做 Soft Node：不开放短信、支付、全部通知、后台持续录音、持续 GPS 或 Shizuku/ADB 全权 Shell。

Portable Voice 的主形态升级为 Short Continuous Voice Session：一次显式触发后可连续多轮与 Autumn 对话，无需每轮重新按键；单轮 Quick Voice 作为同一语音栈的快速入口继续保留。

| 手机能力 | V0.2 |

| --- | --- |

| 电脑文件推手机 | READY（沿用飞书） |

| 手机文件/图片发 Autumn | 优先验证飞书附件链路 |

| 快捷呼叫 Autumn | P0 |

| Portable Voice | P0：Continuous Voice 为主；Quick Voice 单轮 fast path 同栈保留 |

| 打开 App / URL | P1 |

| 写剪贴板 | P1 |

| 深度 Accessibility 控制 | 不进 V0.2 |

| 全天摄像头/麦克风 | 不进 V0.2 |

## 6.1 Continuous Voice Pilot（P0）

一次显式触发（手机快捷键、按钮或耳机入口）后进入 Short Continuous Voice Session；最低验收为连续 3–5 轮，无需每轮重新触发。

同一 Voice Session 复用同一 Autumn 对话上下文；静默超时、手动 Stop 或明确结束语后退出，并清楚显示 listening / speaking / off 状态。

保留 Quick Voice 单轮 fast path：适合提醒、简短命令、公共场景或用户只想说一句的情况。Quick Voice 与 Continuous Voice 共用同一入口、会话栈与安全边界，不建设第二套语音架构。

V0.2 不把 Wake Word、后台常驻 Ambient Mic、自然 barge-in、Windows Screen、Voice + Worker/Eyes 并行融合列为 2C 完成门槛；这些属于 V0.3 Presence。

Voice 层优先保持 VAD / STT / Autumn Core / TTS 可分离，避免为了语音改变 Repair A 的 M2.7 主脑与模型路由；具体供应商、流式协议与成本方案在 2C Voice ADR 中裁决。

产品优先级：连续自然对话 > 单轮语音快捷输入 > Voice 与后台 Worker/视觉的并行协作。

# 7. 主动性：Bounded Initiative

| 原则存在感不等于不停发消息。V0.2 只对“用户行动会因此改变”的事件主动出现。 |

| --- |

Codex/OpenCode/Worker 完成或失败。

用户明确要求“做完告诉我”的 Commitment。

Deadline / Reminder 到点。

Windows 恢复上线，而此前有未完成、需重新确认的任务。

Morning / Evening Brief 属于 P2，可在 V0.2 后期小范围验证，默认不做高频主动闲聊。

# 8. 明确不进入 V0.2 的内容

| 功能 | 去向 / 原因 |

| --- | --- |

| 完整 Autumn Web Console / PWA | V0.3 P0；V0.2 不为 UI 扩范围 |

| Autumn Node Protocol | V0.3 P0 |

| Windows Screen Awareness | V0.3 |

| 手机摄像头 / Room Camera 统一视觉 | V0.3 |

| Ambient Voice / 唤醒词 | V0.3 Home Profile：Wake Word → Continuous Voice Session |

| 米家 / 环境感知 | V0.3 |

| 原生 Android App | 先 PWA + Tasker 验证，后续再决定 |

| Jarvis → Autumn 内部 ID 迁移 | 独立迁移阶段，不夹带 |

| 本地大语言模型 | 当前无必要；32GB 无独显不作为正式依赖 |

| 自然 barge-in / Voice + Eyes/Worker 实时融合 | V0.3：barge-in 为 Voice P0 成熟目标；Eyes/Worker 并行融合 P1，不作为 V0.2 2C 完成条件 |

# 9. 从 Amy-JARVIS 借入 V0.2 的内容

| 借鉴 | Autumn 化后的实现 | 优先度 |

| --- | --- | --- |

| Authority gating | Authority Levels + 任务级一次授权 + audit | P0 |

| Emergency pause / kill | 停止所有 Worker、Codex、OpenCode Job | P1 |

| Persistent daemon / commitments | Commitment Memory、后台 Job 状态 | P1 |

| 多 Agent delegation | Autumn 统一调度 Hermes / OpenCode / Codex | P0 |

| Dashboard / Sidecar / Awareness | 不进 V0.2，留给 V0.3 | Later |

# 10. V0.2 完成定义

用户日常只需要找 Autumn；工作、生活、情感、设备任务不要求用户自己选择 Agent。

Autumn 能受控调用 Hermes Consult / Session，同时不破坏 Hermes 私有记忆边界。

Windows 不再只靠单个 hello_jarvis 白名单程序：能够提交、管理、取消和回收通用 Job。

Direct、OpenCode、Codex 三层 Worker 能按任务价值和成本稳定路由。

Authority Levels 在运行时生效；删除和系统管理员操作仍受硬边界限制。

后台任务结束、失败或已承诺事项可以主动通知；不做无边界主动聊天。

Xiaomi 15 至少能通过一次显式触发进入短时 Continuous Voice Session，连续 3–5 轮无需重复触发；Quick Voice 可作为单轮快速入口；飞书继续保留为可靠远程消息通道。

| V0.2 PASS 句子“Autumn，帮我处理一下。”——用户无需知道最后是 OpenClaw、Hermes、OpenCode、Codex、Pi、Windows 还是手机完成；除非这个信息本身对安全或决策重要。 |

| --- |

规则型 Complexity Gate 已具备：不额外调用 classifier；复杂任务可显式调用 M3 Planner，而普通任务保持 M2.7。

Repair B 在 Phase 2A Freeze 后完成 Context/Token Audit 与逐字段 Token Hygiene；不得以一次性多字段改动替代可回滚实施。

# 11. Rollback 与保护项

V0.1 基线可随时恢复；不重开已 PASS 的 Runner/Bridge/File Return 阶段。

`deadline_doc_sync` 继续受保护，不因 Worker / 权限 / 模型路由调整而修改。

Hermes workspace 不做批量迁移或合并。

内部 `jarvis_* / JarvisRunner / jarvis-bridge / hello_jarvis` 暂不迁名。

每个新执行能力先有最小范围、验收和 rollback，再扩大。

# 12. Model Routing 与 Complexity Gate

Rev5 的正式模型哲学不是“M2.7 一定更好”或“M3 一定更好”，而是把两者放在不同职责层。当前生产默认继续使用 M2.7；M3 不恢复为常驻主脑，而作为复杂任务的高级 Planner / Replanner。

## 12.1 当前 Repair A Frozen Baseline

| 对象 | 当前状态 | 约束 |

| --- | --- | --- |

| Autumn main | minimax/MiniMax-M2.7 | fallbacks=[]；M3 与 DeepSeek 仅在允许模型列表中 |

| Subagents | default = MiniMax-M2.7 | maxConcurrent=1；maxSpawnDepth=1；delegationMode=suggest |

| Hermes | minimax-cn / MiniMax-M2.7 | fallback_providers=[]；api_max_retries=1；api_server=[] |

| DeepSeek V4 Flash | manual only | 不得自动 fallback、不得 subagent 默认、不得自动 route |

| MiniMax quota exhausted | STOP + REPORT | 不得自动切其它厂商 |

## 12.2 规则型 M3 Complexity Gate

不新增 LLM classifier。只有命中硬条件时，Autumn 才显式启动一次 M3 Planner。普通多工具流水线不因为“工具多”就自动升级。

| 硬触发条件 | 动作 |

| --- | --- |

| 用户明确要求“深度处理 / 用 M3 / 仔细规划” | 启动 M3 Planner |

| ≥3 个相互依赖的执行阶段 | M3 做初始计划；M2.7 负责执行 |

| 高风险生产配置 / 安全边界修改 | M3 做风险分析与边界设计 |

| 跨 ≥3 个核心系统，且结果互相依赖 | M3 综合规划 |

| 多文件复杂代码 / Debug | 优先 M3 规划；进入 2B 后重活交 Codex |

| 多工具结果出现冲突，需要重规划 | 允许 1 次 M3 replan |

| M2.7 执行时遇到与计划不一致的事实 | 先停；M3 replan；仍冲突则报告 |

| 普通“搜索 → 发送文件 / 查询 → 回答”等流水线 | 不升级，保持 M2.7 |

M3 调用上限：正常任务最多 1 次初始规划；只有出现真实新冲突时允许 1 次 replan。禁止 M2.7 与 M3 无限互相讨论。

# 13. AUTUMN_GUARDRAIL_REPAIR 状态

| Repair | 状态 | 规划裁决 |

| --- | --- | --- |

| Repair A | PASS / FROZEN | 作为当前生产基线；Phase 2A 不重新打开 |

| Repair B — Token Hygiene | DEFERRED / NOT COMPLETE | 不阻塞 Phase 2A；Phase 2A Final Acceptance + Freeze 后继续，原则上在 2B Worker 扩张前完成 |

## 13.1 Repair B 为什么仍然必须做

Repair B 的目标不是“再省一点 token”，而是先找出真实 context/token 大头，再控制长 session、tool results、重复 workspace 注入、compaction 与 heartbeat 等持续成本。Phase 2B 会加入 OpenCode/Codex/长 Job；若 Token Hygiene 不先收口，后续放大效应更明显。

## 13.2 Repair B 重新实施顺序

| 顺序 | 项目 | 原则 |

| --- | --- | --- |

| B0 | Context / Token Audit | 只读测量；先定位 System Prompt / Workspace / Tool Schema / ToolResult / Session / Heartbeat 等真实大头 |

| B1 | contextInjection | 单字段 dry-run → apply → health → token 对比 → freeze |

| B2 | contextPruning | 优先清理旧 toolResult；验证不破坏任务连续性 |

| B3 | compaction | 再评估 mode/model/keepRecentTokens；默认 housekeeping 不应常态使用 M3 |

| B4 | heartbeat | 最后处理；只有证明有日用价值才保留，避免周期性无意义烧额度 |

| B5 | AGENTS token hygiene | 把已验证的执行纪律固化到运行规则，不靠反复人工提醒 |

## 13.3 单字段实施纪律

记录 before 与当前 health。

只对一个字段做 dry-run / config validate。

只应用这一项；能热加载则不为了“确认”主动重启。

跑一个典型真实任务并记录 context/token 变化。

health + 真实请求验收；PASS 才 freeze。

同类失败两次立即停止；rollback 到最近 frozen baseline。

Gateway 1006 必须结合 restart 时序与 recovery health 判断，不把 transient restart 1006 自动归因于字段本身。

## 13.4 Repair B 未完成期间的临时 Token Hygiene

一个工程阶段 → /new → 执行 → 阶段收尾 → 状态写入项目文档 → 下一阶段再 /new。

不重复读取已经获得的信息。

日志优先 grep / head / tail，不把大段日志长期塞入上下文。

不进行无意义 retry；相同失败两次停止。

不随便开 subagent；DeepSeek 不参与自动 fallback。

# 14. 模型策略验证窗口

开发期负载不能代表稳定日用。Phase 2A 稳定后，至少观察 3–7 天真实日用，再决定是否恢复 M3 默认或升级 MiniMax 套餐。

| 指标 | 关注点 |

| --- | --- |

| M2.7 route/tool correction | 用户需要纠正 Autumn 的次数 |

| M3 escalation rate | 真正需要高级规划的任务占比 |

| M3 replan rate | 一次规划是否足够 |

| 5h quota | 稳定日用是否仍频繁耗尽 |

| Hermes experience | M2.7 是否显著影响自然度/连续性 |

| Session context growth | 普通日用上下文增长速度 |

若只有少数任务触发 M3，维持 M2.7 默认；若大量请求必须先失败再升级 M3，才重新评估默认模型。任何策略更改都应说明收益是否值得修改 Repair A frozen baseline。

## 参考来源与设计借鉴

下列外部项目仅作为设计参考，不构成 Autumn 的运行依赖。

Amy-JARVIS / vierisid/jarvis — 参考 persistent daemon、sidecar、多 Agent、authority gating、emergency pause、desktop awareness 等设计；V0.2 只吸收调度与权限部分。

OpenJarvis — 参考 cost/latency/energy 作为一等指标的思想；Autumn 不照搬其 local-first 路线。
