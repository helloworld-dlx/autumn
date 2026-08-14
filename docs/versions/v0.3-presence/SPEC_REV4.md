AUTUMN

V0.3 · Presence

项目说明书 · Rev4

I am here.

| 版本 | Autumn V0.3 · Presence · Rev4 |

| --- | --- |

| 状态 | PLANNING BASELINE / APPROVED SCOPE / PRIMARY COMPANION / DEVICE PRESENCE UPDATED |

| 更新时间 | 2026-08-14 |

| 前序基线 | Autumn V0.2 · One Autumn = PASS / CLOSED / FROZEN |

Rev4 在 Rev3 Voice Priority 基线上进一步裁决：Companion/PWA 成为 V0.3 的主要交互入口并覆盖文字聊天与文件传输；飞书降级为通知、备用与远程兜底入口。当前正式 Node 为 Pi 5 / Windows / Xiaomi 15；Pi 4 Room Satellite 与房间远场 Wake Word 延后。Device Presence 提升米家、Huawei Buds 语音助手手势与手机小爱同学协作为重点，同时新增 Git Closure Gate：每个产生代码/文档变更的小阶段，验收通过后必须 commit + push 到 private Git。

# 1. 版本定位

| 正式目标V0.3 让 Autumn 从“一个能处理任务的统一入口”进化成“在手机、电脑和现实环境里持续存在的同一个助手”：有统一 Node、有自己的 Companion、有低摩擦实时语音、有按需视觉，并能在明确权限下连接现实设备。 |

| --- |

| 版本 | 主句 | 核心跃迁 | 一句话能力 | 状态 |

| --- | --- | --- | --- | --- |

| V0.1 · Afterglow | I can act. | 执行闭环 | 自然语言 → 工具 → 真实执行 → 返回结果 | 已冻结 |

| V0.2 · One Autumn | I can handle it. | 统一调度 | 一个 Autumn，自动选择主脑 / Hermes / Worker / Codex | PASS / CLOSED / FROZEN |

| V0.3 · Presence | I am here. | 存在与感知 | 统一 Node、Companion、Realtime Voice、Eyes、Device Presence | 本文件 |

| V0.4 · Forge | I can build it. | 创造闭环 | EDA / FPGA / 软件 / 实物实验室自动协作 | 预研 |

V0.3 不追求全天监控，也不追求每个设备都有独立 App。核心仍是 Portable Core + Presence Layer：Autumn 的主脑保持在 Pi 5，Windows 与 Xiaomi 15 作为可插拔 Node、感官、执行端和界面。

# 2. V0.3 的 P0/P1/P2

| 功能 | 优先级 | 一句话价值 |

| --- | --- | --- |

| Autumn Node Protocol Lite | P0 | Pi 5 / Windows / Xiaomi 15 使用统一设备身份、在线状态与 capability 语言 |

| Autumn Companion / PWA | P0 | 成为主要交互入口：文字、Voice、文件、审批、状态 |

| Companion Chat + File Transfer | P0 | 普通日用不再依赖飞书；聊天与文件收发都能在 Companion 完成 |

| Portable Realtime Voice | P0 | 从 V0.2 轮次式 Voice 演进到低延迟持续会话 |

| Natural Barge-in | P0 | 用户开口即可打断 Autumn 并继续或重定向会话 |

| Autumn Eyes API | P0 | 统一 Windows Screen / Phone Camera 的按需视觉 |

| Privacy Kill / Awareness Modes | P0 | Autumn 在看什么必须可见；“闭眼”立即停止 |

| Xiaomi Home Device Presence | P0 | 按 Autumn 自己的设备 allowlist 读取/控制授权米家设备 |

| Huawei Buds Voice Trigger | P0 Portable | 利用耳机已有“语音助手”手势进入 Autumn Voice，具体 Android 路径需实机 Recon |

| Home / Dorm Software Profile | P0 | 不同环境切换能力来源与隐私默认，不改变 Autumn 核心人格 |

| 手机小爱同学协作 | P1 | 只做手机系统侧的官方/稳定 handoff 或互操作，不把小爱当第二个 Autumn |

| Voice + Worker Control | P1 | 语音中查询/暂停/重定向后台 Job |

| Voice + Eyes Fusion | P1 | “你看这个”按 policy 获取按需视觉上下文 |

| Worker 可视化 | P1 | 后台 Codex / Direct / Hermes 状态在 Companion 可见 |

