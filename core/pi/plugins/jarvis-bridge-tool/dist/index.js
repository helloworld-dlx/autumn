// jarvis-bridge-tool plugin (Phase 3A-3)
//
// Bridges OpenClaw (Autumn) to a local Jarvis Bridge HTTP endpoint
// (127.0.0.1:27901) plus a Tailscale-reachable Windows Runner that
// executes whitelisted Python programs.
//
// Exposes exactly seven tools (no more, no less):
//   - jarvis_ping
//   - jarvis_system_info
//   - jarvis_system_status
//   - jarvis_list_directory
//   - jarvis_search_files
//   - jarvis_program_list
//   - jarvis_program_run    (LOW risk, AUTO execution — single hard-coded id)
//
// Internal names keep the jarvis_ prefix as required by Phase 0..3A-2.
// User-visible labels say "Autumn". Bridge package, action names, HTTP
// headers, systemd unit, hello_jarvis program_id are all preserved.

import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { Type } from "typebox";
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

// ---------------------------------------------------------------------------
// Bridge HTTP client (preserved from Phase 0..3A-2, upgraded with deps)
// ---------------------------------------------------------------------------

export const BRIDGE_DEFAULT_URL = "http://127.0.0.1:27901/v1/execute";
// Phase 3A-3: token path was wrong — Bridge actually reads from
// ~/.config/jarvis-bridge/bridge_local.token. Kept the export name for
// back-compat with any external callers that imported the constant.
export const BRIDGE_TOKEN_FILE = "/home/xyzlh/.config/jarvis-bridge/bridge_local.token";
// Legacy alias kept for tests and external callers that built URLs without
// the path. Phase 3A-3: Bridge only accepts POST /v1/execute; the bare host
// URL returns 404 NOT_FOUND.
export const BRIDGE_HOST_ONLY_URL = "http://127.0.0.1:27901";
export const BRIDGE_NODES_URL = "http://127.0.0.1:27901/v1/nodes";
export const BRIDGE_FILE_RETURN_URL = "http://127.0.0.1:27901/v1/files/pull";
export const BRIDGE_COMPANION_ARTIFACT_URL = "http://127.0.0.1:27901/v1/files/publish-text";
export const BRIDGE_HOME_URL = "http://127.0.0.1:27901/v1/home";

// Status codes that must NOT be retried / surfaced as opaque errors.
// The runtime surfaces the original Bridge error body so the LLM can see
// why the call failed; we only swallow nothing — passthrough is honest.
const PASSTHROUGH_ERROR_CODES = new Set([
  400, 401, 403, 404, 408, 409, 410, 412, 413, 414, 415, 416, 417, 418,
  421, 422, 423, 424, 425, 426, 428, 429, 431, 451,
  500, 501, 502, 503, 504, 505, 506, 507, 508, 510, 511,
]);

export function readBridgeToken() {
  try {
    const raw = readFileSync(BRIDGE_TOKEN_FILE, "utf8");
    return raw.trim();
  } catch {
    return null;
  }
}

/**
 * Generic Bridge HTTP client.
 *
 * @param {string}   action  Bridge action name (e.g. "program.list")
 * @param {object}   args    Action arguments
 * @param {object}   [deps]  Overrides for testing
 * @param {function} [deps.fetch]       fetch implementation (default globalThis.fetch)
 * @param {function} [deps.readToken]   token reader (default readBridgeToken)
 * @param {string}   [deps.url]         Bridge URL override
 */
export async function callBridge(action, args, deps = {}) {
  const fetchImpl = deps.fetch ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    return {
      ok: false,
      status: 0,
      bridgeError: "bridge_unreachable",
      bridgeMessage: "fetch is not available in this runtime",
    };
  }
  const url = deps.url ?? BRIDGE_DEFAULT_URL;
  const readToken = deps.readToken ?? readBridgeToken;
  const requestIdHeader = deps.requestIdHeader ?? "x-bridge-request-id";
  const signatureHeader = deps.signatureHeader ?? "x-bridge-signature";
  // Phase 3A-3: Bridge auth header is X-Jarvis-Bridge-Token (not Authorization).
  const bridgeTokenHeader = deps.bridgeTokenHeader ?? "x-jarvis-bridge-token";
  const token = readToken();

  const headers = { "content-type": "application/json" };
  // Phase 3A-3: Bridge reads X-Jarvis-Bridge-Token (not Authorization: Bearer).
  // The header name is preserved from the Bridge contract; only the variable
  // value is sourced from the local token file.
  if (token) headers[bridgeTokenHeader] = token;
  // request-id and signature placeholders (real values stamped at Bridge).
  headers[requestIdHeader] = "plugin-runtime";
  headers[signatureHeader] = "plugin-runtime";

  const body = JSON.stringify({ action, arguments: args ?? {} });
  let response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers,
      body,
    });
  } catch (err) {
    return {
      ok: false,
      status: 0,
      bridgeError: "bridge_unreachable",
      bridgeMessage: String(err && err.message ? err.message : err),
    };
  }

  const bridgeRequestId =
    response.headers && typeof response.headers.get === "function"
      ? response.headers.get(requestIdHeader)
      : null;
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const errCode = (payload && payload.error) || `http_${response.status}`;
    const errMessage =
      (payload && payload.message) || `Bridge returned status ${response.status}`;
    return {
      ok: false,
      status: response.status,
      bridgeRequestId,
      bridgeError: errCode,
      bridgeMessage: errMessage,
    };
  }

  // Bridge returns bridge_request_id in the response body, not in headers.
  // Prefer the body's id; fall back to the header for forward compatibility.
  const bodyBridgeId =
    payload && typeof payload === "object" && typeof payload.bridge_request_id === "string"
      ? payload.bridge_request_id
      : null;

  return {
    ok: true,
    status: response.status,
    bridgeRequestId: bodyBridgeId || bridgeRequestId,
    payload,
  };
}

export async function callBridgeFileReturn(path, deps = {}) {
  const fetchImpl = deps.fetch ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") return { ok: false, status: 0, bridgeError: "bridge_unreachable" };
  if (typeof path !== "string" || !path.trim() || path.length > 4096) {
    return { ok: false, status: 400, bridgeError: "invalid_path" };
  }
  const token = (deps.readToken ?? readBridgeToken)();
  const headers = { "content-type": "application/json" };
  if (token) headers["x-jarvis-bridge-token"] = token;
  let response;
  try {
    response = await fetchImpl(deps.fileReturnUrl ?? BRIDGE_FILE_RETURN_URL, {
      method: "POST", headers, body: JSON.stringify({ path }),
    });
  } catch (err) {
    return { ok: false, status: 0, bridgeError: "bridge_unreachable", bridgeMessage: String(err?.message ?? err) };
  }
  let payload = null;
  try { payload = await response.json(); } catch {}
  if (!response.ok) {
    return {
      ok: false, status: response.status,
      bridgeError: payload?.error_code || `http_${response.status}`,
      bridgeMessage: payload?.message || "File return failed",
    };
  }
  return { ok: true, status: response.status, payload };
}

