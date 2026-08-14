# Autumn V0.2 Phase 2B-5B — Final Acceptance

**Date:** 2026-08-12  
**PHASE2B_5A_RUNNER_EMERGENCY_STOP:** PASS / FROZEN  
**PHASE2B_5B_PI_EMERGENCY_STOP:** PASS / FROZEN

## Accepted Contract

- Runner is the sole persistent owner of `workers_paused`.
- Production routes are `POST /v1/workers/status`, `/pause`, `/resume`.
- Pause gate runs before Job creation, Codex authorization consumption, staging, or process launch.
- Running jobs use existing backend cancel on a best-effort basis.
- status/result/cancel remain available; resume is explicit only; Router never auto-resumes.
- OpenClaw effective tools include `worker_control_status`, `worker_emergency_stop`, `worker_resume` plus existing Worker tools.

## Production E2E

Canonical chain:

`OpenClaw plugin → Pi Bridge 127.0.0.1:27901 → Tailscale → Windows Runner 100.84.13.42:27891`

Final acceptance sequence completed:

1. status returned `workers_paused=false`;
2. pause returned `workers_paused=true`;
3. immediate status returned `true`;
4. harmless Direct `git status` submit was rejected with `WORKERS_PAUSED` and no job was started;
5. explicit resume returned `false`;
6. final status returned `workers_paused=false`.

No Codex job ran while paused. Final production state is `workers_paused=false`.

## Known Minor Observation

One earlier run observed a single immediate status read of `false` after emergency_stop returned `true`. It was not reproduced in final acceptance. Bridge status, the paused submit rejection, and explicit resume prove the safety gate. Keep as MINOR BACKLOG unless a Worker can actually start while paused.

## Scope

No OpenCode implementation. OpenCode Worker is **DEFERRED TO V0.3 / APPROVED SCOPE CHANGE**. Complexity Gate remains **DEFERRED**. No Router redesign.

## Verdict

`PHASE2B_5B_PI_EMERGENCY_STOP = PASS / CLOSED / FROZEN`
