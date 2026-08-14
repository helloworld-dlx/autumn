# Autumn V0.2 · One Autumn — Current Status

**As of:** 2026-08-14  
**AUTUMN_V0_2_ONE_AUTUMN:** PASS / CLOSED / FROZEN  
**PHASE2B:** PASS / CLOSED / FROZEN  
**PHASE2C:** PASS / CLOSED / FROZEN  
**READY_FOR_AUTUMN_V0_3:** YES

**PHASE3A-1:** PASS / CLOSED
**PHASE3A-2:** PASS / CLOSED — Pi in-memory Node Registry Core; loopback `GET /v1/nodes` and `GET /v1/nodes/pi5-core`; Windows/Xiaomi adapters remain deferred.
**PHASE3A-3:** PASS / CLOSED — Pi-side read-only Runner health probe registers `windows-main`; Xiaomi adapter remains deferred.
**PHASE3A-4:** PASS / CLOSED — activity-based Xiaomi 15 presence registers `xiaomi15` as `RECENT`; no periodic phone heartbeat.
**PHASE3A-5:** PASS / CLOSED — `autumn_nodes` reads live Pi Registry only; Windows presence probe is 60s with 180s TTL.
**PHASE3A:** PASS / CLOSED / FROZEN — active Nodes: `pi5-core`, `windows-main`, `xiaomi15`; Pi4, Xiaomi Home, earbuds, Camera/Eyes and future realtime voice remain deferred.
**PHASE3B-0B1:** PASS / CLOSED — Companion Main conversation is stable at `agent:main:companion:main`; Voice runtime IDs no longer create Gateway Voice session identities.
**PHASE3B-0B2:** BLOCKED — offline Companion shell, real health state and Voice recovery passed; Xiaomi 15 Tailscale handoff result is C (no app launch/connection), so silent/on-demand Connect needs separate recon before closure.
**PHASE3B-0C1:** PASS / CLOSED — session hygiene manifest completed; Scope A was approved for official orphan cleanup, while legacy test-session deletion remains deferred by authority and non-blocking.
**PHASE3B-0C2-SCOPE-A:** PASS / CLOSED — 417 unreferenced artifacts removed; OpenClaw reported 393,022,980 bytes reclaimed; physical JSONL decreased from 386 to 167.
**PHASE3B-0C2-SCOPE-B:** DEFERRED / NON-BLOCKING — 8 clearly test-named Voice sessions remain pending `operator.admin`/`operator.pairing` authority; 20 UUID Voice sessions are KEEP.
**PHASE3B-0C:** PASS / CLOSED — Companion session hygiene closure reconciled without changing Gateway authority or deleting user UUID sessions.

## Current Product Truth

用户正常只面对 Autumn。Router Lite 仅使用现有 context/tool rules，不存在 router service、classifier 或 classifier JSON。决策顺序为 Emergency Stop → explicit Hermes → self-answer → Direct Worker → Codex Worker。

| Capability | Current status |
| --- | --- |
| Model Routing / Repair B | PASS / FROZEN；`heartbeat.every="0m"`，`contextInjection="continuation-skip"`，`fallback=[]`，DeepSeek manual-only |
| Hermes Consult / Session / explicit routing | PASS / FROZEN；Autumn 不直接读取 Hermes private files |
| Job Core | PASS / FROZEN；Runner owns lifecycle/process/timeout/cancel/result；terminal irreversible；TTL/restart/atomic persistence intact |
| Direct Worker | PASS / FROZEN；Git/7zip catalog；production bounded stdout/stderr/exit_code result |
| Windows D: Search | PASS / FROZEN；Everything ES fixed-argv filename/path metadata backend；D: result revalidation；no content search；C: `PATH_NOT_ALLOWED` |
| Codex Worker | PASS / FROZEN；exact L3 authorization；Runner staging；production CREATE + MODIFY E2E |
| Emergency Stop | PASS / FROZEN；Runner + Pi/OpenClaw production E2E；persistent pause；explicit resume only |
| Headless Runner | PASS / FROZEN；single `100.84.13.42:27891` listener；hidden startup chain |
| Router Lite | PASS / FROZEN；One Autumn UX；无独立 Router service |
| Portable Voice / Phase 2C | PASS / CLOSED / FROZEN；Quick + Continuous，共用既有 Gateway、Fast Mode、STT/TTS 链路；无硬 turn limit |
| Python / Node | AUTHORIZATION_REQUIRED；production execution authorization path incomplete，不承诺确认后执行 |
| OpenCode Worker | DEFERRED TO V0.3 — APPROVED SCOPE CHANGE；不是 PASS/不是 blocker |
| Complexity Gate | DEFERRED；不是 PASS |

## Production Topology

`Feishu/user → OpenClaw/Autumn on Pi → Pi Bridge 127.0.0.1:27901 → Tailscale → Windows Runner 100.84.13.42:27891`

## Release Closure Evidence

- Existing Phase 2B production evidence remains accepted: Runner health/single listener, Direct production results, Emergency Stop false → true → `WORKERS_PAUSED` → explicit resume → false, Codex authorization smoke stopped at pending, and frozen Runner/Bridge regressions.
- Existing Phase 2C acceptance remains accepted: Quick Voice, Continuous Voice, session continuity, no hard turn cap, Fast Mode, PWA/Tailscale boundary, and static/health checks.
- Everything D: filename/path search production route passed through the real Pi → Bridge → Windows path; C: rejection is `PATH_NOT_ALLOWED`.
- `SEARCH_TO_FEISHU_FILE_RETURN_RECHECK = NOT_REVERIFIED / KNOWN_OPERATIONAL_FAILURE`: search and selection succeeded, existing sender was invoked, helper exited 1, output was intentionally suppressed, valid lark-cli token was observed, no root cause/regression was confirmed, and no retry was performed. Historical accepted file-return evidence remains available; this is non-blocking for V0.2.

## Frozen / Deferred

- `deadline_doc_sync`: UNCHANGED.
- Direct stdout propagation, Emergency Stop, Router Lite, Codex CREATE/MODIFY and Portable Voice: FROZEN.
- OpenCode Worker: DEFERRED TO V0.3 BY APPROVED SCOPE CHANGE.
- Complexity Gate: DEFERRED.
- `open_app`: deferred P1/later; natural barge-in, realtime Voice runtime and Voice + Eyes fusion: V0.3; Wake Word and Ambient Mic: not V0.2.
- No V0.3 implementation is authorized by this status.

Canonical release record: `AUTUMN_V0_2_FINAL_ACCEPTANCE.md`.