export async function callBridgeCompanionArtifact(filename, content, deps = {}) {
  const fetchImpl = deps.fetch ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") return { ok: false, status: 0, bridgeError: "bridge_unreachable" };
  if (typeof filename !== "string" || !filename.trim() || filename.length > 180 || /[\\/\r\n\0]/.test(filename)) {
    return { ok: false, status: 400, bridgeError: "artifact_filename_invalid" };
  }
  if (typeof content !== "string" || !content || Buffer.byteLength(content, "utf8") > 48 * 1024) {
    return { ok: false, status: 413, bridgeError: "artifact_content_invalid" };
  }
  const token = (deps.readToken ?? readBridgeToken)();
  const headers = { "content-type": "application/json" };
  if (token) headers["x-jarvis-bridge-token"] = token;
  let response;
  try {
    response = await fetchImpl(deps.companionArtifactUrl ?? BRIDGE_COMPANION_ARTIFACT_URL, {
      method: "POST", headers, body: JSON.stringify({ filename: filename.trim(), content }),
    });
  } catch (err) {
    return { ok: false, status: 0, bridgeError: "bridge_unreachable", bridgeMessage: String(err?.message ?? err) };
  }
  let payload = null;
  try { payload = await response.json(); } catch {}
  if (!response.ok) {
    return {
      ok: false, status: response.status,
      bridgeError: payload?.error_code || `http_${response.status}`,
      bridgeMessage: payload?.message || "Companion artifact publish failed",
    };
  }
  return { ok: true, status: response.status, payload };
}

export const AutumnHomeParams = Type.Union([
  Type.Object({ action: Type.Literal("list") }, { additionalProperties: false }),
  Type.Object({
    action: Type.Literal("state"),
    device: Type.String({ minLength: 1, maxLength: 48, pattern: "^[a-z][a-z0-9_-]*$" }),
  }, { additionalProperties: false }),
  Type.Object({
    action: Type.Literal("control"),
    device: Type.String({ minLength: 1, maxLength: 48, pattern: "^[a-z][a-z0-9_-]*$" }),
    command: Type.String({ minLength: 1, maxLength: 48, pattern: "^[a-z_][a-z0-9_]*$" }),
  }, { additionalProperties: false }),
]);

export async function callBridgeHome(params, deps = {}) {
  const fetchImpl = deps.fetch ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") return { ok:false,status:0,bridgeError:"bridge_unreachable" };
  const valid = params && typeof params === "object" && (
    (params.action === "list" && Object.keys(params).length === 1) ||
    (params.action === "state" && typeof params.device === "string" && Object.keys(params).length === 2) ||
    (params.action === "control" && typeof params.device === "string" && typeof params.command === "string" && Object.keys(params).length === 3)
  );
  if (!valid) return { ok:false,status:400,bridgeError:"HOME_REQUEST_INVALID" };
  const token = (deps.readToken ?? readBridgeToken)();
  const headers = { "content-type":"application/json" };
  if (token) headers["x-jarvis-bridge-token"] = token;
  let response;
  try {
    response = await fetchImpl(deps.homeUrl ?? BRIDGE_HOME_URL, { method:"POST",headers,body:JSON.stringify(params) });
  } catch (err) {
    return { ok:false,status:0,bridgeError:"bridge_unreachable",bridgeMessage:String(err?.message ?? err) };
  }
  let payload=null;
  try { payload=await response.json(); } catch {}
  if (!response.ok) return {
    ok:false,status:response.status,
    bridgeError:payload?.error_code || `http_${response.status}`,
    bridgeMessage:payload?.message || "Autumn Home request failed",
  };
  return { ok:true,status:response.status,payload };
}

function safeHomeState(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const out={};
  for (const [key,item] of Object.entries(value)) {
    if (!/^[a-z_][a-z0-9_]*$/.test(key)) continue;
    if (["entity_id","domain","service","token"].includes(key)) continue;
    if (["string","number","boolean"].includes(typeof item) || item === null) out[key]=item;
  }
  return out;
}

function safeHomePayload(payload) {
  if (!payload || payload.status !== "OK") return null;
  if (Array.isArray(payload.devices)) return {
    status:"OK",
    devices:payload.devices.slice(0,32).map(item=>({
      device:String(item?.device||"").slice(0,48),
      label:String(item?.label||"").slice(0,80),
      readable:item?.readable===true,
      commands:Array.isArray(item?.commands)?item.commands.filter(x=>typeof x==="string").slice(0,12):[],
      risk:item?.risk === "low" ? "low" : "unknown",
      confirm:item?.confirm === true,
    })),
  };
  if (typeof payload.device === "string") return {
    status:"OK",device:payload.device.slice(0,48),label:String(payload.label||"").slice(0,80),
    ...(typeof payload.command === "string" ? { command:payload.command.slice(0,48) } : {}),
    state:safeHomeState(payload.state),
  };
  return null;
}

export async function execAutumnHome(params, _config, deps) {
  const out=await callBridgeHome(params,deps||{});
  if (!out.ok) return failResult(out.bridgeError||"home_failed",{bridgeMessage:out.bridgeMessage});
  const safe=safeHomePayload(out.payload);
  return safe ? okResult(safe) : failResult("home_response_invalid");
}

// ---------------------------------------------------------------------------
// Bridge Job API client (Phase 2B-3B)
// Calls /v1/jobs/submit, /v1/jobs/status, /v1/jobs/cancel, /v1/jobs/result
// ---------------------------------------------------------------------------

const BRIDGE_JOB_URLS = {
  submit: "http://127.0.0.1:27901/v1/jobs/submit",
  status: "http://127.0.0.1:27901/v1/jobs/status",
  cancel: "http://127.0.0.1:27901/v1/jobs/cancel",
  result: "http://127.0.0.1:27901/v1/jobs/result",
};

export async function callBridgeJob(jobAction, jobPayload, deps = {}) {
  const fetchImpl = deps.fetch ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    return {
      ok: false,
      status: 0,
      bridgeError: "bridge_unreachable",
      bridgeMessage: "fetch is not available",
    };
  }
  const url = BRIDGE_JOB_URLS[jobAction];
  if (!url) {
    return { ok: false, status: 400, bridgeError: "INVALID_JOB_ACTION", bridgeMessage: "Unknown job action" };
  }
  const readToken = deps.readToken ?? readBridgeToken;
  const token = readToken();
  const headers = { "content-type": "application/json" };
  if (token) headers["x-jarvis-bridge-token"] = token;

  let response;
  try {
    response = await fetchImpl(url, { method: "POST", headers, body: JSON.stringify(jobPayload) });
  } catch (err) {
    return {
      ok: false,
      status: 0,
      bridgeError: "bridge_unreachable",
      bridgeMessage: String(err && err.message ? err.message : err),
    };
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const errCode = (payload && payload.error_code) || `http_${response.status}`;
    const errMessage = (payload && payload.message) || `Bridge returned ${response.status}`;
    return { ok: false, status: response.status, bridgeError: errCode, bridgeMessage: errMessage };
  }
  return { ok: true, status: response.status, payload };
}

// ---------------------------------------------------------------------------
// Tool parameter schemas (TypeBox)
// ---------------------------------------------------------------------------

