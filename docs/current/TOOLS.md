# TOOLS.md — Autumn Capability Map

> 本文件是工具使用说明，不是安全授权文件。真正权限由 OpenClaw policy、sender policy、Plugin、Bridge、Runner 等代码与配置控制。

## 0. Capability Map（截至 2026-08-12，Autumn V0.2 final acceptance）

| 能力 | 状态 | 备注 |
| --- | --- | --- |
| Feishu Text | READY | 直接消息回发，无需中间步骤 |
| Feishu Local File Send | READY | `lark-file-sender` 已实测通过；上传到 `upload/` 后 `lark-cli im +messages-send` |
| Feishu Image / Media | READY | 与 Local File Send 同链路，图片/媒体同路径 |
| Raspberry Pi Shell / Exec | READY | `exec` 工具实测（`printf 'AUTUMN_SHELL_OK'`） |
| Windows Raw Shell / Exec | FORBIDDEN | arbitrary raw shell, cmd.exe/powershell.exe used as a shell, and shell=True are forbidden; Python/Node are L3 catalog processes and currently AUTHORIZATION_REQUIRED |
| Direct Worker | READY | Catalog-backed L1/L2；bounded stdout/stderr result 已生产验证 |
| Codex Worker | READY | L3 exact authorization + Runner staging + CREATE/MODIFY-only Publish Gate |
| Emergency Stop | READY | Runner + Pi/OpenClaw production E2E PASS |
| Node observation | READY | `autumn_nodes` reads the live Pi Node Registry; it is read-only and capability is not authorization |

## 0.5 权限域（事实）

### Raspberry Pi / OpenClaw main
- shell / exec：允许
- `lark-cli`：允许
- OpenClaw skills：允许
- 基础命令（`mkdir`、`cp` 等）：允许

### Windows Runner
- arbitrary raw shell, arbitrary cmd.exe/powershell.exe used as a shell, and shell=True: **FORBIDDEN**
- raw Python/Node execution: **FORBIDDEN**; only L3 Direct Worker catalog plus structured argv may request task-scoped authorization, and production currently remains AUTHORIZATION_REQUIRED
- 结构化工具（`jarvis_*`）：自动可用
- Direct Worker（Executable Catalog）：按 L1-L5 分级授权

### 已废弃描述
- 「Feishu sender policy 禁止 exec/node/python」——不再适用，作废。

## 1. Node Observation

### `autumn_nodes`
Use this single read-only tool when the user asks which devices are available, a device's current presence, or its current declared capabilities.

- `{"action":"list"}` lists the bounded live Registry view.
- `{"action":"get","node_id":"windows-main"}` reads one Node.
- `QUERY_FAILED` means the Registry is temporarily unavailable; do not turn it into an `OFFLINE` claim.
- Phone `UNKNOWN` means no recent activity evidence, not offline.
- Presence is observational. **CAPABILITY != AUTHORIZATION**: a declared `job.submit` capability does not approve a job.

This tool never touches presence, registers a Node, executes a capability, wakes a device, or changes authorization.

## 2. Windows Tools

### 1.1 结构化工具（自动可用，无需授权）

### `jarvis_ping`
检查 Windows Runner 是否在线。

### `jarvis_system_info`
获取 Windows 基本系统信息。

### `jarvis_system_status`
获取 CPU、内存、D盘空间、电池、uptime、Python 版本等状态。

### `jarvis_list_directory`
列出 D 盘允许目录。只读。

### `jarvis_search_files`
Search D: filename/path metadata only. Production D: search uses an Everything ES fixed-argv backend; every returned path is revalidated under the requested D: subtree. No content search, no caller ES flags, and search never auto-sends a file.

### `jarvis_program_list`
查看当前允许执行的白名单程序。

### `jarvis_program_run`
执行已登记白名单程序（V0.1 遗留，仅 `hello_jarvis`）。

不得把任意代码、路径、argv、shell、environment 参数塞入该工具。

### 1.2 Direct Worker（Executable Catalog）

