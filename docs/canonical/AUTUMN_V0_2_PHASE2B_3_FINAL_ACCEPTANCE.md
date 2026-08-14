# Autumn V0.2 Phase 2B-3 FINAL ACCEPTANCE

**Date:** 2026-08-11
**Author:** Autumn
**Status:** ✅ PASS / FROZEN

---

## Executive Summary

**PHASE 2B-3B-R3 PAYLOAD RECONCILIATION = PASS**

The OpenClaw `worker_submit` pipeline was failing because the plugin's `type=process` branch generated a different payload than the Runner's expected contract. Exact payload diff revealed 3 missing fields and 1 incorrect default. Fixing those fields in the plugin (no Bridge changes, no Runner changes) made the pipeline work end-to-end.

Both required E2E validations now pass:
- Generic Git via OpenClaw → succeeded ✅
- Python L3 authority gate → AUTHORIZATION_REQUIRED ✅

---

## 1. Health Check

| Check | Result |
|-------|--------|
| Gateway health | ✅ `{"ok":true,"status":"live"}` port 18789 |
| Bridge health | ✅ `jarvis_ping` → pong |
| Runner health | ✅ `system.ping` → pong, `runner_version: 0.1.0` |

No restarts performed except Gateway reload after plugin deploy.

---

## 2. E2E A — Generic Git OpenClaw E2E

**Objective:** `git status` in `D:\majorpath` via OpenClaw `worker_submit`

**PASS ✅**

```
submit_job -> HTTP 200, job_id: ce61ead8-105f-4492-af05-9aa3e85c1eb8
job_status -> succeeded (exit_code: 0)
job_result -> process completed, exit_code: 0
```

Full chain verified:
`OpenClaw worker_submit → Bridge → Runner /v1/jobs/submit → General ProcessJobSpec → Executable Catalog (git) → succeeded`

---

## 3. E2E B — Python Authority Gate

**Objective:** Python process request returns `AUTHORIZATION_REQUIRED` (Python minimum authority = L3)

**PASS ✅**

```
submit_job(python) -> HTTP 403, error_code: AUTHORIZATION_REQUIRED
```

Runner correctly blocks Python at L3 without user credentials. No actual execution occurs.

---

## 4. Payload Reconciliation (Root Cause)

### A. Known-Good Runner Arguments (from prior successful production run)

```json
{
  "backend": "direct",
  "type": "process",
  "executable": "git",
  "arguments": ["status"],
  "cwd": "D:\\majorpath",
  "timeout": 10,
  "write_scope": "none",
  "network_policy": "none"
}
```

### B. Failing worker_submit Runner Arguments (before fix)

```json
{
  "type": "process",
  "executable": "git",
  "arguments": ["status"],
  "cwd": "D:\\majorpath"
}
```

### C. Exact Diff

| FIELD | KNOWN_GOOD | WORKER_SUBMIT | MATCH |
|-------|-----------|---------------|-------|
| backend | `"direct"` | MISSING | ❌ |
| type | `"process"` | `"process"` | ✅ |
| executable | `"git"` | `"git"` | ✅ |
| arguments | `["status"]` | `["status"]` | ✅ |
| cwd | `"D:\\majorpath"` | `"D:\\majorpath"` | ✅ |
| timeout | `10` | MISSING | ❌ |
| write_scope | `"none"` | MISSING | ❌ |
| network_policy | `"none"` | MISSING | ❌ |

**Root cause:** Plugin's `type=process` branch only forwarded `cwd` and `timeout` (conditionally), and omitted `backend`, `write_scope`, and `network_policy` entirely. Runner's exact-key validator requires all 8 fields.

### D. Root Cause Classification

**NOT** "Runner rejects all type=process." Runner's generic job admission works correctly — proven by prior production git status success. The failure was entirely in the OpenClaw plugin's payload generation.

---

## 5. Files Changed

| File | Change |
|------|--------|
| `plugins/jarvis-bridge-tool/dist/index.js` | Fixed `type=process` payload mapping: added `backend: "direct"`, `write_scope: "none"`, `network_policy: "none"`, default `timeout: 10` |

**Backup:** `plugins/jarvis-bridge-tool/dist/index.js.bak.phase2b3b_r3`

**Bridge:** No changes (pure passthrough, confirmed correct)

**Runner:** No changes (frozen per D老师 instruction)

---

## 6. Services Restarted

| Service | Restarted | Notes |
|---------|-----------|-------|
| OpenClaw Gateway | Yes | `openclaw gateway restart` after plugin deploy |
| jarvis-bridge | No | Not restarted |
| Windows Runner | No | Zero Runner changes/restarts |

---

## 7. Production Chain (confirmed)

```
Autumn
→ worker_submit (OpenClaw plugin, fixed payload)
→ callBridgeJob("submit", jobPayload)
→ Bridge: fetch POST http://127.0.0.1:27901/jobs/submit
→ Bridge → Runner signed envelope
→ Runner /v1/jobs/submit
→ General ProcessJobSpec exact-key validation
→ Executable Catalog (git)
→ JobStore + ProcessSupervisor
→ DirectProcessWorkerService
→ Job result
```

---

## 8. Canonical Contract

**Executable Catalog:**
- `7zip` = supported
- `git` = supported
- `python` = supported / L3 gated
- `node` = supported / L3 gated
- everything else = unavailable

**Policy:**
- adding simple executable requires new Worker system = NO
- program-specific Bridge policy = NO
- program-specific OpenClaw tools = NO
- legacy jarvis_* intact = YES
- raw shell = forbidden
- caller executable path = forbidden
- delete hard deny = intact
- L5 deny = intact

**Required payload fields for `type=process`:**
`backend`, `type`, `executable`, `arguments`, `cwd`, `timeout`, `write_scope`, `network_policy`

---

## 9. Conclusion

**PHASE2B_3B = PASS / FROZEN**
**PHASE2B_3 = PASS / FROZEN**

Phase 2B is complete. The OpenClaw → Bridge → Runner pipeline for generic process jobs now works correctly. The fix was entirely in the OpenClaw plugin payload generation — no Bridge or Runner changes required.

The prior blocker description ("Runner rejects all type=process") was inaccurate. The Runner's job admission is correct; the OpenClaw plugin was sending an incomplete payload.

---

## 10. What Was NOT Done

- Phase 2B-4
- OpenCode Worker
- Codex Worker
- Any Windows Runner modification
- Any Bridge modification