const EmptyParams = Type.Object({}, { additionalProperties: false });

export const AutumnNodesParams = Type.Union([
  Type.Object({ action: Type.Literal("list") }, { additionalProperties: false }),
  Type.Object(
    {
      action: Type.Literal("get"),
      node_id: Type.String({ minLength: 1, maxLength: 64, pattern: "^[a-z0-9][a-z0-9-]*$" }),
    },
    { additionalProperties: false },
  ),
]);

const DirectoryParams = Type.Object(
  {
    path: Type.String(),
    offset: Type.Optional(Type.Integer({ minimum: 0 })),
    limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 1000 })),
  },
  { additionalProperties: false }
);

const SearchParams = Type.Object(
  {
    path: Type.String(),
    query: Type.String(),
    kind: Type.Optional(Type.Union([Type.Literal("file"), Type.Literal("directory")])),
    max_results: Type.Optional(Type.Integer({ minimum: 1, maximum: 50 })),
  },
  { additionalProperties: false }
);

const AutumnFileReturnParams = Type.Object(
  { path: Type.String({ minLength: 1, maxLength: 4096 }) },
  { additionalProperties: false },
);

const AutumnCompanionArtifactParams = Type.Object(
  {
    filename: Type.String({ minLength: 1, maxLength: 180 }),
    content: Type.String({ minLength: 1, maxLength: 48000 }),
  },
  { additionalProperties: false },
);

// Program schemas (Phase 3A-3):
// - jarvis_program_list: zero-arg, no path, no code, no anything
// - jarvis_program_run: hardcoded single program_id enum, no other fields
export const ProgramListParams = EmptyParams;

export const ProgramRunParams = Type.Object(
  {
    program_id: Type.Literal("hello_jarvis"),
  },
  { additionalProperties: false }
);

// Phase 2B-3B: Worker tool schemas
// worker_submit: backend=direct, operation in {archive.list, archive.create}
// archive.list: { backend: "direct", operation: "archive.list", archive_path: string }
// archive.create: { backend: "direct", operation: "archive.create", source_paths: string[], output_archive: string }
const WorkerSubmitArchiveListParams = Type.Object(
  {
    backend: Type.Literal("direct"),
    operation: Type.Literal("archive.list"),
    archive_path: Type.String(),
  },
  { additionalProperties: false }
);

const WorkerSubmitArchiveCreateParams = Type.Object(
  {
    backend: Type.Literal("direct"),
    operation: Type.Literal("archive.create"),
    source_paths: Type.Array(Type.String(), { minItems: 1 }),
    output_archive: Type.String(),
  },
  { additionalProperties: false }
);


// Phase 2B-3B R1 General ProcessJobSpec
// executable is a Runner Catalog ID (7zip, git, python, node).
// Pi plugin does NOT resolve paths or enforce authority — that is Runner's job.
const WorkerSubmitProcessParams = Type.Object(
  {
    type: Type.Literal("process"),
    executable: Type.String(),
    arguments: Type.Optional(Type.Array(Type.String(), { default: [] })),
    cwd: Type.Optional(Type.String()),
    timeout: Type.Optional(Type.Number({ minimum: 1 })),
    write_scope: Type.Optional(Type.Array(Type.String(), { default: [] })),
    network_policy: Type.Optional(Type.String()),
  },
  { additionalProperties: false }
);

// Union for schema validation — accept archive operations OR general process OR codex
// Phase 2B-4E2: Codex submit params — defined BEFORE the union that references it
const WorkerSubmitCodexParams = Type.Object(
  {
    backend: Type.Literal("codex"),
    task: Type.String(),
    real_workspace: Type.String(),
    timeout: Type.Optional(Type.Number({ minimum: 1 })),
    authorization_request_id: Type.String(),
  },
  { additionalProperties: false }
);
const WorkerSubmitParams = Type.Union([
  WorkerSubmitArchiveListParams,
  WorkerSubmitArchiveCreateParams,
  WorkerSubmitProcessParams,
  WorkerSubmitCodexParams,
]);

const WorkerStatusParams = Type.Object(
  { job_id: Type.String() },
  { additionalProperties: false }
);

const WorkerCancelParams = Type.Object(
  { job_id: Type.String() },
  { additionalProperties: false }
);

const WorkerResultParams = Type.Object(
  { job_id: Type.String() },
  { additionalProperties: false }
);

// Phase 2B-4E2: Authorization schemas (defined early so Codex params can reference them)
const WorkerAuthorizationRequestParams = Type.Object(
  {
    task: Type.String(),
    real_workspace: Type.String(),
  },
  { additionalProperties: false }
);

const WorkerAuthorizationApproveParams = Type.Object(
  {
    authorization_request_id: Type.String(),
  },
  { additionalProperties: false }
);

// Phase 2B-5B: Worker control — all three actions take exactly {}
const WorkerControlParams = Type.Object({}, { additionalProperties: false });



export const ALLOWED_PROGRAM_IDS = Object.freeze(["hello_jarvis"]);
export const RUN_PROGRAM_ID = "hello_jarvis";
// Keys we explicitly forbid under any circumstances on jarvis_program_run.
export const FORBIDDEN_RUN_KEYS = Object.freeze([
  "path",
  "script",
  "code",
  "command",
  "argv",
  "args",
  "shell",
  "environment",
  "env",
  "working_directory",
  "cwd",
  "timeout",
  "timeout_ms",
]);

// ---------------------------------------------------------------------------
// Result builders — return { content, details } shape the agent runtime expects
// ---------------------------------------------------------------------------

function okResult(payload) {
  return {
    content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
    details: payload,
  };
}

function failResult(reason, details) {
  return {
    content: [{ type: "text", text: `error: ${reason}` }],
    // details may carry a `runner_status` field from redactBridgeCall that
    // we must NOT mistake for the user-visible status. Pin status:"failed"
    // last so caller-provided status can never overwrite it.
    details: Object.assign({ status: "failed", reason }, details || {}, { status: "failed" }),
  };
}

function queryFailedResult() {
  return okResult({
    status: "QUERY_FAILED",
    message: "Node Registry is temporarily unavailable; device presence was not inferred.",
  });
}

function safeNode(node) {
  if (!node || typeof node !== "object") return null;
  if (
    typeof node.protocol_version !== "string" ||
    typeof node.node_id !== "string" ||
    typeof node.node_type !== "string" ||
    typeof node.node_version !== "string" ||
    !["ONLINE", "OFFLINE", "RECENT", "UNKNOWN"].includes(node.online) ||
    !(node.last_seen === null || typeof node.last_seen === "string") ||
    !Array.isArray(node.capabilities) ||
    node.capabilities.length > 16 ||
    !node.capabilities.every((capability) => typeof capability === "string" && /^[a-z][a-z0-9._]*$/.test(capability))
  ) return null;
  return {
    protocol_version: node.protocol_version,
    node_id: node.node_id,
    node_type: node.node_type,
    node_version: node.node_version,
    online: node.online,
    last_seen: node.last_seen,
    capabilities: [...node.capabilities],
  };
}

