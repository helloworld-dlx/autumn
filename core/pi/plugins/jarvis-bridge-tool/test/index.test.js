// jarvis-bridge-tool test suite (Phase 3A-3)
//
// Uses node:test (built-in, no new deps).  Each test injects a
// fake fetch via the deps parameter of the exported exec* functions
// so no real HTTP call ever reaches the Bridge.  Hook logic is tested
// by directly invoking the exported handler factory.

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import pluginEntry, {
  ALLOWED_PROGRAM_IDS,
  FORBIDDEN_RUN_KEYS,
  PROGRAM_RUN_APPROVAL_TIMEOUT_MS,
  RUN_PROGRAM_ID,
  PROGRAM_RUN_TOOL_NAME,
  callBridge,
  execPing,
  execSystemInfo,
  execSystemStatus,
  execListDirectory,
  execSearchFiles,
  execProgramList,
  execProgramRun,
  createProgramRunBeforeHookHandler,
} from "../dist/index.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = resolve(HERE, "..");

// ── helpers ──────────────────────────────────────────────────────────

function captureRegisterApi() {
  const api = {
    registeredTools: [],
    registeredHooks: {},
    pluginConfig: {},
  };
  api.registerTool = (tool, opts) => {
    api.registeredTools.push({ tool, opts });
  };
  api.on = (name, handler, opts) => {
    api.registeredHooks[name] = api.registeredHooks[name] || [];
    api.registeredHooks[name].push({ handler, opts });
  };
  return api;
}

function loadPlugin() {
  const api = captureRegisterApi();
  assert.equal(typeof pluginEntry.register, "function", "plugin entry has register");
  pluginEntry.register(api);
  return api;
}

function jsonResponse(status, payload, extraHeaders = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json", ...extraHeaders },
  });
}

function makeFakeFetch(responses) {
  const calls = [];
  async function fakeFetch(url, init) {
    calls.push({ url, init });
    if (responses.length === 0)
      return new Response('{"error":"no_response_queued"}', { status: 500 });
    return responses.shift();
  }
  return { fakeFetch, calls };
}

/** Call exec* with a fully-mocked Bridge. */
const DEPS_NO_TOKEN = Object.freeze({ readToken: () => null });
function deps(fakeFetch) {
  return { ...DEPS_NO_TOKEN, fetch: fakeFetch };
}

// ── 1. tool count + manifest parity + 15. old-tool regression ────────

test("tool registry has exactly seven tools and manifest matches", () => {
  const api = loadPlugin();
  const names = api.registeredTools.map((t) => t.tool.name).sort();
  assert.deepEqual(names, [
    "jarvis_list_directory",
    "jarvis_ping",
    "jarvis_program_list",
    "jarvis_program_run",
    "jarvis_search_files",
    "jarvis_system_info",
    "jarvis_system_status",
  ]);
  assert.equal(api.registeredTools.length, 7);

  const m = JSON.parse(readFileSync(join(PLUGIN_ROOT, "openclaw.plugin.json"), "utf8"));
  assert.equal(m.contracts.tools.length, 7);
  assert.deepEqual([...m.contracts.tools].sort(), names);
});

test("hook is registered exactly once", () => {
  const api = loadPlugin();
  const hooks = api.registeredHooks["before_tool_call"];
  assert.ok(Array.isArray(hooks));
  assert.equal(hooks.length, 1);
});

// ── 3/5. ProgramListSchema + ProgramList call ────────────────────────

test("jarvis_program_list receives empty-obj schema", () => {
  const api = loadPlugin();
  const s = api.registeredTools.find((t) => t.tool.name === "jarvis_program_list").tool.parameters;
  assert.equal(s.type, "object");
  assert.equal(s.additionalProperties, false);
  assert.deepEqual(s.properties, {});
});

test("jarvis_program_list calls program.list {} and returns trimmed metadata", async () => {
  const { fakeFetch, calls } = makeFakeFetch([
    jsonResponse(200, {
      result: {
        status: "ok",
        runner_request_id: "r-1",
        programs: [
          { program_id: "hello_jarvis", label: "Hello", description: "test", timeout_seconds: 5 },
        ],
      },
    }),
  ]);
  const r = await execProgramList({}, {}, deps(fakeFetch));
  assert.equal(calls.length, 1);
  const body = JSON.parse(calls[0].init.body);
  assert.equal(body.action, "program.list");
  assert.deepEqual(body.arguments, {});
  assert.equal(r.details.programs.length, 1);
  assert.equal(r.details.programs[0].program_id, "hello_jarvis");
  // no secret fields
  assert.equal(r.details.programs[0].path, undefined);
  assert.equal(r.details.programs[0].sha256, undefined);
});

