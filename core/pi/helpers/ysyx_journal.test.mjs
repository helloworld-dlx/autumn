import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

async function fixture(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "ysyx-journal-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const mod = await import(`${new URL("./ysyx_journal.mjs", import.meta.url).href}?${Math.random()}`);
  return { root: path.join(root, "ysyx-learning"), mod };
}
const ordinary = (date = "2026-09-02", more = {}) => ({ date, stage: "D1", minutes: 105, goal: "继续实现 RV32IM 指令。", current_task: "支持RV32IM的NEMU", completed: ["实现 MUL、MULH。"], concepts: ["先得到正确的 64 位乘积再取高位。"], unresolved: ["DIV 尚未开始。"], resolved_unresolved: [], next_step: "继续实现 DIV。", tags: ["rv32m"], bugs: [], milestone_status: "in_progress", checkpoint_signals: {}, ...more });

test("ordinary three-question learning day renders empty bug section without invented PASS", async (t) => {
  const { root, mod } = await fixture(t); const result = await mod.journalRecord(ordinary(), { dataRoot: root });
  const log = await fs.readFile(path.join(root, "logs", "2026-09-02.md"), "utf8");
  assert.match(log, /# 2026-09-02｜D1｜1h45min/); assert.match(log, /## 遇到的问题\n\n- DIV 尚未开始。/); assert.doesNotMatch(log, /PASS|通过/);
  assert.equal(result.state.total_learning_minutes, 105);
});
test("important bug preserves possible root cause as possible", async (t) => {
  const { root, mod } = await fixture(t); await mod.journalRecord(ordinary("2026-09-04", { bugs: [{ title: "div-test 负数 case 错", phenomenon: "负数 case 错", root_cause: "可能是符号扩展", root_cause_status: "possible", verification: null }] }), { dataRoot: root });
  const log = await fs.readFile(path.join(root, "logs", "2026-09-04.md"), "utf8"); assert.match(log, /可能原因：可能是符号扩展/); assert.doesNotMatch(log, /\n原因：可能是符号扩展/);
});
test("confirmed bug requires a confirmed root cause and renders it", async (t) => {
  const { root, mod } = await fixture(t); await assert.rejects(mod.journalRecord(ordinary(undefined, { bugs: [{ title: "x", root_cause_status: "confirmed" }] }), { dataRoot: root }), /confirmed root cause/);
});
test("next step is inherited and user may override its goal", async (t) => {
  const { root, mod } = await fixture(t); await mod.journalRecord(ordinary("2026-09-02", { unresolved: [], checkpoint_signals: {} }), { dataRoot: root });
  assert.equal((await mod.journalContext({ dataRoot: root })).default_goal, "继续实现 DIV。");
  await mod.journalRecord(ordinary("2026-09-03", { goal: "改做 ELF。", unresolved: [] }), { dataRoot: root }); assert.equal((await mod.journalProgress({ dataRoot: root })).current.goal, "改做 ELF。");
});
test("same date rejects rather than silently overwriting", async (t) => { const { root, mod } = await fixture(t); await mod.journalRecord(ordinary(), { dataRoot: root }); await assert.rejects(mod.journalRecord(ordinary(), { dataRoot: root }), /already exists/); });
test("strict record validation rejects invalid stage, minutes, and unknown fields", async (t) => { const { root, mod } = await fixture(t); await assert.rejects(mod.journalRecord(ordinary(undefined, { stage: "D7" }), { dataRoot: root }), /stage is invalid/); await assert.rejects(mod.journalRecord(ordinary(undefined, { minutes: 0 }), { dataRoot: root }), /minutes is invalid/); await assert.rejects(mod.journalRecord({ ...ordinary(), invented: true }, { dataRoot: root }), /unknown/); });
test("CLI rejects arbitrary data root and unknown action fields", async (t) => { const { mod } = await fixture(t); await assert.rejects(mod.main(["journal_context", '{"dataRoot":"C:/outside"}']), /payload is invalid/); await assert.rejects(mod.main(["journal_progress", '{"extra":true}']), /unknown fields/); });
test("atomic write failure does not create state after log path becomes a directory", async (t) => { const { root, mod } = await fixture(t); await fs.mkdir(path.join(root, "logs", "2026-09-02.md"), { recursive: true }); await assert.rejects(mod.journalRecord(ordinary(), { dataRoot: root }), /regular file/); await assert.rejects(fs.access(path.join(root, "state.json"))); });
test("context detects state/log inconsistency", async (t) => { const { root, mod } = await fixture(t); await mod.journalRecord(ordinary(), { dataRoot: root }); const p = path.join(root, "state.json"); const state = JSON.parse(await fs.readFile(p, "utf8")); state.total_learning_minutes = 1; await fs.writeFile(p, JSON.stringify(state)); assert.equal((await mod.journalContext({ dataRoot: root })).state_consistency, "inconsistent"); });
test("summary deterministically limits to fourteen natural days", async (t) => { const { root, mod } = await fixture(t); await mod.journalRecord(ordinary("2026-08-17", { unresolved: [] }), { dataRoot: root }); await mod.journalRecord(ordinary("2026-08-20", { unresolved: [] }), { dataRoot: root }); await mod.journalRecord(ordinary("2026-08-31", { unresolved: [] }), { dataRoot: root }); const summary = await mod.journalSummary({ end_date: "2026-08-31", dataRoot: root }); assert.equal(summary.learning_days, 2); assert.equal(summary.total_minutes, 210); });
test("recent logs are bounded and newest first", async (t) => { const { root, mod } = await fixture(t); await mod.journalRecord(ordinary("2026-09-01", { unresolved: [] }), { dataRoot: root }); await mod.journalRecord(ordinary("2026-09-02", { unresolved: [] }), { dataRoot: root }); const recent = await mod.journalRecent({ limit: 1, dataRoot: root }); assert.deepEqual(recent.map((item) => item.date), ["2026-09-02"]); });
test("D and C reviews keep their own logs", async (t) => { const { root, mod } = await fixture(t); await mod.journalRecord(ordinary("2026-09-01", { unresolved: [] }), { dataRoot: root }); await mod.journalRecord(ordinary("2026-09-02", { stage: "C1", current_task: "工具和基础设施", unresolved: [] }), { dataRoot: root }); assert.equal((await mod.journalReview({ stage: "D", dataRoot: root })).timeline.length, 1); assert.equal((await mod.journalReview({ stage: "C", dataRoot: root })).timeline.length, 1); });
test("unverified mandatory mapping has no percentage and D6 remains optional", async (t) => { const { root, mod } = await fixture(t); const progress = await mod.journalProgress({ dataRoot: root }); assert.equal(progress.mandatory.counts, null); assert.equal(progress.milestones.D6.optional, true); });
test("checkpoint recommendation is not execution and compiler success alone is not a signal", async (t) => { const { root, mod } = await fixture(t); const no = await mod.journalRecord(ordinary(undefined, { completed: ["成功编译。"] }), { dataRoot: root }); assert.equal(no.checkpoint.recommended, false); assert.equal(no.checkpoint.executed, false); });
