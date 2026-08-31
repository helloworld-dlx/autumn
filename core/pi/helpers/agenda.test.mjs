import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const future = new Date("2030-08-10T10:00:00.000Z");

async function fixture(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "autumn-agenda-"));
  t.after(async () => await fs.rm(root, { recursive: true, force: true }));
  const tools = path.join(root, "tools");
  await fs.mkdir(tools, { recursive: true });
  for (const name of ["agenda.mjs", "commitments.mjs", "proactive_completion.mjs"]) {
    await fs.copyFile(new URL(`./${name}`, import.meta.url), path.join(tools, name));
  }
  return await import(`${pathToFileURL(path.join(tools, "agenda.mjs")).href}?fixture=${Date.now()}-${Math.random()}`);
}
function dependencies({ scheduleFailure = false, cancelFailure = false } = {}) {
  const records = new Map();
  const scheduled = [];
  const cancelled = [];
  let serial = 0;
  return {
    records, scheduled, cancelled,
    commitments: {
      async add(input) {
        const id = `CMT-20300810-${String(++serial).padStart(3, "0")}`;
        const commitment = { id, status: "active", external_ref: "", ...input };
        records.set(id, commitment);
        return { commitment, duplicate: false };
      },
      async get(id) { return records.get(id) ?? null; }
    },
    scheduler: {
      async schedule({ commitmentId }) {
        if (scheduleFailure) throw new Error("fixture schedule failure");
        const record = records.get(commitmentId);
        record.external_ref = `openclaw-cron:fixture-${commitmentId}`;
        scheduled.push(commitmentId);
        return { commitment: record, cron: { id: `fixture-${commitmentId}`, externalRef: record.external_ref } };
      },
      async cancel({ commitmentId }) {
        if (cancelFailure) throw new Error("fixture cancel failure");
        const record = records.get(commitmentId);
        record.status = "cancelled";
        cancelled.push(commitmentId);
        return { commitment: record };
      }
    }
  };
}
const deadline = (date = "2030-08-20", time = null) => ({ date, time, timezone: "Asia/Shanghai" });

test("create todo, deadline, stable IDs, and query by kind", async (t) => {
  const agenda = await fixture(t);
  const todo = await agenda.createItem({ title: "read paper", due: null }, { now: future });
  const item = await agenda.createItem({ title: "submit report", due: deadline() }, { now: future });
  assert.equal(todo.id, "ITM-20300810-001");
  assert.equal(item.id, "ITM-20300810-002");
  assert.equal((await agenda.listItems({ kind: "todo" })).length, 1);
  assert.equal((await agenda.listItems({ kind: "deadline" }))[0].id, item.id);
  assert.equal((await agenda.getItem(todo.id)).due, null);
});

test("duplicate titles retain distinct stable identities", async (t) => {
  const agenda = await fixture(t);
  const one = await agenda.createItem({ title: "same title", due: null }, { now: future });
  const two = await agenda.createItem({ title: "same title", due: null }, { now: new Date(future.getTime() + 1) });
  assert.notEqual(one.id, two.id);
});

test("update title and switch todo/deadline without using title as identity", async (t) => {
  const agenda = await fixture(t);
  const todo = await agenda.createItem({ title: "draft", due: null }, { now: future });
  const asDeadline = await agenda.updateItem(todo.id, { title: "draft v2", due: deadline() }, { now: future });
  const asTodo = await agenda.updateItem(todo.id, { due: null }, { now: future });
  assert.equal(asDeadline.id, todo.id);
  assert.equal(asTodo.id, todo.id);
  assert.equal(asTodo.title, "draft v2");
  assert.equal(asTodo.due, null);
});

test("absolute reminder is scheduled through the injected canonical scheduler", async (t) => {
  const agenda = await fixture(t); const deps = dependencies();
  const todo = await agenda.createItem({ title: "call advisor", due: null }, { now: future });
  const result = await agenda.setReminder(todo.id, { type: "absolute", at: "2030-08-11T20:00:00+08:00" }, { dependencies: deps });
  assert.equal(result.type, "absolute");
  assert.equal(deps.scheduled.length, 1);
  assert.match(result.commitment_id, /^CMT-/);
});

test("relative reminder defaults date-only deadlines to 09:00 Asia/Shanghai", async (t) => {
  const agenda = await fixture(t); const deps = dependencies();
  const item = await agenda.createItem({ title: "competition", due: deadline() }, { now: future });
  const result = await agenda.setReminder(item.id, { type: "relative", offset_days: 3 }, { dependencies: deps });
  assert.equal(result.time, "09:00");
  assert.equal(deps.records.get(result.commitment_id).due_at, "2030-08-17T01:00:00.000Z");
});

test("multiple reminders create independent commitments", async (t) => {
  const agenda = await fixture(t); const deps = dependencies();
  const item = await agenda.createItem({ title: "competition", due: deadline() }, { now: future });
  const one = await agenda.setReminder(item.id, { type: "relative", offset_days: 7 }, { dependencies: deps });
  const two = await agenda.setReminder(item.id, { type: "relative", offset_days: 1 }, { dependencies: deps });
  assert.notEqual(one.commitment_id, two.commitment_id);
  assert.equal((await agenda.getItem(item.id)).reminders.length, 2);
});