export async function callBridgeNodes(action, nodeId, deps = {}) {
  if (action !== "list" && action !== "get") {
    return { ok: false, status: 400, bridgeError: "invalid_action" };
  }
  if (action === "get" && (typeof nodeId !== "string" || !/^[a-z0-9][a-z0-9-]*$/.test(nodeId))) {
    return { ok: false, status: 400, bridgeError: "invalid_node_id" };
  }
  const fetchImpl = deps.fetch ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") return { ok: false, status: 0, bridgeError: "bridge_unreachable" };
  const url = action === "list" ? (deps.nodesUrl ?? BRIDGE_NODES_URL) : `${deps.nodesUrl ?? BRIDGE_NODES_URL}/${nodeId}`;
  let response;
  try {
    response = await fetchImpl(url, { method: "GET", headers: { accept: "application/json" }, redirect: "manual" });
  } catch {
    return { ok: false, status: 0, bridgeError: "bridge_unreachable" };
  }
  let payload = null;
  try { payload = await response.json(); } catch { return { ok: false, status: response.status, bridgeError: "invalid_response" }; }
  if (response.status === 404 && action === "get") return { ok: false, status: 404, bridgeError: "node_not_found" };
  if (!response.ok) return { ok: false, status: response.status, bridgeError: "registry_unavailable" };
  return { ok: true, status: response.status, payload };
}

export async function execAutumnNodes(params, _config, deps) {
  const action = params && params.action;
  const nodeId = params && params.node_id;
  if (action !== "list" && action !== "get") return queryFailedResult();
  if (action === "list" && Object.keys(params).length !== 1) return queryFailedResult();
  if (action === "get" && (!/^[a-z0-9][a-z0-9-]*$/.test(nodeId || "") || Object.keys(params).length !== 2)) return queryFailedResult();
  const out = await callBridgeNodes(action, nodeId, deps || {});
  if (!out.ok) {
    if (out.bridgeError === "node_not_found") return okResult({ status: "NODE_NOT_FOUND", node_id: nodeId });
    return queryFailedResult();
  }
  if (action === "list") {
    if (!out.payload || !Array.isArray(out.payload.nodes) || out.payload.nodes.length > 16) return queryFailedResult();
    const nodes = out.payload.nodes.map(safeNode);
    if (nodes.some((node) => node === null)) return queryFailedResult();
    return okResult({ status: "OK", nodes });
  }
  const node = safeNode(out.payload);
  return node ? okResult({ status: "OK", node }) : queryFailedResult();
}

export async function execAutumnFileReturn(params, _config, deps) {
  if (!params || typeof params.path !== "string" || Object.keys(params).length !== 1) {
    return failResult("invalid_path");
  }
  const out = await callBridgeFileReturn(params.path, deps || {});
  if (!out.ok) {
    return failResult(out.bridgeError || "file_return_failed", { bridgeMessage: out.bridgeMessage });
  }
  const payload = out.payload || {};
  if (payload.status !== "succeeded" || typeof payload.transfer_id !== "string") {
    return failResult("file_return_invalid");
  }
  return okResult({
    status: "ready",
    transfer_id: payload.transfer_id,
    filename: typeof payload.filename === "string" ? payload.filename : "returned-file",
    size: typeof payload.size === "number" ? payload.size : null,
    message: "The file is ready for the current Autumn Companion reply and also Activity → Files. Do not expose Pi local paths or send it to Feishu unless explicitly requested.",
  });
}

export async function execAutumnCompanionArtifact(params, _config, deps) {
  if (!params || typeof params.filename !== "string" || typeof params.content !== "string" || Object.keys(params).length !== 2) {
    return failResult("artifact_invalid");
  }
  const out = await callBridgeCompanionArtifact(params.filename, params.content, deps || {});
  if (!out.ok) {
    return failResult(out.bridgeError || "artifact_publish_failed", { bridgeMessage: out.bridgeMessage });
  }
  const payload = out.payload || {};
  if (payload.status !== "succeeded" || typeof payload.transfer_id !== "string") {
    return failResult("artifact_publish_invalid");
  }
  return okResult({
    status: "ready",
    transfer_id: payload.transfer_id,
    filename: typeof payload.filename === "string" ? payload.filename : params.filename,
    size: typeof payload.size === "number" ? payload.size : Buffer.byteLength(params.content, "utf8"),
    message: "The generated text file is ready as an Autumn Companion attachment/download. No ad-hoc HTTP server or Feishu send is needed.",
  });
}

