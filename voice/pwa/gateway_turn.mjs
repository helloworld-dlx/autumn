#!/usr/bin/env node
import readline from "node:readline";
import { randomUUID } from "node:crypto";
import { n as GatewayClient } from "/home/xyzlh/openclaw_workspace/node_modules/openclaw/dist/client-BfgBP91A.js";

const pending = new Map();
const fastModeSessions = new Set();
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

function handleEvent(event, payload) {
  if (event !== "chat" || !payload || typeof payload !== "object") return;
  const runId = payload.runId;
  if (!pending.has(runId)) return;
  if (payload.state === "final") {
    const text = visibleText(payload.message);
    finish(runId, text ? { ok: true, text } : { ok: false, error: "AUTUMN_REPLY_INVALID" });
  } else if (payload.state === "error" || payload.state === "aborted") {
    finish(runId, { ok: false, error: "GATEWAY_TURN_FAILED" });
  }
}

async function sendAndWait(sessionKey, message) {
  const runId = randomUUID();
  return await new Promise((resolve) => {
    const timer = setTimeout(
      () => finish(runId, { ok: false, error: "GATEWAY_TURN_TIMEOUT" }),
      130_000,
    );
    pending.set(runId, { resolve, timer });
    client.request("chat.send", {
      sessionKey,
      agentId: "main",
      message,
      timeoutMs: 120_000,
      idempotencyKey: runId,
    }).catch(() => finish(runId, { ok: false, error: "GATEWAY_REQUEST_FAILED" }));
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
    if (typeof request.message !== "string" || typeof request.sessionKey !== "string") {
      throw new Error("INVALID_REQUEST");
    }
    const startedAt = Date.now();
    const canonicalSessionKey = `agent:main:${request.sessionKey}`;
    if (!fastModeSessions.has(canonicalSessionKey)) {
      const modeResult = await sendAndWait(canonicalSessionKey, "/fast on");
      if (!modeResult.ok) {
        process.stdout.write(`${JSON.stringify(modeResult)}\n`);
        continue;
      }
      fastModeSessions.add(canonicalSessionKey);
    }
    const result = await sendAndWait(canonicalSessionKey, request.message);
    process.stdout.write(`${JSON.stringify({ ...result, latencyMs: Date.now() - startedAt })}\n`);
  } catch (error) {
    process.stdout.write(`${JSON.stringify({
      ok: false,
      error: "GATEWAY_REQUEST_FAILED",
      code: typeof error?.gatewayCode === "string" ? error.gatewayCode : error?.name ?? "Error",
    })}\n`);
  }
}

client.stop();
