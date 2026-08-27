import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

import {
  NOTIFICATION_TOOLS,
  OPENCLAW_GATEWAY_RUNTIME,
  OPENCLAW_MODEL,
  buildCronCreateParams,
  finalizeCronCompletion,
  openClawCronRef,
  renderCronPrompt,
  resolveTrustedFeishuTarget,
  scheduleTimeCommitment
} from "./proactive_completion.mjs";

const future = "2030-08-10T12:00:00.000Z";
const now = new Date("2030-08-10T11:00:00.000Z");
const trustedTarget = "user:ou_fixtureowner";
const fixture = (overrides = {}) => ({
  id: "CMT-20300810-001",
  status: "active",
  created_at: "2030-08-10T10:00:00.000Z",
  summary: "提醒用户提交阶段验收结果",
  trigger_type: "time",
  trigger: "到达约定时间",
  next_action: "请查看阶段验收结果。",
  due_at: future,
  external_ref: "",
  ...overrides
});

function memoryStore(initial) {
  const record = { ...initial };
  return {
    record,
    completeCalls: 0,
    async get(id) { return id === record.id ? { ...record } : null; },
    async findByExternalRef(ref) { return record.external_ref === ref ? { ...record } : null; },
    async setExternalRef(id, ref) {
      if (id !== record.id) throw new Error("not found");
      if (record.status !== "active") throw new Error("not active");
      record.external_ref = ref;
      return { ...record };
    },
    async complete(id) {
      if (id !== record.id || record.status !== "active") throw new Error("not active");
      record.status = "completed";
      this.completeCalls += 1;
      return { ...record };
    }
  };
}

test("Cron payload is one-shot, isolated, light-context, minimal-tool and targeted Feishu announce", () => {
  const params = buildCronCreateParams(fixture(), trustedTarget, now);
  assert.equal(params.schedule.kind, "at");
  assert.equal(params.deleteAfterRun, true);
  assert.equal(params.sessionTarget, "isolated");
  assert.equal(params.payload.lightContext, true);
  assert.deepEqual(params.payload.toolsAllow, ["jarvis_system_status"]);
  assert.deepEqual(NOTIFICATION_TOOLS, ["jarvis_system_status"]);
  assert.equal(params.payload.model, OPENCLAW_MODEL);
  assert.equal(params.delivery.mode, "announce");
  assert.equal(params.delivery.channel, "feishu");
  assert.equal(params.delivery.to, trustedTarget);
  assert.equal(params.delivery.bestEffort, false);
  assert.ok(params.payload.message.length < 1200);
  assert.doesNotMatch(params.payload.message, /COMMITMENTS\.md|ACTIVE_CONTEXT|Hermes|subagent|memory_search|memory_get/i);
});