// Strip internal-only fields so they never reach user-visible output.
function redactBridgeCall(call) {
  if (!call || typeof call !== "object") return call;
  const out = {};
  for (const [k, v] of Object.entries(call)) {
    if (k === "bridgeRequestId" || k === "runnerRequestId") {
      out[k] = v;
      continue;
    }
    if (
      k === "runner_status" ||
      k === "programs" ||
      k === "result" ||
      k === "execution_status" ||
      k === "exit_code" ||
      k === "timed_out" ||
      k === "structured" ||
      k === "program_id"
    ) {
      out[k] = v;
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Five legacy tool execute bodies (preserved from Phase 3A-2)
//
// Each accepts an optional `deps` override for testability. In production
// the register() callback passes `api.pluginConfig` (which is {}). Tests
// call these directly with `{ fetch: fakeFetch }`.
// ---------------------------------------------------------------------------

export async function execPing(_params, _config, deps) {
  const out = await callBridge("system.ping", {}, deps || {});
  if (!out.ok) {
    return failResult(out.bridgeError || "bridge_error", {
      bridgeError: out.bridgeError,
      bridgeMessage: out.bridgeMessage,
    });
  }
  return okResult({ ok: true, bridge_status: out.status, payload: out.payload });
}

export async function execSystemInfo(_params, _config, deps) {
  const out = await callBridge("system.info", {}, deps || {});
  if (!out.ok) {
    return failResult(out.bridgeError || "bridge_error", {
      bridgeError: out.bridgeError,
      bridgeMessage: out.bridgeMessage,
    });
  }
  return okResult({
    bridge_status: out.status,
    runner: out.payload && out.payload.runner,
  });
}

export async function execSystemStatus(_params, _config, deps) {
  const out = await callBridge("system.status", {}, deps || {});
  if (!out.ok) {
    return failResult(out.bridgeError || "bridge_error", {
      bridgeError: out.bridgeError,
      bridgeMessage: out.bridgeMessage,
    });
  }
  return okResult({ bridge_status: out.status, payload: out.payload });
}

// Phase 1B Bridge/Runner contract for files actions (verified via curl
// against 127.0.0.1:27901/v1/execute on 2026-08-07):
//   action = "files.list_directory", arguments = { path: "D:\\..." }
//   action = "files.search",         arguments = { path: "D:\\...", query: "...", max_results: 1..50 }
// Runner rejects offset/limit on list_directory and max_results > 50 on
// search (returns error_code REQUEST_INVALID). Both actions return
// { result: { search_root, items: [...], returned_count, truncated, ... } }.

const SEARCH_MAX_RESULTS = 50;

export async function execListDirectory(params, _config, deps) {
  // User-visible schema is { path, offset?, limit? } — we forward only
  // `path` to Bridge because Runner rejects offset/limit.
  const out = await callBridge(
    "files.list_directory",
    { path: params.path },
    deps || {},
  );
  if (!out.ok) {
    return failResult(out.bridgeError || "bridge_error", {
      bridgeError: out.bridgeError,
      bridgeMessage: out.bridgeMessage,
    });
  }
  const payload = (out.payload && out.payload.result) || {};
  return okResult({
    bridge_status: out.status,
    path: payload.path || payload.search_root || params.path,
    entries: Array.isArray(payload.entries)
      ? payload.entries
      : Array.isArray(payload.items)
        ? payload.items
        : [],
    total:
      typeof payload.total === "number"
        ? payload.total
        : typeof payload.returned_count === "number"
          ? payload.returned_count
          : null,
  });
}

export async function execSearchFiles(params, _config, deps) {
  // User-visible schema is { path, query, kind?, max_results? }. Keep the
  // old root/pattern aliases only for direct internal callers; the registered
  // tool schema intentionally exposes only the new names.
  const path = params.path ?? params.root;
  const query = params.query ?? params.pattern;
  const requested = typeof params.max_results === "number" ? params.max_results : SEARCH_MAX_RESULTS;
  const clampedMax = Math.max(1, Math.min(SEARCH_MAX_RESULTS, Math.floor(requested)));
  const out = await callBridge(
    "files.search",
    { path, query, ...(params.kind ? { kind: params.kind } : {}), max_results: clampedMax },
    deps || {},
  );
  if (!out.ok) {
    return failResult(out.bridgeError || "bridge_error", {
      bridgeError: out.bridgeError,
      bridgeMessage: out.bridgeMessage,
    });
  }
  if (out.payload && out.payload.status && out.payload.status !== "success") {
    return failResult(out.payload.error_code || "runner_rejected", {
      bridgeError: out.payload.error_code || "runner_rejected",
      bridgeMessage: out.payload.message || "Windows Runner rejected the search",
    });
  }
  const payload = (out.payload && out.payload.result) || {};
  return okResult({
    bridge_status: out.status,
    path,
    query,
    ...(params.kind ? { kind: params.kind } : {}),
    matches: Array.isArray(payload.matches)
      ? payload.matches
      : Array.isArray(payload.items)
        ? payload.items
        : [],
    total:
      typeof payload.total === "number"
        ? payload.total
        : typeof payload.returned_count === "number"
          ? payload.returned_count
          : null,
  });
}

// ---------------------------------------------------------------------------
// New Phase 3A-3 tool execute bodies
// ---------------------------------------------------------------------------

/**
 * jarvis_program_list — read-only enumeration of registered Windows programs.
 * No params accepted. Returns bridge + runner IDs (safe) + program metadata.
 * No paths, no sha256, no tokens, no stack traces.
 */
export async function execProgramList(_params, _config, deps) {
  const out = await callBridge("program.list", {}, deps || {});
  if (!out.ok) {
    return failResult(out.bridgeError || "bridge_error", {
      bridgeError: out.bridgeError,
      bridgeMessage: out.bridgeMessage,
    });
  }
  const inner = (out.payload && out.payload.result) || {};
  const meta = out.payload || {};
  const programs = Array.isArray(inner.programs) ? inner.programs : [];
  const trimmed = programs.map((p) => ({
    program_id: p && p.program_id,
    label: p && p.label,
    description: p && p.description,
    timeout_seconds: p && p.timeout_seconds,
  }));
  return okResult({
    status: meta.status || inner.status || "ok",
    bridge_request_id: out.bridgeRequestId || null,
    runner_request_id: meta.runner_request_id || null,
    programs: trimmed,
  });
}

/**
 * jarvis_program_run — run a whitelisted program (single hard-coded id).
 *
 * Defense in depth: this function validates the inbound params strictly
 * before calling Bridge. If any forbidden key slips in, or the program_id
 * is not the allowed literal, we return a failed result WITHOUT calling
 * Bridge.
 *
 * Success definition: Bridge HTTP 200 + runner status=success +
 * execution_status=succeeded + exit_code=0 + timed_out=false.
 * Any other combination is failure and must NOT be described as "done".
 */
export async function execProgramRun(params, _config, deps) {
  // Strict whitelist of accepted keys.
  const keys = params && typeof params === "object" ? Object.keys(params) : [];
  if (!ALLOWED_PROGRAM_IDS.includes(params && params.program_id)) {
    return failResult("unsupported_program_id", {
      allowed_programs: ALLOWED_PROGRAM_IDS.slice(),
      received_keys: keys,
    });
  }
  for (const forbidden of FORBIDDEN_RUN_KEYS) {
    if (Object.prototype.hasOwnProperty.call(params, forbidden)) {
      return failResult("forbidden_parameter", {
        forbidden_key: forbidden,
        allowed_programs: ALLOWED_PROGRAM_IDS.slice(),
      });
    }
  }
  if (keys.length !== 1) {
    return failResult("unexpected_parameter_count", {
      expected: 1,
      received: keys.length,
      received_keys: keys,
      allowed_programs: ALLOWED_PROGRAM_IDS.slice(),
    });
  }

  const bridgeArgs = { program_id: RUN_PROGRAM_ID };
  const out = await callBridge("program.run", bridgeArgs, deps || {});

  if (!out.ok) {
    return failResult(out.bridgeError || "bridge_error", {
      bridgeError: out.bridgeError,
      bridgeMessage: out.bridgeMessage,
      bridge_request_id: out.bridgeRequestId || null,
      program_id: RUN_PROGRAM_ID,
    });
  }

  const inner = (out.payload && out.payload.result) || {};
  const meta = out.payload || {};
  // Bridge returns status at the top level of payload, and result fields
  // (execution_status, exit_code, timed_out, stdout) inside payload.result.
  const runnerStatus = meta.status || inner.status || "unknown";
  const executionStatus = inner.execution_status || "unknown";
  const exitCode = typeof inner.exit_code === "number" ? inner.exit_code : null;
  const timedOut = !!inner.timed_out;

  const success =
    runnerStatus === "success" &&
    executionStatus === "succeeded" &&
    !timedOut &&
    exitCode === 0;

  // Try to surface the stdout JSON if it parses; do not store the raw
  // string in details because it may carry "hello from jarvis" which is
  // a misread signal (not an assistant name — see Phase 3A-3 report §7).
  let structured = null;
  if (typeof inner.stdout === "string") {
    const firstLine = inner.stdout.split(/\r?\n/, 1)[0].trim();
    try {
      structured = JSON.parse(firstLine);
    } catch {
      structured = null;
    }
  }

  // Surface the runner-side status as `runner_status` (not `status`) so it
  // cannot collide with the user-visible status controlled by failResult.
  const details = redactBridgeCall({
    bridge_request_id: out.bridgeRequestId || null,
    runner_request_id: (out.payload && out.payload.runner_request_id) || inner.runner_request_id || null,
    runner_status: runnerStatus,
    program_id: RUN_PROGRAM_ID,
    result: {
      execution_status: executionStatus,
      exit_code: exitCode,
      timed_out: timedOut,
      structured,
    },
  });

  if (success) {
    return okResult({
      status: "ok",
      program_id: RUN_PROGRAM_ID,
      assistant_name: "Autumn",
      bridge_request_id: out.bridgeRequestId || null,
      runner_request_id: (out.payload && out.payload.runner_request_id) || inner.runner_request_id || null,
      execution_status: executionStatus,
      exit_code: exitCode,
      timed_out: timedOut,
      structured,
    });
  }
  return failResult("program_run_failed", details);
}

// ---------------------------------------------------------------------------
// Phase 2B-3B: Worker tool execute bodies
// ---------------------------------------------------------------------------

function jobOutToResult(out, fallbackDetails) {
  if (!out.ok) {
    return failResult(out.bridgeError || "job_failed", {
      bridgeError: out.bridgeError,
      bridgeMessage: out.bridgeMessage,
      ...fallbackDetails,
    });
  }
  const p = out.payload || {};
  const status = p.status || "unknown";

  // Phase 2B-4E3 R7B: Runner rejection / failure returns HTTP 200 from Bridge
  // but status != "success". Surface the error with full details instead of {}.
  const RUNNER_FAILURE = ["rejected", "failed", "cancelled", "timeout"];
  if (RUNNER_FAILURE.includes(status)) {
    return failResult(p.error_code || status, {
      runner_status: status,
      job_id: p.job_id,
      bridgeError: p.error_code,
      bridgeMessage: p.message,
      runner_request_id: out.runner_request_id,
      ...fallbackDetails,
    });
  }

  const terminal = status === "success" || status === "failed" || status === "cancelled" || status === "timeout";
  return {
    content: [{ type: "text", text: JSON.stringify(p.result || p, null, 2) }],
    details: { status, job_id: p.job_id || p.result?.job_id, terminal },
  };
}

// Phase 2B-3B R1: known catalog IDs — Runner resolves these to real executables.
// Pi plugin does NOT enforce this list; Runner Authority does.
const KNOWN_CATALOG_IDS = Object.freeze(["7zip", "git", "python", "node"]);

export async function execWorkerSubmit(params, _config, deps) {
  // Strict schema: TypeBox already validates operation type at registration.
  // Additional guard: reject forbidden keys that should never appear.
  const forbiddenKeys = ["executable_path", "raw_command", "command_string", "shell", "raw", "script"];
  for (const k of forbiddenKeys) {
    if (k in (params || {})) {
      return failResult("forbidden_parameter", { forbidden_key: k });
    }
  }

  let jobPayload;
  if (params && params.backend === "codex") {
    // Phase 2B-4E2: Codex submit — requires authorization_request_id from prior approval.
    // Runner contract: backend=codex, task, real_workspace, timeout, authorization_request_id.
    jobPayload = {
      backend: "codex",
      task: params.task,
      real_workspace: params.real_workspace,
      timeout: params.timeout || 60,
      authorization_request_id: params.authorization_request_id,
    };
  } else if (params && params.type === "process") {
    // R1 ProcessJobSpec — must match Runner's exact contract.
    // backend="direct" + write_scope/network_policy="none" are required fields.
    // timeout default=10 matches known-good baseline.
    const args = Array.isArray(params.arguments) ? params.arguments : [];
    jobPayload = {
      backend: "direct",
      type: "process",
      executable: params.executable,
      arguments: args,
    };
    if (params.cwd) jobPayload.cwd = params.cwd;
    if (params.timeout) jobPayload.timeout = params.timeout;
    else jobPayload.timeout = 10;
    jobPayload.write_scope = params.write_scope || "none";
    jobPayload.network_policy = params.network_policy || "none";
  } else {
    // Archive operations (archive.list, archive.create) — pass through unchanged.
    // Bridge forwards as-is to Runner, which routes to DirectProcessWorkerService.
    jobPayload = params;
  }

  const out = await callBridgeJob("submit", jobPayload, deps || {});
  return jobOutToResult(out, {});
}

export async function execWorkerStatus(params, _config, deps) {
  const out = await callBridgeJob("status", { job_id: params.job_id }, deps || {});
  return jobOutToResult(out, { job_id: params.job_id });
}

export async function execWorkerCancel(params, _config, deps) {
  const out = await callBridgeJob("cancel", { job_id: params.job_id }, deps || {});
  return jobOutToResult(out, { job_id: params.job_id });
}

export async function execWorkerResult(params, _config, deps) {
  const out = await callBridgeJob("result", { job_id: params.job_id }, deps || {});
  return jobOutToResult(out, { job_id: params.job_id });
}

// Phase 2B-4E2: Authorization tools (stateless passthrough)
function authOutToResult(out, fallbackDetails) {
  if (!out.ok) {
    return failResult(out.bridgeError || "authorization_failed", {
      bridgeError: out.bridgeError,
      bridgeMessage: out.bridgeMessage,
      ...fallbackDetails,
    });
  }
  const p = out.payload || {};
  return {
    content: [{ type: "text", text: JSON.stringify(p.result || p, null, 2) }],
    details: { status: p.status || "ok", ...fallbackDetails },
  };
}

export async function execWorkerAuthorizationRequest(params, _config, deps) {
  const out = await callBridgeAuthorization("request", {
    task: params.task,
    real_workspace: params.real_workspace,
  }, deps || {});
  return authOutToResult(out, {});
}

export async function execWorkerAuthorizationApprove(params, _config, deps) {
  const out = await callBridgeAuthorization("approve", {
    authorization_request_id: params.authorization_request_id,
  }, deps || {});
  return authOutToResult(out, { authorization_request_id: params.authorization_request_id });
}

// ---------------------------------------------------------------------------
// Plugin entry — definePluginEntry so register() wires both tools + hook
// ---------------------------------------------------------------------------

// Phase 2B-4E2: Bridge Authorization API client (stateless passthrough)
const BRIDGE_AUTH_URLS = {
  request: "http://127.0.0.1:27901/v1/authorizations/request",
  approve: "http://127.0.0.1:27901/v1/authorizations/approve",
};

export async function callBridgeAuthorization(authAction, authPayload, deps = {}) {
  const fetchImpl = deps.fetch ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    return { ok: false, status: 0, bridgeError: "bridge_unreachable", bridgeMessage: "fetch is not available" };
  }
  const url = BRIDGE_AUTH_URLS[authAction];
  if (!url) {
    return { ok: false, status: 400, bridgeError: "INVALID_AUTH_ACTION", bridgeMessage: "Unknown auth action" };
  }
  const readToken = deps.readToken ?? readBridgeToken;
  const token = readToken();
  const headers = { "content-type": "application/json" };
  if (token) headers["x-jarvis-bridge-token"] = token;
  let response;
  try {
    response = await fetchImpl(url, { method: "POST", headers, body: JSON.stringify(authPayload) });
  } catch (err) {
    return { ok: false, status: 0, bridgeError: "bridge_unreachable", bridgeMessage: String(err && err.message ? err.message : err) };
  }
  let payload = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    const errCode = (payload && payload.error_code) || `http_${response.status}`;
    const errMessage = (payload && payload.message) || `Bridge returned ${response.status}`;
    return { ok: false, status: response.status, bridgeError: errCode, bridgeMessage: errMessage };
  }
  return { ok: true, status: response.status, payload };
}

// ---------------------------------------------------------------------------
// Phase 2B-5B: Worker control client (stateless passthrough to Bridge)
// Calls /v1/workers/status, /v1/workers/pause, /v1/workers/resume
// Bridge is pure passthrough — Runner is sole state owner.
// ---------------------------------------------------------------------------

const BRIDGE_WORKER_CONTROL_URLS = {
  status: "http://127.0.0.1:27901/v1/workers/status",
  pause:  "http://127.0.0.1:27901/v1/workers/pause",
  resume: "http://127.0.0.1:27901/v1/workers/resume",
};

export async function callBridgeWorkerControl(controlAction, deps = {}) {
  const fetchImpl = deps.fetch ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    return { ok: false, status: 0, bridgeError: "bridge_unreachable", bridgeMessage: "fetch is not available" };
  }
  const url = BRIDGE_WORKER_CONTROL_URLS[controlAction];
  if (!url) {
    return { ok: false, status: 400, bridgeError: "INVALID_WORKER_CONTROL_ACTION", bridgeMessage: "Unknown worker control action" };
  }
  const readToken = deps.readToken ?? readBridgeToken;
  const token = readToken();
  const headers = { "content-type": "application/json" };
  if (token) headers["x-jarvis-bridge-token"] = token;
  let response;
  try {
    response = await fetchImpl(url, { method: "POST", headers, body: "{}" });
  } catch (err) {
    return { ok: false, status: 0, bridgeError: "bridge_unreachable", bridgeMessage: String(err && err.message ? err.message : err) };
  }
  let payload = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    const errCode  = (payload && payload.error_code) || `http_${response.status}`;
    const errMsg   = (payload && payload.message)  || `Bridge returned ${response.status}`;
    return { ok: false, status: response.status, bridgeError: errCode, bridgeMessage: errMsg };
  }
  return { ok: true, status: response.status, payload };
}