// ── 5/6/7. ProgramRun param validation at both hook + execute levels ──

test("hook + execute reject unknown program_id", async () => {
  const api = loadPlugin();
  const hook = api.registeredHooks["before_tool_call"][0].handler;
  const blocked = await hook({ toolName: PROGRAM_RUN_TOOL_NAME, params: { program_id: "evil" } }, {});
  assert.equal(blocked.block, true);
  assert.equal(blocked.requireApproval, undefined);

  const r = await execProgramRun({ program_id: "evil" }, {}, {});
  assert.equal(r.details.status, "failed");
  assert.equal(r.details.reason, "unsupported_program_id");
});

test("hook + execute reject every forbidden key", async () => {
  const api = loadPlugin();
  const hook = api.registeredHooks["before_tool_call"][0].handler;
  for (const k of FORBIDDEN_RUN_KEYS) {
    const params = { program_id: "hello_jarvis", [k]: "anything" };
    const b = await hook({ toolName: PROGRAM_RUN_TOOL_NAME, params }, {});
    assert.equal(b.block, true, `hook must block ${k}`);
    assert.equal(b.requireApproval, undefined);
    const r = await execProgramRun(params, {}, {});
    assert.equal(r.details.status, "failed");
    assert.equal(r.details.reason, "forbidden_parameter");
  }
});

test("hook + execute reject extra keys", async () => {
  const api = loadPlugin();
  const hook = api.registeredHooks["before_tool_call"][0].handler;
  const b = await hook({ toolName: PROGRAM_RUN_TOOL_NAME, params: { program_id: "hello_jarvis", foo: 1 } }, {});
  assert.equal(b.block, true);
  assert.equal(b.blockReason, "unexpected_parameter_count");

  const r = await execProgramRun({ program_id: "hello_jarvis", foo: 1 }, {}, {});
  assert.equal(r.details.status, "failed");
  assert.equal(r.details.reason, "unexpected_parameter_count");
});

// ── 8. single Bridge call, no retry ──────────────────────────────────

test("successful program.run calls Bridge exactly once", async () => {
  const { fakeFetch, calls } = makeFakeFetch([
    jsonResponse(200, {
      result: {
        status: "success",
        runner_request_id: "r-ok",
        execution_status: "succeeded",
        exit_code: 0,
        timed_out: false,
        stdout: '{"ok":true,"line":"hello from jarvis"}\n',
      },
    }),
  ]);
  const r = await execProgramRun({ program_id: "hello_jarvis" }, {}, deps(fakeFetch));
  assert.equal(calls.length, 1, "exactly one Bridge call");
  const body = JSON.parse(calls[0].init.body);
  assert.equal(body.action, "program.run");
  assert.deepEqual(body.arguments, { program_id: "hello_jarvis" });
  assert.equal(r.details.status, "ok");
  assert.equal(r.details.execution_status, "succeeded");
  assert.equal(r.details.exit_code, 0);
  assert.equal(r.details.structured.ok, true);
  assert.equal(r.details.assistant_name, "Autumn");
});

// ── 9. hook only intercepts program_run ──────────────────────────────

test("hook passes through all six non-run tools", async () => {
  const api = loadPlugin();
  const hook = api.registeredHooks["before_tool_call"][0].handler;
  for (const name of [
    "jarvis_ping",
    "jarvis_system_info",
    "jarvis_system_status",
    "jarvis_list_directory",
    "jarvis_search_files",
    "jarvis_program_list",
  ]) {
    const r = await hook({ toolName: name, params: {} }, {});
    assert.equal(r, undefined, `${name} must return void`);
  }
});

// ── 10/11/12/13. approval shape (documentary + contract) ─────────────

