# Autumn Roadmap

## V0.2 — One Autumn

**Status:** PASS / CLOSED / FROZEN (2026-08-12)

Frozen scope: model routing and Repair B, Hermes Consult/Session, Job Core, Direct Worker with bounded output, Codex Worker CREATE/MODIFY staging flow, Emergency Stop, headless Runner, and Router Lite.

## V0.2 Phase 2C — Portable Voice

**Status:** PASS / CLOSED / FROZEN (2026-08-13)

Quick Voice and Continuous Voice share the existing SiliconFlow STT to Autumn agent:main Fast Mode to MiniMax TTS path. Continuous Voice has no product turn cap; it ends through Stop, idle timeout or explicit session end. Android open_app is deferred until a separately approved native/deep-link path. See PHASE2C_FINAL_ACCEPTANCE_REPORT.md.

## Approved Scope Changes

- **OpenCode Worker:** DEFERRED TO V0.3 by approved scope change. It was part of the earlier V0.2 plan; it is not retroactively reclassified, not PASS, and not a V0.2 blocker.
- **Complexity Gate:** DEFERRED. It is not PASS and must not be reopened as part of V0.2 closure.

## V0.3 Entry Boundary

`READY_FOR_AUTUMN_V0_3 = YES`. V0.3 Phase 3B Companion Presence is **PASS / CLOSED / FROZEN** (2026-08-16): exact Conversation continuation, current-chat Windows file return, bounded generated artifacts, PWA shell v6, and main memory index recovery are accepted. The known Xiaomi Tailscale handoff diagnostic remains non-blocking and deferred; it is not silently reclassified as PASS.

Do not start Phase 3C. Any OpenCode Worker or Complexity Gate work requires a new, explicit scope and acceptance plan. The V0.2 and frozen Phase 3B contracts must remain unchanged unless separately authorized.
