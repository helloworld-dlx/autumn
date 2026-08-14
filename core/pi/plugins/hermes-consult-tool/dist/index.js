// hermes-consult-tool plugin (Autumn V0.2 Phase 2A-3)
//
// Exposes exactly one internal tool to the Autumn main agent:
//   hermes_consult(question, context?)
//
// The public contract is intentionally narrower than the Hermes API server.
// Transport, auth, model, provider, toolsets, session state and timeout are
// all controlled here or by the host/test harness; none are model inputs.

import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { Type } from "typebox";
import { randomUUID } from "node:crypto";

// ---------------------------------------------------------------------------
// Frozen contract and controlled transport configuration
// ---------------------------------------------------------------------------

export const TOOL_NAME = "hermes_consult";

export const QUESTION_MIN_CHARS = 1;
export const QUESTION_MAX_CHARS = 2000;
export const CONTEXT_MAX_CHARS = 2000;

export const STATUS_OK = "ok";
export const STATUS_TIMEOUT = "timeout";
export const STATUS_RATE_LIMITED = "rate_limited";
export const STATUS_REJECTED = "rejected";
export const STATUS_UNAVAILABLE = "unavailable";
export const STATUS_INVALID_RESPONSE = "invalid_response";

// Compatibility alias for older internal tests; it is never emitted.
export const STATUS_FAILED = STATUS_UNAVAILABLE;

export const ERROR_NONE = null;
export const ERROR_UNAVAILABLE = "HERMES_UNAVAILABLE";
export const ERROR_RATE_LIMITED = "PROVIDER_RATE_LIMIT";
export const ERROR_REJECTED = "PROVIDER_REJECTED";
export const ERROR_TIMEOUT = "CONSULT_TIMEOUT";
export const ERROR_INVALID_RESPONSE = "INVALID_RESPONSE";
export const ERROR_INTERNAL = "INTERNAL_ERROR";

// Compatibility alias for the pre-freeze helper name; it is never emitted.
export const ERROR_BAD_REQUEST = ERROR_INVALID_RESPONSE;

export const API_SERVER_ENDPOINT =
  "http://127.0.0.1:8642/v1/chat/completions";
// Session traffic uses a separate, server-owned profile. It never accepts
// model/provider/tool/session controls from Autumn or its model.
export const SESSION_API_SERVER_ENDPOINT =
  "http://127.0.0.1:8642/v1/session/chat/completions";
// Hermes' Official API may spend longer than ten seconds in its normal
// AIAgent/provider dispatch path. Keep a bounded adapter deadline, but do not
// abort a healthy local request before Hermes' normal response window.
export const API_SERVER_TIMEOUT_MS = 120_000;
const API_SERVER_MODEL = "hermes-agent";

export const SESSION_TOOL_NAME = "hermes_session";
export const SESSION_MAX_USER_TURNS = 8;
export const SESSION_IDLE_EXPIRY_MS = 30 * 60 * 1000;
export const SESSION_MESSAGE_MAX_CHARS = QUESTION_MAX_CHARS;
export const SESSION_ACTIONS = Object.freeze(["start", "message", "end", "status"]);
export const ERROR_SESSION_CONTEXT_UNAVAILABLE = "SESSION_CONTEXT_UNAVAILABLE";
export const ERROR_SESSION_INVALID = "SESSION_INVALID_REQUEST";
export const ERROR_SESSION_MAX_TURNS = "SESSION_MAX_TURNS";

const STABLE_ERROR_CODES = new Set([
  ERROR_UNAVAILABLE,
  ERROR_RATE_LIMITED,
  ERROR_REJECTED,
  ERROR_TIMEOUT,
  ERROR_INVALID_RESPONSE,
  ERROR_INTERNAL,
]);

const SAFE_FAILURE_ANSWERS = Object.freeze({
  [ERROR_UNAVAILABLE]: "Hermes consult is currently unavailable.",
  [ERROR_RATE_LIMITED]: "Hermes consult is temporarily rate limited.",
  [ERROR_REJECTED]: "Hermes consult could not accept this request.",
  [ERROR_TIMEOUT]: "Hermes consult timed out.",
  [ERROR_INVALID_RESPONSE]: "Hermes returned an invalid response.",
  [ERROR_INTERNAL]: "Hermes consult failed internally.",
});