| Harmony 平板 HUD / 手表通知 | P1 | Presence 扩展，不阻塞 V0.3 |

| Android Accessibility | P2 | 只有 PWA/正常 Android 能力确实不够时才考虑 |

| Pi 4 Room Satellite / 远场 Wake Word | Later | 当前 V0.3 不作为 PASS blocker |

| DeepSeek Harness | Late Evaluation | OpenCode 不再是必须项；最后再判断是否值得以 DeepSeek Harness 替代 |

# 3. 实施阶段与顺序

| 阶段 | 主题 | 完成后进入下一阶段的门 |

| --- | --- | --- |

| V0.3-0 | Git Baseline + Rev4 | Private monorepo 建立；V0.2 tag 固化；Rev4 canonical 入库并 push |

| 3A | Node Protocol Lite | Pi5 / Windows / Xiaomi15 至少能统一报告身份、版本、在线与 capabilities |

| 3B | Autumn Companion | Companion 可作为主要入口完成文字聊天、Voice、文件收发、Devices/Senses/Approvals/Jobs 基础视图 |

| 3C | Realtime Voice | 手机稳定 5+ 轮、streaming、natural barge-in；Quick Voice 保留同栈 fast path |

| 3D | Autumn Eyes + Privacy | Windows Screen + Phone Camera 接入统一 vision.capture；Privacy Kill 可验收 |

| 3E | Device Presence | 米家 allowlist 闭环 + Huawei Buds 入口；手机小爱协作按可行性做 P1 |

| 3F | Presence Fusion + Final | Home/Dorm software profile、跨能力融合、可视化和 V0.3 Final Acceptance |

| 阶段原则一次只关一个门。每个小阶段先完成最小实现、真实设备 smoke 和必要测试，再执行 Git Closure Gate；不允许在当前阶段顺手提前实现下一阶段。 |

| --- |

# 4. 核心架构：Autumn Core + Node + Companion

| Autumn Core                       Raspberry Pi 5                            │                    Autumn Node Protocol Lite              ┌─────────────┴─────────────┐              │                           │           Windows                    Xiaomi 15            Node                         Node       Files / Worker               Voice / Camera       Screen / Apps                Soft actions              │                           │              └──────────┬────────────────┘                         │                 Autumn Companion / PWA               Chat · Talk · Files · Status                         │                 Feishu = fallback/notify |

| --- |

Pi 5 仍是 Autumn Core 与 24/7 中枢；V0.3 不迁移主脑。

Windows Runner、Voice Bridge 等 V0.2 已冻结能力不重写，只通过薄 Adapter 进入统一 Node capability。

Xiaomi 15 是 Portable Presence 主设备：Companion、Realtime Voice、Phone Camera、软动作与耳机入口。

Pi 4 暂不作为当前正式 Node；未来接入时必须复用同一 Node Protocol，而不是另造一套客户端。

Tailscale 继续作为主要私网，不为 Node 暴露公网控制端口。

# 5. Autumn Node Protocol Lite

V0.3 的关键不是先写三个客户端，而是统一设备能力的语言。Node 只声明“我是谁、我在线吗、我能做什么”，Core 决定何时调用。

| 能力族 | 示例 capability | 当前 Node |

| --- | --- | --- |

| 状态 | node.status / version / network | Pi5 / Windows / Phone |

| 文件 | file.search / file.return | Windows |

| Worker | job.submit / status / cancel | Windows |

| 视觉 | screen.capture / camera.capture | Windows / Phone |

| 语音 | voice.session / voice.stop | Phone |

| 软动作 | open_url / clipboard_set / notify / open_app? | Phone / Windows |

| 环境 | home.read / home.control | Pi5 → Home sidecar |

Node 必须有稳定身份、协议版本、在线状态、能力清单与最小权限。

capability 不等于授权：设备声明“可控制灯”后，Core 仍需通过 Autumn Authority 与 Device Policy 决定能否执行。

不做通用远程 shell；已有 Runner authority 继续生效。

3A P0 只覆盖 Pi5 / Windows / Xiaomi15 的最低必要字段，不建设泛化微服务框架。

# 6. Autumn Companion / PWA（主要交互入口）

| 入口裁决V0.3 开始，Companion/PWA 是日常主要交互入口；飞书不再与它平级竞争。飞书保留为通知、备用远程入口和 Companion 不可用时的兜底通道。用户仍只面对同一个 Autumn。 |

