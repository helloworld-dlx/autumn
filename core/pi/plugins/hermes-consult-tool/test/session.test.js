import test from "node:test";
import assert from "node:assert/strict";

import {
  ApiServerBackend,
  ERROR_NONE,
  ERROR_SESSION_CONTEXT_UNAVAILABLE,
  ERROR_SESSION_INVALID,
  ERROR_SESSION_MAX_TURNS,
  ERROR_TIMEOUT,
  EphemeralHermesSessionRegistry,
  SessionParamsSchema,
  SESSION_IDLE_EXPIRY_MS,
  SESSION_API_SERVER_ENDPOINT,
  SESSION_MAX_USER_TURNS,
  STATUS_OK,
  createHermesSessionTool,
  execHermesSession,
  normalizedResult,
  registerHermesSessionTool,
} from "../dist/index.js";

function fakeResponse(status, payload) {
  return { status, async json() { return payload; } };
}

function makeFixtureRegistry(options = {}) {
  const calls = [];
  let answerNumber = 0;
  const backend = options.backend || {
    async session(messages) {
      calls.push(structuredClone(messages));
      if (options.nextResult) return options.nextResult(messages);
      answerNumber += 1;
      return normalizedResult(
        STATUS_OK,
        `fixture-answer-${answerNumber}`,
        ERROR_NONE,
        `fixture-response-${answerNumber}`,
      );
    },
  };
  const registry = new EphemeralHermesSessionRegistry({
    backend,
    clock: options.clock,
  });
  return { calls, backend, registry };
}

async function invoke(tool, params) {
  return (await tool.execute("offline-session-test", params)).details;
}

function sessionTool(registry, conversationKey) {
  return createHermesSessionTool(registry.get(conversationKey));
}

test("ApiServerBackend sends bounded session messages with zero tools", async () => {
  let call;
  const backend = new ApiServerBackend({
    apiKey: "synthetic-session-key",
    fetchImpl: async (url, options) => {
      call = { url, options };
      return fakeResponse(200, {
        id: "chatcmpl-session-fixture-001",
        choices: [{ message: { role: "assistant", content: "session answer" } }],
      });
    },
  });
  const messages = [
    { role: "user", content: "first" },
    { role: "assistant", content: "prior answer" },
    { role: "user", content: "second" },
  ];
  const result = await backend.session(messages);
  assert.equal(result.status, STATUS_OK);
  assert.equal(result.consult_id, "chatcmpl-session-fixture-001");
  assert.equal(call.url, SESSION_API_SERVER_ENDPOINT);
  assert.equal(call.options.headers.Authorization, "Bearer synthetic-session-key");
  const request = JSON.parse(call.options.body);
  assert.deepEqual(Object.keys(request).sort(), ["messages", "stream"]);
  assert.equal(request.stream, false);
  assert.deepEqual(request.messages, messages);
  assert.equal("tools" in request, false);
  assert.equal("model" in request, false);
  assert.equal("X-Hermes-Session-Id" in call.options.headers, false);
});

test("start and message preserve bounded prior context without exposing an id", async () => {
  const { calls, registry } = makeFixtureRegistry();
  const tool = sessionTool(registry, "conversation-a");
  const started = await invoke(tool, { action: "start", message: "first" });
  assert.equal(started.status, STATUS_OK);
  assert.equal(started.turn_count, 1);
  const continued = await invoke(tool, { action: "message", message: "second" });
  assert.equal(continued.status, STATUS_OK);
  assert.equal(continued.turn_count, 2);
  assert.deepEqual(calls[1], [
    { role: "user", content: "first" },
    { role: "assistant", content: "fixture-answer-1" },
    { role: "user", content: "second" },
  ]);
  assert.equal("session_id" in continued, false);
  assert.equal(JSON.stringify(continued).includes("fixture-response-2"), false);
  assert.deepEqual(await invoke(tool, { action: "status" }), { active: true, turn_count: 2 });
});

test("end clears history and later messages cannot reuse it", async () => {
  const { calls, registry } = makeFixtureRegistry();
  const tool = sessionTool(registry, "conversation-end");
  await invoke(tool, { action: "start", message: "private first" });
  assert.equal((await invoke(tool, { action: "end" })).active, false);
  const inactive = await invoke(tool, { action: "message", message: "must not continue" });
  assert.equal(inactive.status, "inactive");
  assert.equal(calls.length, 1);
  assert.deepEqual(await invoke(tool, { action: "status" }), { active: false, turn_count: 0 });
});

test("one active session per conversation and no cross-conversation history", async () => {
  const { calls, registry } = makeFixtureRegistry();
  const first = sessionTool(registry, "conversation-one");
  const secondFactoryView = sessionTool(registry, "conversation-one");
  const other = sessionTool(registry, "conversation-two");
  await invoke(first, { action: "start", message: "one" });
  const duplicate = await invoke(secondFactoryView, { action: "start", message: "duplicate" });
  assert.equal(duplicate.status, "already_active");
  await invoke(other, { action: "start", message: "two" });
  assert.deepEqual(calls[1], [{ role: "user", content: "two" }]);
  await invoke(first, { action: "message", message: "one-followup" });
  assert.deepEqual(calls[2], [
    { role: "user", content: "one" },
    { role: "assistant", content: "fixture-answer-1" },
    { role: "user", content: "one-followup" },
  ]);
});

