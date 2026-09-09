import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { buildDashboard, dashboardData } from "./ysyx_dashboard.mjs";
import { journalRecord } from "./ysyx_journal.mjs";

async function fixture(t) {
  const parent = await fs.mkdtemp(path.join(os.tmpdir(), "ysyx-dashboard-"));
  const root = path.join(parent, "ysyx-learning"); t.after(() => fs.rm(parent, { recursive: true, force: true }));
  const record = (date, stage, more = {}) => ({ date, stage, minutes: 90, goal: "实现功能", current_task: stage === "D1" ? "支持RV32IM的NEMU" : "程序的机器级表示", completed: ["MUL/MULH cpu-tests PASS"], concepts: ["mulh uses the high half"], unresolved: stage === "D1" ? ["DIV still open"] : [], resolved_unresolved: [], next_step: "next real step", tags: ["rv32m"], bugs: [{ title: "signed case", phenomenon: "negative input failed", root_cause_status: "confirmed", root_cause: "sign extension", fix: "corrected extension", verification: "regression PASS" }], milestone_status: stage === "D1" ? "done" : "in_progress", checkpoint_signals: {} , ...more });
  await journalRecord(record("2026-09-01", "D1"), { dataRoot: root });
  await journalRecord(record("2026-09-08", "D2", { completed: ["read machine representation"], concepts: ["two's complement"], bugs: [] }), { dataRoot: root });
  return root;
}

test("dashboard derives overview, timeline, and lightweight stats from synthetic canonical data", async (t) => {
  const root = await fixture(t); const data = await dashboardData({ dataRoot: root });
  assert.equal(data.overview.current_substage, "D2"); assert.equal(data.overview.learning_days, 2); assert.equal(data.overview.total_minutes, 180);
  assert.deepEqual(data.stats.by_substage.D1, { minutes: 90, days: 1 }); assert.equal(data.stats.concept_count, 2); assert.equal(data.stats.bug_count, 1);
  assert.equal(data.timeline[0].source.includes("MUL/MULH cpu-tests PASS"), true);
});
test("builder writes one deterministic offline HTML with all four pages and no external endpoint", async (t) => {
  const root = await fixture(t); const first = await buildDashboard({ dataRoot: root }); const output = path.join(root, "dashboard.html"); const html = await fs.readFile(output, "utf8");
  const second = await buildDashboard({ dataRoot: root }); const again = await fs.readFile(output, "utf8");
  assert.equal(first.learning_days, 2); assert.deepEqual(second, first); assert.equal(html, again);
  for (const label of ["Overview", "Timeline", "Review", "Stats", "mulh", "MUL/MULH cpu-tests PASS"]) assert.match(html, new RegExp(label));
  assert.doesNotMatch(html, /https?:\/\//); assert.doesNotMatch(html, /fetch\(/);
});
test("dashboard embeds journal text safely without creating executable markup", async (t) => {
  const root = await fixture(t); await fs.readFile(path.join(root, "logs", "2026-09-01.md"), "utf8");
  const state = JSON.parse(await fs.readFile(path.join(root, "state.json"), "utf8")); state.current_goal = "</script><script>bad()</script>"; await fs.writeFile(path.join(root, "state.json"), JSON.stringify(state));
  await buildDashboard({ dataRoot: root }); const html = await fs.readFile(path.join(root, "dashboard.html"), "utf8");
  assert.doesNotMatch(html, /<\/script><script>bad\(\)<\/script>/); assert.match(html, /\\u003c\/script\\u003e/);
});
test("builder rejects a symlink dashboard target", async (t) => {
  if (process.platform === "win32") { t.skip("Windows test environment cannot create symlinks"); return; }
  const root = await fixture(t); const target = path.join(root, "dashboard.html"); await fs.symlink(path.join(root, "state.json"), target);
  await assert.rejects(buildDashboard({ dataRoot: root }), /regular file/);
});
