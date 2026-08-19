// jarvis-bridge-tool current contract tests.
// All network input is mocked; no test calls the Bridge or a Runner.

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import pluginEntry, {
  callBridgeNodes,
  callBridgeFileReturn,
  callBridgeCompanionArtifact,
  execAutumnNodes,
  execAutumnFileReturn,
  execAutumnCompanionArtifact,
  execPing,
  execSearchFiles,
  callBridgeHome,
  execAutumnHome,
} from "../dist/index.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = resolve(HERE, "..");

function captureRegisterApi() {
  const api = { registeredTools: [], pluginConfig: {} };
  api.registerTool = (tool, opts) => api.registeredTools.push({ tool, opts });
  return api;
}

function loadPlugin() {
  const api = captureRegisterApi();
  pluginEntry.register(api);
  return api;
}

function jsonResponse(status, payload) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function fakeFetch(responses) {
  const calls = [];
  return {
    calls,
    fetch: async (url, init) => {
      calls.push({ url, init });
      return responses.shift();
    },
  };
}

const PI5 = {
  protocol_version: "1", node_id: "pi5-core", node_type: "core",
  node_version: "v0.2-frozen", online: "ONLINE", last_seen: "2026-08-14T00:00:00Z",
  capabilities: ["agent.main", "gateway", "bridge.forward", "home.read", "home.control"], metadata: {},
};
const WINDOWS = {
  protocol_version: "1", node_id: "windows-main", node_type: "windows",
  node_version: "runner-v1", online: "ONLINE", last_seen: "2026-08-14T00:00:00Z",
  capabilities: ["system.status", "file.search", "file.return", "job.submit", "job.status", "job.cancel", "codex.submit"], metadata: {},
};
const PHONE = {
  protocol_version: "1", node_id: "xiaomi15", node_type: "phone",
  node_version: "companion-pwa-v19", online: "UNKNOWN", last_seen: "2026-08-14T00:00:00Z",
  capabilities: ["voice.listen", "voice.speak", "camera.capture", "open_url", "clipboard.set"], metadata: {},
};

test("manifest and runtime register the exact current tool set", () => {
  const api = loadPlugin();
  const names = api.registeredTools.map((entry) => entry.tool.name).sort();
  assert.deepEqual(names, [
    "autumn_companion_artifact", "autumn_file_return", "autumn_home", "autumn_nodes", "jarvis_list_directory", "jarvis_ping", "jarvis_program_list",
    "jarvis_program_run", "jarvis_search_files", "jarvis_system_info", "jarvis_system_status",
    "worker_authorization_approve", "worker_authorization_request", "worker_cancel",
    "worker_control_status", "worker_emergency_stop", "worker_result", "worker_resume",
    "worker_status", "worker_submit",
  ]);
  const manifest = JSON.parse(readFileSync(join(PLUGIN_ROOT, "openclaw.plugin.json"), "utf8"));
  assert.deepEqual([...manifest.contracts.tools].sort(), names);
});

test("autumn_nodes exposes only list and get parameters", () => {
  const api = loadPlugin();
  const tool = api.registeredTools.find((entry) => entry.tool.name === "autumn_nodes").tool;
  assert.equal(tool.parameters.anyOf.length, 2);
  assert.match(tool.description, /read-only/i);
  assert.match(tool.description, /CAPABILITY != AUTHORIZATION/);
});

test("autumn_nodes list/get make fixed GET Registry queries and return bounded nodes", async () => {
  const mock = fakeFetch([
    jsonResponse(200, { nodes: [PI5, WINDOWS, PHONE] }),
    jsonResponse(200, { ...WINDOWS, metadata: { private_field: "must-not-leak" } }),
  ]);
  const list = await execAutumnNodes({ action: "list" }, {}, { fetch: mock.fetch });
  assert.equal(list.details.status, "OK");
  assert.deepEqual(list.details.nodes.map((node) => node.node_id), ["pi5-core", "windows-main", "xiaomi15"]);
  assert.equal(list.details.nodes[2].online, "UNKNOWN");
  assert.equal(list.details.nodes[2].online === "OFFLINE", false);
  const get = await execAutumnNodes({ action: "get", node_id: "windows-main" }, {}, { fetch: mock.fetch });
  assert.equal(get.details.status, "OK");
  assert.deepEqual(get.details.node.capabilities, WINDOWS.capabilities);
  assert.equal(JSON.stringify(get).includes("must-not-leak"), false);
  assert.deepEqual(mock.calls.map((call) => call.init.method), ["GET", "GET"]);
  assert.equal(mock.calls[0].url, "http://127.0.0.1:27901/v1/nodes");
  assert.equal(mock.calls[1].url, "http://127.0.0.1:27901/v1/nodes/windows-main");
});

