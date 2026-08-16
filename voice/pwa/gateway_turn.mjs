#!/usr/bin/env node
import readline from "node:readline";
import { randomUUID } from "node:crypto";
import { n as GatewayClient } from "/home/xyzlh/openclaw_workspace/node_modules/openclaw/dist/client-BfgBP91A.js";

const pending = new Map();
let readyResolve;
let readyReject;
const ready = new Promise((resolve, reject) => {
  readyResolve = resolve;
  readyReject = reject;
});
const client = new GatewayClient({
  url: "ws://127.0.0.1:18789",
  clientName: "gateway-client",
  clientDisplayName: "autumn-voice-bridge",
  mode: "backend",
  role: "operator",
  scopes: ["operator.write"],
  platform: process.platform,
  minProtocol: 4,
  maxProtocol: 4,
  requestTimeoutMs: 130_000,
  onHelloOk: () => readyResolve(),
  onConnectError: () => readyReject(new Error("GATEWAY_CONNECT_FAILED")),
  onEvent: ({ event, payload }) => handleEvent(event, payload),
  onClose: () => {
    for (const runId of pending.keys()) finish(runId, { ok: false, error: "GATEWAY_DISCONNECTED" });
  },
});

function visibleText(message) {
  if (!message || typeof message !== "object") return "";
  const content = message.content;
  if (typeof content === "string") {
    return content.split("\n").filter((line) => line.trim() !== "NO_REPLY").join("\n").trim();
  }
  if (!Array.isArray(content)) return "";
  const text = content
    .filter((part) => part && part.type === "text" && typeof part.text === "string")
    .map((part) => part.text.trim())
    .filter(Boolean)
    .join("\n");
  return text.split("\n").filter((line) => line.trim() !== "NO_REPLY").join("\n").trim();
}

function finish(runId, result) {
  const item = pending.get(runId);
  if (!item) return;
  pending.delete(runId);
  clearTimeout(item.timer);
  item.resolve(result);
}

function emitDelta(item, text) {
  if (!item?.onDelta || !text) return;
  let delta = "";
  if (!item.lastText) {
    delta = text;
    item.lastText = text;
  } else if (text.startsWith(item.lastText)) {
    delta = text.slice(item.lastText.length);
    item.lastText = text;
  } else if (item.lastText.endsWith(text) || item.lastText === text) {
    return;
  } else {
    // Some Gateway builds emit incremental chunks while others emit the
    // accumulated assistant text. Preserve both without changing session flow.
    delta = text;
    item.lastText += text;
  }
  if (delta) item.onDelta(delta, item.lastText);
}

function handleEvent(event, payload) {
  if (event !== "chat" || !payload || typeof payload !== "object") return;
  const runId = payload.runId;
  const item = pending.get(runId);
  if (!item) return;
  // OpenClaw chat events normally carry the canonical sessionKey. When present,
  // require it to match the exact Companion bucket requested by this turn.
  // Older Gateway builds that omit the field remain compatible.
  if (typeof payload.sessionKey === "string" && payload.sessionKey !== item.sessionKey) {
    finish(runId, { ok: false, error: "GATEWAY_SESSION_MISMATCH" });
    return;
  }
  if (payload.state === "delta") {
    emitDelta(item, visibleText(payload.message));
  } else if (payload.state === "final") {
    const text = visibleText(payload.message);
    finish(runId, text ? { ok: true, text } : { ok: false, error: "AUTUMN_REPLY_INVALID" });
  } else if (payload.state === "error" || payload.state === "aborted") {
    finish(runId, { ok: false, error: "GATEWAY_TURN_FAILED" });
  }
}

async function sendAndWait(sessionKey, message, fastMode, attachments = [], onDelta = null) {
  const runId = randomUUID();
  return await new Promise((resolve) => {
    const timer = setTimeout(
      () => finish(runId, { ok: false, error: "GATEWAY_TURN_TIMEOUT" }),
      130_000,
    );
    pending.set(runId, { resolve, timer, sessionKey, onDelta, lastText: "" });
    client.request("chat.send", {
      sessionKey,
      agentId: "main",
      message,
      attachments,
      fastMode,
      timeoutMs: 120_000,
      idempotencyKey: runId,
    }).catch(() => finish(runId, { ok: false, error: "GATEWAY_REQUEST_FAILED" }));
  });
}

function attachmentNameFromLocation(value) {
  const location = firstString(
    typeof value === "string" ? value : "",
    value?.url,
    value?.mediaUrl,
    value?.href,
    value?.path,
    value?.source?.url,
    value?.source?.path,
  );
  if (!location) return "";
  try {
    const pathname = /^https?:/i.test(location) ? new URL(location).pathname : location;
    const tail = pathname.replace(/\\/g, "/").split("/").filter(Boolean).at(-1) || "";
    return decodeURIComponent(tail).slice(0, 180);
  } catch {
    return location.replace(/\\/g, "/").split("/").filter(Boolean).at(-1)?.slice(0, 180) || "";
  }
}

