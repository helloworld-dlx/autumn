# Autumn V0.1 · Afterglow
## 完成基线与 V0.2 规划交接文档

- **日期**：2026-08-07
- **版本**：Autumn V0.1 · Afterglow
- **中文名**：TBD
- **状态**：RELEASE READY / BASELINE FREEZE
- **用途**：长期备份、恢复基线、交给 V0.2 总管规划 AI
- **安全说明**：本文不包含真实 Token、HMAC Key、Feishu Secret、完整敏感 ID、私聊内容或 Hermes 私有数据。

---

## 1. V0.1 一句话定义

Autumn 是一个以 **OpenClaw main 为主 Agent、树莓派 5 为 24 小时中枢、Windows 笔记本为受控执行节点、飞书私聊为主要入口** 的个人多设备 AI 助手。

主链路：

```text
D老师
  ↓
飞书
  ↓
Autumn / OpenClaw main
  ├─ OpenClaw 原生：Web / Cron / Memory / Shell / Skills / Feishu
  └─ Windows 专用：jarvis_* tools
        ↓
     Jarvis Bridge
        ↓ Tailscale
     Windows Runner
```

V0.1 的完成定义不是“拥有所有 Jarvis 功能”，而是先建立一条可靠、可日用、可恢复、可继续扩展的闭环。


## 2. 身份与人格

### 正式身份
- 英文名：**Autumn**
- 中文名：**TBD**
- 主题：**Afterglow / 余晖**
- 主 Agent：OpenClaw `main`
- 主入口：飞书私聊

### 人格方向
当前 workspace 已从早期“白芷”迁移到 Autumn：
- 女性人格；
- 私人女秘书 / Chief of Staff 气质；
- 成熟、聪明、从容；
- 有主见、有熟人感；
- 有适量幽默、吐槽、动作感和夜间松弛感；
- 不机械角色扮演，不像客服机器人；
- 更接近电影里的 Jarvis / Friday：能做事、有连续性、有存在感。

### Workspace 文件
```text
IDENTITY.md
SOUL.md
AGENTS.md
TOOLS.md
```

职责：
- `IDENTITY.md`：名字、主题、身份；
- `SOUL.md`：人格、语气、活人感；
- `AGENTS.md`：运行规则、安全边界、博客规则、Hermes 隔离；
- `TOOLS.md`：能力地图与工具路由。

内部 `jarvis_* / JarvisRunner / jarvis-bridge / hello_jarvis` 暂时保留，仅作为兼容 ID，不代表助手仍叫 Jarvis。


## 3. Agent 分工

### Autumn
负责：
- 工作与学习辅助；
- 项目推进；
- Web；
- Reminder / Cron；
- 设备状态；
- Windows 文件与程序；
- Feishu 文件/图片；
- 后续语音、家居等扩展。

### Hermes
Hermes 是独立副 Agent。

冻结边界：
- Autumn 不读 Hermes SOUL；
- 不读 Hermes memory；
- 不主动同步私人内容；
- 不自动跨 Agent 读取 Hermes 私有数据；
- V0.1 不重新设计 Hermes。


## 4. 设备与网络

### Raspberry Pi 5
角色：
- 24 小时中枢；
- OpenClaw Gateway；
- Jarvis Bridge；
- local shell / exec；
- OpenClaw skills；
- Feishu / `lark-cli`；
- Reminder / Cron；
- Web；
- Memory；
- Windows 文件中转。

当前接受保留的服务/端口：
- OpenClaw：`18789/tcp`
- VNC：`5900/tcp`
- rpcbind：`111/tcp/udp`

这些在 V0.1 中不是阻塞项，不继续反复审查。

### Windows 笔记本
角色：
- 受控执行节点；
- 合盖/休眠属于正常状态；
- 不要求 24 小时在线。

核心：
```text
D:\JarvisWorkspace\JarvisRunner
D:\JarvisScripts
```

Task Scheduler：
```text
JARVIS Windows Runner
```

### 网络
- Pi ↔ Windows：Tailscale 私网；
- Windows Runner：仅绑定 Tailscale IPv4，端口 `27891`；
- Bridge：仅 `127.0.0.1:27901`；
- 不使用公网暴露 / Funnel。


## 5. V0.1 最终能力矩阵