| --- |

| 入口 | V0.3 角色 | 是否主要入口 |

| --- | --- | --- |

| Autumn Companion / PWA | 文字聊天、Voice、文件上传/下载、Camera、审批、设备/任务状态 | YES |

| 飞书 | 通知、紧急/备用聊天、兼容既有文件回传、远程兜底 | NO / fallback |

| Windows Tray | 连接、暂停、Privacy Kill、Stop Workers、打开 Companion | 辅助 |

| 原生 Android App | 只有 PWA/系统限制明确阻碍日用时才考虑 thin wrapper | 默认不做 |

## 6.1 Companion MVP 页面

Chat：必须支持与 Autumn 的正常文字聊天；不是调试输入框。

Talk：复用 V0.2 Afterglow Voice 页面并演进到 Realtime Voice。

Files：用户可显式上传文件给 Autumn，也能下载/接收 Autumn 返回的文件；通过 Tailscale 私网，浏览器不持有 Gateway/provider secret。

Home：第一屏看 Autumn 在线、设备、Active Jobs、待审批、Senses。

Devices：Node 在线状态、版本、capabilities 与权限摘要。

Senses：Voice / Vision / Assist 当前来源和开关。

Approvals：L3/L4 与 Device Control 的任务级确认。

Jobs：Direct / Codex / Hermes 的状态与 Cancel；不暴露 Hermes 私聊正文。

## 6.2 Chat / Voice / File 的“一入口”原则

Companion Chat 与 Talk 必须路由到同一个 Autumn 主 Agent、同一人格、Memory 与 Authority；Voice runtime 不是第二个助手。

普通日用不应要求“聊天去飞书、语音去网页、文件又回飞书”。3B PASS 前，Companion 必须具备文字聊天 + 文件收发的最低闭环。

飞书可以继续收到提醒和异步任务结果；这是 transport/fallback，不等于第二个主入口。

如果跨 surface 的短期 transcript 完全统一会显著增加复杂度，V0.3 P0 优先保证同一 Autumn 的身份/Memory/工具语义；Companion 内部的 Chat + Voice 必须共享一致上下文。

# 7. Voice

## 7.1 Portable Realtime Voice（P0）

Xiaomi 15 + Huawei Buds 作为主要移动输入输出。

V0.2 的 utterance STT → Autumn → TTS 链保持 fallback，不继续为实时感过度优化。

V0.3 主链目标是 persistent realtime audio session：streaming input/output、smart turn、natural barge-in。

Quick Voice 保留为同一 Voice Session abstraction 的单轮 fast path。

Voice Session ≠ Task Session；后台 Worker 可异步存在，Voice + Worker Control 为 P1。

## 7.2 Huawei Buds 语音助手手势（P0 Portable）

用户现有 Huawei Buds 有专门的“语音助手”手势，因此优先把它作为随身 Autumn 的物理入口。

第一步必须在 Xiaomi 15 上实测这个手势实际触发的是 Android 默认数字助理、厂商助手 intent、media/assistant key event 还是其他路径。

优先使用系统现有能力、Tasker/shortcut/intent；只有 PWA 无法接住该手势且确实影响日用时，才考虑极薄 Android wrapper。

耳机手势只负责“进入/唤醒 Autumn Voice Session”，不在耳机侧复制 Agent 或 Memory。

## 7.3 手机小爱同学协作（P1）

这里的小爱同学指 Xiaomi 15 手机上的系统/应用助手，不是智能音箱。

目标是共存与互操作，而不是把小爱改造成 Autumn，也不 root/patch 系统。

优先探索官方/稳定的 Android assistant handoff、intent 或 shortcut：例如耳机手势若固定触发系统助手，评估是否能把 Autumn 设为可选入口；不可稳定实现则不作为 V0.3 blocker。

米家控制由 Autumn → Home Device Sidecar 完成，不依赖“让小爱代执行”才能成立。

# 8. Autumn Eyes / EDITH（P0）

| Autumn Eyes / EDITH├── windows.screen└── phone.cameravision.capture(source=?, mode=on-demand) |

| --- |

| Awareness Mode | 行为 | 默认 |

| --- | --- | --- |

| OFF | 不读取屏幕/摄像头 | 随时可选 |

| BASIC | 窗口标题、前台程序等低敏感元数据 | Windows 可选 |

| ON-DEMAND | 用户明确要求才截图/拍照 | 默认视觉模式 |

