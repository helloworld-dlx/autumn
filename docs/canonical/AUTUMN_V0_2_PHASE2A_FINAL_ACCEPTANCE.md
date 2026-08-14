# Autumn V0.2 Phase 2A Final Acceptance

accepted_at: 2026-08-10T10:46:22+08:00
status: PASS / FROZEN

## Scope

This acceptance freezes the Phase 2A implementation already validated in production:

- Hermes Consult
- Hermes Session
- Continuity Lite
- Commitment Memory Lite
- Proactive Completion

This pass used current canonical static checks, offline fixtures, contract tests, and minimal health smoke only. It did not issue a real MiniMax request, start a real Hermes conversation, create a Commitment or reminder, send a notification, start Phase 2B, or modify Repair B.

## Architecture Summary

### Model routing

- Autumn default: `minimax/MiniMax-M2.7`
- Automatic fallbacks: `[]`
- Subagents default: `minimax/MiniMax-M2.7`
- Subagent concurrency: `1`
- MiniMax-M3: explicit complex-task upgrade only
- DeepSeek: manual selection only

### Hermes Consult

`Autumn main -> hermes_consult -> ApiServerBackend -> 127.0.0.1:8642/v1/chat/completions -> Hermes`

- `platform_toolsets.api_server = []`
- Consult has zero Hermes tools.
- The frozen normalized result contract is unchanged.
- No provider call was made during this final acceptance.

### Hermes Session

`Autumn main -> hermes_session -> bounded Autumn-side messages[] -> /v1/session/chat/completions -> hermes-session-private`

- Actions: `start`, `message`, `end`, `status`
- Maximum user turns: `8`
- Idle expiry: `30 minutes`
- Approved Hermes tools: `memory`, `session_search`, `skills_list`, `skill_view`
- Execution, browser, arbitrary file, delegation, messaging, cron, and skill-management tools are absent from the private profile.
- `persist_session=false` blocks native session JSON, state database creation/flush, direct session-log callers, and request-debug dumps.
- Hermes MemoryStore writes remain available through the approved memory tool.

### Continuity Lite

- Canonical recent state: `memory/ACTIVE_CONTEXT.md`
- Native tools: `memory_search`, `memory_get`
- Provider: `none`
- Backend: local SQLite FTS
- Indexed sources: workspace `memory/` only
- Full memory and full Active Context are not automatically injected; retrieval is relevance-driven.
- Hermes private paths are outside the index.

### Commitment Memory

- Source of truth: `memory/COMMITMENTS.md`
- Helper: `tools/commitments.mjs`
- Actions: add, list active, get, complete, cancel
- Canonical statuses: active, completed, cancelled
- OpenClaw Cron binding: `openclaw-cron:<cron_id>`
- No legacy `cron:<cron_id>` binding remains.

### Proactive Completion

`active Commitment -> one-shot OpenClaw Cron -> isolated light-context MiniMax-M2.7 turn -> Feishu announce -> delivered event -> completed Commitment`

- One-shot and delete-after-run
- Isolated session and light context
- Minimal compatibility tool policy: `jarvis_ping` exposed; normal notification calls no tools
- Trusted Feishu target is resolved by the adapter and is not model-controllable
- Producer and completion consumer share `openclaw-cron:<cron_id>`
- Delivery success completes once; run/delivery failure leaves the Commitment active; duplicate events are idempotent

## PASS Matrix

| Component | Static/contract result | Runtime or smoke evidence | Freeze status |
| --- | --- | --- | --- |
| Model routing | M2.7 defaults, no fallback, subagent concurrency 1 | Config validated | PASS / FROZEN |
| Hermes Consult | Current contract tests pass; zero-tool API profile | Hermes health OK; prior live acceptance retained | PASS / FROZEN |
| Hermes Session | Current JS and private-profile Python tests pass | Status-only smoke: inactive, zero turns, zero provider calls | PASS / FROZEN |
| Continuity Lite | FTS index valid; relevant retrieval works | Active Context found; Hermes path count zero | PASS / FROZEN |
| Commitment Memory | Parser/helper and status fixtures pass | Canonical store indexed; legacy Cron prefix count zero | PASS / FROZEN |
| Proactive Completion | Producer/consumer and idempotency contracts pass | Prior one-shot Feishu delivery received and Commitment reconciled completed | PASS / FROZEN |