| 能力 | 状态 | 说明 |
|---|---|---|
| Autumn Persona / Workspace | ✅ READY | 新 workspace 已迁移 |
| Feishu Text | ✅ READY | 主入口 |
| Web / Browser | ✅ READY | 已真实使用 |
| Reminder / Cron | ✅ READY | 最终复测成功 |
| Memory | 🟡 PREVIOUSLY WORKING | 之前可用，本轮未重新完整验收 |
| Pi Shell / Exec | ✅ READY | 最终产品决策：允许完整本地 shell |
| Pi Local File → Feishu | ✅ READY | `lark-file-sender` 实测 |
| Pi Image / Media → Feishu | ✅ READY | 图片实测 |
| Windows Ping | ✅ READY | `jarvis_ping` |
| Windows Info / Status | ✅ READY | CPU / RAM / D盘 / 电池 / uptime |
| Windows Directory List | ✅ READY | D盘只读 |
| Windows File Search | ✅ READY | D盘只读，契约漂移已修 |
| Windows Program List / Run | ✅ READY | `hello_jarvis` LOW/AUTO |
| Windows → Pi File Pull | ✅ READY | Phase 3B-2 |
| Windows → Feishu File Return | ✅ READY | Phase 3B-3 |
| Arbitrary Windows Shell | ❌ FORBIDDEN | CMD / PowerShell / 任意 Python 不开放 |
| Third-party Sending | ❌ DEFAULT FORBIDDEN | 默认只发本人 |
| Hermes Private Access | ❌ FORBIDDEN | 严格隔离 |
| Blog Project Rules | ✅ READY | 独立真实项目规则保留 |


## 6. Windows Runner

正式 7 个 action：

```text
system.ping
system.info
system.status
files.list_directory
files.search
program.list
program.run
```

对应 OpenClaw tools：

```text
jarvis_ping
jarvis_system_info
jarvis_system_status
jarvis_list_directory
jarvis_search_files
jarvis_program_list
jarvis_program_run
```

### Windows 文件安全边界
- 只允许 `D:\`；
- C盘拒绝；
- 其他盘拒绝；
- UNC 拒绝；
- ADS 拒绝；
- reparse / symlink / junction 越界拒绝；
- 不提供删除、移动、重命名、任意写入；
- 文件搜索只读。

### 白名单程序
当前唯一：

```text
hello_jarvis
```

策略：
```text
risk = LOW
execution_policy = AUTO
```

固定程序、无用户参数、不允许 path/argv/shell/environment 注入。

未来新增 program_id 必须重新定风险等级，不自动继承 AUTO。


## 7. Windows 文件导出与回传

### Phase 3B-1：Runner `/v1/file`
新增：

```text
POST /v1/file
```

特点：
- 不进入 action registry；
- body 只接受 `{"path":"D:\\..."}`；
- 复用 HMAC-SHA256 / timestamp / request_id / nonce / anti-replay；
- 内部认证 action：`file.export`；
- 16 MiB 固定上限；
- `application/octet-stream`；
- 64 KiB streaming；
- `Content-Length`；
- 不 Base64；
- 不把文件正文塞入 `/v1/task` JSON；
- 使用同一打开 handle 做读取与 TOCTOU 检查。

Phase 3B-1 完成记录：
```text
83 tests
0 failures
doctor = 0
selftest = 0
```

首次生产未加载新路由，重启 Windows Runner 后 `/v1/file` 生效。

### Phase 3B-2：Pi file-pull
Bridge 增加受控文件拉取/清理能力：
- Windows → Pi streaming；
- 随机 transfer_id；
- caller 不能指定 Pi 任意输出路径；
- `.part` → 原子完成；
- 16 MiB 双侧限制；
- Pi 边收边计算 SHA-256；
- 失败清理；
- 不把 HMAC key 暴露给 LLM。

### Phase 3B-3：Windows → Feishu
完整日用流程：

```text
D老师：找 D 盘里的 PA1 PDF
Autumn：列候选
D老师：把第1个发给我
Autumn：
  Windows file-pull
  → Pi staging
  → lark-file-sender
  → lark-cli
  → 飞书本人
  → cleanup
