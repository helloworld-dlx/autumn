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

`READY_FOR_AUTUMN_V0_3 = YES`. `READY_FOR_PHASE3C = YES`. V0.3 Phase 3B Companion Presence and `PHASE3B_POSTFREEZE_UI_PATCH` are **PASS / CLOSED / FROZEN** (2026-08-16): exact Conversation continuation, current-chat Windows file return, bounded generated artifacts, viewport-contained Chat scrolling, Home Node status alignment, Auto/System dynamic theme, PWA shell v7, and main memory index recovery are accepted. The known Xiaomi Tailscale handoff diagnostic remains non-blocking and deferred; it is not silently reclassified as PASS.

### V0.3 Phase 3C-2 — Voice Stability

**Status:** PASS / CLOSED / FROZEN

Stability-first Voice Bridge delivery: at most one early speech prefix per turn, final audio limited to a proven non-overlapping remainder, existing full-TTS fallback retained, and Presence assertions fail closed without reliable `autumn_nodes` evidence. Exact Companion conversation, Fast Mode, existing permissions, and frozen V0.2/3A/3B contracts remain unchanged. No latency number is claimed and no Presence fast path was added.

### V0.3 Phase 3C-3 — Natural Barge-in

**Status:** PASS / CLOSED / FROZEN

Continuous Voice now supports stability-first browser-side Natural Barge-in: speaking activity ducks playback, confirmed sustained speech invalidates the current generation, clears old playback, and continues the next utterance in the same exact Companion conversation. Quick Voice remains single-turn. Stop, stale-generation protection, fallback, Fast Mode, and the existing service topology remain unchanged.

Streaming text is retained. Aggressive Streaming TTS and further latency optimization are optional future work, not acceptance requirements. The MiniMax tool-selection / `autumn_nodes` issue is an independent Autumn Core Tool Selection backlog item and does not block Phase 3C Voice closure.

Any OpenCode Worker, Complexity Gate, Phase 3D, or Phase 3E work requires a new, explicit scope and acceptance plan. The V0.2 and frozen Phase 3B contracts remain unchanged unless separately authorized.