Phase 2B 通用 Direct Worker，通过 `worker_submit` 等工具调度。
Autumn 应根据任务类型和风险等级自主选择对应 worker。

**L1 — AUTO（只读，无风险）：**
- Git 只读：`git status / diff / log / show / rev-parse`
- 7zip 查看：`7zip archive.list`（列出 ZIP 内部文件）

**L2 — AUTO（新建只读归档）：**
- `7zip archive.create`（创建新 ZIP）

**L3 — 需要授权（AUTHORIZATION_REQUIRED）：**
- Git workspace write：`git add / commit`
- Python 执行
- Node 执行

当前 production 的 Python / Node 执行授权链未完成，只能返回 `AUTHORIZATION_REQUIRED`；不得承诺“确认后即可执行”。

**L4 — 禁止自动执行：**
- Git 网络操作：`git push / pull / fetch / clone` 等

**L5 — 禁止（HARD DENY）：**
- destructive git 操作
- 任意 delete / remove

**Windows Runner hard boundary**: arbitrary raw shell, cmd.exe/powershell.exe used as a shell, and shell=True are forbidden. All Windows work uses structured tools or Direct Worker catalog plus structured argv. Python/Node minimum authority is L3 task-scoped authorization; production remains AUTHORIZATION_REQUIRED.

Direct `worker_result` 对 process job 返回 bounded `stdout`、`stderr`、`exit_code`、`stdout_truncated`、`stderr_truncated`；stdout/stderr 各自上限为 8192 bytes。该链路已在 production 通过 `D:\majorpath` 的 `git status` 与 `git log -1 --pretty=fuller` 验证。

### 1.3 Worker 控制工具（Phase 2B-5B）

Phase 2B-5B 新增三个 worker 控制工具，Bridge 纯透传，Runner 是唯一状态 owner。

### `worker_control_status`
查询 Runner pause/resume 状态。返回 `{ workers_paused: boolean }`。

### `worker_emergency_stop`
紧急暂停 Runner：停止接受新 Job，运行中的 Job 执行 best-effort cancel。新提交返回 HTTP 409 + `WORKERS_PAUSED`。安全动作，无需用户确认。

### `worker_resume`
恢复 Runner：重新开放 Job 提交。只有用户明确要求（"恢复 Worker"、"解除暂停"、"resume"）时才调用。不得因新任务自动 resume。

## 3. OpenClaw Native Capabilities

### Cron / Reminder
优先用于一次性提醒、周期提醒、定时检查和后台周期任务。不要为了普通提醒新写 Python Scheduler。

### Web / Browser
优先用于网页查询、最新信息、在线文档和资料搜索。

### Memory
用于稳定长期偏好、项目长期约定和重要工作上下文。不要保存 secret。

### Feishu
优先复用当前 OpenClaw / Feishu 已有能力：文字、图片、文件、媒体、卡片。以现场 OpenClaw 版本和实际工具 schema 为准。

如果树莓派本地已经有目标文件，优先尝试原生 Feishu / file-transfer 能力，不自行重写 Feishu API。

### file-transfer
当前已安装。

使用前应根据现场真实能力确认：
- 是否能发送树莓派本地文件；
- 是否绑定 origin direct chat；
- 文件大小限制；
- 临时文件行为；
- 是否需要额外 recipient。

## 4. Routing Examples

“晚上 9 点提醒我交作业” → cron / reminder

“查一下 Quartus 这个错误” → web / browser

“电脑现在怎么样” → `jarvis_system_status`

“有哪些设备可用” / “Windows 在线吗，能做什么” → `autumn_nodes`

“找一下 D 盘 PA1” → `jarvis_search_files`

“列一下 D:\xxx” → `jarvis_list_directory`

“有哪些可运行程序” → `jarvis_program_list`

“运行 hello_jarvis” → `jarvis_program_run`

“把树莓派上的这个文件发给我” → 优先 Feishu / file-transfer 原生能力

“把 Windows 搜到的第一个文件发给我” → 当前仍需确认 Windows → 树莓派 的受控文件数据链路是否已经有原生方案。不要伪装成已支持。**（3B-3 后已更新：见下"Windows → Feishu 文件回传"）**