function failureResult(errorCode) {
  const code = STABLE_ERROR_CODES.has(errorCode)
    ? errorCode
    : ERROR_INTERNAL;
  const status = {
    [ERROR_UNAVAILABLE]: STATUS_UNAVAILABLE,
    [ERROR_RATE_LIMITED]: STATUS_RATE_LIMITED,
    [ERROR_REJECTED]: STATUS_REJECTED,
    [ERROR_TIMEOUT]: STATUS_TIMEOUT,
    [ERROR_INVALID_RESPONSE]: STATUS_INVALID_RESPONSE,
    [ERROR_INTERNAL]: STATUS_UNAVAILABLE,
  }[code];
  return normalizedResult(
    status,
    SAFE_FAILURE_ANSWERS[code],
    code,
    null,
  );
}

// ---------------------------------------------------------------------------
// Strict Autumn input schema
// ---------------------------------------------------------------------------

export const ConsultParams = Type.Object(
  {
    question: Type.String({
      minLength: QUESTION_MIN_CHARS,
      maxLength: QUESTION_MAX_CHARS,
      description: "The question to consult Hermes with. Required.",
    }),
    context: Type.Optional(
      Type.String({
        minLength: 1,
        maxLength: CONTEXT_MAX_CHARS,
        description: "Optional short current-task context. Capped.",
      }),
    ),
  },
  { additionalProperties: false },
);

export { ConsultParams as ConsultParamsSchema };

export const SessionParams = Type.Object(
  {
    action: Type.Union(SESSION_ACTIONS.map((action) => Type.Literal(action))),
    message: Type.Optional(
      Type.String({
        minLength: 1,
        maxLength: SESSION_MESSAGE_MAX_CHARS,
        description: "The message for a session start or turn. Optional on start.",
      }),
    ),
  },
  { additionalProperties: false },
);

export { SessionParams as SessionParamsSchema };

function isConsultRequest(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const keys = Object.keys(value);
  if (keys.some((key) => key !== "question" && key !== "context")) {
    return false;
  }
  if (
    typeof value.question !== "string" ||
    value.question.trim().length === 0 ||
    value.question.length > QUESTION_MAX_CHARS
  ) {
    return false;
  }
  if (value.context !== undefined) {
    if (
      typeof value.context !== "string" ||
      value.context.trim().length === 0 ||
      value.context.length > CONTEXT_MAX_CHARS
    ) {
      return false;
    }
  }
  return true;
}

function isSessionRequest(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const keys = Object.keys(value);
  if (keys.some((key) => key !== "action" && key !== "message")) return false;
  if (!SESSION_ACTIONS.includes(value.action)) return false;
  if (value.message !== undefined) {
    if (
      (value.action !== "start" && value.action !== "message") ||
      typeof value.message !== "string" ||
      value.message.trim().length === 0 ||
      value.message.length > SESSION_MESSAGE_MAX_CHARS
    ) {
      return false;
    }
  }
  return value.action === "start" || value.action === "message" || value.message === undefined;
}

function isSessionMessages(messages) {
  return (
    Array.isArray(messages) &&
    messages.length <= SESSION_MAX_USER_TURNS * 2 &&
    messages.every(
      (message) =>
        message &&
        typeof message === "object" &&
        (message.role === "user" || message.role === "assistant") &&
        typeof message.content === "string" &&
        message.content.trim().length > 0,
    )
  );
}

// ---------------------------------------------------------------------------
// Normalized result helpers
// ---------------------------------------------------------------------------

export function normalizedResult(
  status,
  answer,
  errorCode,
  consultId = null,
) {
  return {
    status,
    answer,
    consult_id: consultId,
    error_code: errorCode,
  };
}

function okResult(payload) {
  return {
    content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
    details: payload,
  };
}

function safeToolResult(errorCode) {
  return okResult(failureResult(errorCode));
}

// ---------------------------------------------------------------------------
// Backend abstraction
// ---------------------------------------------------------------------------

