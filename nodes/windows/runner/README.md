# JARVIS Windows Runner V0.1

> Current production status (2026-08-12): the Runner is the frozen Autumn V0.2 Job/Direct/Codex/Emergency-Stop runtime at `100.84.13.42:27891`, started headlessly from `D:\JarvisWorkspace\JarvisRunner`. See `CURRENT_STATUS.md`. Historical paragraphs below describe the original V0.1/Phase 2B-3A build-up and do not override current production truth.

这是 JARVIS 的 Windows 重型执行节点安全骨架。树莓派上的 OpenClaw 负责主 Agent 决策；未来 Bridge 只会转发结构化请求；Runner 只会对已注册、受控的动作作出响应。

Phase 2B-3A-R1 保持最小 Tailscale-only HTTP/1.1 入口：仅精确绑定配置的 100.64.0.0/10 IPv4，`GET /v1/health` 返回最小健康结果，legacy `POST /v1/task` 和 `POST /v1/file` 保持原语义。现有四个 `/v1/jobs/*` 路由使用同一 HMAC 签名协议暴露 General Direct Process Worker；7-Zip archive preset 继续兼容，通用 submit 只接受 Runner catalog ID、结构化参数列表、D 盘内 cwd、受限 timeout/scope/policy。它不是公网服务，未实现 Tailscale Serve/Funnel、TLS、Bridge 或 OpenClaw 接入。

生产认证密钥的固定位置为 `D:\JarvisWorkspace\JarvisSecrets\runner_auth.key`；仓库不包含、不会生成或打印该密钥。`run-signed-request --request-json <JSON>` 仅接受完整的协议 1.0 签名请求；本地 `run-action` 仅用于开发和诊断。

## 运行

### Windows 本地验证解释器

在此机器上，先探测并优先使用已安装的 Python 3.13.5，而不是因 `.venv` 启动器报错就判定运行时缺失或安装新依赖：

```powershell
$runnerPython = 'C:\Users\丁励行\AppData\Local\Programs\Python\Python313\python.exe'
& $runnerPython --version
& $runnerPython -m unittest discover -s tests -v
```

该绝对路径是 2026-08-10 已验证的本机位置；路径和版本属于运行时事实，验证前应重新探测。若 `.venv\Scripts\python.exe` 无法找到其 base interpreter，使用上述已验证解释器执行测试即可；不要为此自动安装、升级或重建 Python/venv。

```powershell
.\.venv\Scripts\python.exe -m jarvis_runner.cli doctor
.\.venv\Scripts\python.exe -m jarvis_runner.cli selftest
.\.venv\Scripts\python.exe -m jarvis_runner.cli serve-tailscale
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m jarvis_runner.cli run-action files.list_directory --arguments-json '{"path":"D:\\JarvisWorkspace\\JarvisRunner","max_results":10}'
.\.venv\Scripts\python.exe -m jarvis_runner.cli run-action files.search --arguments-json '{"path":"D:\\JarvisWorkspace\\JarvisRunner","query":"README","extensions":[".md"]}'
```

## 安全边界

- 动作通过固定注册表白名单，不动态导入或按字符串执行函数。
- 不实现 arbitrary raw shell、任意 `cmd.exe` / `powershell.exe`、`shell=True`、下载执行或删除能力；legacy `hello_jarvis` 仍固定哈希。结构化进程只能经 Direct Worker 的 Runner-owned catalog 和 argv；用户文本不能拼接为 shell。
- `POST /v1/task` 与所有 `/v1/jobs/*` 路由在读取正文前精确限制来源 IP；只接受受长度限制的 UTF-8 JSON object、`application/json` 和非 chunked 请求。Job 路由复用 HMAC-SHA256、时间窗、request_id、nonce 与 anti-replay。连接读取超时 15 秒，响应后关闭。
- production catalog 当前包含 7-Zip、Git、Python、Node；`files.search` 在生产 D:\ 范围经固定 argv 调用 Everything ES 作为 filename/path metadata backend，且不暴露 ES flags 或内容搜索。Git 只读命令为 L1；workspace write 为 L3、network 为 L4，当前均停在授权门前；Python/Node 不是 blanket deny，最低 authority 为 L3（声明 external network 时 L4），当前仍是 `AUTHORIZATION_REQUIRED`，未因本文档或搜索修复而启用生产执行。
- 前台 `serve-tailscale` 可由 Ctrl+C 正常停止；不会修改防火墙、Tailscale 设置、服务、计划任务或创建密钥。
- 受控写入限定在 `D:\JarvisWorkspace`，并防止路径穿越与伪前缀。
- 审计日志按 `audit_max_bytes` 受控轮转，保留 `audit_backup_count` 个编号备份（默认分别为 5242880 字节和 3 个）；参数递归脱敏，不记录完整动作输出。
- 配置可选覆盖，但不读取环境变量中的密钥或令牌。
- `doctor` 使用标准库 AST 作防御性危险调用检查；它不是完整安全证明。
- 路径校验检查现存符号链接和 Windows 重解析点，但不能完全消除 TOCTOU；未来写动作须在打开文件前再次校验。
- 文件动作只返回名称、规范化路径、类型、大小和最后修改时间；`files.search` 在生产固定为 D:\ 全盘 filename/path discovery，Everything 返回路径仍逐项经 Runner D:\ 边界验证。它们有结果数、扫描数、时间和输出预算，不读取正文、不计算哈希，也不创建索引或缓存。
- `program.list` 只返回 `hello_jarvis` 的有限元数据；`program.run` 只允许使用 `D:\JarvisScripts\hello_jarvis.py`，固定 5 秒超时、无参数、无 shell，并限制 stdout/stderr 各 8192 字节。
- 在加入任何有副作用动作前，必须设计“执行前审计意图 + 执行后结果”的机制。

## 后续阶段

后续须经过单独审查和授权，才可能加入文件候选选择、一次确认后向用户自己的飞书回传、Bridge 的认证网络接口、有限 CMD 白名单及服务化；这些能力均不属于当前版本。
