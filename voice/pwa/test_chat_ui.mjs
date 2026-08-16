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
assert.match(script, /if\(\(!message&&!sendingFiles\.length\)\|\|pending\)return/, "pending sends are not concurrent and file-only sends are allowed");
assert.match(script, /fetch\('\/api\/conversations\/'\+encodeURIComponent\(id\)\+'\/history'/, "active Conversation history loads on reload");
assert.match(script, /fetch\('\/api\/conversations'/, "Conversation list loads from the Bridge");
assert.match(script, /conversationId:sendingConversation/, "Chat sends to the active Conversation");
assert.match(script, /autumnActiveConversationId/, "active Conversation is shared with Talk");
assert.match(source, /ContinuousVoiceSession\(crypto\.randomUUID\(\),globalThis\.autumnActiveConversationId\|\|'main'/, "Talk uses the active Conversation");
assert.match(script, /const id='c_'\+crypto\.randomUUID\(\)/, "new Conversation gets one stable opaque id");
assert.doesNotMatch(source, /Project \/ Temporary 将在权限边界解除后接入/, "internal blocker copy is not shown in production UI");

assert.match(source, /@media\(max-width:900px\)\{\.chat-shell\{[^}]*overflow:visible;backdrop-filter:none/, "mobile Conversation rail is not clipped by the Chat shell stacking context");
assert.match(source, /if\(page==='chat'\)\{closeRail\(\);refreshConversations\(\)\.then\(\(\)=>loadHistory\(activeConversationId\)\)\}/, "entering Chat refreshes history so recent Talk turns become visible");
assert.match(source, /id="chat-file-input" type="file" multiple/, "Chat exposes a multi-file picker");
assert.match(script, /MAX_ATTACHMENTS=3,MAX_ATTACHMENT_BYTES=8\*1024\*1024,MAX_ATTACHMENT_TOTAL=12\*1024\*1024/, "client file caps mirror Bridge policy");
assert.match(script, /Promise\.all\(sendingFiles\.map\(encodeAttachment\)\)/, "selected files are encoded only for the submitted turn");
assert.match(script, /JSON\.stringify\(\{conversationId:sendingConversation,message,attachments,newConversation\}\)/, "Chat forwards attachments and explicit first-turn provenance with the active Conversation");
assert.match(source, /fetch\('\/api\/companion\/status',\{cache:'no-store'\}\)/, "live Companion status is fetched on demand");
assert.match(source, /\/api\/files\/returned\//, "returned files expose a download route in Activity");
assert.doesNotMatch(source, /setInterval\(/, "Companion status does not add background polling");

assert.match(script, /const pinned=conversations\.find\(item=>item\.id===activeConversationId\)/, "sessions.list lag cannot silently switch the active Conversation");
assert.match(script, /payload\.conversationKey!==expectedKey/, "Chat rejects any conversation routing mismatch");
assert.match(source, /data\.conversationKey!==expectedKey/, "Talk rejects any conversation routing mismatch");
assert.match(source, /newConversation/, "Chat and Talk mark only explicit newly-created Conversations for first-turn auto-title");
assert.match(source, /replyAttachments/, "assistant-returned files are surfaced in the current Chat turn");
assert.match(source, /attachment\.transferId\?' downloadable'/, "returned assistant attachments render as download cards");


assert.match(source, /body\.chat-page-open #page-chat \.chat-messages\{[^}]*overflow-y:auto;overscroll-behavior:contain/, "Chat uses an internal message scroller instead of growing the whole page");
assert.match(source, /document\.body\.classList\.toggle\('chat-page-open',page==='chat'\)/, "page navigation locks document scrolling only while Chat is active");
assert.match(source, /\.node-list \.status-badge\{width:64px;min-width:64px/, "Home node state badges share one aligned width");
assert.match(source, /function nextAutoBoundary\(now=new Date\(\)\)/, "Auto theme schedules the next 07:00/17:00/20:00 boundary without polling");
assert.match(source, /setTimeout\(\(\)=>applyTheme\('auto',\{persist:false\}\),delay\)/, "Auto theme re-resolves at the next boundary");
assert.match(source, /refreshDynamicTheme\(\);touchPresence\(\);probeAutumn\(\)/, "returning to the PWA refreshes the time-based theme");
assert.match(source, /'Auto · '\+actual/, "Auto exposes its resolved visual theme for debugging");
assert.match(source, /interactive-widget=resizes-content/, "mobile keyboard can resize the Chat viewport instead of covering the composer");

console.log("Chat composer and Main history regression: PASS");