## Real Live Acceptance Evidence

- Hermes Consult and Hermes Session had already completed their bounded live acceptance before this final freeze; they were not called again here.
- Continuity retrieved the Phase 2A context from `ACTIVE_CONTEXT.md` through native local FTS.
- Commitment `CMT-20260810-001` is completed and bound to its canonical `openclaw-cron:` reference.
- The corresponding native Cron run finished `ok`, Feishu delivery was `delivered`, one message was observed, and no duplicate delivery was observed.
- The notification turn used one isolated MiniMax-M2.7 agent turn, exposed only `jarvis_ping`, made zero tool/Hermes/subagent calls, and consumed 1385 total tokens.
- Token classification: `IDEAL / ACCEPTED_FOR_V0.2`.

## Current Regression Evidence

- Hermes Consult/Session OpenClaw tests: 24/24 PASS
- Hermes private Session persistence/profile tests: 10/10 PASS
- Proactive Completion/Commitment tests: 22/22 PASS
- Canonical OpenClaw plugin/helper syntax checks: PASS
- OpenClaw config validation: PASS
- OpenClaw Gateway health: PASS
- Hermes API health: PASS
- Memory index/search health: PASS
- OpenClaw Cron scheduler health: PASS
- Feishu default channel health: PASS

## Known Limitations

- Continuity search is FTS-only. Embeddings are not enabled. This is `ACCEPTED_FOR_V0.2`.
- A notification uses one bounded light-context Agent/LLM turn. The measured 1385-token run is accepted; further token optimization is not required for V0.2.
- The isolated notification turn exposes `jarvis_ping` because this OpenClaw runtime rejects an explicit empty tool allowlist. Expected and observed notification tool calls remain zero.
- The earlier systemd/lark-cli delivery route is not the production path. Its historical acceptance artifacts remain preserved for audit; elapsed timers have no next trigger.

## Deferred Items

- systemd -> lark-cli zero-token direct delivery: `DEFERRED_OPTIMIZATION / NON_BLOCKING`
- Repair B: `DEFERRED` to a separate post-freeze repair
  - contextInjection
  - contextPruning
  - compaction
  - heartbeat optimization
  - AGENTS token hygiene
- Phase 2B Worker: not started

## Protected Items

- `deadline_doc_sync` unchanged
- Hermes private `SOUL.md`, `USER.md`, and `MEMORY.md` content unchanged by this acceptance
- Hermes backend and frozen Consult/Session contracts unchanged
- JarvisRunner, jarvis-bridge, `jarvis_*`, and `hello_jarvis` unchanged
- Repair A routing unchanged
- Existing main heartbeat remains `30m / target=none`; it was not modified
- contextInjection, contextPruning, and compaction were not modified

## Rollback References

- `backup/phase2a-8a-continuity-lite-20260809-170208`
- `backup/phase2a-8b-commitment-memory-20260809-172411`
- `backup/phase2a-9a-proactive-completion-20260809-182753`
- `backup/phase2a-9e-proactive-cron-20260810-090637`
- `backup/phase2a-9h-native-cron-repair-20260810-094641`
- `backup/phase2a-9h-closure-repair-20260810-102500`
- `backup/phase2a-10-final-freeze-20260810-104622`

Rollback must remain scoped to the affected Phase 2A file and must not overwrite later user data or protected services without a new explicit authorization.

## Next Approved Step

The next approved stage is the independent post-freeze Repair B audit/repair. Phase 2B Worker implementation has not started and requires a separate instruction.

## Final Decision

`PHASE2A_FINAL_ACCEPTANCE = PASS`

`PHASE2A = PASS / FROZEN`

`READY_FOR_REPAIR_B = yes`
