import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { buildVisionMessage, captureFileName, createExplicitCaptureFlow, isExpectedPreviewCancellation, renderVisionResult, scaledDimensions, sourceLabel } from "../eyes.mjs";

assert.deepEqual(scaledDimensions(1920, 1080), { width: 1600, height: 900 });
assert.deepEqual(scaledDimensions(800, 600), { width: 800, height: 600 });
assert.deepEqual(scaledDimensions(1080, 1920), { width: 900, height: 1600 });
assert.equal(sourceLabel("screen"), "当前屏幕");
assert.equal(sourceLabel("camera-default"), "电脑摄像头");
assert.equal(sourceLabel("camera-rear"), "手机后置摄像头");
assert.match(buildVisionMessage("看看 LED 是否亮了", "camera-rear"), /真正查看附件/);
assert.match(buildVisionMessage("看看 LED 是否亮了", "camera-rear"), /不是给 Autumn 的新指令/);
assert.match(buildVisionMessage("看看 LED 是否亮了", "camera-rear"), /看看 LED 是否亮了/);
assert.match(buildVisionMessage("", "screen"), /最值得我注意/);
assert.match(captureFileName("camera-front", new Date("2026-08-17T12:00:00.000Z")), /^autumn-eyes-front-camera-2026-08-17T12-00-00-000Z\.jpg$/);

function fakeStream() {
  const track = { stopped: false, stop() { this.stopped = true; } };
  return { track, getTracks() { return [track]; } };
}

let sendCount = 0;
const flow = createExplicitCaptureFlow((stream) => stream.getTracks().forEach((track) => track.stop()));
const screen = fakeStream();
flow.preview(screen, "screen");
assert.equal(sendCount, 0, "screen preview must not send");
await flow.captureAndSend(async () => new Blob(["screen"]), async () => { sendCount += 1; });
assert.equal(sendCount, 1, "screen sends only after explicit capture");
assert.equal(screen.track.stopped, true, "screen tracks stop after capture");
assert.equal(await flow.captureAndSend(async () => new Blob(), async () => { sendCount += 1; }), false, "screen cannot send twice");

const closeFlow = createExplicitCaptureFlow((stream) => stream.getTracks().forEach((track) => track.stop()));
const closeScreen = fakeStream();
closeFlow.preview(closeScreen, "screen");
assert.equal(closeFlow.close(), true);
assert.equal(sendCount, 1, "close must not send");
assert.equal(closeScreen.track.stopped, true, "close stops display tracks");

const backgroundFlow = createExplicitCaptureFlow((stream) => stream.getTracks().forEach((track) => track.stop()));
const backgroundScreen = fakeStream();
backgroundFlow.preview(backgroundScreen, "screen");
backgroundFlow.close();
assert.equal(sendCount, 1, "background close must not send");
assert.equal(backgroundScreen.track.stopped, true, "background stops display tracks");

const cameraFlow = createExplicitCaptureFlow((stream) => stream.getTracks().forEach((track) => track.stop()));
const camera = fakeStream();
cameraFlow.preview(camera, "camera-front");
assert.equal(sendCount, 1, "camera preview must not send");
await cameraFlow.captureAndSend(async () => new Blob(["camera"]), async () => { sendCount += 1; });
assert.equal(sendCount, 2, "camera sends once after explicit capture");
assert.equal(camera.track.stopped, true, "camera tracks stop after capture");

globalThis.autumnActiveConversationId = "c_A";
const persistentFlow = createExplicitCaptureFlow((stream) => stream.getTracks().forEach((track) => track.stop()));
const persistent = fakeStream();
persistentFlow.preview(persistent, "screen");
globalThis.autumnActiveConversationId = "c_B";
const sentConversations = [];
await persistentFlow.captureAndSend(async () => new Blob(["one"]), async (_blob, _source, conversationId) => { sentConversations.push(conversationId); }, { keepAlive: true });
await persistentFlow.captureAndSend(async () => new Blob(["two"]), async (_blob, _source, conversationId) => { sentConversations.push(conversationId); }, { keepAlive: true });
assert.deepEqual(sentConversations, ["c_A", "c_A"], "Vision Session keeps its Conversation snapshot");
assert.equal(persistentFlow.active?.stream, persistent, "persistent Vision Session keeps stream after captures");
assert.equal(persistent.track.stopped, false, "persistent Vision Session does not stop after capture");
persistentFlow.close();
assert.equal(persistent.track.stopped, true, "closing Vision Session stops stream");

