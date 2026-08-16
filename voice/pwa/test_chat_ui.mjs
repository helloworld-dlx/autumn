import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("./index.html", import.meta.url), "utf8");
const start = source.indexOf("const form=document.querySelector('#chat-form')");
const script = source.slice(start, source.indexOf("</script>", start));
const clearAt = script.indexOf("input.value='';");
const fetchAt = script.indexOf("fetch('/api/chat'");

assert.ok(start >= 0);
assert.ok(clearAt >= 0 && clearAt < fetchAt, "only the submitted draft is cleared before the request");
assert.doesNotMatch(script, /input\.disabled\s*=/, "composer remains editable while pending");
assert.doesNotMatch(script.slice(fetchAt), /input\.value\s*=/, "reply or failure cannot clear a waiting draft");
assert.match(script, /if\(!message\|\|pending\)return/, "pending sends are not concurrent");
assert.match(script, /fetch\('\/api\/conversations\/'\+encodeURIComponent\(id\)\+'\/history'/, "active Conversation history loads on reload");
assert.match(script, /fetch\('\/api\/conversations'/, "Conversation list loads from the Bridge");
assert.match(script, /conversationId:sendingConversation/, "Chat sends to the active Conversation");
assert.match(script, /autumnActiveConversationId/, "active Conversation is shared with Talk");
assert.match(source, /ContinuousVoiceSession\(crypto\.randomUUID\(\),globalThis\.autumnActiveConversationId\|\|'main'/, "Talk uses the active Conversation");
assert.match(script, /const id='c_'\+crypto\.randomUUID\(\)/, "new Conversation gets one stable opaque id");
assert.doesNotMatch(source, /Project \/ Temporary 将在权限边界解除后接入/, "internal blocker copy is not shown in production UI");

assert.match(source, /@media\(max-width:900px\)\{\.chat-shell\{[^}]*overflow:visible;backdrop-filter:none/, "mobile Conversation rail is not clipped by the Chat shell stacking context");
assert.match(source, /if\(page==='chat'\)\{closeRail\(\);refreshConversations\(\)\.then\(\(\)=>loadHistory\(activeConversationId\)\)\}/, "entering Chat refreshes history so recent Talk turns become visible");
assert.match(source, /form\.append\('conversationId',session\.conversationId\)/, "Talk uploads the active Conversation id");

console.log("Chat composer and Main history regression: PASS");