test("notification policy exposes only registered read-only jarvis_system_status", async () => {
  const source = await fs.readFile(new URL("../plugins/jarvis-bridge-tool/dist/index.js", import.meta.url), "utf8");
  assert.match(source, /name:\s*["']jarvis_system_status["']/);
  assert.deepEqual(NOTIFICATION_TOOLS, ["jarvis_system_status"]);
  assert.doesNotMatch(NOTIFICATION_TOOLS.join(" "), /hermes|memory|web|browser|file|program|exec|delegate|session/i);
});

test("prompt contains only the exact short notification contract", () => {
  const prompt = renderCronPrompt(fixture());
  assert.match(prompt, /^只向用户发送下面这句话，不解释，不调用任何工具：/);
  assert.match(prompt, /commitment_id = CMT-20300810-001$/);
  assert.ok(Buffer.byteLength(prompt, "utf8") < 2000);
});

test("relative reminder intent is routed through the canonical schedule-time producer", async () => {
  const agents = await fs.readFile(new URL("../../../docs/current/AGENTS.md", import.meta.url), "utf8");
  assert.match(agents, /ACKNOWLEDGEMENT != SCHEDULING/);
  assert.match(agents, /两分钟后提醒我/);
  assert.match(agents, /agent:main:companion:\*/);
  assert.match(agents, /tools\/commitments\.mjs add/);
  assert.match(agents, /tools\/proactive_completion\.mjs schedule-time <commitment_id>/);
  assert.match(agents, /禁止为了用户提醒直接调用 native `cron` tool/);
  assert.match(agents, /`schedule-time` 失败后禁止改用 `schedule-systemd`/);
  assert.match(agents, /只有返回 canonical `openclaw-cron:` binding 后才确认提醒/);
  assert.match(agents, /`operator\.admin` 只是一项 scheduler transport 权限/);
  assert.match(agents, /`deadline_doc_sync` 与其他既有 job 必须保持不变/);
});

test("canonical scheduler requests operator.admin only as its Gateway transport scope", async () => {
  const source = await fs.readFile(new URL("./proactive_completion.mjs", import.meta.url), "utf8");
  assert.equal(OPENCLAW_GATEWAY_RUNTIME, "/home/xyzlh/openclaw_workspace/node_modules/openclaw/dist/plugin-sdk/gateway-runtime.js");
  assert.match(source, /import \{ fileURLToPath, pathToFileURL \} from "node:url"/);
  assert.match(source, /scopes: \["operator\.admin"\]/);
  assert.doesNotMatch(source, /gateway", "call"/);
  assert.equal(source.match(/operator\.admin/g)?.length, 1);
});

test("successful schedule binds the returned Cron id", async () => {
  const store = memoryStore(fixture());
  let captured;
  const scheduler = { async create(params) { captured = params; return { id: "cron-fixture-001" }; }, async remove() { throw new Error("unexpected remove"); } };
  const result = await scheduleTimeCommitment({ commitmentId: store.record.id, store, scheduler, resolveTarget: async () => trustedTarget, now });
  assert.equal(store.record.external_ref, "openclaw-cron:cron-fixture-001");
  assert.equal(result.cron.externalRef, store.record.external_ref);
  assert.equal(captured.deleteAfterRun, true);
  assert.equal(captured.delivery.to, trustedTarget);
});

test("Cron producer and completion consumer share the canonical external_ref contract", async () => {
  const store = memoryStore(fixture());
  const scheduler = {
    async create() { return { id: "abc123" }; },
    async remove() { throw new Error("unexpected remove"); }
  };
  const scheduled = await scheduleTimeCommitment({
    commitmentId: store.record.id,
    store,
    scheduler,
    resolveTarget: async () => trustedTarget,
    now
  });
  assert.equal(openClawCronRef("abc123"), "openclaw-cron:abc123");
  assert.equal(scheduled.cron.externalRef, "openclaw-cron:abc123");
  assert.equal(store.record.external_ref, "openclaw-cron:abc123");
  const finalized = await finalizeCronCompletion({ cronId: "abc123", runStatus: "ok", deliveryStatus: "delivered", delivered: true, store });
  assert.equal(finalized.completed, true);
  assert.equal(store.record.status, "completed");
});

test("scheduler failure leaves commitment active and unbound", async () => {
  const store = memoryStore(fixture());
  const scheduler = { async create() { throw new Error("fixture create failure"); }, async remove() {} };
  await assert.rejects(scheduleTimeCommitment({ commitmentId: store.record.id, store, scheduler, resolveTarget: async () => trustedTarget, now }), /fixture create failure/);
  assert.equal(store.record.status, "active");
  assert.equal(store.record.external_ref, "");
});

test("binding failure removes created Cron and does not invent external_ref", async () => {
  const store = memoryStore(fixture());
  store.setExternalRef = async () => { throw new Error("fixture bind failure"); };
  let removed = "";
  const scheduler = { async create() { return { id: "cron-fixture-002" }; }, async remove(id) { removed = id; } };
  await assert.rejects(scheduleTimeCommitment({ commitmentId: store.record.id, store, scheduler, resolveTarget: async () => trustedTarget, now }), /fixture bind failure/);
  assert.equal(removed, "cron-fixture-002");
  assert.equal(store.record.external_ref, "");
});

for (const [name, overrides, pattern] of [
  ["completed cannot schedule", { status: "completed" }, /not active/],
  ["cancelled cannot schedule", { status: "cancelled" }, /not active/],
  ["duplicate binding is rejected", { external_ref: "openclaw-cron:existing" }, /already has/],
  ["malformed due_at is rejected", { due_at: "not-a-date" }, /due_at is invalid/]
]) {
  test(name, async () => {
    const store = memoryStore(fixture(overrides));
    const scheduler = { async create() { throw new Error("must not create"); }, async remove() {} };
    await assert.rejects(scheduleTimeCommitment({ commitmentId: store.record.id, store, scheduler, resolveTarget: async () => trustedTarget, now }), pattern);
  });
}

test("trusted Feishu target resolves from allowlisted main direct-session intersection", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "autumn-feishu-target-"));
  t.after(async () => await fs.rm(root, { recursive: true, force: true }));
  const configPath = path.join(root, "openclaw.json");
  const sessionsPath = path.join(root, "sessions.json");
  await fs.writeFile(configPath, JSON.stringify({ channels: { feishu: { enabled: true, dmPolicy: "allowlist", allowFrom: ["ou_fixtureowner", "ou_other"] } } }));
  await fs.writeFile(sessionsPath, JSON.stringify({ "agent:main:feishu:direct:ou_fixtureowner": { updatedAt: 1 }, "agent:main:main": {} }));
  assert.equal(await resolveTrustedFeishuTarget({ configPath, sessionsPath }), trustedTarget);
});

