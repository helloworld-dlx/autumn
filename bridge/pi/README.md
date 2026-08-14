# JARVIS Bridge (Autumn)
树莓派 loopback Bridge。固定监听 `127.0.0.1:27901`，使用本地 token 接受 legacy execute、Job、Codex authorization 与 Worker control 路由，并生成 Runner 1.0 HMAC 请求转发到 Tailscale Runner。Bridge 不拥有 Job、authorization 或 pause 状态，不执行命令，不自动重试。

## 当前阶段
Autumn V0.2 Final Acceptance：Bridge 保持透明转发边界；legacy `/v1/execute` 仍只放行 7 个合法 action，Phase 2B 路由使用独立 namespace：

| # | Action | 说明 |
|---|--------|------|
| 1 | `system.ping` | Runner 健康探针 |
| 2 | `system.info`  | 主机/系统信息 |
| 3 | `system.status`| 实时状态（CPU/内存/磁盘/电池/运行时长）|
| 4 | `files.list_directory` | 列目录 |
| 5 | `files.search` | 文件名/关键词检索 |
| 6 | `program.list` | 列出 Runner 注册的程序 |
| 7 | `program.run`  | 以 `{"program_id": "..."}` 运行已注册程序 |

## 不变项
- 监听地址：`127.0.0.1:27901`
- Production Runner 地址：`http://100.84.13.42:27891`（canonical Tailscale target）
- HMAC 协议：`protocol_version 1.0`，`key_id=running-local-v1`，60 秒 nonce/request_id 有效期
- 本地 token 路径：`~/.config/jarvis-bridge/bridge_local.token`
- 包名 / 服务名 / Header / 协议字段 暂不迁移

## Bridge 转发边界（强制）
- Bridge 只做透明转发；不解析、不执行、不重试。
- Bridge 不接受：`script_path`、`code`、`argv`、`command`、`shell`、`environment`、`working_directory`。
- Bridge 不生成 Python 命令，不解析或执行程序。
- `program.run` 失败一次即返回 `RUNNER_TIMEOUT` / `RUNNER_OFFLINE`，**不会自动重试**。
- 未登记 action（含历史 `raw.command`）由 Bridge 在 `ACTION_NOT_ALLOWED` 拒绝。

Phase 2B routes: `/v1/jobs/submit|status|cancel|result`、`/v1/authorizations/request|approve`、`/v1/workers/status|pause|resume`。这些路由各自做本地 token 检查后原样签名转发，不扩展 legacy `ACTIONS`。

## CLI
```
python -m jarvis_bridge.cli doctor
python -m jarvis_bridge.cli selftest
python -m jarvis_bridge.cli serve
python -m jarvis_bridge.cli call --action program.list --arguments-json '{}'
python -m jarvis_bridge.cli call --action program.run --arguments-json '{"program_id":"hello_jarvis"}'
```

## 测试
```
python -m unittest discover -s tests -v
```