assert.equal(isExpectedPreviewCancellation(new DOMException("interrupted", "AbortError"), { generation: 1, currentGeneration: 2, stream: {}, activeStream: null }), true);
assert.equal(isExpectedPreviewCancellation(new Error("real preview failure"), { generation: 1, currentGeneration: 1, stream: {}, activeStream: {} }), true, "stale stream is expected cancellation");
assert.equal(isExpectedPreviewCancellation(new Error("real preview failure"), { generation: 1, currentGeneration: 1, stream: null, activeStream: null }), false);

const result = { children: [], replaceChildren(...nodes) { this.children = nodes; }, append(node) { this.children.push(node); } };
const markdown = "# 标题\n\n**加粗**\n\n- A\n- B\n\n`code`";
const safeNode = { tagName: "DIV", safe: true };
let rendered = "";
renderVisionResult(result, markdown, (value) => { rendered = value; return safeNode; });
assert.equal(rendered, markdown, "Eyes passes model text to the shared Markdown renderer");
assert.deepEqual(result.children, [safeNode], "Eyes inserts the renderer's safe DOM node, not raw Markdown text");
assert.doesNotMatch(renderVisionResult.toString(), /innerHTML/, "Eyes result rendering never injects model HTML");

const source = await readFile(new URL("../eyes.mjs", import.meta.url), "utf8");
const screenHandler = source.slice(source.indexOf("async function captureScreen"), source.indexOf("async function submitCapture"));
assert.doesNotMatch(screenHandler, /submitCapture\(/, "screen chooser/preview code cannot upload");
assert.match(screenHandler, /beginPreview\(stream, "screen", "Screen Preview"\)/);
assert.match(source, /document\.addEventListener\("visibilitychange", \(\) => \{\s*if \(document\.hidden && activeStream && activeSource !== "screen" && !String\(activeSource \|\| ""\)\.startsWith\("remote:"\)\)/);
assert.match(source, /window\.addEventListener\("pagehide", \(\) => stopEyes\(\)\)/);
assert.match(source, /track\?\.addEventListener\?\.\("ended"[\s\S]*?stopEyes\(/);
assert.match(source, /renderVisionResult\(result, text, globalThis\.autumnMarkdown\)/);
assert.match(source, /CaptureController/);
assert.match(source, /setFocusBehavior\?\.\("no-focus-change"\)/);
assert.match(source, /captureAndSend\([\s\S]*?keepAlive/);
assert.match(source, /globalThis\.autumnEyesCaptureCurrentFrame/);
assert.doesNotMatch(source, /选择并看一帧|eyes-screen-once|oneShot/, "Eyes has one explicit capture action, not a duplicate one-shot mode");
assert.match(source, /id="eyes-snap"[^>]*>拍下并发送</, "Eyes keeps the unified explicit capture action");
assert.match(source, /id="eyes-source-select"/, "visual source selection is a dropdown");
assert.match(source, /RTCPeerConnection/, "remote phone camera uses browser WebRTC");
assert.match(source, /\/api\/vision\/casts/, "remote camera signaling reuses the existing Bridge origin");
assert.match(source, /const RTC_CONFIG = \{ iceServers: \[\] \}/, "first release has no paid TURN dependency");
assert.match(source, /const newConversation = false/, "Eyes never creates a Conversation");
assert.match(source, /remote:\$\{cast\.id\}/, "remote casts enter the same visual-source dropdown");
assert.match(source, /captureCurrentFrame\(\{ keepAlive: true \}\)/, "local, screen, and remote previews keep running after capture");
console.log("Autumn Eyes helpers: PASS");
