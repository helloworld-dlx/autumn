import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

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
test("initialize creates the approved D1 state without inventing a learning day", async (t) => { const { root, mod } = await fixture(t); const state = await mod.journalInitialize({}, { dataRoot: root }); assert.equal(state.current_stage, "D"); assert.equal(state.current_substage, "D1"); assert.equal(state.current_task, "支持RV32IM的NEMU"); assert.equal(state.total_learning_days, 0); assert.equal(state.total_learning_minutes, 0); await assert.rejects(mod.journalInitialize({}, { dataRoot: root }), /already initialized/); });
test("checkpoint recommendation is not execution and compiler success alone is not a signal", async (t) => { const { root, mod } = await fixture(t); const no = await mod.journalRecord(ordinary(undefined, { completed: ["成功编译。"] }), { dataRoot: root }); assert.equal(no.checkpoint.recommended, false); assert.equal(no.checkpoint.executed, false); });
test("ordinary reading day does not suggest a checkpoint", async (t) => {
  const { root, mod } = await fixture(t); const result = await mod.journalRecord(ordinary(undefined, { completed: ["阅读 NEMU 执行流程。"], checkpoint_signals: {} }), { dataRoot: root });
  assert.equal(result.checkpoint.recommended, false);
});
test("long learning day with failed tests does not suggest a checkpoint", async (t) => {
  const { root, mod } = await fixture(t); const result = await mod.journalRecord(ordinary(undefined, { minutes: 180, completed: ["MUL 测试仍失败。"], checkpoint_signals: {} }), { dataRoot: root });
  assert.equal(result.checkpoint.recommended, false);
});
test("explicit MUL/MULH cpu-tests pass suggests a manual checkpoint", async (t) => {
  const { root, mod } = await fixture(t); const result = await mod.journalRecord(ordinary(undefined, { completed: ["MUL/MULH 都通过 cpu-tests。"], checkpoint_signals: { tests_passed: true } }), { dataRoot: root });
  assert.equal(result.checkpoint.recommended, true); assert.match(result.checkpoint.message, /MUL\/MULH/); assert.equal(result.checkpoint.provider, "unavailable");
});
test("unconfirmed 'probably fixed' does not suggest a checkpoint", async (t) => {
  const { root, mod } = await fixture(t); const result = await mod.journalRecord(ordinary(undefined, { completed: ["DIV 好像好了。"], checkpoint_signals: {} }), { dataRoot: root });
  assert.equal(result.checkpoint.recommended, false);
});
test("confirmed bug fix with regression PASS suggests a checkpoint", async (t) => {
  const { root, mod } = await fixture(t); const result = await mod.journalRecord(ordinary(undefined, { completed: ["修复除法符号扩展，regression PASS。"], checkpoint_signals: { bug_fixed_regression: true } }), { dataRoot: root });
  assert.equal(result.checkpoint.recommended, true);
});
test("D1 closure is a strong checkpoint signal and is not repeated", async (t) => {
  const { root, mod } = await fixture(t); const first = await mod.journalRecord(ordinary("2026-09-02", { completed: ["D1 完成，准备 D2。"], milestone_status: "done", checkpoint_signals: { substage_completed: true, before_new_stage: true } }), { dataRoot: root });
  assert.equal(first.checkpoint.recommended, true); assert.equal(first.checkpoint.message, "checkpoint: complete D1 RV32IM NEMU");
  const second = await mod.journalRecord(ordinary("2026-09-03", { completed: ["整理 D1 收尾。"], milestone_status: "done", checkpoint_signals: { substage_completed: true } }), { dataRoot: root });
  assert.equal(second.checkpoint.recommended, false); assert.equal(second.checkpoint.suppressed, "already_suggested");
  const state = (await mod.journalContext({ dataRoot: root })).state; assert.equal(state.checkpoint_suggestions.length, 1);
});
test("user-confirmed manual checkpoint records no fake hash", async (t) => {
  const { root, mod } = await fixture(t); await mod.journalRecord(ordinary(), { dataRoot: root });
  const result = await mod.journalCheckpointConfirmed({ date: "2026-09-02", substage: "D1", message: "checkpoint: complete D1 RV32IM NEMU" }, { dataRoot: root });
  assert.deepEqual(result.manual_checkpoint, { date: "2026-09-02", substage: "D1", message: "checkpoint: complete D1 RV32IM NEMU", confirmed_by_user: true });
  assert.equal(Object.hasOwn(result.manual_checkpoint, "hash"), false);
});
test("unavailable Git provider does not prevent checkpoint suggestion or journal save", async (t) => {
  const { root, mod } = await fixture(t); const result = await mod.journalRecord(ordinary(undefined, { checkpoint_signals: { module_finished_verified: true } }), { dataRoot: root });
  assert.equal(result.checkpoint.recommended, true); assert.equal(result.checkpoint.provider, "unavailable");
  await fs.access(path.join(root, "logs", "2026-09-02.md")); await fs.access(path.join(root, "state.json"));
});
test("completed substage closure preserves only the user's review answers and never overwrites", async (t) => {
  const { root, mod } = await fixture(t); await mod.journalRecord(ordinary(undefined, { milestone_status: "done", checkpoint_signals: { substage_completed: true } }), { dataRoot: root });
  const context = await mod.journalClosureContext({ stage: "D1", dataRoot: root }); assert.equal(context.learning_days, 1); assert.equal(context.logged_concepts[0].text, "先得到正确的 64 位乘积再取高位。");
  const result = await mod.journalClosureRecord({ stage: "D1", highlights: ["先验证 64 位乘积。"], revisit: ["DIV 的边界。"], redo: null }, { dataRoot: root });
  const review = await fs.readFile(path.join(root, "reviews", "D1-closure.md"), "utf8"); assert.equal(result.review_path, "reviews/D1-closure.md"); assert.match(review, /先验证 64 位乘积。/); assert.match(review, /DIV 的边界。/); assert.doesNotMatch(review, /三大收获/);
  await assert.rejects(mod.journalClosureRecord({ stage: "D1", highlights: ["重复。"], revisit: [] }, { dataRoot: root }), /already exists/);
});
test("closure is unavailable until the user-confirmed milestone is done", async (t) => {
  const { root, mod } = await fixture(t); await mod.journalRecord(ordinary(), { dataRoot: root });
  await assert.rejects(mod.journalClosureContext({ stage: "D1", dataRoot: root }), /completed substage/);
  await assert.rejects(mod.journalClosureRecord({ stage: "D1", highlights: ["x"], revisit: [] }, { dataRoot: root }), /completed substage/);
});
test("skill advertises narrow YSYX journal activation and protects generic notes", async () => {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const skill = await fs.readFile(path.resolve(here, "..", "skills", "ysyx-engineering-journal", "SKILL.md"), "utf8");
  assert.match(skill, /description:.*一生一芯.*YSYX.*journal_context/);
  assert.match(skill, /node \/home\/xyzlh\/\.openclaw\/workspace\/tools\/ysyx_journal\.mjs journal_context/);
  assert.match(skill, /不位于本 Skill 目录/);
  for (const phrase of ["记录一下一生一芯", "记录今天的一生一芯", "今天一生一芯学了", "帮我记一下今天 YSYX", "一生一芯学习日志", "我今天 D1 学了", "看看我一生一芯进度", "最近一生一芯学了什么", "帮我整理最近两周一生一芯", "帮我复习 D 阶段", "帮我复习 C 阶段"]) assert.match(skill, new RegExp(phrase));
  assert.match(skill, /记录一下我今天的随想/);
  assert.match(skill, /不是 general memory/);
});
test("workspace routing gives YSYX journal precedence over continuity memory", async () => {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const agents = await fs.readFile(path.resolve(here, "..", "..", "..", "docs", "current", "AGENTS.md"), "utf8");
  assert.match(agents, /YSYX Engineering Journal priority/);
  assert.match(agents, /第一步必须.*journal_context.*不得.*memory_search.*memory_get.*USER\.md/);
  assert.ok(agents.indexOf("YSYX Engineering Journal priority") < agents.indexOf("### 10A. Continuity Lite"));
  assert.match(agents, /记录一下我今天的随想.*不属于此例外/);
  assert.match(agents, /你还记得我之前说过的某件事情吗？.*不属于此例外/);
});