export class HermesConsultBackend {
  constructor() {
    if (new.target === HermesConsultBackend) {
      throw new Error("HermesConsultBackend is abstract");
    }
  }

  async consult(_params) {
    throw new Error("consult() not implemented");
  }
}

// ---------------------------------------------------------------------------
// Offline test/fault-injection backend
// ---------------------------------------------------------------------------

export class MockHermesConsultBackend extends HermesConsultBackend {
  constructor(options = {}) {
    super();
    this.mode = options.mode || "ok";
    this.consultCount = 0;
  }

  async consult({ question, context } = {}) {
    this.consultCount += 1;
    switch (this.mode) {
      case "ok": {
        const consultId = randomUUID();
        const answer =
          (context && context.trim()
            ? "[mock] Consulted on: " + question + " (with context)."
            : "[mock] Consulted on: " + question + ".");
        return normalizedResult(STATUS_OK, answer, ERROR_NONE, consultId);
      }
      case "timeout":
        return failureResult(ERROR_TIMEOUT);
      case "rate_limited":
        return failureResult(ERROR_RATE_LIMITED);
      case "rejected":
        return failureResult(ERROR_REJECTED);
      case "unavailable":
        return failureResult(ERROR_UNAVAILABLE);
      case "raw_exception":
        throw new Error("RAW_UPSTREAM_SECRET: boom");
      case "unexpected_shape":
        return { anything: true, raw: "sensitive" };
      default:
        return failureResult(ERROR_UNAVAILABLE);
    }
  }
}

// ---------------------------------------------------------------------------
// Official Hermes API server adapter
// ---------------------------------------------------------------------------

function configuredApiServerKey(options) {
  if (Object.prototype.hasOwnProperty.call(options, "apiKey")) {
    return typeof options.apiKey === "string" ? options.apiKey : "";
  }
  // These are host-controlled API-server auth variables, not model inputs.
  // Their values are never included in a normalized result or error.
  return process.env.HERMES_API_SERVER_KEY || process.env.API_SERVER_KEY || "";
}

function isConnectionFailure(error) {
  return (
    error instanceof TypeError ||
    error?.code === "ECONNREFUSED" ||
    error?.code === "ECONNRESET" ||
    error?.code === "ENOTFOUND"
  );
}

/**
 * Adapter for the current Hermes Official API Server contract:
 *   POST http://127.0.0.1:8642/v1/chat/completions
 *   body: { model, stream: false, messages: [{ role: "user", content }] }
 *   response: { id, choices: [{ message: { content } }] }
 *
 * fetchImpl, apiKey, and timeoutMs are dependency-injection hooks for
 * the host/test harness. Production uses the fixed endpoint/model/timeout.
 */
export class ApiServerBackend extends HermesConsultBackend {
  constructor(options = {}) {
    super();
    this._fetchImpl = options.fetchImpl || globalThis.fetch;
    this._apiKey = configuredApiServerKey(options);
    this._timeoutMs =
      Number.isInteger(options.timeoutMs) && options.timeoutMs > 0
        ? options.timeoutMs
        : API_SERVER_TIMEOUT_MS;
  }

  async consult({ question, context } = {}) {
    const request = {
      question,
      ...(context === undefined ? {} : { context }),
    };
    if (!isConsultRequest(request)) {
      return failureResult(ERROR_INVALID_RESPONSE);
    }
    if (typeof this._fetchImpl !== "function") {
      return failureResult(ERROR_UNAVAILABLE);
    }

    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this._timeoutMs);