test("requireApproval is well-formed, secret-free, and parameter-bound", async () => {
  const api = loadPlugin();
  const hook = api.registeredHooks["before_tool_call"][0].handler;
  const r = await hook({ toolName: PROGRAM_RUN_TOOL_NAME, params: { program_id: "hello_jarvis" } }, {});
  assert.ok(r);
  assert.equal(r.block, undefined);
  const a = r.requireApproval;
  assert.ok(a);
  assert.equal(a.title, "\u8fd0\u884c Autumn \u767d\u540d\u5355\u7a0b\u5e8f");
  assert.equal(a.severity, "warning");
  assert.equal(a.timeoutBehavior, "deny");
  assert.equal(a.timeoutMs, PROGRAM_RUN_APPROVAL_TIMEOUT_MS);
  assert.deepEqual(a.allowedDecisions, ["allow-once", "deny"]);
  assert.equal(a.pluginId, "jarvis-bridge-tool");
  // No secrets in description/title
  for (const leak of ["Bearer", "signature", "nonce", "token", "PATH=", "/home/xyzlh/.openclaw/secrets"])
    assert.equal(a.description.includes(leak), false, `description leaks "${leak}"`);
  // Params bound
  assert.deepEqual(r.params, { program_id: RUN_PROGRAM_ID });
});

test("approval denies allow-always, has passive observer, sets deny-on-timeout", () => {
  const api = loadPlugin();
  const hook = api.registeredHooks["before_tool_call"][0].handler;
  return hook({ toolName: PROGRAM_RUN_TOOL_NAME, params: { program_id: "hello_jarvis" } }, {}).then((r) => {
    assert.equal(r.requireApproval.allowedDecisions.includes("allow-always"), false);
    assert.equal(r.requireApproval.timeoutBehavior, "deny");
    assert.equal(typeof r.requireApproval.onResolution, "function");
  });
});

// ── 14. failure not reported as success ──────────────────────────────

test("execProgramRun fails for: runner-failed, timed-out, non-zero exit, Bridge error", async () => {
  // runner status=failed
  let { fakeFetch, calls } = makeFakeFetch([
    jsonResponse(200, { result: { status: "failed", runner_request_id: "r", execution_status: "failed", exit_code: 2, timed_out: false } }),
  ]);
  let r = await execProgramRun({ program_id: "hello_jarvis" }, {}, deps(fakeFetch));
  assert.equal(r.details.status, "failed");
  assert.equal(r.details.reason, "program_run_failed");

  // execution_status=timed_out
  ({ fakeFetch, calls } = makeFakeFetch([
    jsonResponse(200, { result: { status: "success", runner_request_id: "r2", execution_status: "timed_out", exit_code: 124, timed_out: true } }),
  ]));
  r = await execProgramRun({ program_id: "hello_jarvis" }, {}, deps(fakeFetch));
  assert.equal(r.details.status, "failed");

  // exit_code non-zero
  ({ fakeFetch, calls } = makeFakeFetch([
    jsonResponse(200, { result: { status: "success", runner_request_id: "r3", execution_status: "succeeded", exit_code: 1, timed_out: false } }),
  ]));
  r = await execProgramRun({ program_id: "hello_jarvis" }, {}, deps(fakeFetch));
  assert.equal(r.details.status, "failed");

  // Bridge non-200
  ({ fakeFetch, calls } = makeFakeFetch([
    jsonResponse(503, { error: "bridge_down", message: "Bridge offline" }),
  ]));
  r = await execProgramRun({ program_id: "hello_jarvis" }, {}, deps(fakeFetch));
  assert.equal(r.details.status, "failed");
  assert.equal(r.details.bridgeError, "bridge_down");

  // unparseable stdout but success markers → ok (not failure)
  ({ fakeFetch, calls } = makeFakeFetch([
    jsonResponse(200, { result: { status: "success", runner_request_id: "r4", execution_status: "succeeded", exit_code: 0, timed_out: false, stdout: "not json" } }),
  ]));
  r = await execProgramRun({ program_id: "hello_jarvis" }, {}, deps(fakeFetch));
  assert.equal(r.details.status, "ok");
  assert.equal(r.details.structured, null);
});

// ── 15. old five tools still functional (exec* outputs) ───────────────

test("execPing returns ok with mocked bridge", async () => {
  const { fakeFetch, calls } = makeFakeFetch([
    jsonResponse(200, { pong: true, timestamp: "2026-08-06T22:00:00Z" }),
  ]);
  const r = await execPing({}, {}, deps(fakeFetch));
  assert.equal(r.details.ok, true);
  assert.equal(r.details.bridge_status, 200);
  assert.deepEqual(r.details.payload, { pong: true, timestamp: "2026-08-06T22:00:00Z" });
  assert.equal(calls.length, 1);
  assert.equal(JSON.parse(calls[0].init.body).action, "system.ping");
});