test("missing or ambiguous trusted target rejects scheduling without binding", async () => {
  for (const resolveTarget of [async () => "", async () => "chat:oc_untrusted", async () => { throw new Error("trusted target unavailable"); }]) {
    const store = memoryStore(fixture());
    let created = false;
    const scheduler = { async create() { created = true; return { id: "must-not-exist" }; }, async remove() {} };
    await assert.rejects(scheduleTimeCommitment({ commitmentId: store.record.id, store, scheduler, resolveTarget, now }));
    assert.equal(created, false);
    assert.equal(store.record.status, "active");
    assert.equal(store.record.external_ref, "");
  }
});

test("caller cannot override adapter-resolved delivery target", async () => {
  const store = memoryStore(fixture());
  let captured;
  const scheduler = { async create(params) { captured = params; return { id: "cron-fixture-target" }; }, async remove() {} };
  await scheduleTimeCommitment({ commitmentId: store.record.id, store, scheduler, resolveTarget: async () => trustedTarget, target: "user:ou_modelsupplied", now });
  assert.equal(captured.delivery.to, trustedTarget);
});

test("confirmed run and delivery complete exactly once", async () => {
  const store = memoryStore(fixture({ external_ref: "openclaw-cron:cron-fixture-003" }));
  const first = await finalizeCronCompletion({ cronId: "cron-fixture-003", runStatus: "ok", deliveryStatus: "delivered", delivered: true, store });
  const second = await finalizeCronCompletion({ cronId: "cron-fixture-003", runStatus: "ok", deliveryStatus: "delivered", delivered: true, store });
  assert.equal(first.completed, true);
  assert.equal(second.completed, false);
  assert.equal(second.reason, "not-active");
  assert.equal(store.completeCalls, 1);
});

for (const [name, values] of [
  ["run failure", { runStatus: "error", deliveryStatus: "delivered", delivered: true }],
  ["delivery status failure", { runStatus: "ok", deliveryStatus: "not-delivered", delivered: true }],
  ["delivered false", { runStatus: "ok", deliveryStatus: "delivered", delivered: false }],
  ["unknown delivery", { runStatus: "ok", deliveryStatus: "unknown", delivered: undefined }]
]) {
  test(`${name} keeps commitment active`, async () => {
    const store = memoryStore(fixture({ external_ref: "openclaw-cron:cron-fixture-004" }));
    const result = await finalizeCronCompletion({ cronId: "cron-fixture-004", ...values, store });
    assert.equal(result.completed, false);
    assert.equal(store.record.status, "active");
    assert.equal(store.completeCalls, 0);
  });
}

