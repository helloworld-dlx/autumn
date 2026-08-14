# Autumn

> I am here.

Autumn 是一个运行在多设备之间的个人 AI assistant：在 Raspberry Pi 5 上负责 Core，在 Windows 上负责受控执行，在 Xiaomi 15 上提供 Companion / mobile node 能力。

当前开发版本：**V0.3 · Presence**  
冻结基线：**V0.2 · One Autumn — PASS / CLOSED / FROZEN**

## Version history

- **V0.1 · Afterglow** — “I can act.”
- **V0.2 · One Autumn** — “I can handle it.”（PASS / CLOSED / FROZEN）
- **V0.3 · Presence** — “I am here.”（CURRENT；本仓库尚未宣称 V0.3 已实现）

## 当前能力

Autumn 当前拥有冻结的 One Autumn 路由、Hermes 隔离通路、Pi Bridge、受控 Windows Runner、Direct Worker、Codex Worker 的 CREATE/MODIFY 授权链、Emergency Stop，以及 Portable Voice / PWA 私有路径。详细状态见 [docs/current/CURRENT_STATUS.md](docs/current/CURRENT_STATUS.md)。

## 核心架构

`Feishu/user → OpenClaw/Autumn on Raspberry Pi 5 → Pi Bridge → Tailscale → Windows execution node`

Xiaomi 15 是 Companion / mobile node。Autumn 的用户体验保持 One Autumn；具体 authority 和工具边界见 [AGENTS.md](docs/current/AGENTS.md) 与 [TOOLS.md](docs/current/TOOLS.md)。

## Security boundary

- raw shell denied；Windows authority 外的 `C:\` 路径拒绝。
- Delete / L5 denied。
- Python / Node 只能走 structured L3，当前为 `AUTHORIZATION_REQUIRED`。
- secrets、private memory、sessions、runtime state 永不提交 Git。

完整边界见 [AGENTS.md](docs/current/AGENTS.md)、[TOOLS.md](docs/current/TOOLS.md) 和 [MIGRATION_BOUNDARY.md](docs/architecture/MIGRATION_BOUNDARY.md)。

## Git repository 与 production

本仓库是 **source + docs + deploy templates**，不是完整的 live Autumn state。生产文件仍在 Pi 和 Windows 的原位置运行；live secrets、sessions、memory、device-local state 不进入 Git。因此 `git clone` 不等于完整恢复个人 Autumn。

未来目标流程为：

`git clone → bootstrap → import secrets → restore state → autumn doctor`

`ONE_COMMAND_RESTORE = FUTURE / NOT_YET`。本轮不实现 bootstrap、restore 或部署迁移。

## Repository layout

- `core/pi/`：Autumn 自研 plugins 与 helpers
- `bridge/pi/`：Pi Bridge
- `nodes/windows/`：Windows Runner、Bridge 与 tests
- `voice/pwa/`：Portable Voice Bridge / PWA
- `deploy/systemd/`：非敏感 systemd templates
- `docs/current/`：当前 canonical 状态
- `docs/versions/`：按版本保存的 canonical 文档
- `docs/architecture/`：跨版本架构与迁移边界
- `docs/decisions/`：长期有效的 decision records

## Development workflow

先阅读当前文档，确认变更只属于明确 scope；在对应源码位置修改并验证；再同步必要的 source/docs 快照，检查 secrets boundary，使用清晰的 Git commit 推送。生产 runtime、配置和冻结实现保持原位置，不由 `git clone` 自动覆盖。
