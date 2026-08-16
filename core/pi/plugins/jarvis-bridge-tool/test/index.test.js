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
  capabilities: ["agent.main", "gateway", "bridge.forward"], metadata: {},
};
const WINDOWS = {
  protocol_version: "1", node_id: "windows-main", node_type: "windows",
  node_version: "runner-v1", online: "ONLINE", last_seen: "2026-08-14T00:00:00Z",
  capabilities: ["system.status", "file.search", "file.return", "job.submit", "job.status", "job.cancel", "codex.submit"], metadata: {},
};
const PHONE = {
  protocol_version: "1", node_id: "xiaomi15", node_type: "phone",
  node_version: "voice-pwa-v0.2", online: "UNKNOWN", last_seen: "2026-08-14T00:00:00Z",
  capabilities: ["voice.listen", "voice.speak", "open_url", "clipboard.set"], metadata: {},
};

test("manifest and runtime register the exact current tool set", () => {
  const api = loadPlugin();
  const names = api.registeredTools.map((entry) => entry.tool.name).sort();
  assert.deepEqual(names, [
    "autumn_companion_artifact", "autumn_file_return", "autumn_nodes", "jarvis_list_directory", "jarvis_ping", "jarvis_program_list",
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