test("registry failure is QUERY_FAILED and unknown node is not offline", async () => {
  const unavailable = await execAutumnNodes(
    { action: "list" }, {}, { fetch: async () => { throw new Error("unreachable"); } },
  );
  assert.equal(unavailable.details.status, "QUERY_FAILED");
  assert.equal(JSON.stringify(unavailable).includes("OFFLINE"), false);
  const missing = await execAutumnNodes(
    { action: "get", node_id: "missing-node" }, {}, { fetch: async () => jsonResponse(404, { error_code: "NOT_FOUND" }) },
  );
  assert.equal(missing.details.status, "NODE_NOT_FOUND");
});

test("invalid Node input has no write path and cannot form an arbitrary URL", async () => {
  const invalid = await callBridgeNodes("get", "windows/main", {
    fetch: async () => { throw new Error("must not call"); },
  });
  assert.equal(invalid.bridgeError, "invalid_node_id");
  const action = await execAutumnNodes(
    { action: "touch", node_id: "xiaomi15" }, {}, { fetch: async () => { throw new Error("must not call"); } },
  );
  assert.equal(action.details.status, "QUERY_FAILED");
});

test("autumn_file_return is exact-path, token-authenticated, and does not leak Pi local paths", async () => {
  const mock = fakeFetch([jsonResponse(200, {
    status: "succeeded", transfer_id: "abcdefghijklmnop", filename: "report.pdf", size: 1234,
    sha256: "deadbeef", local_path: "/must/not/leak",
  })]);
  const raw = await callBridgeFileReturn("D:\\docs\\report.pdf", {
    fetch: mock.fetch, readToken: () => "t".repeat(32),
  });
  assert.equal(raw.ok, true);
  assert.equal(mock.calls[0].url, "http://127.0.0.1:27901/v1/files/pull");
  assert.equal(mock.calls[0].init.method, "POST");
  assert.equal(mock.calls[0].init.headers["x-jarvis-bridge-token"], "t".repeat(32));
  assert.deepEqual(JSON.parse(mock.calls[0].init.body), { path: "D:\\docs\\report.pdf" });
  const result = await execAutumnFileReturn({ path: "D:\\docs\\report.pdf" }, {}, {
    fetch: async () => jsonResponse(200, { status: "succeeded", transfer_id: "abcdefghijklmnop", filename: "report.pdf", size: 1234 }),
    readToken: () => "t".repeat(32),
  });
  assert.equal(result.details.status, "ready");
  assert.equal(result.details.transfer_id, "abcdefghijklmnop");
  assert.equal(JSON.stringify(result).includes("local_path"), false);
});

test("autumn_companion_artifact creates bounded text files without arbitrary Pi path access", async () => {
  const mock = fakeFetch([jsonResponse(200, {
    status: "succeeded", transfer_id: "qrstuvwxyzABCDEF", filename: "note.md", size: 5, sha256: "abc",
  })]);
  const raw = await callBridgeCompanionArtifact("note.md", "hello", {
    fetch: mock.fetch, readToken: () => "t".repeat(32),
  });
  assert.equal(raw.ok, true);
  assert.equal(mock.calls[0].url, "http://127.0.0.1:27901/v1/files/publish-text");
  assert.deepEqual(JSON.parse(mock.calls[0].init.body), { filename: "note.md", content: "hello" });
  const result = await execAutumnCompanionArtifact({ filename: "note.md", content: "hello" }, {}, {
    fetch: async () => jsonResponse(200, { status: "succeeded", transfer_id: "qrstuvwxyzABCDEF", filename: "note.md", size: 5 }),
    readToken: () => "t".repeat(32),
  });
  assert.equal(result.details.status, "ready");
  assert.equal(result.details.transfer_id, "qrstuvwxyzABCDEF");
  assert.equal(JSON.stringify(result).includes("local_path"), false);
  const rejected = await callBridgeCompanionArtifact("../secret.md", "x", { fetch: async () => { throw new Error("must not call"); } });
  assert.equal(rejected.bridgeError, "artifact_filename_invalid");
});

test("existing read-only ping remains a single Bridge request", async () => {
  const mock = fakeFetch([jsonResponse(200, { pong: true })]);
  const result = await execPing({}, {}, { fetch: mock.fetch, readToken: () => null });
  assert.equal(result.details.ok, true);
  assert.equal(mock.calls.length, 1);
  assert.equal(mock.calls[0].init.method, "POST");
});