    try {
      const content = context === undefined
        ? question
        : "Context:\n" + context + "\n\nQuestion:\n" + question;
      const headers = {
        Accept: "application/json",
        "Content-Type": "application/json",
      };
      if (this._apiKey) {
        headers.Authorization = "Bearer " + this._apiKey;
      }

      const response = await this._fetchImpl(API_SERVER_ENDPOINT, {
        method: "POST",
        headers,
        body: JSON.stringify({
          model: API_SERVER_MODEL,
          stream: false,
          messages: [{ role: "user", content }],
        }),
        signal: controller.signal,
      });

      const status = Number(response?.status);
      if (status === 429) return failureResult(ERROR_RATE_LIMITED);
      if (status >= 400 && status < 500) return failureResult(ERROR_REJECTED);
      if (status >= 500) return failureResult(ERROR_UNAVAILABLE);
      if (!response || typeof response.json !== "function" || status < 200 || status >= 300) {
        return failureResult(ERROR_INVALID_RESPONSE);
      }

      let payload;
      try {
        payload = await response.json();
      } catch {
        return failureResult(ERROR_INVALID_RESPONSE);
      }

      const consultId = typeof payload?.id === "string" ? payload.id.trim() : "";
      const message = payload?.choices?.[0]?.message;
      const answer = message?.content;
      if (
        !consultId ||
        consultId.length > 256 ||
        message?.role !== "assistant" ||
        typeof answer !== "string" ||
        answer.trim().length === 0 ||
        answer.length > 8000
      ) {
        return failureResult(ERROR_INVALID_RESPONSE);
      }
      return normalizedResult(STATUS_OK, answer.trim(), ERROR_NONE, consultId);
    } catch (error) {
      if (timedOut || error?.name === "AbortError") {
        return failureResult(ERROR_TIMEOUT);
      }
      if (isConnectionFailure(error)) {
        return failureResult(ERROR_UNAVAILABLE);
      }
      return failureResult(ERROR_INTERNAL);
    } finally {
      clearTimeout(timer);
    }
  }
  async session(messages = []) {
    if (!isSessionMessages(messages)) {
      return failureResult(ERROR_INVALID_RESPONSE);
    }
    if (typeof this._fetchImpl !== "function") {
      return failureResult(ERROR_UNAVAILABLE);
    }

    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this._timeoutMs);

    try {
      const headers = {
        Accept: "application/json",
        "Content-Type": "application/json",
      };
      if (this._apiKey) {
        headers.Authorization = "Bearer " + this._apiKey;
      }
      const response = await this._fetchImpl(SESSION_API_SERVER_ENDPOINT, {
        method: "POST",
        headers,
        body: JSON.stringify({ stream: false, messages }),
        signal: controller.signal,
      });
      const status = Number(response?.status);
      if (status === 429) return failureResult(ERROR_RATE_LIMITED);
      if (status >= 400 && status < 500) return failureResult(ERROR_REJECTED);
      if (status >= 500) return failureResult(ERROR_UNAVAILABLE);
      if (!response || typeof response.json !== "function" || status < 200 || status >= 300) {
        return failureResult(ERROR_INVALID_RESPONSE);
      }

      let payload;
      try {
        payload = await response.json();
      } catch {
        return failureResult(ERROR_INVALID_RESPONSE);
      }
      const responseId = typeof payload?.id === "string" ? payload.id.trim() : "";
      const message = payload?.choices?.[0]?.message;
      const answer = message?.content;
      if (
        !responseId ||
        responseId.length > 256 ||
        message?.role !== "assistant" ||
        typeof answer !== "string" ||
        answer.trim().length === 0 ||
        answer.length > 8000
      ) {
        return failureResult(ERROR_INVALID_RESPONSE);
      }
      return normalizedResult(STATUS_OK, answer.trim(), ERROR_NONE, responseId);
    } catch (error) {
      if (timedOut || error?.name === "AbortError") {
        return failureResult(ERROR_TIMEOUT);
      }
      if (isConnectionFailure(error)) {
        return failureResult(ERROR_UNAVAILABLE);
      }
      return failureResult(ERROR_INTERNAL);
    } finally {
      clearTimeout(timer);
    }
  }

}
// ---------------------------------------------------------------------------
function sessionState(active, turnCount) {
  return { active: Boolean(active), turn_count: turnCount };
}

function sessionFailure(result, active, turnCount) {
  return {
    status: result.status,
    active: Boolean(active),
    turn_count: turnCount,
    answer: result.answer,
    error_code: result.error_code,
  };
}

