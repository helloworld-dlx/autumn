import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const html = await readFile(new URL("./index.html", import.meta.url), "utf8");
const bridge = await readFile(new URL("./voice_bridge.py", import.meta.url), "utf8");
const gateway = await readFile(new URL("./gateway_turn.mjs", import.meta.url), "utf8");
const worker = await readFile(new URL("./sw.js", import.meta.url), "utf8");

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
assert.match(worker, /autumn-companion-shell-v6/);

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