test("jarvis_search_files exposes path/query/kind and forwards the exact contract", async () => {
  const api = loadPlugin();
  const tool = api.registeredTools.find((entry) => entry.tool.name === "jarvis_search_files").tool;
  assert.deepEqual(Object.keys(tool.parameters.properties).sort(), ["kind", "max_results", "path", "query"]);
  assert.equal(tool.parameters.additionalProperties, false);
  assert.equal(tool.parameters.properties.root, undefined);
  assert.equal(tool.parameters.properties.pattern, undefined);

  const mock = fakeFetch([jsonResponse(200, { status: "success", result: { items: [{ path: "D:\\\\Study\\\\总结与计划", kind: "directory" }], returned_count: 1 } })]);
  const result = await execSearchFiles({ path: "D:\\\\", query: "总结与计划", kind: "directory", max_results: 7 }, {}, { fetch: mock.fetch });
  assert.equal(result.details.bridge_status, 200);
  assert.deepEqual(JSON.parse(mock.calls[0].init.body), {
    action: "files.search",
    arguments: { path: "D:\\\\", query: "总结与计划", kind: "directory", max_results: 7 },
  });
});

test("jarvis_search_files forwards file kind and keeps internal root/pattern compatibility", async () => {
  const mock = fakeFetch([
    jsonResponse(200, { status: "success", result: { items: [], returned_count: 0 } }),
    jsonResponse(200, { status: "success", result: { items: [], returned_count: 0 } }),
  ]);
  await execSearchFiles({ path: "D:\\\\", query: "note.txt", kind: "file", max_results: 3 }, {}, { fetch: mock.fetch });
  assert.deepEqual(JSON.parse(mock.calls[0].init.body).arguments, { path: "D:\\\\", query: "note.txt", kind: "file", max_results: 3 });
  await execSearchFiles({ root: "D:\\\\", pattern: "legacy" }, {}, { fetch: mock.fetch });
  assert.deepEqual(JSON.parse(mock.calls[1].init.body).arguments, { path: "D:\\\\", query: "legacy", max_results: 50 });
});

test("jarvis_search_files surfaces Runner path rejection instead of returning an empty success", async () => {
  const mock = fakeFetch([jsonResponse(200, { status: "rejected", error_code: "PATH_NOT_ALLOWED", message: "path is not allowed" })]);
  const result = await execSearchFiles({ path: "C:\\\\", query: "Windows", kind: "file" }, {}, { fetch: mock.fetch });
  assert.equal(result.details.status, "failed");
  assert.equal(result.details.bridgeError, "PATH_NOT_ALLOWED");
});

test("autumn_home uses the fixed Bridge route and sanitizes safe responses", async () => {
  const mock = fakeFetch([jsonResponse(200, { status: "OK", devices: [{ device: "desk_lamp", label: "Desk Lamp", readable: true, commands: ["on"], risk: "low", confirm: false, entity_id: "light.secret" }] })]);
  const raw = await callBridgeHome({ action: "list" }, { fetch: mock.fetch, readToken: () => "t".repeat(32) });
  assert.equal(raw.ok, true);
  assert.equal(mock.calls[0].url, "http://127.0.0.1:27901/v1/home");
  assert.equal(mock.calls[0].init.headers["x-jarvis-bridge-token"], "t".repeat(32));
  const result = await execAutumnHome({ action: "list" }, {}, { fetch: async () => jsonResponse(200, { status: "OK", device: "desk_lamp", label: "Desk Lamp", state: { state: "on", entity_id: "light.secret", service: "turn_on" } }) });
  assert.equal(result.details.status, "OK");
  assert.equal(JSON.stringify(result).includes("entity_id"), false);
  assert.equal(JSON.stringify(result).includes("service"), false);
});

test("autumn_home validates control shape before fetch and surfaces unknown aliases", async () => {
  let calls = 0;
  const fetch = async () => { calls += 1; return jsonResponse(404, { error_code: "HOME_DEVICE_NOT_FOUND" }); };
  const invalid = await callBridgeHome({ action: "control", device: "desk_lamp", command: "on", service: "unlock" }, { fetch });
  assert.equal(invalid.bridgeError, "HOME_REQUEST_INVALID");
  assert.equal(calls, 0);
  const missing = await execAutumnHome({ action: "state", device: "door_lock" }, {}, { fetch });
  assert.equal(missing.details.status, "failed");
  assert.equal(missing.details.reason, "HOME_DEVICE_NOT_FOUND");
});

test("autumn_home accepts bounded control value and rejects invalid values", async () => {
  const seen=[];
  const fetch=async (url,init)=>{seen.push(JSON.parse(init.body));return jsonResponse(200,{status:"OK",state:{state:"on",percentage:35}})};
  const ok=await callBridgeHome({action:"control",device:"room_fan",command:"set_speed",value:35},{fetch});
  assert.equal(ok.ok,true); assert.deepEqual(seen[0],{action:"control",device:"room_fan",command:"set_speed",value:35});
  for(const value of [-1,101,1.5,true]){
    const invalid=await callBridgeHome({action:"control",device:"room_fan",command:"set_speed",value},{fetch});
    assert.equal(invalid.bridgeError,"HOME_REQUEST_INVALID");
  }
});
