import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";

export const COURSE_VERSION = "v24.07";
export const SUBSTAGES = Object.freeze({
  D1: "支持RV32IM的NEMU", D2: "程序的机器级表示", D3: "AM运行时环境",
  D4: "用RTL实现迷你RISC-V处理器", D5: "设备和输入输出", D6: "D阶段流片准备（optional）",
  C1: "工具和基础设施", C2: "支持RV32E的单周期NPC", C3: "调试技巧",
  C4: "ELF文件和链接", C5: "异常处理和RT-Thread"
});
const STAGES = new Set(Object.keys(SUBSTAGES));
const STATES = new Set(["not_started", "in_progress", "done"]);
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const fail = (message) => { throw new Error(message); };
const here = path.dirname(fileURLToPath(import.meta.url));
// Runtime helpers live in <OpenClaw workspace>/tools, matching agenda.mjs.
export const DEFAULT_DATA_ROOT = path.resolve(here, "..", "ysyx-learning");

function plain(value, field, { required = true, max = 600 } = {}) {
  if (value === null && !required) return null;
  if (typeof value !== "string") fail(`${field} must be a string`);
  const result = value.trim();
  if (required && !result) fail(`${field} must not be empty`);
  if (result.length > max || /[\0\r]/.test(result)) fail(`${field} is invalid`);
  return result;
}
function date(value) { if (typeof value !== "string" || !DATE.test(value) || Number.isNaN(Date.parse(`${value}T00:00:00Z`))) fail("date is invalid"); return value; }
function only(value, fields, name) { if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).some((key) => !fields.has(key))) fail(`${name} has unknown or invalid fields`); }
function strings(value, field, maxItems = 30) { if (!Array.isArray(value) || value.length > maxItems) fail(`${field} must be an array`); return value.map((item) => plain(item, field)); }
function stageGroup(stage) { return stage.startsWith("D") ? "D" : "C"; }
function formatMinutes(minutes) { return `${Math.floor(minutes / 60)}h${minutes % 60}min`; }
function emptyState() {
  return {
    schema_version: 1, course_version: COURSE_VERSION, timezone: "Asia/Shanghai",
    current_stage: null, current_substage: null, current_task: null, current_goal: null,
    last_learning_date: null, total_learning_days: 0, total_learning_minutes: 0,
    milestones: Object.fromEntries(Object.entries(SUBSTAGES).map(([id, label]) => [id, { label, status: "not_started", optional: id === "D6" }])),
    official_mandatory_task_mapping: { source_status: "unverified", source_name: null, source_reference: null, imported_at: null, items: [] },
    last_manual_git_checkpoint: null, unresolved_items: [], indexes: { tags: {}, concepts: {}, bugs: {} }
  };
}
export function parseState(source) {
  let state; try { state = JSON.parse(source); } catch { fail("state is invalid JSON"); }
  only(state, new Set(Object.keys(emptyState())), "state");
  if (state.schema_version !== 1 || state.course_version !== COURSE_VERSION || state.timezone !== "Asia/Shanghai") fail("state version is invalid");
  for (const field of ["current_stage", "current_substage", "current_task", "current_goal", "last_learning_date"]) if (state[field] !== null && typeof state[field] !== "string") fail(`state ${field} is invalid`);
  if (state.current_stage !== null && !["D", "C"].includes(state.current_stage)) fail("state current_stage is invalid");
  if (state.current_substage !== null && !STAGES.has(state.current_substage)) fail("state current_substage is invalid");
  if (state.last_learning_date !== null) date(state.last_learning_date);
  if (!Number.isInteger(state.total_learning_days) || state.total_learning_days < 0 || !Number.isInteger(state.total_learning_minutes) || state.total_learning_minutes < 0) fail("state totals are invalid");
  only(state.milestones, new Set(Object.keys(SUBSTAGES)), "milestones");
  for (const [id, entry] of Object.entries(state.milestones)) {
    only(entry, new Set(["label", "status", "optional"]), `milestone ${id}`);
    if (entry.label !== SUBSTAGES[id] || !STATES.has(entry.status) || entry.optional !== (id === "D6")) fail(`milestone ${id} is invalid`);
  }
  only(state.official_mandatory_task_mapping, new Set(["source_status", "source_name", "source_reference", "imported_at", "items"]), "mandatory mapping");
  if (state.official_mandatory_task_mapping.source_status !== "unverified" && state.official_mandatory_task_mapping.source_status !== "verified") fail("mandatory source status is invalid");
  if (!Array.isArray(state.official_mandatory_task_mapping.items)) fail("mandatory items are invalid");
  if (!Array.isArray(state.unresolved_items) || !state.indexes || typeof state.indexes !== "object") fail("state collections are invalid");
  return state;
}
export const serializeState = (state) => `${JSON.stringify(parseState(JSON.stringify(state)), null, 2)}\n`;