```

规则：
- 搜索到文件 ≠ 自动授权发送；
- “把第 N 个发给我”即本次本人发送确认；
- 精确指定 D盘文件并要求发送，同样视为确认；
- 不多问一次“确认吗”；
- 不自动发群聊/第三方；
- 不自动打包目录；
- 16 MiB 上限；
- Windows 原文件不修改；
- Pi 临时文件发送后清理；
- Feishu 发送失败不自动重复发送。

V0.1 复用现有 `lark-file-sender + cp + lark-cli`，没有自研 Feishu 上传 API。


## 8. 权限模型最终决策

### Raspberry Pi / Autumn main
明确允许：
```text
local shell / exec
mkdir
cp
lark-cli
OpenClaw skills
本地维护脚本
```

这是 V0.1 最终产品取舍。原因是 OpenClaw 的大量原生能力与 skill 依赖 shell，完全禁用会明显破坏实际可用性。

### Windows
继续严格：
```text
任意 CMD        ❌
任意 PowerShell ❌
任意 Python     ❌
任意 Shell      ❌
```

Windows 只能通过结构化 `jarvis_*` 工具和批准的 program。

最终模型：

```text
Pi      = 通用 Agent 主机
Windows = 受控远程执行设备
```


## 9. OpenClaw 原生能力原则

V0.1 确立：

> OpenClaw 原生能力优先，自研只补真正缺失的部分。

路由：
```text
网页资料 → Web / Browser
提醒 → Cron / Reminder
Pi 本地文件/图片 → Feishu / lark-cli / skills
记忆 → OpenClaw Memory
Windows 状态/文件/程序 → jarvis_* tools
```

因此 Phase 3B 最终只自研 Windows 文件数据链路，Feishu 层直接复用已有能力。


## 10. Plugin Approval 决策

曾尝试 OpenClaw 2026.6.1 plugin approval。

实际：
- Feishu 可以收到 approval 文本；
- 但不是原先按钮式审批体验；
- `/approve` 无法正常完成 resolution；
- 不适合作为 V0.1 日常执行确认。

最终：
- `hello_jarvis` 作为 LOW/AUTO；
- 当前 plugin approval 退出关键路径；
- 未来“联网 / 写文件 / 参数显著改变行为”的程序应重新设计确认机制。


## 11. 个人技术博客项目

博客是真实存在的独立项目，不能因 Autumn 重构被删除或覆盖。

固定规则：
- 可维护页面布局/样式；
- 可优化文章格式；
- 可整理草稿；
- 不编造经历、成果、奖项、项目进度；
- 不删除旧文章，除非用户明确要求；
- 新文章默认：

```yaml
draft: true
```

只有用户明确确认才能发布为：

```yaml
draft: false
```

只有实际修改博客项目时才运行：

```bash
npm run build
```

不得把这条规则错误应用到 Autumn、Runner、MajorPath、FPGA 等其他项目。


## 12. deadline_doc_sync

`deadline_doc_sync` 是受保护的既有任务。

除非 D老师 在当前会话明确要求，否则：
- 不修改；
- 不迁移；
- 不删除；
- 不重建；
- 不改 agentId；
- 不改 schedule；
- 不改 payload；
- 不改工具依赖；
- 不因其他策略顺手影响它。

V0.1 整个收尾阶段保持该边界。


## 13. 阶段完成摘要

- **Phase 0**：Tailscale、备份、基础服务确认；
- **Phase 1A**：Runner 安全骨架，ping/info；
- **Phase 1B**：D盘 list/search、安全路径边界；
- **Phase 1C**：system.status；
- **Phase 1D**：HMAC / expiry / request_id / nonce；
- **Phase 1E**：Runner Tailscale HTTP 服务；
- **Phase 2A/2B**：Pi Bridge 与真实 Runner 往返；
- **Phase 2C**：OpenClaw plugin，7 个 Windows tools；
- **Phase 2D**：Task Scheduler、audit rotation、常驻；
- **Phase 3A**：program.list / program.run / hello_jarvis；
- **Phase 3B**：Windows 文件 → Pi → Feishu；
- **Phase 4A**：Final Acceptance。

Final Acceptance 中用户明确实测成功：
1. Windows 状态；
2. Windows offline；
3. D盘搜索；
4. 搜索结果 → 文件发送本人飞书。

此外：
- Cron 最终复测成功；
- Pi 本地文件发送成功；
- 图片发送成功；
- Web 正常；
- Program run 正常；
- Blog rules 正常；
- Memory 之前正常，本轮未重测。

用户决定剩余非关键项不阻塞 V0.1，进入 Release Snapshot。


## 14. 已接受、不阻塞 V0.1 的事项

以下不要在 V0.1 收尾继续折腾：

1. 内部 Jarvis 命名：`jarvis_* / JarvisRunner / jarvis-bridge / hello_jarvis`；
2. duplicate plugin id / workspace override warning；
3. state migration warnings；
4. Feishu plugin approval UX；
5. Memory final round 未重测；
6. Windows 不始终在线（设计行为，不是故障）。

不要为了“干净”重新打开已经 PASS 的阶段。


## 15. V0.1 未包含的后续候选

以下属于 V0.2+，不是 V0.1 缺陷：

- Voice / ASR / TTS；
- 唤醒词；
- 连续语音与打断；
- 创乐博语音模块；
- 米家 / 智能家居；
- Codex 重型执行桥；
- 更多 Windows registered programs；
- Windows 写文件类能力；
- 截图 / 摄像头；
- 更主动的日程与上下文自动化；
- 中文名；
- Jarvis → Autumn 内部 ID 正式迁移；
- 更成熟的高风险确认 UX。

V0.2 应由规划 AI 根据 **日用价值 / 开发成本 / 风险 / OpenClaw 原生能力** 重新排序，而不是按此列表顺序开发。


## 16. Phase 4B — Release Snapshot

建议当前基线命名：

```text
Autumn_V0.1_Afterglow_2026-08-07
```

建议保存两类快照。

### A. Shareable / Planner Snapshot
用于交给 V0.2 总管规划 AI。

建议包含：
```text
AUTUMN_V0_1_COMPLETION_AND_V0_2_HANDOFF.md
IDENTITY.md
SOUL.md
AGENTS.md
TOOLS.md
Runner 的 CURRENT_STATUS / README / implementation reports
Bridge / Phase 3B reports
Capability Matrix
```

必须排除：
- Token；
- HMAC Key；
- runner.json；
- openclaw.json；
- Feishu Secret；
- 完整敏感 user/open/chat IDs；
- 私聊内容；
- Hermes 私有数据。

### B. Private Restore Snapshot
仅 D老师 自己保存。

Raspberry Pi 建议包含：
```text
~/.openclaw/workspace/IDENTITY.md
~/.openclaw/workspace/SOUL.md
~/.openclaw/workspace/AGENTS.md
~/.openclaw/workspace/TOOLS.md
~/.openclaw/workspace/plugins/jarvis-bridge-tool/
~/jarvis-bridge/
OpenClaw 真实配置（私密）
exec policy / approvals
systemd user units
local skills
```

Windows 建议包含：
```text
D:\JarvisWorkspace\JarvisRunner\
D:\JarvisScripts\hello_jarvis.py
JARVIS Windows Runner Task Scheduler XML
```

真实 secret/config 只进加密私有归档，不放进给其他 AI 的分享包。

### 快照校验
对归档生成：
```text
SHA256
file manifest
timestamp
version label
```

manifest 记录版本、路径和 hash，不记录 secret 值。


## 17. 给 V0.2 总管规划 AI 的强约束

把以下视为**稳定基线**，不是重新审查对象：

- Pi = 中枢；
- Windows = 受控执行节点；
- Feishu = 当前主入口；
- OpenClaw main = Autumn；
- Hermes = 独立副 Agent；
- Tailscale 主链路；
- Windows D盘边界；
- Windows arbitrary shell 禁止；
- Pi local shell 允许；
- Windows file return 已工作；
- Reminder / Web / Feishu 原生优先；
- `deadline_doc_sync` 不动；
- 已 PASS 阶段不重新打开。

V0.2 规划原则：
1. 先查 OpenClaw 原生能力；
2. 再决定是否自研；
3. 优先真实日用价值；
4. 不为了安全洁癖破坏可用性；
5. Pi 与 Windows 继续差异化授权；
6. 每个新功能定义用户场景、风险、确认方式、最小实现、验收、rollback；
7. 内部命名迁移不要顺手夹进其他功能。


## 18. V0.2 规划 AI 应先回答

1. 当前日用闭环最大的缺口是什么？
2. Voice、Smart Home、Codex、更多 Windows 程序，哪个单位成本价值最高？
3. 哪些 OpenClaw 已原生具备？
4. 哪些需要额外硬件？
5. 哪些会改变当前安全模型？
6. 哪些适合拆成 V0.2.x？
7. 是否先做语音 MVP，而不是完整语音系统？
8. 中文名 / 内部命名迁移是否值得现在做？
9. 如何确保始终可以 rollback 到 V0.1？
10. V0.2 的完成定义是什么？


## 19. 最终结论

# AUTUMN V0.1 · AFTERGLOW — RELEASE READY

V0.1 已形成完整日用闭环：

```text
自然语言
→ Autumn
→ OpenClaw 原生能力 / Windows 专用能力
→ 执行
→ 飞书返回
```

已经能稳定覆盖：

```text
问
查
提醒
看电脑
找文件
跑批准程序
把 Windows 文件发到飞书
```

同时保留明确边界：

```text
Pi 可以通用执行
Windows 严格受控
Hermes 独立
高风险能力没有提前开放
```

V0.1 到此冻结，不再追加功能。

后续问题不再是“V0.1 还缺什么”，而是：

> **Autumn V0.2 应该让 Autumn 从“已经能用”进化成什么？**
