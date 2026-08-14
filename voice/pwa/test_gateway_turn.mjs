import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("./gateway_turn.mjs", import.meta.url), "utf8");

assert.match(source, /\["chat", "voice"\]\.includes\(request\.source\)/);
assert.match(source, /const canonicalSessionKey = `agent:main:\$\{request\.sessionKey\}`;/);
assert.match(source, /request\.source === "voice"/);
assert.match(source, /fastMode,/);
assert.doesNotMatch(source, /\/fast (?:on|off)/);

console.log("Gateway turn profile regression: PASS");