test("execSystemInfo/Status/ListDirectory/SearchFiles all return ok shapes", async () => {
  let { fakeFetch, calls } = makeFakeFetch([
    jsonResponse(200, { runner: { hostname: "win" } }),
  ]);
  let r = await execSystemInfo({}, {}, deps(fakeFetch));
  assert.equal(r.details.runner.hostname, "win");
  assert.equal(calls.length, 1);
  assert.equal(JSON.parse(calls[0].init.body).action, "system.info");

  ({ fakeFetch, calls } = makeFakeFetch([
    jsonResponse(200, { cpu_percent: 12 }),
  ]));
  r = await execSystemStatus({}, {}, deps(fakeFetch));
  assert.equal(r.details.payload.cpu_percent, 12);
  assert.equal(JSON.parse(calls[0].init.body).action, "system.status");

  ({ fakeFetch, calls } = makeFakeFetch([
    jsonResponse(200, { result: { path: "D:\\", entries: [{ name: "a.txt" }], total: 1 } }),
  ]));
  r = await execListDirectory({ path: "D:\\" }, {}, deps(fakeFetch));
  assert.deepEqual(r.details.entries, [{ name: "a.txt" }]);
  assert.equal(r.details.total, 1);
  assert.equal(JSON.parse(calls[0].init.body).action, "fs.list");

  ({ fakeFetch, calls } = makeFakeFetch([
    jsonResponse(200, { result: { root: "D:\\", pattern: "*.py", matches: ["x.py"], total: 1 } }),
  ]));
  r = await execSearchFiles({ root: "D:\\", pattern: "*.py" }, {}, deps(fakeFetch));
  assert.deepEqual(r.details.matches, ["x.py"]);
  assert.equal(JSON.parse(calls[0].init.body).action, "fs.search");
});

// ── 16. No Hermes references ─────────────────────────────────────────

test("plugin source has zero references to Hermes / hermes / \u70df\u96e8", () => {
  const src = readFileSync(join(PLUGIN_ROOT, "dist", "index.js"), "utf8");
  for (const w of ["hermes", "Hermes", "HERMES", "\u70df\u96e8", "\u9a9a\u8bcd", "\u9ad8\u6d53\u5ea6"])
    assert.equal(src.includes(w), false, `must not contain "${w}"`);
});

// ── 17. No secrets in result content ─────────────────────────────────

test("result text / details never leak tokens, signatures, paths", async () => {
  const { fakeFetch } = makeFakeFetch([
    jsonResponse(200, { result: { status: "success", runner_request_id: "abc-123", execution_status: "succeeded", exit_code: 0, timed_out: false, stdout: '{"ok":true}' } }),
  ]);
  const r = await execProgramRun({ program_id: "hello_jarvis" }, {}, deps(fakeFetch));
  const t = JSON.stringify(r);
  for (const leak of ["Bearer ", "signature", "nonce=", "key=", "/home/xyzlh/.openclaw/secrets"])
    assert.equal(t.includes(leak), false, `text leaks "${leak}"`);
  // runner_request_id is a per-call correlation id — allowed.
  assert.equal(r.details.runner_request_id, "abc-123");
});

// ── ALLOWED_PROGRAM_IDS contract ───────────────────────────────────

test("ALLOWED_PROGRAM_IDS is frozen and only contains hello_jarvis", () => {
  assert.deepEqual([...ALLOWED_PROGRAM_IDS], ["hello_jarvis"]);
  assert.equal(RUN_PROGRAM_ID, "hello_jarvis");
  assert.throws(() => { ALLOWED_PROGRAM_IDS.push("x"); }, TypeError);
});

// ── callBridge unit test ────────────────────────────────────────────

test("callBridge surfaces bridgeError on non-200", async () => {
  const { fakeFetch, calls } = makeFakeFetch([
    jsonResponse(404, { error: "unknown_action", message: "no such action" }),
  ]);
  const o = await callBridge("program.run", {}, deps(fakeFetch));
  assert.equal(calls.length, 1);
  assert.equal(o.ok, false);
  assert.equal(o.bridgeError, "unknown_action");
});

test("callBridge returns payload on 200", async () => {
  const { fakeFetch } = makeFakeFetch([
    jsonResponse(200, { ok: true }, { "x-bridge-request-id": "req-7" }),
  ]);
  const o = await callBridge("program.list", {}, deps(fakeFetch));
  assert.equal(o.ok, true);
  assert.equal(o.status, 200);
  assert.equal(o.bridgeRequestId, "req-7");
  assert.deepEqual(o.payload, { ok: true });
});

