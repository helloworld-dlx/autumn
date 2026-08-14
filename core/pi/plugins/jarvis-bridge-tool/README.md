# Jarvis Bridge Tool (OpenClaw Plugin)

Local OpenClaw tool plugin. Exposes the existing fixed Bridge tools plus one
read-only Node Registry observation tool. It
proxy to the local Jarvis Bridge running at `127.0.0.1:27901`. The Bridge itself
calls the Windows Runner. The plugin does **not** talk to the Runner directly,
does **not** spawn shells, does **not** read or write arbitrary files, and does
**not** expose the Bridge token, Runner key, or any signature/nonce.

## Tools

### `autumn_nodes`

The single Node observation tool accepts `{"action":"list"}` or
`{"action":"get","node_id":"windows-main"}` and makes only a loopback
`GET` request to the Pi Bridge Registry. It cannot touch/register a Node,
execute a capability, or change authorization. `QUERY_FAILED` means only that
the Registry query failed; it is not an offline assertion. Presence is
observational and **CAPABILITY != AUTHORIZATION**.

| Tool | Model parameters | Bridge action |
|---|---|---|
| `jarvis_ping` | `{}` | `system.ping` |
| `jarvis_system_info` | `{}` | `system.info` |
| `jarvis_system_status` | `{}` | `system.status` |
| `jarvis_list_directory` | `{ path: "D:\\dir" }` | `files.list_directory` |
| `jarvis_search_files` | `{ path, query, kind?, extensions? }` | `files.search` |

`path` must start with `D:\` (case-insensitive, Windows-style). Any other drive
letter, UNC path, device path, or URL is rejected before the Bridge call.

`query` (search_files) must be 1–200 chars and contain no NUL, `/`, `\`, or `:`.
`extensions` items must start with `.` and there must be at most 20.
`kind` must be one of `file`, `directory`, `any`.

## Hard rules enforced in code

- Bridge URL is hardcoded: `http://127.0.0.1:27901/v1/execute`. Not configurable.
- Token is read from `~/.config/jarvis-bridge/bridge_local.token` at call time.
  Token value is never logged, never returned, never persisted by the plugin.
- HTTP fetch:
  - `redirect: "manual"` (no redirects).
  - No proxy (`dispatcher` not set).
  - Timeout: 10 seconds.
  - Only POST to `/v1/execute`.
- The plugin **never** opens a socket to anything except `127.0.0.1:27901`.
- The plugin contains **no** `child_process`, `spawn`, `exec`, `shell`, `eval`,
  `Function(...)`, dynamic `import()` of user-supplied paths, or arbitrary fs
  reads/writes. The only fs read in the entire plugin is the Bridge token file.

## Files

```
package.json
openclaw.plugin.json
dist/index.js              # plugin entry; ESM
README.md
.gitignore
node_modules/              # local symlinks (openclaw, typebox) — no internet
```

## Build

This plugin is plain JavaScript (no TypeScript build step). All imports resolve
from the symlinked `node_modules/`.

## Install

```bash
openclaw plugins install --link \
  /home/xyzlh/.openclaw/workspace/plugins/jarvis-bridge-tool

openclaw plugins enable jarvis-bridge-tool
openclaw plugins validate --root /home/xyzlh/.openclaw/workspace/plugins/jarvis-bridge-tool \
                        --entry ./dist/index.js
```

Restart OpenClaw Gateway once after install/enable to load the new tools.