function normalizeBug(raw) {
  only(raw, new Set(["title", "phenomenon", "location", "root_cause", "root_cause_status", "fix", "verification"]), "bug");
  const status = raw.root_cause_status ?? "unknown";
  if (!["confirmed", "possible", "unknown"].includes(status)) fail("bug root cause status is invalid");
  const result = { title: plain(raw.title, "bug title", { max: 160 }), root_cause_status: status };
  for (const key of ["phenomenon", "location", "root_cause", "fix", "verification"]) result[key] = raw[key] === undefined || raw[key] === null ? null : plain(raw[key], `bug ${key}`, { max: 800 });
  if (status === "confirmed" && !result.root_cause) fail("confirmed root cause is required");
  return result;
}
function normalizeRecord(raw) {
  only(raw, new Set(["date", "stage", "minutes", "goal", "current_task", "completed", "concepts", "unresolved", "resolved_unresolved", "next_step", "tags", "bugs", "milestone_status", "checkpoint_signals"]), "record");
  const stage = plain(raw.stage, "stage", { max: 3 }); if (!STAGES.has(stage)) fail("stage is invalid");
  if (!Number.isInteger(raw.minutes) || raw.minutes < 1 || raw.minutes > 1440) fail("minutes is invalid");
  const milestoneStatus = raw.milestone_status ?? "in_progress"; if (!STATES.has(milestoneStatus)) fail("milestone status is invalid");
  const signals = raw.checkpoint_signals ?? {};
  only(signals, new Set(["tests_passed", "module_finished_verified", "bug_fixed_regression", "before_major_refactor", "before_new_stage", "stable_end_of_day"]), "checkpoint signals");
  for (const value of Object.values(signals)) if (typeof value !== "boolean") fail("checkpoint signal is invalid");
  return {
    date: date(raw.date), stage, minutes: raw.minutes,
    goal: raw.goal == null ? null : plain(raw.goal, "goal", { max: 600 }),
    current_task: raw.current_task == null ? null : plain(raw.current_task, "current_task", { max: 240 }),
    completed: strings(raw.completed ?? [], "completed"), concepts: strings(raw.concepts ?? [], "concepts"),
    unresolved: strings(raw.unresolved ?? [], "unresolved"), resolved_unresolved: strings(raw.resolved_unresolved ?? [], "resolved_unresolved"),
    next_step: raw.next_step == null ? null : plain(raw.next_step, "next_step", { max: 600 }), tags: strings(raw.tags ?? [], "tags", 20), bugs: (raw.bugs ?? []).map(normalizeBug), milestone_status: milestoneStatus, checkpoint_signals: signals
  };
}
function section(title, body) { return [`## ${title}`, "", body, ""].join("\n"); }
export function renderLog(record, { gitProvider = "unavailable", checkpoint = null } = {}) {
  const lines = [`# ${record.date}｜${record.stage}｜${formatMinutes(record.minutes)}`, ""];
  lines.push(section("目标", record.goal ?? ""));
  lines.push(section("今天完成", record.completed.map((value) => `- ${value}`).join("\n")));
  lines.push(section("今天真正理解的东西", record.concepts.map((value) => `- ${value}`).join("\n")));
  const problems = [];
  for (const value of record.unresolved) problems.push(`- ${value}`);
  for (const bug of record.bugs) {
    if (problems.length) problems.push("");
    problems.push(`### ${bug.title}`, "");
    if (bug.phenomenon) problems.push(`现象：${bug.phenomenon}`, "");
    if (bug.location) problems.push(`定位：${bug.location}`, "");
    if (bug.root_cause) problems.push(`${bug.root_cause_status === "confirmed" ? "原因" : "可能原因"}：${bug.root_cause}`, "");
    if (bug.fix) problems.push(`修复：${bug.fix}`, "");
    if (bug.verification) problems.push(`验证：${bug.verification}`, "");
  }
  lines.push(section("遇到的问题", problems.join("\n").trimEnd()));
  lines.push(section("Git", [`- provider: ${gitProvider}`, "- manual checkpoint: （未查询）", `- checkpoint suggestion: ${checkpoint?.message ?? "（无）"}`].join("\n")));
  lines.push(section("下一步", record.next_step ?? ""));
  return `${lines.join("\n").replaceAll("\r\n", "\n").replaceAll("\r", "\n")}\n`;
}
function sections(source) { const result = new Map(); const matches = [...source.matchAll(/^## ([^\n]+)\n\n([\s\S]*?)(?=^## |(?![\s\S]))/gm)]; for (const match of matches) result.set(match[1], match[2].trim()); return result; }
function bullets(body) { return body ? body.split("\n").filter((line) => line.startsWith("- ")).map((line) => line.slice(2)) : []; }
export function parseLog(source) {
  const heading = source.match(/^# (\d{4}-\d{2}-\d{2})｜([DC][1-6])｜(\d+)h(\d+)min\n/m); if (!heading || !STAGES.has(heading[2])) fail("log header is invalid");
  const blocks = sections(source); const problem = blocks.get("遇到的问题") ?? "";
  const bugs = [...problem.matchAll(/^### ([^\n]+)\n\n([\s\S]*?)(?=^### |(?![\s\S]))/gm)].map((match) => ({ title: match[1], text: match[2].trim() }));
  return { date: heading[1], stage: heading[2], minutes: Number(heading[3]) * 60 + Number(heading[4]), goal: blocks.get("目标") || null, completed: bullets(blocks.get("今天完成")), concepts: bullets(blocks.get("今天真正理解的东西")), unresolved: bullets(problem).filter((line) => !line.startsWith("provider:")), next_step: blocks.get("下一步") || null, bugs };
}
async function regular(target) { const stat = await fs.lstat(target).catch((error) => error.code === "ENOENT" ? null : Promise.reject(error)); if (stat && (!stat.isFile() || stat.isSymbolicLink())) fail("journal target must be a regular file"); }
async function atomicWrite(target, value) { await regular(target); const temp = `${target}.tmp-${process.pid}-${randomUUID()}`; try { await fs.writeFile(temp, value, { encoding: "utf8", mode: 0o600 }); await fs.rename(temp, target); } finally { await fs.unlink(temp).catch(() => {}); } }
async function locked(root, work) { await fs.mkdir(root, { recursive: true, mode: 0o700 }); const lock = path.join(root, ".journal.lock"); let handle; for (let n = 0; n < 80; n += 1) { try { handle = await fs.open(lock, "wx", 0o600); break; } catch (error) { if (error.code !== "EEXIST") throw error; await new Promise((resolve) => setTimeout(resolve, 25)); } } if (!handle) fail("journal is busy"); try { return await work(); } finally { await handle.close().catch(() => {}); await fs.unlink(lock).catch(() => {}); } }
function paths(root) { return { root, state: path.join(root, "state.json"), logs: path.join(root, "logs") }; }
async function entries(root) { const directory = path.join(root, "logs"); const names = await fs.readdir(directory).catch((error) => error.code === "ENOENT" ? [] : Promise.reject(error)); const result = []; for (const name of names.filter((name) => DATE.test(name.slice(0, 10)) && name.endsWith(".md")).sort()) result.push(parseLog(await fs.readFile(path.join(directory, name), "utf8"))); return result; }
async function readState(root) { const target = paths(root).state; await regular(target); const source = await fs.readFile(target, "utf8").catch((error) => error.code === "ENOENT" ? null : Promise.reject(error)); return source === null ? emptyState() : parseState(source); }
function derived(logs) { return { total_learning_days: logs.length, total_learning_minutes: logs.reduce((total, item) => total + item.minutes, 0), last_learning_date: logs.at(-1)?.date ?? null }; }
function consistency(state, logs) { const value = derived(logs); return state.total_learning_days === value.total_learning_days && state.total_learning_minutes === value.total_learning_minutes && state.last_learning_date === value.last_learning_date ? "consistent" : "inconsistent"; }
function addIndex(index, values, day) { for (const value of values) { const key = value.toLowerCase(); index[key] ??= []; if (!index[key].includes(day)) index[key].push(day); } }
export function recommendCheckpoint(record) { const reasons = Object.entries(record.checkpoint_signals).filter(([, value]) => value).map(([key]) => key); if (!reasons.length) return { recommended: false, executed: false, provider: "unavailable", reasons: [], message: null }; const summary = record.completed[0]?.replace(/[\r\n]/g, " ").slice(0, 72) || "stable verified checkpoint"; return { recommended: true, executed: false, provider: "unavailable", reasons, message: `checkpoint: ${record.stage} ${summary}`, modes: ["mark_current_state", "commit_changes"] }; }
export async function journalContext({ dataRoot = DEFAULT_DATA_ROOT } = {}) { const state = await readState(dataRoot); const logs = await entries(dataRoot); return { course_version: COURSE_VERSION, state, default_goal: logs.at(-1)?.next_step ?? null, git_provider: { status: "unavailable" }, state_consistency: consistency(state, logs) }; }
export async function journalInitialize(input = {}, { dataRoot = DEFAULT_DATA_ROOT } = {}) {
  only(input, new Set(), "initialize");
  return await locked(dataRoot, async () => {
    const layout = paths(dataRoot); const exists = await fs.lstat(layout.state).then((stat) => { if (!stat.isFile() || stat.isSymbolicLink()) fail("journal state must be a regular file"); return true; }).catch((error) => error.code === "ENOENT" ? false : Promise.reject(error));
    if (exists) fail("journal is already initialized");
    if ((await entries(dataRoot)).length) fail("journal logs already exist");
    const state = emptyState(); state.current_stage = "D"; state.current_substage = "D1"; state.current_task = SUBSTAGES.D1; state.milestones.D1.status = "in_progress";
    await atomicWrite(layout.state, serializeState(state)); return state;
  });
}
export async function journalRecord(input, { dataRoot = DEFAULT_DATA_ROOT } = {}) {
  const record = normalizeRecord(input); return await locked(dataRoot, async () => {
    const layout = paths(dataRoot); await fs.mkdir(layout.logs, { recursive: true, mode: 0o700 }); const target = path.join(layout.logs, `${record.date}.md`); await regular(target); if (await fs.lstat(target).then(() => true).catch((error) => error.code === "ENOENT" ? false : Promise.reject(error))) fail("record already exists for date");
    const state = await readState(dataRoot); const logs = await entries(dataRoot); if (consistency(state, logs) !== "consistent") fail("state/log inconsistency detected");
    const checkpoint = recommendCheckpoint(record); await atomicWrite(target, renderLog(record, { checkpoint }));
    state.current_stage = stageGroup(record.stage); state.current_substage = record.stage; state.current_task = record.current_task; state.current_goal = record.goal; state.milestones[record.stage].status = record.milestone_status;
    const latest = [...logs, parseLog(await fs.readFile(target, "utf8"))]; Object.assign(state, derived(latest));
    state.unresolved_items = state.unresolved_items.filter((item) => !record.resolved_unresolved.includes(item.summary)); for (const summary of record.unresolved) if (!state.unresolved_items.some((item) => item.summary === summary)) state.unresolved_items.push({ summary, stage: record.stage, first_seen_date: record.date, status: "open" });
    addIndex(state.indexes.tags, record.tags, record.date); addIndex(state.indexes.concepts, record.concepts, record.date); addIndex(state.indexes.bugs, record.bugs.map((bug) => bug.title), record.date);
    await atomicWrite(layout.state, serializeState(state)); return { record: parseLog(await fs.readFile(target, "utf8")), checkpoint, state };
  });
}
function windowEntries(logs, end, days) { date(end); const start = new Date(`${end}T00:00:00Z`); start.setUTCDate(start.getUTCDate() - days + 1); const first = start.toISOString().slice(0, 10); return logs.filter((entry) => entry.date >= first && entry.date <= end); }
function aggregate(items) { return { learning_days: items.length, total_minutes: items.reduce((n, item) => n + item.minutes, 0), stages: [...new Set(items.map((item) => item.stage))], confirmed_completed_facts: items.flatMap((item) => item.completed.map((text) => ({ date: item.date, text }))), confirmed_concepts: items.flatMap((item) => item.concepts.map((text) => ({ date: item.date, text }))), bugs: items.flatMap((item) => item.bugs.map((bug) => ({ date: item.date, ...bug }))), unresolved_items: items.flatMap((item) => item.unresolved.map((text) => ({ date: item.date, text }))), checkpoints: [] }; }
export async function journalProgress({ dataRoot = DEFAULT_DATA_ROOT } = {}) { const state = await readState(dataRoot); const mandatory = state.official_mandatory_task_mapping; const counts = mandatory.source_status === "verified" ? Object.fromEntries(Object.keys(SUBSTAGES).map((stage) => { const items = mandatory.items.filter((item) => item.substage === stage && item.mandatory); return [stage, { done: items.filter((item) => item.status === "done").length, total: items.length }]; })) : null; return { course_version: COURSE_VERSION, current: { stage: state.current_stage, substage: state.current_substage, task: state.current_task, goal: state.current_goal }, totals: { learning_days: state.total_learning_days, minutes: state.total_learning_minutes }, milestones: state.milestones, mandatory: { source_status: mandatory.source_status, counts }, unresolved_items: state.unresolved_items, last_manual_git_checkpoint: state.last_manual_git_checkpoint }; }
export async function journalRecent({ limit = 10, dataRoot = DEFAULT_DATA_ROOT } = {}) { if (!Number.isInteger(limit) || limit < 1 || limit > 50) fail("limit is invalid"); const logs = await entries(dataRoot); return logs.slice(-limit).reverse(); }
export async function journalSummary({ end_date = new Date().toISOString().slice(0, 10), dataRoot = DEFAULT_DATA_ROOT } = {}) { return { window_days: 14, end_date: date(end_date), ...aggregate(windowEntries(await entries(dataRoot), end_date, 14)) }; }
export async function journalReview({ stage, dataRoot = DEFAULT_DATA_ROOT } = {}) { if (!["D", "C"].includes(stage)) fail("review stage is invalid"); const logs = (await entries(dataRoot)).filter((entry) => stageGroup(entry.stage) === stage); const progress = await journalProgress({ dataRoot }); return { stage, timeline: logs.map((entry) => ({ date: entry.date, substage: entry.stage, minutes: entry.minutes, next_step: entry.next_step })), ...aggregate(logs), milestones: Object.fromEntries(Object.entries(progress.milestones).filter(([id]) => stageGroup(id) === stage)), verified_mandatory: progress.mandatory.source_status === "verified" ? progress.mandatory.counts : null }; }
export async function main(argv = process.argv.slice(2)) { const [action, payload = "{}", ...extra] = argv; if (extra.length) fail("unexpected arguments"); let input; try { input = JSON.parse(payload); } catch { fail("payload must be JSON"); } if (!input || typeof input !== "object" || Array.isArray(input) || Object.hasOwn(input, "dataRoot")) fail("payload is invalid"); const allowed = { journal_initialize: [], journal_context: [], journal_record: null, journal_progress: [], journal_recent: ["limit"], journal_summary: ["end_date"], journal_review: ["stage"] }; if (!(action in allowed)) fail("unsupported action"); if (allowed[action] && Object.keys(input).some((key) => !allowed[action].includes(key))) fail("payload has unknown fields"); const calls = { journal_initialize: () => journalInitialize(input), journal_context: () => journalContext(), journal_record: () => journalRecord(input), journal_progress: () => journalProgress(), journal_recent: () => journalRecent(input), journal_summary: () => journalSummary(input), journal_review: () => journalReview(input) }; process.stdout.write(`${JSON.stringify(await calls[action](), null, 2)}\n`); }
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch((error) => { process.stderr.write(`Error: ${error.message}\n`); process.exitCode = 1; });