test("callBridge handles fetch error gracefully", async () => {
  async function fakeFetch() { throw new Error("ECONNREFUSED"); }
  const o = await callBridge("program.list", {}, { ...DEPS_NO_TOKEN, fetch: fakeFetch });
  assert.equal(o.ok, false);
  assert.equal(o.bridgeError, "bridge_unreachable");
  assert.ok(o.bridgeMessage.includes("ECONNREFUSED"));
});

// ── FORBIDDEN_RUN_KEYS exhaustive check ─────────────────────────────

test("FORBIDDEN_RUN_KEYS includes all documented forbidden fields", () => {
  const expected = [
    "path", "script", "code", "command", "argv", "args",
    "shell", "environment", "env", "working_directory", "cwd",
    "timeout", "timeout_ms",
  ];
  assert.deepEqual([...FORBIDDEN_RUN_KEYS].sort(), expected.sort());
  assert.equal(FORBIDDEN_RUN_KEYS.length, expected.length);
});

// ── 18. fail-result status must be pinned to "failed" ─────────────────
//
// Regression guard: even if Runner reports runner_status="success" while
// execution_status="timed_out" or exit_code!=0, the user-visible status
// MUST stay "failed". Runner's status must surface under runner_status
// to avoid colliding with the user-visible status field.

test("fail details never surface runner_status as user-visible status", async () => {
  for (const fixture of [
    { result: { status: "success", execution_status: "timed_out", exit_code: 124, timed_out: true } },
    { result: { status: "success", execution_status: "succeeded", exit_code: 1, timed_out: false } },
    { result: { status: "failed", execution_status: "failed", exit_code: 2, timed_out: false } },
  ]) {
    const { fakeFetch } = makeFakeFetch([
      jsonResponse(200, { result: fixture.result }),
    ]);
    const r = await execProgramRun({ program_id: "hello_jarvis" }, {}, deps(fakeFetch));
    assert.equal(r.details.status, "failed", `must pin to "failed" for ${JSON.stringify(fixture.result)}`);
    // Runner-side status must surface under runner_status, not status
    assert.equal(typeof r.details.runner_status, "string");
    // If Runner reports "success" but execution failed/timed-out, the
    // runner_status must not bleed into the user-visible status.
    if (fixture.result.status === "success") {
      assert.notEqual(r.details.runner_status, r.details.status);
    }
  }
});

// ── 19. integration: simulated OpenClaw runtime dispatch ──────────────
//
// These tests simulate OpenClaw's `plugin.approval.*` runtime dispatch:
//   - block → tool not called
//   - requireApproval → wait for decision
//       allow-once/allow-always → tool called (Bridge hit)
//       deny/timeout(no-route=no) → tool NOT called (Bridge not hit)
//       no-route → fail closed per OpenClaw docs ("No approval route | The call is blocked")
//
// We do NOT execute the real runtime; we replicate its decision flow
// against the hook + execProgramRun pair.

/**
 * Simulate OpenClaw runtime dispatch: hook → approval → executor.
 * Returns { calls, executed, blocked, reason, decision, result }.
 */
async function simulateRuntimeDispatch({ hook, executor, fetchImpl, decision, params }) {
  const calls = { count: 0 };
  async function fakeFetch(url, init) {
    calls.count++;
    return fetchImpl(url, init);
  }
  const hookResult = await hook({ toolName: PROGRAM_RUN_TOOL_NAME, params }, {});

  if (hookResult && hookResult.block) {
    return { calls, executed: false, blocked: true, reason: hookResult.blockReason };
  }

  if (hookResult && hookResult.requireApproval) {
    if (decision === "allow-once" || decision === "allow-always") {
      // OpenClaw runtime would call executor with the bound params
      const finalParams = hookResult.params || params;
      const result = await executor(finalParams, {}, { readToken: () => null, fetch: fakeFetch });
      return { calls, executed: true, blocked: false, decision, result };
    }
    // deny / timeout / no-route → OpenClaw blocks the call
    return { calls, executed: false, blocked: true, decision };
  }

  // No approval requested → executor called directly (should not happen for run tool)
  const result = await executor(params, {}, { readToken: () => null, fetch: fakeFetch });
  return { calls, executed: true, blocked: false, decision: null, result };
}

test("integration: hook blocks unsupported program_id → no Bridge call", async () => {
  const api = loadPlugin();
  const hook = api.registeredHooks["before_tool_call"][0].handler;
  const r = await simulateRuntimeDispatch({
    hook,
    executor: execProgramRun,
    fetchImpl: () => { throw new Error("Bridge should not be called"); },
    decision: "allow-once",
    params: { program_id: "evil" },
  });
  assert.equal(r.blocked, true);
  assert.equal(r.executed, false);
  assert.equal(r.calls.count, 0);
  assert.equal(r.reason, "unsupported_program_id");
});