function safeAttachmentMeta(value) {
  if (!value || (typeof value !== "object" && typeof value !== "string")) return null;
  const fileName = firstString(
    typeof value === "object" ? value.fileName : "",
    typeof value === "object" ? value.filename : "",
    typeof value === "object" ? value.name : "",
    attachmentNameFromLocation(value),
  ).slice(0, 180);
  const mimeType = firstString(
    typeof value === "object" ? value.mimeType : "",
    typeof value === "object" ? value.mime : "",
    typeof value === "object" ? value.contentType : "",
    typeof value === "object" ? value.type?.includes?.("/") ? value.type : "" : "",
  ).slice(0, 120);
  const sizeValue = typeof value === "object" ? (value.sizeBytes ?? value.size ?? value.bytes) : null;
  const sizeBytes = Number.isFinite(sizeValue) && sizeValue >= 0 ? Math.floor(sizeValue) : null;
  const declaredType = typeof value === "object" ? firstString(value.type, value.kind) : "";
  if (!fileName && !mimeType && !["file", "attachment", "image", "document", "media"].includes(declaredType)) return null;
  return { fileName: fileName || "附件", mimeType: mimeType || "application/octet-stream", sizeBytes };
}

function visibleAttachments(message) {
  if (!message || typeof message !== "object") return [];
  const candidates = [];
  for (const field of ["attachments", "files", "media", "mediaUrls"]) {
    if (Array.isArray(message[field])) candidates.push(...message[field]);
  }
  if (Array.isArray(message.content)) {
    for (const part of message.content) {
      if (!part || typeof part !== "object" || part.type === "text") continue;
      if (["file", "attachment", "image", "document", "media"].includes(part.type) || part.fileName || part.filename || part.mediaUrl || part.url || part.source) {
        candidates.push(part);
        if (part.source && typeof part.source === "object") candidates.push(part.source);
      }
    }
  }
  const seen = new Set();
  return candidates.map(safeAttachmentMeta).filter((item) => {
    if (!item) return false;
    const key = `${item.fileName}\u0000${item.mimeType}\u0000${item.sizeBytes ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 6);
}

function transcriptMessageId(message) {
  return firstString(message?.__openclaw?.id, message?.messageId, message?.id);
}

async function loadHistory(sessionKey) {
  const result = await client.request("chat.history", {
    sessionKey,
    agentId: "main",
    limit: 40,
    maxChars: 12_000,
  });
  const messages = Array.isArray(result?.messages) ? result.messages : [];
  const visible = [];
  for (const message of messages) {
    if (!message || !["user", "assistant"].includes(message.role)) continue;
    const text = visibleText(message);
    const attachments = visibleAttachments(message);
    const messageId = transcriptMessageId(message);
    if (!text && !attachments.length) continue;
    visible.push({
      role: message.role,
      text,
      attachments,
      ...(messageId ? { messageId } : {}),
    });
  }
  return visible;
}

function firstString(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

async function loadCompanionSessions() {
  const result = await client.request("sessions.list", { limit: 100 });
  const sessions = Array.isArray(result?.sessions) ? result.sessions : [];
  const prefix = "agent:main:companion:";
  return sessions.flatMap((session) => {
    if (!session || typeof session !== "object") return [];
    const key = typeof session.key === "string" ? session.key : "";
    if (!key.startsWith(prefix)) return [];
    const id = key.slice(prefix.length);
    if (!id) return [];
    // displayName identifies the Gateway client, not the conversation.
    const label = firstString(session.label, session.title, session.derivedTitle);
    const preview = firstString(session.preview).slice(0, 160);
    const updatedAt = firstString(session.updatedAt, session.lastActivityAt, session.createdAt);
    return [{ id, key, label, preview, updatedAt }];
  });
}

client.start();
await Promise.race([
  ready,
  new Promise((_, reject) => setTimeout(() => reject(new Error("GATEWAY_CONNECT_TIMEOUT")), 15_000)),
]);

const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of lines) {
  let request;
  try {
    request = JSON.parse(line);
    if (typeof request.sessionKey !== "string") {
      throw new Error("INVALID_REQUEST");
    }
    if (request.action === "history") {
      const messages = await loadHistory(`agent:main:${request.sessionKey}`);
      process.stdout.write(`${JSON.stringify({ ok: true, messages })}\n`);
      continue;
    }
    if (request.action === "sessions") {
      const sessions = await loadCompanionSessions();
      process.stdout.write(`${JSON.stringify({ ok: true, sessions })}\n`);
      continue;
    }
    if (typeof request.message !== "string" || !["chat", "voice"].includes(request.source)) throw new Error("INVALID_REQUEST");
    const attachments = request.source === "chat" && Array.isArray(request.attachments) ? request.attachments : [];
    const startedAt = Date.now();
    const canonicalSessionKey = `agent:main:${request.sessionKey}`;
    const stream = request.source === "voice" && request.stream === true;
    const requestId = typeof request.requestId === "string" && request.requestId ? request.requestId : randomUUID();
    const result = await sendAndWait(
      canonicalSessionKey,
      request.message,
      request.source === "voice",
      attachments,
      stream ? (delta, text) => {
        process.stdout.write(`${JSON.stringify({ type: "delta", requestId, delta, text })}\n`);
      } : null,
    );
    const payload = { ...result, latencyMs: Date.now() - startedAt };
    process.stdout.write(`${JSON.stringify(stream ? { type: "final", requestId, ...payload } : payload)}\n`);
  } catch (error) {
    process.stdout.write(`${JSON.stringify({
      ok: false,
      error: "GATEWAY_REQUEST_FAILED",
      code: typeof error?.gatewayCode === "string" ? error.gatewayCode : error?.name ?? "Error",
    })}\n`);
  }
}

client.stop();