test("unknown Cron id is ignored", async () => {
  const store = memoryStore(fixture({ external_ref: "openclaw-cron:cron-fixture-005" }));
  const result = await finalizeCronCompletion({ cronId: "cron-unknown", runStatus: "ok", deliveryStatus: "delivered", delivered: true, store });
  assert.equal(result.matched, false);
  assert.equal(store.record.status, "active");
});

test("cron_changed hook forwards only finished delivery metadata", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "autumn-proactive-plugin-"));
  t.after(async () => await fs.rm(root, { recursive: true, force: true }));
  const pluginDir = path.join(root, "plugins", "proactive-cron-completion", "dist");
  const toolsDir = path.join(root, "tools");
  await fs.mkdir(pluginDir, { recursive: true });
  await fs.mkdir(toolsDir, { recursive: true });
  await fs.copyFile(new URL("../plugins/proactive-cron-completion/dist/index.js", import.meta.url), path.join(pluginDir, "index.js"));
  await fs.copyFile(new URL("./proactive_completion.mjs", import.meta.url), path.join(toolsDir, "proactive_completion.mjs"));
  await fs.copyFile(new URL("./commitments.mjs", import.meta.url), path.join(toolsDir, "commitments.mjs"));
  const pluginModule = await import(`${pathToFileURL(path.join(pluginDir, "index.js")).href}?fixture=${Date.now()}`);
  const { handleCronChanged } = pluginModule;
  let registeredName;
  let registeredHandler;
  pluginModule.default.register({ on(name, handler) { registeredName = name; registeredHandler = handler; } });
  assert.equal(registeredName, "cron_changed");
  assert.equal(typeof registeredHandler, "function");
  let received;
  const finalize = async (value) => { received = value; return { matched: true, completed: true }; };
  const skipped = await handleCronChanged({ action: "started", jobId: "cron-fixture-006" }, finalize);
  assert.equal(skipped.handled, false);
  const handled = await handleCronChanged({ action: "finished", jobId: "cron-fixture-006", status: "ok", deliveryStatus: "delivered", delivered: true }, finalize);
  assert.equal(handled.completed, true);
  assert.deepEqual(received, { cronId: "cron-fixture-006", runStatus: "ok", deliveryStatus: "delivered", delivered: true });
});

test("Commitment helper regression uses an isolated temporary canonical store", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "autumn-commitments-"));
  t.after(async () => await fs.rm(root, { recursive: true, force: true }));
  await fs.mkdir(path.join(root, "tools"), { recursive: true });
  await fs.mkdir(path.join(root, "memory"), { recursive: true });
  const source = new URL("./commitments.mjs", import.meta.url);
  const target = path.join(root, "tools", "commitments.mjs");
  await fs.copyFile(source, target);
  const helper = await import(`${pathToFileURL(target).href}?fixture=${Date.now()}`);
  const one = await helper.addCommitment({ summary: "fixture one", trigger_type: "time", trigger: "fixture", next_action: "notify", due_at: future, now });
  assert.equal((await helper.listActiveCommitments()).length, 1);
  assert.equal((await helper.getCommitment(one.commitment.id)).id, one.commitment.id);
  await helper.setCommitmentExternalRef(one.commitment.id, "openclaw-cron:fixture-job");
  assert.equal((await helper.findCommitmentByExternalRef("openclaw-cron:fixture-job")).id, one.commitment.id);
  await helper.completeCommitment(one.commitment.id);
  const two = await helper.addCommitment({ summary: "fixture two", trigger_type: "manual", trigger: "fixture", next_action: "follow up", now: new Date(now.getTime() + 1000) });
  await helper.cancelCommitment(two.commitment.id);
  assert.equal((await helper.getCommitment(one.commitment.id)).status, "completed");
  assert.equal((await helper.getCommitment(two.commitment.id)).status, "cancelled");
  await assert.rejects(helper.setCommitmentExternalRef(two.commitment.id, "/tmp/not-allowed"));
});
