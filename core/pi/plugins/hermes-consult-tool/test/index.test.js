// hermes-consult-tool Phase 2A-3 tests.
// All backend calls below use mocks or injected local fixtures. No Hermes or
// MiniMax request is made by this suite.

import test from "node:test";
import assert from "node:assert/strict";

import pluginEntry, {
  API_SERVER_ENDPOINT,
  ApiServerBackend,
  ConsultParamsSchema,
  ERROR_INTERNAL,
  ERROR_INVALID_RESPONSE,
  ERROR_NONE,
  ERROR_RATE_LIMITED,
  ERROR_REJECTED,
  ERROR_TIMEOUT,
  ERROR_UNAVAILABLE,
  HermesConsultBackend,
  MockHermesConsultBackend,
  STATUS_INVALID_RESPONSE,
  STATUS_OK,
  STATUS_TIMEOUT,
  SESSION_TOOL_NAME,
  createProductionBackend,
  execHermesConsult,
  normalizedResult,
  registerHermesConsultTool,
} from "../dist/index.js";

function captureRegisterApi() {
  const api = { registeredTools: [] };
  api.registerTool = (tool, opts) => api.registeredTools.push({ tool, opts });
  return api;
}

function fakeResponse(status, payload, malformed = false) {
  return {
    status,
    async json() {
      if (malformed) throw new Error("malformed fixture");
      return payload;
    },
  };
}

function assertNormalized(result, expected) {
  assert.deepEqual(Object.keys(result).sort(), [
    "answer",
    "consult_id",
    "error_code",
    "status",
  ]);
  assert.deepEqual(result, expected);
}

test("production registration uses ApiServerBackend and frozen Consult plus Session tools", () => {
  const api = captureRegisterApi();
  pluginEntry.register(api);
  assert.equal(api.registeredTools.length, 2);
  assert.equal(api.registeredTools[0].tool.name, "hermes_consult");
  assert.equal(api.registeredTools[1].opts.name, "hermes_session");
  assert.ok(createProductionBackend() instanceof ApiServerBackend);
  assert.deepEqual(
    Object.keys(api.registeredTools[0].tool.parameters.properties).sort(),
    ["context", "question"],
  );
});

test("registered Session factory exposes local status without a backend call", async () => {
  const api = captureRegisterApi();
  pluginEntry.register(api);
  const sessionTool = api.registeredTools[1].tool({ sessionId: "offline-status-conversation" });
  assert.equal(api.registeredTools[1].opts.name, SESSION_TOOL_NAME);
  assert.equal(sessionTool.name, SESSION_TOOL_NAME);
  const result = await sessionTool.execute("offline-status", { action: "status" });
  assert.deepEqual(result.details, { active: false, turn_count: 0 });
});

test("schema and execution reject unknown control fields", async () => {
  assert.equal(ConsultParamsSchema.additionalProperties, false);
  assert.deepEqual(ConsultParamsSchema.required, ["question"]);
  const backend = new MockHermesConsultBackend();
  for (const params of [
    { question: "q", endpoint: "x" },
    { question: "q", api_key: "x" },
    { question: "q", provider: "x" },
    { question: "q", model: "x" },
    { question: "q", session_id: "x" },
    { question: "q", toolset: "x" },
    { question: "q", memory_path: "x" },
    { question: "q", file_path: "x" },
    { question: "q", shell: "x" },
    { question: "q", timeout: 1 },
  ]) {
    const out = await execHermesConsult(backend, params);
    assert.equal(out.details.error_code, ERROR_INVALID_RESPONSE);
  }
  assert.equal(backend.consultCount, 0);
});

test("frozen question/context bounds are retained", () => {
  assert.equal(ConsultParamsSchema.properties.question.maxLength, 2000);
  assert.equal(ConsultParamsSchema.properties.context.maxLength, 2000);
  assert.equal(ConsultParamsSchema.properties.context.minLength, 1);
});

test("HermesConsultBackend remains abstract", () => {
  assert.throws(() => new HermesConsultBackend(), /abstract/);
});

test("ApiServerBackend success uses the official request and response shape", async () => {
  let call;
  const backend = new ApiServerBackend({
    apiKey: "synthetic-api-server-key",
    fetchImpl: async (url, options) => {
      call = { url, options };
      return fakeResponse(200, {
        id: "chatcmpl-fixture-001",
        choices: [{ message: { role: "assistant", content: "A safe fixture answer." } }],
      });
    },
  });
  const result = await backend.consult({
    question: "question fixture",
    context: "context fixture",
  });
  assertNormalized(result, {
    status: STATUS_OK,
    answer: "A safe fixture answer.",
    consult_id: "chatcmpl-fixture-001",
    error_code: ERROR_NONE,
  });
  assert.equal(call.url, API_SERVER_ENDPOINT);
  assert.equal(call.options.method, "POST");
  assert.equal(call.options.headers.Authorization, "Bearer synthetic-api-server-key");
  const request = JSON.parse(call.options.body);
  assert.deepEqual(Object.keys(request).sort(), ["messages", "model", "stream"]);
  assert.equal(request.model, "hermes-agent");
  assert.equal(request.stream, false);
  assert.deepEqual(request.messages, [{
    role: "user",
    content: "Context:\ncontext fixture\n\nQuestion:\nquestion fixture",
  }]);
});

