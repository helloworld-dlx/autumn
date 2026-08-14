# JARVIS Bridge Phase 2A
最小、同步、只读的树莓派 loopback Bridge。仅 `127.0.0.1:27901`、`GET /v1/health` 和本地 token 认证的 `POST /v1/execute`；生成 Runner 1.0 HMAC 请求并调用 Tailscale Runner。没有 OpenClaw、飞书、SQLite、队列、重试、服务化、文件发送或 Python/CMD action。
