import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { nextObjectLayout, shouldShowIdle, transientLifecycle, smartObjectRects, rectsOverlap } from '../spatial_shell.mjs';


// ---- merged from test_chat_ui.mjs ----
{

const source = await readFile(new URL("../index.html", import.meta.url), "utf8");
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
assert.doesNotMatch(source, /id="themeToggle"|id="themePanel"|autumnTheme|resolveTheme|nextAutoBoundary/, "Phase 3E Companion is Afterglow-only with no hidden theme state");
assert.match(source, /Afterglow · local only/);
assert.match(source, /function isPortableCompanion\(\)\{return \/Android\|iPhone\|iPad\/i\.test\(navigator\.userAgent\|\|''\)\}/);
assert.match(source, /if\(!isPortableCompanion\(\)\)return;fetch\('\/api\/presence\/touch'/, "Xiaomi presence touch is mobile-gated");
assert.doesNotMatch(source, /留给 Phase 3D/);
assert.doesNotMatch(source, /感知入口|Xiaomi 15 Camera \/ Remote Eyes 已可用/);
assert.match(source, /id="home-devices"/);
assert.match(source, /home_devices\.mjs/);
assert.match(source, /interactive-widget=resizes-content/, "mobile keyboard can resize the Chat viewport instead of covering the composer");

console.log("Chat composer and Main history regression: PASS");
}

// ---- merged from test_companion_files.mjs ----
{

const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
const bridge = await readFile(new URL("../voice_bridge.py", import.meta.url), "utf8");
const gateway = await readFile(new URL("../gateway_turn.mjs", import.meta.url), "utf8");
const worker = await readFile(new URL("../sw.js", import.meta.url), "utf8");

assert.match(html, /id="activity-jobs"/);
assert.match(html, /id="activity-files"/);
assert.match(html, /id="activity-approvals"/);
assert.match(html, /id="devices-grid"/);
assert.match(html, /globalThis\.autumnRefreshCompanionStatus=refreshCompanionStatus/);
assert.match(bridge, /MAX_CHAT_ATTACHMENTS = 3/);
assert.match(bridge, /MAX_CHAT_ATTACHMENT_BYTES = 8 \* 1024 \* 1024/);
assert.match(bridge, /MAX_CHAT_ATTACHMENT_TOTAL_BYTES = 12 \* 1024 \* 1024/);
assert.match(bridge, /\/api\/companion\/status/);
assert.match(bridge, /\/api\/files\/returned/);
assert.match(gateway, /attachments,/);
assert.match(gateway, /client\.request\("chat\.send"/);
assert.match(worker, /autumn-companion-shell-v22/);
assert.match(worker, /\/barge_in\.mjs/);
assert.match(worker, /\/eyes\.mjs/);
assert.match(worker, /\/spatial_shell\.mjs/);
assert.match(html, /src="\/eyes\.mjs"/);
assert.match(html, /src="\/spatial_shell\.mjs"/);

assert.match(html, /device-state/);
assert.match(html, /device surface device-/);
assert.match(html, /files-open-all/);
assert.match(html, /includeHidden=1/);
assert.match(html, /\/visibility/);
assert.match(bridge, /autumn-companion-hidden-files-v1\.json/);
assert.match(bridge, /set_returned_file_hidden/);
assert.match(html, /replyAttachments/);
assert.match(html, /transferId/);
assert.match(bridge, /_new_returned_attachments/);
console.log("Companion files/activity/devices source regression: PASS");
}

// ---- merged from test_markdown.mjs ----
{

class Element {
  constructor(tagName) { this.tagName = tagName; this.children = []; this.className = ''; this._text = ''; }
  append(...nodes) { this.children.push(...nodes); }
  get firstChild() { return this.children[0]; }
  get textContent() { return this._text; }
  set textContent(value) { this._text = String(value); }
}

const source = await readFile(new URL('../index.html', import.meta.url), 'utf8');
const renderer = source.slice(source.indexOf('function appendInline'), source.indexOf('function show('));
const markdown = new Function('document', `${renderer}; return markdown;`)({
  createElement: (tagName) => new Element(tagName),
  createTextNode: (text) => ({ tagName: '#text', textContent: String(text) }),
});

function find(root, tagName) {
  if (root.tagName === tagName) return root;
  for (const child of root.children || []) { const found = find(child, tagName); if (found) return found; }
}

test('Markdown fenced code creates pre and code DOM', () => {
  const root = markdown('```\nconst answer = 42;\n```');
  const pre = find(root, 'pre');
  assert.equal(pre.firstChild.tagName, 'code');
  assert.equal(pre.firstChild.textContent, 'const answer = 42;');
});

test('Markdown tables create table DOM', () => {
  const root = markdown('| Name | Value |\n| --- | --- |\n| Autumn | Ready |');
  assert.equal(find(root, 'table').tagName, 'table');
});

test('Markdown keeps plain text and escapes HTML', () => {
  const root = markdown('普通文本\n<script>alert(1)</script>');
  assert.equal(root.children[0].tagName, 'p');
  assert.equal(root.children[0].children[0].textContent, '普通文本');
  assert.equal(find(root, 'script'), undefined);
  assert.equal(root.children[1].children[0].textContent, '<script>alert(1)</script>');
});
}

// ---- merged from test_reachability.mjs ----
{

const html = await readFile(new URL('../index.html', import.meta.url), 'utf8');
const worker = await readFile(new URL('../sw.js', import.meta.url), 'utf8');

test('service worker caches only the static Companion shell', () => {
  for (const asset of ['"/"', '"/index.html"', '"/continuous_voice.mjs"', '"/spatial_shell.mjs"', '"/home_devices.mjs"', '"/nodes_ui.mjs"', '"/mobile_shell.mjs"', '"/manifest.webmanifest"', '"/icons/autumn-192.png"', '"/icons/autumn-512.png"', '"/assets/afterglow-home.webp"']) assert.match(worker, new RegExp(asset.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  for (const privateRoute of ['/api/', '/health', '/audio/', 'IndexedDB', 'sync']) assert.doesNotMatch(worker, new RegExp(privateRoute.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
});

test('connectivity is determined by same-origin health, not browser network state', () => {
  assert.match(html, /fetch\('\/health',\{cache:'no-store',signal:controller\.signal\}\)/);
  assert.match(html, /CONNECTING/);
  assert.match(html, /CONNECTED/);
  assert.match(html, /DISCONNECTED/);
  assert.doesNotMatch(html, /navigator\.onLine/);
});

test('Companion shell keeps health probes on foreground events without a Tailscale handoff control', () => {
  assert.doesNotMatch(html, /id="connect"/);
  assert.doesNotMatch(html, /connectButton\.onclick/);
  assert.match(html, /visibilitychange/);
  assert.match(html, /pageshow/);
  assert.match(html, /window\.addEventListener\('focus'/);
});

test('Phase 3E repair keeps Nodes friendly and mobile navigation drawer-only', async () => {
  const nodes = await readFile(new URL('../nodes_ui.mjs', import.meta.url), 'utf8');
  const mobile = await readFile(new URL('../mobile_shell.mjs', import.meta.url), 'utf8');
  assert.match(nodes, /Pi 5 · Core/);
  assert.match(nodes, /Windows · Runner/);
  assert.match(nodes, /Xiaomi 15 · Phone/);
  assert.match(nodes, /autumnRenderNodes/);
  assert.doesNotMatch(nodes, /node_version|capabilities\.join|toISOString/);
  assert.match(mobile, /mobile-dock\{display:none!important\}/);
  assert.match(mobile, /autumn-mobile-nav-trigger/);
  assert.match(mobile, /data-page|nav-btn/);
  assert.match(html, /src="\/nodes_ui\.mjs"/);
  assert.match(html, /src="\/mobile_shell\.mjs"/);
  assert.doesNotMatch(html, /感知入口/);
});

test('mobile Spatial Shell exposes Talk and utility popover', async () => {
  const spatial = await readFile(new URL('../spatial_shell.mjs', import.meta.url), 'utf8');
  const sw = await readFile(new URL('../sw.js', import.meta.url), 'utf8');
  assert.match(spatial, /spatial-mobile-talk/);
  assert.match(spatial, /spatial-mobile-more/);
  assert.match(spatial, /RAIL_ICONS\.talk.*<span>Talk<\/span>/s);
  assert.match(spatial, /data-mobile-utility="activity"/);
  assert.match(spatial, /data-mobile-utility="devices"/);
  assert.match(spatial, /data-mobile-utility="eyes"/);
  assert.match(spatial, /data-mobile-utility="files"/);
  assert.match(spatial, /mobileTalk\.addEventListener\("click".*openTalk/s);
  assert.match(spatial, /action === "activity" \|\| action === "devices".*openUtility\(action\)/s);
  assert.match(spatial, /action === "eyes".*showEyes\(\)/s);
  assert.match(spatial, /action === "files".*showFiles\(\)/s);
  assert.match(spatial, /mobile-dock\{display:none!important\}/);
  assert.match(spatial, /safe-area-inset-top/);
  assert.match(spatial, /safe-area-inset-bottom/);
  assert.match(spatial, /\.spatial-brand\{min-width:0/);
  assert.match(spatial, /#autumn-spatial-root \.conn\{width:34px;height:34px;padding:0;font-size:0/);
  assert.match(spatial, /aria-controls="spatial-mobile-menu"/);
  assert.match(sw, /autumn-companion-shell-v22/);
});

test('Voice fails fast while Autumn is disconnected', () => {
  assert.match(html, /Autumn is disconnected\. Connect first\./);
  assert.match(html, /if\(connectivityState!==\'CONNECTED\'\)\{show\('连接'/);
  assert.match(html, /if\(connectivityState!==\'CONNECTED\'\)\{failForContext\(ctx,'Autumn is disconnected\. Connect first\.'/);
});
}

// ---- merged from test_spatial_shell.mjs ----
{

test("idle is empty-first", () => {
  assert.equal(shouldShowIdle([]), true);
  assert.equal(shouldShowIdle(["vision"]), false);
});

test("desktop object budget is hero plus two secondary", () => {
  const result = nextObjectLayout(["vision", "files", "task"], "devices");
  assert.equal(result.hero, "devices");
  assert.deepEqual(result.secondary, ["vision", "files"]);
  assert.deepEqual(result.stacked, ["task"]);
});

test("mobile object budget is hero plus one secondary", () => {
  const result = nextObjectLayout(["vision", "files"], "task", { mobile: true });
  assert.equal(result.hero, "task");
  assert.deepEqual(result.secondary, ["vision"]);
  assert.deepEqual(result.stacked, ["files"]);
});

test("transient objects retire through stack", () => {
  assert.deepEqual(
    transientLifecycle("status"),
    { name: "status", enter: "visible", retire: "stack", final: "hidden" },
  );
});

test("source reuses real Companion DOM instead of duplicating Chat Talk Eyes", async () => {
  const source = await readFile(new URL("../spatial_shell.mjs", import.meta.url), "utf8");
  assert.match(source, /#page-chat \.chat-shell/);
  assert.match(source, /#page-talk \.talk-wrap/);
  assert.match(source, /#page-eyes \.eyes-shell/);
  assert.match(source, /chatHost\.append\(chatShell\)/);
  assert.match(source, /talkBody\.append\(talkWrap\)/);
  assert.match(source, /spatial-vision-body/);
  assert.match(source, /autumnEyesClose/);
  assert.match(source, /autumnRefreshCompanionStatus/);
  assert.match(source, /filesOpenAll\?\.click/);
  assert.match(source, /data-page = extra\.page|button\.dataset\.page = extra\.page/);
});

test("source keeps glass restrained and uses real generated background", async () => {
  const source = await readFile(new URL("../spatial_shell.mjs", import.meta.url), "utf8");
  assert.match(source, /url\('\/assets\/afterglow-home\.webp'\)/);
  assert.match(source, /backdrop-filter:blur\(18px\)/);
  assert.match(source, /spatial-ambient-plane/);
  assert.doesNotMatch(source, /three|react|pixi/i);
});

test("second UX pass keeps Talk non-modal and objects manipulable", async () => {
  const source = await readFile(new URL("../spatial_shell.mjs", import.meta.url), "utf8");
  assert.match(source, /spatial-talk-overlay/);
  assert.match(source, /spatial-talk-eyes/);
  assert.match(source, /data-focus|toggleFocus/);
  assert.match(source, /object-focus-mode/);
  assert.match(source, /resize:both/);
  assert.match(source, /spatial-stack-pill/);
  assert.match(source, /spatial-action-label/);
  assert.match(source, /\.spatial-talk-overlay\{[\s\S]*position:absolute;left:50%;bottom:18px/);
});

console.log("Spatial shell source regression: PASS");
}

test("smart layout keeps one object as a large hero", () => {
  const rects = smartObjectRects(["vision"]);
  assert.deepEqual(rects.vision, { left: 3, top: 3, width: 94, height: 88 });
});

test("smart layout makes two desktop objects non-overlapping 63/31 split", () => {
  const rects = smartObjectRects(["vision", "files"]);
  const toPx = (r) => ({ left:r.left, top:r.top, right:r.left+r.width, bottom:r.top+r.height });
  assert.equal(rectsOverlap(toPx(rects.vision), toPx(rects.files), 0), false);
  assert.ok(rects.vision.width > rects.files.width);
});

test("spatial source exposes manual drag and one-click reflow", async () => {
  const source = await readFile(new URL("../spatial_shell.mjs", import.meta.url), "utf8");
  assert.match(source, /enableDragging/);
  assert.match(source, /reflowObjects/);
  assert.match(source, /检测到窗口重叠，已自动重排/);
  assert.match(source, /makeButton\("重排"/);
});

test("collapsed Chat uses a compact icon instead of rotated conversation text", async () => {
  const source = await readFile(new URL("../spatial_shell.mjs", import.meta.url), "utf8");
  assert.match(source, /collapsed-glyph/);
  assert.match(source, /collapsed-label">CHAT/);
  assert.doesNotMatch(source, /writing-mode:vertical-rl;transform:rotate\(180deg\);margin-top:8px/);
});

test("conversation manager lives in the main Context Field, not Chat", async () => {
  const source = await readFile(new URL("../spatial_shell.mjs", import.meta.url), "utf8");
  assert.match(source, /id="spatial-context-open"/);
  assert.match(source, /id="spatial-context-pop"/);
  assert.match(source, /contextPop\?\.append\(conversationRail\)/);
  assert.match(source, /\.spatial-chat-host \.conversation-toggle\{display:none!important\}/);
  assert.doesNotMatch(source, /spatial-chat-context-pop/);
});

test("installed PWA uses a first-paint spatial boot gate", async () => {
  const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
  const source = await readFile(new URL("../spatial_shell.mjs", import.meta.url), "utf8");
  assert.match(html, /<html lang="zh-CN" class="spatial-boot">/);
  assert.match(html, /html\.spatial-boot \.app>\.layout\{visibility:hidden\}/);
  assert.match(source, /classList\.remove\("spatial-boot"\)/);
  assert.match(source, /classList\.add\("spatial-ready"\)/);
});

test("conversation soft archive is explicit, conservative, and Main is protected", async () => {
  const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
  assert.match(html, /id="conversation-cleanup"/);
  assert.match(html, /id="conversation-archived"/);
  assert.match(html, /conversationListTitle\.textContent=showArchived\?'已归档':'Conversation'/, "conversation list script remains valid after archive wiring");
  assert.match(html, /async function cleanupTestConversations/);
  assert.match(html, /\/api\/conversations\/.*\/archive/);
  assert.doesNotMatch(html, /method:'DELETE'/, "archive never calls session deletion");
  assert.match(html, /if\(id==='main'\)return/);
  assert.match(html, /globalThis\.autumnConversationController=/);
  assert.match(html, /只有这里的“＋”可以创建新 Conversation/);
  assert.match(html, /async function archiveConversation\(id,title/);
  assert.match(html, /if\(!confirmed&&!confirm\(/, "individual archive requires confirmation");
  assert.match(html, /activeConversationId='main'/, "archiving active Conversation returns to Main");
  assert.match(html, /归档 Conversation 失败/);
  assert.match(html, /当前回复还在进行中，请稍后再归档对话/);
  assert.match(html, /globalThis\.autumnPresentUiHints\?\.\(payload\.uiHints\)/, "Chat presents spatial objects from structured uiHints");
  assert.match(html, /event\.type==='ui'/, "streaming Talk presents tool-driven spatial hints");
  assert.match(html, /fetch\(\'\/api\/barge-intent\'/, "Barge-in uses an STT intent gate before aborting playback");
});

test("Home module is compact, room-aware, and Companion-only managed", async () => {
  const home = await readFile(new URL("../home_devices.mjs", import.meta.url), "utf8");
  assert.match(home, /发现新设备/);
  assert.match(home, /加入 Autumn/);
  assert.match(home, /可控制/);
  assert.match(home, /只读/);
  assert.match(home, /room/);
  assert.doesNotMatch(home, /set_percentage|volume_set/);
});