test("ApiServerBackend allows a delayed local response within its bounded window", async () => {
  const backend = new ApiServerBackend({
    timeoutMs: 100,
    fetchImpl: async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
      return fakeResponse(200, {
        id: "chatcmpl-delayed-fixture-001",
        choices: [{ message: { role: "assistant", content: "Delayed fixture answer." } }],
      });
    },
  });
  const result = await backend.consult({ question: "delayed fixture" });
  assertNormalized(result, {
    status: STATUS_OK,
    answer: "Delayed fixture answer.",
    consult_id: "chatcmpl-delayed-fixture-001",
    error_code: ERROR_NONE,
  });
});

test("invalid, empty, malformed, and unexpected responses normalize to INVALID_RESPONSE", async () => {
  const fixtures = [
    null,
    {},
    { id: "x", choices: [] },
    { id: "x", choices: [{ message: {} }] },
    { id: "x", choices: [{ message: { content: "" } }] },
    { id: "x", choices: [{ message: { content: "ok" } }] },
  ];
  for (const payload of fixtures) {
    const backend = new ApiServerBackend({
      fetchImpl: async () => fakeResponse(200, payload),
    });
    const result = await backend.consult({ question: "q" });
    assert.equal(result.error_code, ERROR_INVALID_RESPONSE);
    assert.equal(result.consult_id, null);
    assert.ok(result.answer.length > 0);
  }
  const malformedBackend = new ApiServerBackend({
    fetchImpl: async () => fakeResponse(200, null, true),
  });
  const malformed = await malformedBackend.consult({ question: "q" });
  assert.equal(malformed.error_code, ERROR_INVALID_RESPONSE);
});

test("HTTP and transport faults normalize to stable codes", async () => {
  const rate = new ApiServerBackend({
    fetchImpl: async () => fakeResponse(429, { error: "redacted" }),
  });
  assert.equal((await rate.consult({ question: "q" })).error_code, ERROR_RATE_LIMITED);

  const rejected = new ApiServerBackend({
    fetchImpl: async () => fakeResponse(400, { error: "1026 redacted" }),
  });
  assert.equal((await rejected.consult({ question: "q" })).error_code, ERROR_REJECTED);

  const offline = new ApiServerBackend({
    fetchImpl: async () => {
      throw new TypeError("connection refused at redacted endpoint");
    },
  });
  assert.equal((await offline.consult({ question: "q" })).error_code, ERROR_UNAVAILABLE);

  const internal = new ApiServerBackend({
    fetchImpl: async () => {
      throw new Error("internal stack and secret");
    },
  });
  assert.equal((await internal.consult({ question: "q" })).error_code, ERROR_INTERNAL);
});

test("bounded timeout normalizes without leaking raw exception", async () => {
  const backend = new ApiServerBackend({
    timeoutMs: 10,
    fetchImpl: async (_url, { signal }) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => {
          const error = new Error("raw timeout details");
          error.name = "AbortError";
          reject(error);
        });
      }),
  });
  const result = await backend.consult({ question: "q" });
  assert.equal(result.error_code, ERROR_TIMEOUT);
  assert.ok(!JSON.stringify(result).includes("raw timeout"));
});

test("normalized failure results satisfy the frozen four-field shape", async () => {
  for (const mode of ["timeout", "rate_limited", "rejected", "unavailable"]) {
    const result = await new MockHermesConsultBackend({ mode }).consult({ question: "q" });
    assert.equal(result.answer.length > 0, true);
    assert.equal(result.consult_id, null);
    assert.ok(result.error_code);
  }
});

test("tool execution normalizes backend exceptions and arbitrary shapes", async () => {
  const raw = await execHermesConsult(
    new MockHermesConsultBackend({ mode: "raw_exception" }),
    { question: "q" },
  );
  assert.equal(raw.details.error_code, ERROR_INTERNAL);
  assert.ok(!JSON.stringify(raw).includes("RAW_UPSTREAM_SECRET"));

  const unexpected = await execHermesConsult(
    new MockHermesConsultBackend({ mode: "unexpected_shape" }),
    { question: "q" },
  );
  assert.equal(unexpected.details.error_code, ERROR_INVALID_RESPONSE);
  assert.ok(!JSON.stringify(unexpected).includes("sensitive"));
});

test("explicit test injection keeps mock out of production default", async () => {
  const api = captureRegisterApi();
  registerHermesConsultTool(api, new MockHermesConsultBackend({ mode: "ok" }));
  const out = await api.registeredTools[0].tool.execute("test-call", {
    question: "offline",
  });
  assert.equal(out.details.status, STATUS_OK);
  assert.ok(out.details.answer.includes("[mock]"));
});

test("normalized results expose no internal transport metadata", async () => {
  const backend = new ApiServerBackend({
    apiKey: "synthetic-secret",
    fetchImpl: async () => {
      throw new Error("https://internal.example secret provider model stack");
    },
  });
  const result = await backend.consult({ question: "q" });
  const serialized = JSON.stringify(result);
  for (const forbidden of [
    API_SERVER_ENDPOINT,
    "synthetic-secret",
    "internal.example",
    "provider",
    "stack",
  ]) {
    assert.ok(!serialized.includes(forbidden));
  }
});

test("normalizedResult retains exactly the frozen keys", () => {
  const result = normalizedResult(STATUS_OK, "answer", ERROR_NONE, "opaque-id");
  assert.deepEqual(Object.keys(result).sort(), [
    "answer",
    "consult_id",
    "error_code",
    "status",
  ]);
});