export class EphemeralHermesSession {
  constructor({ backend, clock = () => Date.now() } = {}) {
    this._backend = backend;
    this._clock = clock;
    this.active = false;
    this.messages = [];
    this.createdAt = null;
    this.lastActivity = null;
    this.userTurns = 0;
    this.runtimeSessionId = null;
    this._queue = Promise.resolve();
  }

  _enqueue(work) {
    const next = this._queue.then(work, work);
    this._queue = next.catch(() => undefined);
    return next;
  }

  _clear() {
    this.active = false;
    this.messages = [];
    this.createdAt = null;
    this.lastActivity = null;
    this.userTurns = 0;
    this.runtimeSessionId = null;
  }

  _expire(now) {
    if (this.active && now - this.lastActivity >= SESSION_IDLE_EXPIRY_MS) {
      this._clear();
      return true;
    }
    return false;
  }

  status() {
    this._expire(this._clock());
    return sessionState(this.active, this.userTurns);
  }

  async execute(request) {
    return this._enqueue(() => this._execute(request));
  }

  async _execute({ action, message } = {}) {
    const now = this._clock();
    this._expire(now);

    if (action === "status") return sessionState(this.active, this.userTurns);
    if (action === "end") {
      this._clear();
      return { status: "ended", ...sessionState(false, 0) };
    }
    if (action === "start") {
      if (this.active) {
        return { status: "already_active", ...sessionState(true, this.userTurns) };
      }
      this.active = true;
      this.messages = [];
      this.createdAt = now;
      this.lastActivity = now;
      this.userTurns = 0;
      this.runtimeSessionId = randomUUID();
      if (message === undefined) {
        return { status: "started", ...sessionState(true, 0) };
      }
      return this._message(message);
    }
    if (action === "message") return this._message(message);
    return {
      status: "invalid",
      ...sessionState(this.active, this.userTurns),
      error_code: ERROR_SESSION_INVALID,
    };
  }

  async _message(message) {
    this._expire(this._clock());
    if (!this.active) {
      return { status: "inactive", ...sessionState(false, 0) };
    }
    if (this.userTurns >= SESSION_MAX_USER_TURNS) {
      return {
        status: "max_turns_reached",
        ...sessionState(true, this.userTurns),
        error_code: ERROR_SESSION_MAX_TURNS,
        answer: "Hermes session reached its 8-turn limit; end it or start a new session.",
      };
    }

    const candidate = [...this.messages, { role: "user", content: message }];
    this.lastActivity = this._clock();
    let result;
    try {
      result = this._backend && typeof this._backend.session === "function"
        ? await this._backend.session(candidate)
        : failureResult(ERROR_UNAVAILABLE);
    } catch {
      result = failureResult(ERROR_INTERNAL);
    }
    this.lastActivity = this._clock();
    const normalized = normalizeBackendResult(result);
    if (normalized.status !== STATUS_OK) {
      return sessionFailure(normalized, true, this.userTurns);
    }

    this.messages = [...candidate, { role: "assistant", content: normalized.answer }];
    this.userTurns += 1;
    return {
      status: STATUS_OK,
      active: true,
      turn_count: this.userTurns,
      answer: normalized.answer,
      error_code: ERROR_NONE,
    };
  }
}

export class EphemeralHermesSessionRegistry {
  constructor({ backend, clock = () => Date.now() } = {}) {
    this.backend = backend;
    this.clock = clock;
    this.sessions = new Map();
  }

  get(conversationKey) {
    if (!conversationKey) return null;
    let session = this.sessions.get(conversationKey);
    if (!session) {
      session = new EphemeralHermesSession({ backend: this.backend, clock: this.clock });
      this.sessions.set(conversationKey, session);
    }
    return session;
  }
}

function conversationKeyFromToolContext(toolContext) {
  const sessionId = typeof toolContext?.sessionId === "string" ? toolContext.sessionId.trim() : "";
  if (sessionId) return "session-id:" + sessionId;
  const sessionKey = typeof toolContext?.sessionKey === "string" ? toolContext.sessionKey.trim() : "";
  return sessionKey ? "session-key:" + sessionKey : null;
}

