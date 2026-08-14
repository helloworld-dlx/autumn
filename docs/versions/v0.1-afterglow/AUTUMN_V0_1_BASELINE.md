# Autumn V0.1 · Afterglow — Baseline Manifest

## Version

- **Version**: Autumn V0.1 · Afterglow
- **Snapshot ID**: Autumn_V0.1_Afterglow_2026-08-07
- **Date**: 2026-08-07
- **OpenClaw Version**: 2026.6.1 (2e08f0f)

## Infrastructure Roles

| Node | Role |
|------|------|
| Raspberry Pi 5 | Primary AI agent host / OpenClaw main / LAN dashboard |
| Windows Runner | Secondary compute node / Windows-specific tool execution |
| Feishu | Primary user messaging channel |

## Network Endpoints

| Service | Value |
|---------|-------|
| OpenClaw Gateway Port | 18789 |
| OpenClaw Dashboard | http://192.168.2.147:18789/ |
| Jarvis Bridge Listen | 127.0.0.1:27901 (Pi) |
| Jarvis Runner Base | http://100.84.13.42:27891 (Windows) |
| Bridge Token Path | ~/.config/jarvis-bridge/bridge_local.token |
| Runner Auth Key Path | ~/.config/jarvis-bridge/runner_auth.key |

## Jarvis Bridge — Allowed Actions (7 total)

| Action | Purpose |
|--------|---------|
| system.ping | Check Windows Runner online |
| system.info | Static Windows metadata |
| system.status | Live CPU/memory/battery/disk |
| files.list_directory | Read-only D:\ directory listing |
| files.search | Filename search on D:\ |
| program.list | Query allowed programs |
| program.run | Execute whitelisted program only |

**Security boundary**: No script path, argv, command, shell, environment, working_directory, or arbitrary Python execution.

## File Transfer Pipeline

| Step | Component |
|------|-----------|
| Windows → Pi | jarvis_bridge.cli file-pull (HTTP, authenticated) |
| Pi Staging | ~/.openclaw/workspace/upload/windows-transfer/<tid>/ |
| Pi → Feishu | lark-cli im messages-send (bot identity) |
| Cleanup | Automatic after send (staging + Bridge transfer record) |

## Windows File Sender Skill

- **Path**: ~/.openclaw/workspace/skills/windows-file-sender/
- **Script**: send.sh
- **Trigger**: D老师 explicit file request only
- **Recipient**: Fixed — D老师 personal Feishu (<REDACTED_PRIVATE_RECIPIENT_ID>)
- **Transfer IDs**: Bridged via jarvis_bridge file-pull, staged locally, sent via lark-cli

## Lark CLI

- **Version**: 1.0.23
- **Path**: /usr/bin/lark-cli
- **Feishu Sending**: READY (bot identity, direct chat)

## Cron / Reminder

- **Status**: READY
- **Implementation**: OpenClaw native cron (systemd user service)
- **Session targets**: main (systemEvent), isolated (agentTurn), current
- **Schedule types**: at, every, cron

## Web

- **Status**: READY
- **Capabilities**: web_search, web_fetch

## Windows Security Boundary

- **Arbitrary CMD/PowerShell/Python/Shell**: FORBIDDEN
- **Allowed path**: jarvis_* structured tools + jarvis_program_run (whitelist)
- **Whitelisted programs**: hello_jarvis

## Pi Shell Policy

- **exec tool**: ALLOWED on Pi
- **Operations**: mkdir, cp, shell commands, npm, git, etc.

## Hermes Isolation

- Autumn does NOT read, reference, or modify Hermes SOUL, memory, or private files
- No automatic cross-agent private content sync
- Hermes retains independent workspace at /home/xyzlh/.hermes/

## Protected Items

- deadline_doc_sync: NOT modified
- Hermes workspace: NOT accessed
- Windows Runner source: NOT modified
- Bridge source: NOT modified
- OpenClaw plugin source: NOT modified
- Task Scheduler XML: NOT modified
- Tailscale config: NOT modified

## Intentional Ignores

- lark-cli update notice (1.0.85 available vs 1.0.23 current)
- Duplicate plugin / migrated sidecar warnings
- Pre-V0.1 non-critical diagnostic warnings