| ASSIST | 特定工作会话低频感知 | 用户显式开启 |

“Autumn，闭眼”必须立即停止视觉采集，并在 Companion/Tray 清楚显示 Vision OFF。

Windows Screen 第一价值是看当前错误/界面；Phone Camera 第一价值是让用户主动把镜头对准开发板、书、物品和现场。

当前 V0.3 不要求 Room Camera；不做全天房间录像或永久高频桌面截图。

# 9. Device Presence：米家 / 耳机 / 手机系统

## 9.1 Xiaomi Home（P0）

米家不直接暴露“整个账号”给 Autumn。建议以 Home Assistant + 小米官方 Xiaomi Home Integration 作为 Home Device Sidecar，再由 Autumn 自己的 Device Policy 做第二层最小权限过滤。

| Autumn Core   │Device Policy (allowlist)   │Home Device Adapter   │Home Assistant   │Xiaomi official Xiaomi Home integration   │授权的米家设备 |

| --- |

Home Assistant 能看到的设备 ≠ Autumn 能控制的设备。Autumn 必须维护独立 allowlist。

每个允许设备声明：alias、允许 read 的属性、允许 control 的 action、是否需要确认、风险等级。

不在 allowlist 的设备对 Autumn 视为不存在：不得查询状态、不得控制、不得把完整设备清单暴露给模型。

高风险设备（门锁、安防、摄像头隐私/敏感控制等）默认 DENY 或强确认；V0.3 不追求无确认自动化。

实际 Home Assistant entity/device IDs 属 device-local config / encrypted backup；Git 只保存 policy schema/example，不保存个人家庭拓扑。

| 类型 | 默认能力 | 示例策略 |

| --- | --- | --- |

| 灯 / 普通插座 | READ + CONTROL | 可加入 allowlist；第一版控制可要求确认 |

| 空调 / 风扇 | READ + CONTROL | 温度/模式等限定 action；越界值拒绝 |

| 环境传感器 | READ | 默认只读 |

| 扫地机等移动设备 | 按设备裁决 | 可读；控制是否开放由用户单独批准 |

| 门锁 / 安防 / 敏感摄像头 | DENY / HIGH RISK | V0.3 不做无确认控制 |

| 未列入 allowlist 的设备 | INVISIBLE / DENY | Autumn 不可见、不可碰 |

## 9.2 Home / Dorm Software Profile（P0）

| 能力 | Home | Dorm / Portable |

| --- | --- | --- |

| 主要语音 | Phone / Huawei Buds；未来可加 Room Satellite | Phone / Huawei Buds |

| 主要视觉 | Windows Screen + Phone Camera | Windows Screen + Phone Camera |

| 现实设备 | 米家 allowlist 可用 | 少量/按需 |

| 控制端 | Companion + 飞书通知 | Companion + 飞书通知 |

| 隐私默认 | ON-DEMAND；可选 ASSIST | 更保守；Ambient 不存在 |

| 延期裁决Pi 4 Room Satellite、房间远场麦克风/扬声器、Wake Word → Ambient Voice 闭环从当前 V0.3 PASS 条件移除，进入 V0.3.x / later。当前 Home Presence 由 Phone Voice + Eyes + Xiaomi Home 即可成立。 |

| --- |

# 10. Worker / Sub-agent 与可视化

Codex Worker、Direct Worker 与 Hermes 延续 V0.2 已冻结边界；Companion Jobs 页面显示任务名、Worker、开始时间、权限范围、状态与 Cancel。

OpenCode Worker 不再是 V0.3 必须项。

DeepSeek Harness 放到 V0.3 主线末尾再做一次价值评估：只有它能补充 Codex/Hermes 现有能力并且复杂度可控时才实施。

不因为“预留了 Worker 槽位”就强行新增 Worker。

# 11. Git / 工程交付纪律（Rev4 新增）

| Git Closure Gate从 V0.3 开始，每个产生源码、文档、配置模板或部署脚本变更的小阶段，只有在该阶段验收通过并成功 commit + push 到 Autumn private GitHub monorepo 后，才允许标记 CLOSED / FROZEN 并进入下一阶段。 |

| --- |

一个 private monorepo 管理 Pi / Windows / Phone / Companion / docs，不拆成多个互相漂移的 release。

阶段开始：先 git status，确认基线和工作树；阶段完成：最小测试 + 真实 smoke → 检查 diff → secret boundary → commit → push。