// Phase 2B-5B: Worker control execute bodies — stateless passthrough
function workerControlOutToResult(out) {
  if (!out.ok) {
    return failResult(out.bridgeError || "worker_control_failed", {
      bridgeError: out.bridgeError,
      bridgeMessage: out.bridgeMessage,
    });
  }
  const p = out.payload || {};
  return {
    content: [{ type: "text", text: JSON.stringify(p, null, 2) }],
    details: { status: p.status || "ok", workers_paused: p.workers_paused },
  };
}

export async function execWorkerControlStatus(_params, _config, deps) {
  const out = await callBridgeWorkerControl("status", deps || {});
  return workerControlOutToResult(out);
}

export async function execWorkerEmergencyStop(_params, _config, deps) {
  const out = await callBridgeWorkerControl("pause", deps || {});
  return workerControlOutToResult(out);
}

export async function execWorkerResume(_params, _config, deps) {
  const out = await callBridgeWorkerControl("resume", deps || {});
  return workerControlOutToResult(out);
}

const PLUGIN_DESCRIPTION =
  "OpenClaw Autumn tool plugin — existing Bridge-backed tools, Node Registry, and Companion file return/artifact publishing. " +
  "autumn_home exposes the Pi-local allowlisted Home Presence surface. " +
  "Seven legacy probes + two program tools preserved from Phase 3A-3. " +
  "Four Phase 2B-3B R1 worker tools: submit, status, cancel, result. " +
  "Two Phase 2B-4E2 authorization tools: authorization_request, authorization_approve. " +
  "Three Phase 2B-5B worker control tools: control_status, emergency_stop, resume. " +
  "autumn_nodes observes only the current Pi Node Registry; capability never grants authorization. " +
  "autumn_file_return returns one explicitly requested Windows file to Companion; autumn_companion_artifact creates a generated text artifact directly in the same Companion transfer store. " +
  "Worker operations: archive.list, archive.create (backend=direct) + R1 General ProcessJobSpec (type=process, catalog executables) + Codex (backend=codex).";