test("integration: hook blocks forbidden key → no Bridge call", async () => {
  const api = loadPlugin();
  const hook = api.registeredHooks["before_tool_call"][0].handler;
  const r = await simulateRuntimeDispatch({
    hook,
    executor: execProgramRun,
    fetchImpl: () => { throw new Error("Bridge should not be called"); },
    decision: "allow-once",
    params: { program_id: "hello_jarvis", path: "C:\\evil.exe" },
  });
  assert.equal(r.blocked, true);
  assert.equal(r.calls.count, 0);
  assert.ok(r.reason.startsWith("forbidden_parameter"));
});

test("integration: allow-once → exactly one Bridge call with bound params", async () => {
  const api = loadPlugin();
  const hook = api.registeredHooks["before_tool_call"][0].handler;
  const r = await simulateRuntimeDispatch({
    hook,
    executor: execProgramRun,
    fetchImpl: () => jsonResponse(200, {
      result: { status: "success", runner_request_id: "rid", execution_status: "succeeded", exit_code: 0, timed_out: false, stdout: '{"ok":true}' },
    }),
    decision: "allow-once",
    params: { program_id: "hello_jarvis" },
  });
  assert.equal(r.blocked, false);
  assert.equal(r.executed, true);
  assert.equal(r.calls.count, 1, "exactly one Bridge call after allow-once");
  assert.equal(r.result.details.execution_status, "succeeded");
});

test("integration: deny → no Bridge call", async () => {
  const api = loadPlugin();
  const hook = api.registeredHooks["before_tool_call"][0].handler;
  const r = await simulateRuntimeDispatch({
    hook,
    executor: execProgramRun,
    fetchImpl: () => { throw new Error("Bridge should not be called after deny"); },
    decision: "deny",
    params: { program_id: "hello_jarvis" },
  });
  assert.equal(r.blocked, true);
  assert.equal(r.decision, "deny");
  assert.equal(r.calls.count, 0);
});

test("integration: timeout with timeoutBehavior=deny → no Bridge call", async () => {
  const api = loadPlugin();
  const hook = api.registeredHooks["before_tool_call"][0].handler;
  const r = await simulateRuntimeDispatch({
    hook,
    executor: execProgramRun,
    fetchImpl: () => { throw new Error("Bridge should not be called after timeout"); },
    decision: "timeout",
    params: { program_id: "hello_jarvis" },
  });
  assert.equal(r.blocked, true);
  assert.equal(r.decision, "timeout");
  assert.equal(r.calls.count, 0);
});

test("integration: no approval route → fail closed, no Bridge call", async () => {
  const api = loadPlugin();
  const hook = api.registeredHooks["before_tool_call"][0].handler;
  const r = await simulateRuntimeDispatch({
    hook,
    executor: execProgramRun,
    fetchImpl: () => { throw new Error("Bridge should not be called when no approval route"); },
    decision: "no-route",
    params: { program_id: "hello_jarvis" },
  });
  assert.equal(r.blocked, true);
  assert.equal(r.decision, "no-route");
  assert.equal(r.calls.count, 0);
});

test("integration: allowedDecisions explicitly excludes allow-always", async () => {
  const api = loadPlugin();
  const hook = api.registeredHooks["before_tool_call"][0].handler;
  const r = await hook({ toolName: PROGRAM_RUN_TOOL_NAME, params: { program_id: "hello_jarvis" } }, {});
  const decisions = r.requireApproval.allowedDecisions;
  assert.ok(decisions.includes("allow-once"));
  assert.ok(decisions.includes("deny"));
  assert.equal(decisions.includes("allow-always"), false, "allow-always must NOT be exposed");
});

test("integration: onResolution is a passive observer (no persistence)", async () => {
  const api = loadPlugin();
  const hook = api.registeredHooks["before_tool_call"][0].handler;
  const r = await hook({ toolName: PROGRAM_RUN_TOOL_NAME, params: { program_id: "hello_jarvis" } }, {});
  // Call onResolution multiple times — must not throw, must not mutate state
  const onRes = r.requireApproval.onResolution;
  onRes("allow-once");
  onRes("deny");
  onRes("timeout");
  // No way to inspect persistent state from the hook side, but we verify
  // the function exists and is callable as the OpenClaw docs require.
  assert.equal(typeof onRes, "function");
});