如果有文件变更但 push 失败：阶段状态不得写 CLOSED；报告 GIT_PUBLISH_BLOCKED。

如果纯只读 Recon / Audit 没有任何文件变化：明确报告 NO_GIT_CHANGE，本轮无需制造空 commit。

大版本/正式阶段封版使用 tag；普通小修只 commit，不滥用 tag。

任何真实 Token、OAuth、Feishu Secret、Tailscale state、私人 session/memory、Home entity topology 不进入 Git。

| Stage implementation      ↓Tests / real-device smoke PASS      ↓git diff + secret boundary check      ↓git commit -m "phase: ..."      ↓git push origin main      ↓Stage = PASS / CLOSED |

| --- |

# 12. Portability-ready 设计约束（本版只约束，不实施完整迁移）

V0.3 开发期间不得把硬件路径、API Key、家庭设备 ID 等写死进 Core；使用 device-local config / env / inventory。

Git 保存 source / docs / schema / deploy template；secrets 与 mutable state 分离。

V0.3 PASS 后单独进入 Reliability & Portability Track：bootstrap / doctor / encrypted backup / restore / fresh-device migration test。

正式迁移目标不是“SD 卡能不能直接拔过去”，而是“新机器 + Git + secrets/state restore 可以重建 Autumn”。

# 13. V0.3 完成定义

Pi 5、Windows、Xiaomi 15 以统一 Node 概念向 Autumn Core 报告在线、版本与 capabilities。

Autumn Companion/PWA 成为主要交互入口：可完成正常文字聊天、Voice、文件上传/下载，并查看 Devices、Senses、Approvals、Jobs 基础状态；飞书仅作为通知/备用入口继续存在。

Xiaomi 15 可一次触发进入 Portable Realtime Voice Session，稳定完成至少 5 轮连续对话并支持 natural barge-in；Quick Voice 保留。

Huawei Buds 的“语音助手”手势至少完成一次可靠 Autumn Voice 入口闭环，或若 Android/厂商明确阻塞则形成可复现证据与批准的最小替代入口。

Windows Screen + Phone Camera 接入统一 Autumn Eyes；“Autumn，闭眼”可立即停止视觉。

Xiaomi Home 至少完成一组 allowlist 设备的真实 READ + CONTROL 闭环，并证明未授权设备对 Autumn 不可见/不可控制。

Home / Dorm software profile 切换不会改变 Autumn 核心人格、Memory、Authority 或 Worker 能力。

所有 V0.3 小阶段的最终变更均已经 commit + push；Git 工作树/远端基线可追踪。

| V0.3 PASS 句子“Autumn 不只是一个联系人了。我在手机、电脑和现实设备之间用不同方式叫她，但主入口和身份仍然只有一个 Autumn。” |

| --- |

# 14. 不进入当前 V0.3 的内容

Pi 4 Room Satellite、Room Camera、房间远场 Wake Word / Ambient Voice：V0.3.x / later。

完整原生 Android App：除非 PWA/Tasker/系统 assistant handoff 被证明存在硬限制。

全天摄像头、全天麦克风、持续 GPS、所有通知读取。

未经用户批准的米家全账号控制；未在 allowlist 的设备一律不可碰。

门锁、安防、敏感摄像头等高风险设备的无确认控制。

root/patch 手机小爱或耳机固件。

OpenCode Worker 作为必选项。

DeepSeek Harness 作为 V0.3 PASS blocker。

EDA / Quartus / 嘉立创创造闭环：属于 V0.4 Forge。

# 15. 参考来源与设计借鉴

Autumn V0.3 · Presence · Rev3：本 Rev4 的直接 planning baseline。

Xiaomi 官方 Xiaomi Home Integration for Home Assistant：用于设备发现/MIoT 映射与 Home sidecar 设计参考；Autumn 仍增加自己的设备 allowlist。

Huawei 官方 FreeBuds 手势文档：确认多个 FreeBuds 系列可将手势配置为唤醒 Voice Assistant；实际 Xiaomi 15 触发路径需 3E 实机 Recon。

Amy-JARVIS：参考 Brain + Sidecar、capability、Dashboard 与 deployment/doctor 思路，不作为运行依赖。

OpenClaw / Tailscale / Home Assistant：继续作为 Autumn 现有平台、私网与 Home sidecar 的基础组件。

Autumn · Afterglow Project Line