export default definePluginEntry({
  id: "jarvis-bridge-tool",
  name: "Jarvis Bridge Tool",
  description: PLUGIN_DESCRIPTION,
  register(api) {
    const cfg = api.pluginConfig || {};

    api.registerTool({
      name: "autumn_nodes",
      label: "Autumn node status",
      description:
        "Read-only current device presence and declared capabilities from the Pi Node Registry. " +
        "Use for device availability, online state, or current capabilities. " +
        "action=list or action=get with node_id. Presence is observational; CAPABILITY != AUTHORIZATION. " +
        "QUERY_FAILED means the Registry could not be queried, not that a device is offline.",
      parameters: AutumnNodesParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execAutumnNodes(_p, cfg, cfg),
    });

    api.registerTool({
      name: "autumn_home",
      label: "Autumn Home",
      description:
        "Read or control only devices explicitly present in Autumn's Pi-local Home allowlist. " +
        "Use action=list, action=state with a device alias, or action=control with a device alias + configured command. " +
        "Never invent Home Assistant entity IDs, domains, services or service data. Unallowlisted devices are invisible. " +
        "Only the adapter can map aliases to Home Assistant. CAPABILITY != AUTHORIZATION.",
      parameters: AutumnHomeParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execAutumnHome(_p, cfg, cfg),
    });

    api.registerTool({
      name: "autumn_file_return",
      label: "Return selected Windows file now",
      description:
        "Return one exact Windows file to the user's Autumn Companion download area. " +
        "For a request originating from an Autumn Companion/PWA session, this is the DEFAULT file-return transport: when the user explicitly selects an exact Windows path (or one unambiguous search result) and says send/return/download it, call this tool in the SAME TURN. " +
        "Do NOT switch to legacy Feishu/lark-file-sender merely because the user says 'send it to me'; use Feishu only when the user explicitly asks to send it to Feishu. " +
        "Do not merely acknowledge the request and do not claim the file is ready unless this tool returns status=ready. " +
        "Read-only on Windows: no delete, rename, move, shell, or arbitrary directory export. " +
        "The Runner still enforces the existing file export path and size policy.",
      parameters: AutumnFileReturnParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execAutumnFileReturn(_p, cfg, cfg),
    });

    api.registerTool({
      name: "autumn_companion_artifact",
      label: "Create a generated text file for this Companion chat",
      description:
        "Create one text/code/Markdown artifact directly in Autumn Companion's transfer store and make it downloadable in the current Companion turn. " +
        "Use this when the user asks you to turn content you generated into a file and send it HERE/current Companion chat. " +
        "Pass filename + complete text content; do not first write a Pi temp file, do not start an HTTP server, and do not send to Feishu unless the user explicitly asks for Feishu. " +
        "This tool cannot read arbitrary Pi files and cannot delete anything. It only creates a bounded text artifact.",
      parameters: AutumnCompanionArtifactParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execAutumnCompanionArtifact(_p, cfg, cfg),
    });

    // Five legacy tools
    api.registerTool({
      name: "jarvis_ping",
      label: "Autumn ping",
      description:
        "Probes the local Jarvis Bridge (127.0.0.1:27901) and reports its status.",
      parameters: EmptyParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execPing(_p, cfg, cfg),
    });
    api.registerTool({
      name: "jarvis_system_info",
      label: "Autumn system info",
      description:
        "Returns static Windows Runner metadata from the Bridge (no secret values).",
      parameters: EmptyParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execSystemInfo(_p, cfg, cfg),
    });
    api.registerTool({
      name: "jarvis_system_status",
      label: "Autumn system status",
      description:
        "Returns live Windows Runner CPU/memory/battery metrics from the Bridge.",
      parameters: EmptyParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execSystemStatus(_p, cfg, cfg),
    });
    api.registerTool({
      name: "jarvis_list_directory",
      label: "Autumn list directory",
      description:
        "Lists one Windows directory entry. Path is read-only; no shell, no mutation.",
      parameters: DirectoryParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execListDirectory(_p, cfg, cfg),
    });
    api.registerTool({
      name: "jarvis_search_files",
      label: "Autumn search files",
      description:
        "Searches Windows filenames under a root directory. Read-only, no exec.",
      parameters: SearchParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execSearchFiles(_p, cfg, cfg),
    });

    // Phase 3A-3: two new tools
    api.registerTool({
      name: "jarvis_program_list",
      label: "Autumn list programs",
      description:
        "\u5217\u51fa Autumn \u5f53\u524d\u5141\u8bb8\u5728 Windows \u4e0a\u8fd0\u884c\u7684\u767d\u540d\u5355 Python \u7a0b\u5e8f\u3002" +
        "\u8fd9\u662f\u53ea\u8bfb\u67e5\u8be2\uff0c\u4e0d\u8fd0\u884c\u7a0b\u5e8f\uff0c\u4e0d\u63a5\u53d7\u8def\u5f84\u6216\u4ee3\u7801\u3002",
      parameters: ProgramListParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execProgramList(_p, cfg, cfg),
    });
    api.registerTool({
      name: "jarvis_program_run",
      label: "Autumn run whitelisted program",
      description:
        "\u5728\u7528\u6237\u9010\u6b21\u786e\u8ba4\u540e\uff0c\u901a\u8fc7 Autumn \u5728 Windows \u4e0a\u8fd0\u884c\u4e00\u4e2a\u5df2\u767b\u8bb0\u7684\u767d\u540d\u5355 Python \u7a0b\u5e8f\u3002" +
        "\u4e0d\u80fd\u4f20\u5165\u8def\u5f84\u3001\u4ee3\u7801\u3001\u547d\u4ee4\u3001\u53c2\u6570\u6570\u7ec4\u6216\u73af\u5883\u53d8\u91cf\u3002\u5f53\u524d\u4ec5\u652f\u6301 hello_jarvis\u3002",
      parameters: ProgramRunParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execProgramRun(_p, cfg, cfg),
    });

    // Phase 2B-3B R1: four worker tools — archive operations + general process
    api.registerTool({
      name: "worker_submit",
      label: "Autumn worker submit",
      description:
        "Submit a job to the Windows Runner via the Bridge Job API. " +
        "Supports two operation families: " +
        "(1) archive.list / archive.create (backend=direct): list or create zip archives. " +
        "(2) type=process + executable (Runner Catalog ID): run a catalog program (7zip, git, python, node). " +
        "process: executable (catalog id), arguments (string array), cwd, timeout, write_scope, network_policy. " +
        "Pi plugin does NOT resolve executable paths — Runner Authority does. " +
        "Returns a job_id for status/result polling.",
      parameters: WorkerSubmitParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execWorkerSubmit(_p, cfg, cfg),
    });
    api.registerTool({
      name: "worker_status",
      label: "Autumn worker status",
      description:
        "Query the current state of a Runner job by job_id. " +
        "Returns bounded job state: queued / running / success / failed / cancelled / timeout. " +
        "No list-all-jobs; one job per call.",
      parameters: WorkerStatusParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execWorkerStatus(_p, cfg, cfg),
    });
    api.registerTool({
      name: "worker_cancel",
      label: "Autumn worker cancel",
      description:
        "Cancel a Runner job by job_id. " +
        "Termination is performed by the Windows Process Supervisor, not by the Bridge. " +
        "Returns the cancellation confirmation from Runner.",
      parameters: WorkerCancelParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execWorkerCancel(_p, cfg, cfg),
    });
    api.registerTool({
      name: "worker_result",
      label: "Autumn worker result",
      description:
        "Retrieve the terminal result of a Runner job by job_id. " +
        "If job is not yet terminal (queued/running), returns still running state. " +
        "No sleep/poll loops inside this tool.",
      parameters: WorkerResultParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execWorkerResult(_p, cfg, cfg),
    });

    // Phase 2B-4E2: Authorization tools
    api.registerTool({
      name: "worker_authorization_request",
      label: "Autumn worker authorization request",
      description:
        "Submit a Codex authorization request to the Windows Runner. " +
        "Returns an authorization_request_id that must be approved by the user before calling worker_authorization_approve. " +
        "Stateless passthrough — Bridge does not store or auto-approve requests.",
      parameters: WorkerAuthorizationRequestParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execWorkerAuthorizationRequest(_p, cfg, cfg),
    });
    api.registerTool({
      name: "worker_authorization_approve",
      label: "Autumn worker authorization approve",
      description:
        "Approve a pending Codex authorization request by ID. " +
        "The authorization_request_id must come from a prior worker_authorization_request call. " +
        "Stateless passthrough — Bridge does not store or track authorization state.",
      parameters: WorkerAuthorizationApproveParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execWorkerAuthorizationApprove(_p, cfg, cfg),
    });

    // Phase 2B-5B: Worker control tools — stateless passthrough to Bridge/Runner
    api.registerTool({
      name: "worker_control_status",
      label: "Autumn worker control status",
      description:
        "Query the Windows Runner worker pause/resume state. " +
        "Returns { workers_paused: boolean }. Bridge is a pure passthrough — Runner owns all state.",
      parameters: WorkerControlParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execWorkerControlStatus(_p, cfg, cfg),
    });
    api.registerTool({
      name: "worker_emergency_stop",
      label: "Autumn emergency stop",
      description:
        "Emergency-stop the Windows Runner: pause all job acceptance. " +
        "Jobs already running are best-effort cancelled. " +
        "New job submissions will be rejected with WORKERS_PAUSED until resume. " +
        "Bridge is a pure passthrough — Runner owns all state.",
      parameters: WorkerControlParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execWorkerEmergencyStop(_p, cfg, cfg),
    });
    api.registerTool({
      name: "worker_resume",
      label: "Autumn worker resume",
      description:
        "Resume the Windows Runner: unpause job acceptance. " +
        "Bridge is a pure passthrough — Runner owns all state. " +
        "Only call when the user explicitly requests resume.",
      parameters: WorkerControlParams,
      execute: async (toolCallId, _p, signal, onUpdate) =>
        await execWorkerResume(_p, cfg, cfg),
    });

  },
});