test("max 8 user turns blocks expansion without compression", async () => {
  const { calls, registry } = makeFixtureRegistry();
  const tool = sessionTool(registry, "conversation-limit");
  await invoke(tool, { action: "start" });
  for (let index = 0; index < SESSION_MAX_USER_TURNS; index += 1) {
    await invoke(tool, { action: "message", message: `turn-${index}` });
  }
  const blocked = await invoke(tool, { action: "message", message: "turn-9" });
  assert.equal(calls.length, SESSION_MAX_USER_TURNS);
  assert.equal(blocked.error_code, ERROR_SESSION_MAX_TURNS);
  assert.equal(blocked.turn_count, SESSION_MAX_USER_TURNS);
  assert.deepEqual(await invoke(tool, { action: "status" }), { active: true, turn_count: 8 });
});

test("30 minute idle expiry clears the in-memory session", async () => {
  let now = 1000;
  const { calls, registry } = makeFixtureRegistry({ clock: () => now });
  const tool = sessionTool(registry, "conversation-idle");
  await invoke(tool, { action: "start", message: "old" });
  now += SESSION_IDLE_EXPIRY_MS;
  assert.deepEqual(await invoke(tool, { action: "status" }), { active: false, turn_count: 0 });
  await invoke(tool, { action: "start", message: "new" });
  assert.deepEqual(calls[1], [{ role: "user", content: "new" }]);
});

test("timeout or error keeps the active session and prior history intact", async () => {
  let callNumber = 0;
  const calls = [];
  const backend = {
    async session(messages) {
      calls.push(structuredClone(messages));
      callNumber += 1;
      if (callNumber === 2) return { status: "timeout", answer: "timed out", consult_id: null, error_code: ERROR_TIMEOUT };
      return normalizedResult(STATUS_OK, `answer-${callNumber}`, ERROR_NONE, `response-${callNumber}`);
    },
  };
  const registry = new EphemeralHermesSessionRegistry({ backend });
  const tool = sessionTool(registry, "conversation-error");
  await invoke(tool, { action: "start", message: "kept" });
  const failed = await invoke(tool, { action: "message", message: "failed turn" });
  assert.equal(failed.error_code, ERROR_TIMEOUT);
  assert.deepEqual(await invoke(tool, { action: "status" }), { active: true, turn_count: 1 });
  await invoke(tool, { action: "message", message: "retry" });
  assert.equal(calls[2].some((item) => item.content === "failed turn"), false);
  assert.equal(calls[2][0].content, "kept");
});

test("factory binds state to trusted conversation context and refuses missing context", async () => {
  const { calls, registry, backend } = makeFixtureRegistry();
  const registered = [];
  registerHermesSessionTool({ registerTool(tool) { registered.push(tool); } }, backend, registry);
  assert.equal(registered.length, 1);
  const factory = registered[0];
  const toolA = factory({ sessionId: "openclaw-conversation-a" });
  const toolAAgain = factory({ sessionId: "openclaw-conversation-a" });
  const toolB = factory({ sessionId: "openclaw-conversation-b" });
  await invoke(toolA, { action: "start", message: "a" });
  assert.equal((await invoke(toolAAgain, { action: "start" })).status, "already_active");
  await invoke(toolB, { action: "start", message: "b" });
  assert.deepEqual(calls[1], [{ role: "user", content: "b" }]);
  const missing = factory({});
  const unavailable = await invoke(missing, { action: "start" });
  assert.equal(unavailable.error_code, ERROR_SESSION_CONTEXT_UNAVAILABLE);
});

test("session schema rejects model-controlled routing, identity, storage, and tool fields", async () => {
  assert.equal(SessionParamsSchema.additionalProperties, false);
  assert.deepEqual(SessionParamsSchema.required, ["action"]);
  const { registry, backend } = makeFixtureRegistry();
  const session = registry.get("contract-conversation");
  for (const field of ["endpoint", "url", "provider", "model", "api_key", "timeout", "session_id", "storage_path", "toolset", "memory_path", "history_path"]) {
    const result = await execHermesSession(session, { action: "message", message: "x", [field]: "model-controlled" });
    assert.equal(result.details.error_code, ERROR_SESSION_INVALID, field);
  }
  assert.equal(backend.session, backend.session);
  assert.deepEqual(await invoke(createHermesSessionTool(session), { action: "status" }), { active: false, turn_count: 0 });
  assert.equal("runtimeSessionId" in session, true);
  assert.equal("storagePath" in session, false);
  assert.equal("historyPath" in session, false);
});