test("no reminder is created by default", async (t) => {
  const agenda = await fixture(t); const deps = dependencies();
  const item = await agenda.createItem({ title: "no reminder", due: deadline() }, { now: future });
  assert.equal((await agenda.getItem(item.id)).reminders.length, 0);
  assert.equal(deps.scheduled.length, 0);
});

test("relative reminder without due is rejected", async (t) => {
  const agenda = await fixture(t);
  const todo = await agenda.createItem({ title: "todo", due: null }, { now: future });
  await assert.rejects(agenda.setReminder(todo.id, { type: "relative", offset_days: 1 }, { dependencies: dependencies() }), /requires a deadline/);
});

test("remove reminder cancels its commitment and preserves its item", async (t) => {
  const agenda = await fixture(t); const deps = dependencies();
  const item = await agenda.createItem({ title: "item", due: null }, { now: future });
  const scheduled = await agenda.setReminder(item.id, { type: "absolute", at: "2030-08-11T20:00:00+08:00" }, { dependencies: deps });
  const result = await agenda.removeReminder(item.id, scheduled.commitment_id, { dependencies: deps });
  assert.equal(result.id, item.id);
  assert.equal(result.reminders.length, 0);
  assert.deepEqual(deps.cancelled, [scheduled.commitment_id]);
});

test("due update creates replacement bindings before cancelling old relative reminders", async (t) => {
  const agenda = await fixture(t); const deps = dependencies();
  const item = await agenda.createItem({ title: "competition", due: deadline("2030-08-20") }, { now: future });
  const old = await agenda.setReminder(item.id, { type: "relative", offset_days: 3 }, { dependencies: deps });
  const updated = await agenda.updateItem(item.id, { due: deadline("2030-08-25") }, { now: future, dependencies: deps });
  assert.equal(updated.due.date, "2030-08-25");
  assert.notEqual(updated.reminders[0].commitment_id, old.commitment_id);
  assert.deepEqual(deps.cancelled, [old.commitment_id]);
});

test("schedule failure leaves Agenda due unchanged", async (t) => {
  const agenda = await fixture(t); const good = dependencies(); const bad = dependencies({ scheduleFailure: true });
  const item = await agenda.createItem({ title: "competition", due: deadline("2030-08-20") }, { now: future });
  await agenda.setReminder(item.id, { type: "relative", offset_days: 3 }, { dependencies: good });
  await assert.rejects(agenda.updateItem(item.id, { due: deadline("2030-08-25") }, { now: future, dependencies: bad }), /schedule failure/);
  assert.equal((await agenda.getItem(item.id)).due.date, "2030-08-20");
});

test("complete and delete cancel future reminders before changing Agenda", async (t) => {
  const agenda = await fixture(t); const deps = dependencies();
  const one = await agenda.createItem({ title: "complete", due: null }, { now: future });
  const oneReminder = await agenda.setReminder(one.id, { type: "absolute", at: "2030-08-11T20:00:00+08:00" }, { dependencies: deps });
  const completed = await agenda.completeItem(one.id, { now: future, dependencies: deps });
  assert.equal(completed.status, "completed");
  assert.ok(deps.cancelled.includes(oneReminder.commitment_id));
  const two = await agenda.createItem({ title: "delete", due: null }, { now: future });
  const twoReminder = await agenda.setReminder(two.id, { type: "absolute", at: "2030-08-12T20:00:00+08:00" }, { dependencies: deps });
  await agenda.deleteItem(two.id, { dependencies: deps });
  assert.equal(await agenda.getItem(two.id), null);
  assert.ok(deps.cancelled.includes(twoReminder.commitment_id));
});

test("cancellation failure leaves item active and undeleted", async (t) => {
  const agenda = await fixture(t); const good = dependencies();
  const item = await agenda.createItem({ title: "keep", due: null }, { now: future });
  await agenda.setReminder(item.id, { type: "absolute", at: "2030-08-11T20:00:00+08:00" }, { dependencies: good });
  good.scheduler.cancel = async () => { throw new Error("fixture cancel failure"); };
  await assert.rejects(agenda.deleteItem(item.id, { dependencies: good }), /cancellation failed/);
  assert.equal((await agenda.getItem(item.id)).status, "active");
});

test("invalid date and ambiguous references are rejected by the helper boundary", async (t) => {
  const agenda = await fixture(t);
  await assert.rejects(agenda.createItem({ title: "bad", due: deadline("2030-02-30") }, { now: future }), /due.date is invalid/);
  await assert.rejects(agenda.updateItem("ITM-20300810-999", { title: "missing" }, { now: future }), /item not found/);
});

test("write failure does not claim creation", async (t) => {
  const agenda = await fixture(t);
  await fs.mkdir(agenda.AGENDA_PATH, { recursive: true });
  await assert.rejects(agenda.createItem({ title: "blocked", due: null }, { now: future }));
});

test("generated view is not a mutation source and helper has no native cron or arbitrary path interface", async (t) => {
  const agenda = await fixture(t);
  const item = await agenda.createItem({ title: "visible", due: deadline() }, { now: future });
  const view = await fs.readFile(agenda.DEADLINES_VIEW_PATH, "utf8");
  const source = await fs.readFile(new URL("./agenda.mjs", import.meta.url), "utf8");
  assert.match(view, /Generated view\. Canonical data lives in the Agenda store\./);
  assert.match(view, new RegExp(item.id));
  assert.doesNotMatch(source, /cron\.(?:add|remove)|systemctl|lark-cli|--path|writeFile\(.*input/i);
});