export async function execHermesSession(session, params) {
  if (!isSessionRequest(params)) {
    return okResult({ status: "invalid", active: false, turn_count: 0, error_code: ERROR_SESSION_INVALID });
  }
  if (!session) {
    return okResult({
      status: "unavailable",
      active: false,
      turn_count: 0,
      error_code: ERROR_SESSION_CONTEXT_UNAVAILABLE,
    });
  }
  try {
    return okResult(await session.execute(params));
  } catch {
    return okResult({ status: "unavailable", ...session.status(), error_code: ERROR_INTERNAL });
  }
}

export function createHermesSessionTool(session) {
  return {
    name: SESSION_TOOL_NAME,
    label: "Hermes session (internal)",
    description:
      "Internal Autumn temporary Hermes session. Only action and optional message are accepted; " +
      "the runtime owns conversation isolation, endpoint, model, tools, and session identity.",
    parameters: SessionParams,
    execute: async (_toolCallId, params) => execHermesSession(session, params),
  };
}

export function registerHermesSessionTool(api, backend, registry) {
  const selectedBackend = backend || createProductionBackend();
  const selectedRegistry = registry || new EphemeralHermesSessionRegistry({ backend: selectedBackend });
  api.registerTool((toolContext) => {
    const conversationKey = conversationKeyFromToolContext(toolContext);
    const session = conversationKey ? selectedRegistry.get(conversationKey) : null;
    return createHermesSessionTool(session);
  }, { name: SESSION_TOOL_NAME });
}
// Tool execution and backend wiring
// ---------------------------------------------------------------------------

function normalizeBackendResult(result) {
  if (
    result?.status === STATUS_OK &&
    result?.error_code === ERROR_NONE &&
    typeof result.answer === "string" &&
    result.answer.trim().length > 0 &&
    typeof result.consult_id === "string" &&
    result.consult_id.trim().length > 0
  ) {
    return normalizedResult(
      STATUS_OK,
      result.answer.trim(),
      ERROR_NONE,
      result.consult_id.trim(),
    );
  }
  if (STABLE_ERROR_CODES.has(result?.error_code)) {
    return failureResult(result.error_code);
  }
  return failureResult(ERROR_INVALID_RESPONSE);
}

export async function execHermesConsult(backend, params) {
  if (!backend || typeof backend.consult !== "function") {
    return safeToolResult(ERROR_UNAVAILABLE);
  }
  if (!isConsultRequest(params)) {
    return safeToolResult(ERROR_INVALID_RESPONSE);
  }

  let result;
  try {
    result = await backend.consult({
      question: params.question,
      ...(params.context === undefined ? {} : { context: params.context }),
    });
  } catch {
    return safeToolResult(ERROR_INTERNAL);
  }

  return okResult(normalizeBackendResult(result));
}

export function createProductionBackend() {
  return new ApiServerBackend();
}

// Explicit host/test-harness injection point. The model can only reach the
// two frozen tool fields; backend selection never comes from tool parameters.
export function registerHermesConsultTool(api, backend) {
  const selectedBackend = backend || createProductionBackend();
  api.registerTool({
    name: TOOL_NAME,
    label: "Hermes consult (internal)",
    description:
      "Internal Autumn consult capability. Accepts only question and optional " +
      "current-task context; returns a normalized Hermes opinion or safe error.",
    parameters: ConsultParams,
    execute: async (_toolCallId, params) =>
      execHermesConsult(selectedBackend, params),
  });
}

const PLUGIN_DESCRIPTION =
  "Internal Autumn capability: hermes_consult(question, context?) plus " +
  "bounded ephemeral hermes_session(action, message?). Production uses the " +
  "controlled Hermes Official API Server adapter; mock backends are available " +
  "only through explicit test injection. Session state is in-memory; its " +
  "Hermes-owned profile fixes private background and four approved tools.";

export default definePluginEntry({
  id: "hermes-consult-tool",
  name: "Hermes Consult Tool",
  description: PLUGIN_DESCRIPTION,
  register(api) {
    const productionBackend = createProductionBackend();
    registerHermesConsultTool(api, productionBackend);
    registerHermesSessionTool(api, productionBackend);
  },
});
