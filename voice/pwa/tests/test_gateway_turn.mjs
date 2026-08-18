import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../gateway_turn.mjs", import.meta.url), "utf8");

assert.match(source, /\["chat", "voice"\]\.includes\(request\.source\)/);
assert.match(source, /const canonicalSessionKey = `agent:main:\$\{request\.sessionKey\}`;/);
assert.match(source, /request\.source === "voice"/);

assert.match(source, /attachments,/);
assert.match(source, /request\.source === "chat" && Array\.isArray\(request\.attachments\)/);
assert.match(source, /visibleAttachments\(message\)/);
assert.match(source, /transcriptMessageId\(message\)/);
assert.match(source, /\.\.\.\(messageId \? \{ messageId \} : \{\}\)/);
assert.match(source, /fastMode,/);
assert.doesNotMatch(source, /\/fast (?:on|off)/);
assert.match(source, /client\.request\("chat\.history"/);
assert.match(source, /limit: 40/);
assert.match(source, /maxChars: 12_000/);
assert.match(source, /request\.action === "history"/);
assert.match(source, /client\.request\("sessions\.list"/);
assert.match(source, /agent:main:companion:/);
assert.match(source, /request\.action === "sessions"/);
assert.match(source, /const label = firstString\(session\.label, session\.title, session\.derivedTitle\)/);
assert.doesNotMatch(source, /firstString\(session\.label, session\.title, session\.displayName/);
assert.ok(source.includes('scopes: ["operator.write"]'));
assert.ok(!source.includes('operator.admin'));
assert.ok(source.includes('caps: ["tool-events"]'));

console.log("Gateway turn profile regression: PASS");

assert.match(source, /GATEWAY_SESSION_MISMATCH/, "Gateway event routing is guarded against cross-session drift");
assert.match(source, /pending\.set\(runId, \{ resolve, timer, sessionKey, onDelta, onTrace, lastText: "", trace:/, "pending turns retain the exact requested session key and streaming state");
assert.match(source, /data\.name !== "autumn_nodes"/, "tool diagnostics are limited to the approved presence tool");

assert.match(source, /payload\.state === "delta"/, "Gateway chat deltas are surfaced for streaming voice");
assert.match(source, /type: "delta"/, "streaming helper emits delta records");
assert.match(source, /type: "final"/, "streaming helper terminates with a final record");