### 4.1 Router Lite (Phase 2B_6)

完整决策树见 `AGENTS.md §16 Router Lite`。
本页只列对应到工具层的入口：

| 决策 | 工具入口 |
| --- | --- |
| Emergency Stop | `worker_emergency_stop` / `worker_resume` |
| Explicit Hermes | `hermes_session` / `hermes_consult`（FROZEN） |
| Self-answer | —（不需要工具） |
| Direct Worker L1/L2 | `worker_submit`（direct，catalog auto） |
| Direct Worker L3（Python/Node） | 仍 AUTHORIZATION_REQUIRED；当前 Router 不得假装可自动跑 |
| Direct Worker L4/L5 | HARD DENY；告知用户当前不能自动执行 |
| Codex Worker | `worker_authorization_request` → 用户确认 → `worker_authorization_approve` → `worker_submit backend=codex` |

不在本页展开；详见 AGENTS.md §16.1–§16.5。

## 5. Known Gaps / To Verify

### Windows → Feishu 文件回传
**READY**（2026-08-07，Phase 3B-3）

链路：`Search → explicit user selection → file-pull → lark-file-sender → cleanup`

- `jarvis_search_files` / `jarvis_list_directory` 列候选
- D老师 明确选择（"把第 1 个发给我"）或直接给精确 Windows 路径
- `~/.openclaw/workspace/skills/windows-file-sender/send.sh '<path>'`
  - 调用 `jarvis_bridge.cli file-pull` (Phase 3B-2) 拉到 Pi
  - stage 到 `~/.openclaw/workspace/upload/windows-transfer/<tid>/`
  - 复用 `lark-cli im +messages-send` (Phase 3B-3 之前的 lark-file-sender 链路) 发给 D老师 本人 (收件人写死 `<REDACTED_PRIVATE_RECIPIENT_ID>`)
  - cleanup staging + Bridge transfer（无论发送成败）
- 失败语义：file-pull 失败不调用 lark-cli；lark-cli 失败不自动重试（防 Feishu 重复发送），cleanup 后报告

不修改 Windows Runner / Bridge 协议 / OpenClaw plugin / openclaw.json / SOUL / IDENTITY / lark-file-sender skill。

详细报告：`/home/xyzlh/jarvis-bridge/PHASE3B3_WINDOWS_FILE_SEND_REPORT.md`。

### Reminder / Cron
OpenClaw 已具备基础能力，但要做一次真实用户体验验收。

### Feishu Local File Send
✅ **READY（2026-08-07 实测）**：通过 `lark-file-sender` 已完成端到端验证。`upload/` + `lark-cli im +messages-send` 链路工作正常，原生 bot 身份发送即可（`--as user` 在 strict mode 下会被拦截）。

### Voice
后续阶段。优先复用 OpenClaw 已有 voice / TTS / ASR 能力，再决定是否接额外语音模块。

### Smart Home
后续阶段。

### Codex Worker
**READY（Autumn V0.2）**。已完成真实 production CREATE + MODIFY E2E。

- exact task + exact real workspace 的 L3 request 必须先得到用户下一轮明确批准；request 不得使用开放占位 task；
- authorization 单次消费；caller 不提供 staging path、任意 flags/env/model；
- Codex 仅在 Runner-owned staging/work 内工作，real workspace 只经 Publish Gate 接收 CREATE/MODIFY；
- DELETE / rename / move hard deny，subprocess network disabled；
- task 内使用 workspace-relative path，不指导 Codex 访问 real workspace absolute path。

OpenCode Worker 不在此能力中：它由批准的 scope change 从 V0.2 延后到 V0.3，当前不是 PASS，也不是 V0.2 blocker。

## 6. Safety Reminder

文档中的规则不能代替真正安全边界。

真正权限控制来自：
- tool policy；
- sender policy；
- plugin schema；
- Bridge allowlist；
- Runner validation；
- HMAC / replay protection。

如果文档与真实权限不一致，以真实权限为安全底线，并向 D老师 报告差异。
