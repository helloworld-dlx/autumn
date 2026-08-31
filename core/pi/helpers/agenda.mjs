import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { addCommitment, getCommitment } from "./commitments.mjs";
import { cancelTimeCommitment, scheduleTimeCommitment } from "./proactive_completion.mjs";

const workspace = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const memoryDir = path.join(workspace, "memory");
export const AGENDA_PATH = path.join(memoryDir, "agenda.json");
export const DEADLINES_VIEW_PATH = path.join(workspace, "deadlines.md");
const lockPath = path.join(memoryDir, ".agenda.json.lock");
const ID = /^ITM-\d{8}-\d{3}$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;
const ZONED_ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?(?:Z|[+-]\d{2}:\d{2})$/;
const fail = (message) => { throw new Error(message); };
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function text(value, name, required = true, max = 240) {
  if (typeof value !== "string") fail(`${name} must be a string`);
  const result = value.trim();
  if (required && !result) fail(`${name} is required`);
  if (result.length > max || /[\r\n]/.test(result)) fail(`${name} is invalid`);
  return result;
}
function date(value) {
  const result = text(value, "due.date", true, 10);
  if (!DATE.test(result)) fail("due.date is invalid");
  const parsed = new Date(`${result}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== result) fail("due.date is invalid");
  return result;
}
function time(value, required = false) {
  if (value === null || value === undefined || value === "") {
    if (required) fail("time is required");
    return null;
  }
  const result = text(value, "time", true, 5);
  if (!TIME.test(result)) fail("time is invalid");
  return result;
}
function due(value) {
  if (value === null) return null;
  if (!value || typeof value !== "object" || Array.isArray(value)) fail("due is invalid");
  const result = { date: date(value.date), time: time(value.time), timezone: text(value.timezone ?? "Asia/Shanghai", "due.timezone", true, 40) };
  if (result.timezone !== "Asia/Shanghai") fail("due.timezone is invalid");
  return result;
}
function reminder(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail("reminder is invalid");
  const commitment_id = text(value.commitment_id, "reminder.commitment_id", true, 40);
  if (!/^CMT-\d{8}-\d{3}$/.test(commitment_id)) fail("reminder.commitment_id is invalid");
  if (value.type === "absolute") {
    const at = text(value.at, "reminder.at", true, 40);
    if (!ZONED_ISO.test(at) || Number.isNaN(Date.parse(at))) fail("reminder.at is invalid");
    return { type: "absolute", at, commitment_id };
  }
  if (value.type === "relative") {
    if (Number.isInteger(value.offset_days) && value.offset_days >= 0 && value.offset_days <= 3650) return { type: "relative", offset_days: value.offset_days, time: time(value.time, true), commitment_id };
    if (Number.isInteger(value.offset_minutes) && value.offset_minutes >= 1 && value.offset_minutes <= 525600) return { type: "relative", offset_minutes: value.offset_minutes, commitment_id };
  }
  fail("reminder is invalid");
}
function item(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail("item is invalid");
  const result = {
    id: text(value.id, "id", true, 20), title: text(value.title, "title"), due: due(value.due),
    status: text(value.status, "status", true, 20), reminders: Array.isArray(value.reminders) ? value.reminders.map(reminder) : fail("reminders is invalid"),
    created_at: text(value.created_at, "created_at", true, 40), updated_at: text(value.updated_at, "updated_at", true, 40)
  };
  if (!ID.test(result.id)) fail("id is invalid");
  if (!["active", "completed"].includes(result.status)) fail("status is invalid");
  if (Number.isNaN(Date.parse(result.created_at)) || Number.isNaN(Date.parse(result.updated_at))) fail("timestamps are invalid");
  if (new Set(result.reminders.map((entry) => entry.commitment_id)).size !== result.reminders.length) fail("duplicate reminder binding");
  return result;
}
export function parseAgenda(source) {
  let parsed;
  try { parsed = JSON.parse(source); } catch { fail("agenda store is invalid JSON"); }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed) || parsed.schema_version !== 1 || !Array.isArray(parsed.items)) fail("agenda store shape is invalid");
  const items = parsed.items.map(item);
  if (new Set(items.map((entry) => entry.id)).size !== items.length) fail("duplicate item id");
  return { schema_version: 1, items };
}
export const serializeAgenda = (store) => `${JSON.stringify({ schema_version: 1, items: store.items.map(item) }, null, 2)}\n`;
function deadlineLabel(entry) { return entry.due.time ? `${entry.due.date} ${entry.due.time} (${entry.due.timezone})` : entry.due.date; }
function line(entry) { return `- [${entry.id}] ${entry.title} — ${deadlineLabel(entry)}`; }
export function renderDeadlinesView(store) {
  const active = store.items.filter((entry) => entry.status === "active");
  const deadlines = active.filter((entry) => entry.due).sort((a, b) => deadlineLabel(a).localeCompare(deadlineLabel(b)));
  const todos = active.filter((entry) => !entry.due).sort((a, b) => a.created_at.localeCompare(b.created_at));
  return [
    "<!-- Generated view. Canonical data lives in the Agenda store. Do not use this file as mutation source. -->",
    "# 我的事项",
    "",
    "## Deadlines",
    ...(deadlines.length ? deadlines.map(line) : ["- 暂无"]),
    "",
    "## Todos",
    ...(todos.length ? todos.map((entry) => `- [${entry.id}] ${entry.title}`) : ["- 暂无"]),
    ""
  ].join("\n");
}
async function assertRegular(target) {
  const stat = await fs.lstat(target).catch((error) => error.code === "ENOENT" ? null : Promise.reject(error));
  if (stat?.isSymbolicLink()) fail("agenda path must not be a symlink");
}
async function readStore() {
  await assertRegular(AGENDA_PATH);
  const source = await fs.readFile(AGENDA_PATH, "utf8").catch((error) => error.code === "ENOENT" ? '{"schema_version":1,"items":[]}' : Promise.reject(error));
  return parseAgenda(source);
}
async function atomicWrite(target, value) {
  await assertRegular(target);
  const temporary = `${target}.tmp-${process.pid}-${randomUUID()}`;
  try { await fs.writeFile(temporary, value, { encoding: "utf8", mode: 0o600 }); await fs.rename(temporary, target); }
  finally { await fs.unlink(temporary).catch(() => {}); }
}
async function persist(store) {
  const normalized = parseAgenda(serializeAgenda(store));
  await atomicWrite(AGENDA_PATH, serializeAgenda(normalized));
  await atomicWrite(DEADLINES_VIEW_PATH, renderDeadlinesView(normalized));
  return normalized;
}
async function locked(work) {
  await fs.mkdir(memoryDir, { recursive: true, mode: 0o700 });
  let handle;
  for (let attempt = 0; attempt < 80; attempt += 1) {
    try { handle = await fs.open(lockPath, "wx", 0o600); break; }
    catch (error) { if (error.code !== "EEXIST") throw error; await wait(25); }
  }
  if (!handle) fail("agenda store is busy");
  try { return await work(); }
  finally { await handle.close().catch(() => {}); await fs.unlink(lockPath).catch(() => {}); }
}
function idFor(items, now) {
  const day = now.toISOString().slice(0, 10).replaceAll("-", "");
  const highest = items.reduce((max, entry) => { const match = entry.id.match(new RegExp(`^ITM-${day}-(\\d{3})$`)); return match ? Math.max(max, Number(match[1])) : max; }, 0);
  if (highest >= 999) fail("daily item id space exhausted");
  return `ITM-${day}-${String(highest + 1).padStart(3, "0")}`;
}
const defaultDeps = { commitments: { add: addCommitment, get: getCommitment }, scheduler: { schedule: scheduleTimeCommitment, cancel: cancelTimeCommitment } };
function timestamp(now) { if (!(now instanceof Date) || Number.isNaN(now.getTime())) fail("now is invalid"); return now.toISOString(); }
function ensureItem(store, id) { const result = store.items.find((entry) => entry.id === text(id, "id", true, 20)); if (!result) fail("item not found"); return result; }
function absoluteAt(value) {
  const result = text(value, "at", true, 40);
  if (!ZONED_ISO.test(result) || Number.isNaN(Date.parse(result))) fail("at is invalid");
  if (new Date(result).getTime() <= Date.now()) fail("reminder time must be in the future");
  return result;
}
function relativeAt(itemValue, spec) {
  if (!itemValue.due) fail("relative reminder requires a deadline");
  if (Number.isInteger(spec.offset_minutes)) {
    if (!itemValue.due.time) fail("minute offset requires a deadline time");
    return new Date(Date.parse(`${itemValue.due.date}T${itemValue.due.time}:00+08:00`) - spec.offset_minutes * 60000).toISOString();
  }
  const clock = time(spec.time) ?? itemValue.due.time ?? "09:00";
  return new Date(Date.parse(`${itemValue.due.date}T${clock}:00+08:00`) - spec.offset_days * 86400000).toISOString();
}
function normalizedReminderSpec(input) {
  if (input?.type === "absolute") return { type: "absolute", at: absoluteAt(input.at) };
  if (input?.type === "relative") {
    if (Number.isInteger(input.offset_days) && input.offset_days >= 0 && input.offset_days <= 3650) return { type: "relative", offset_days: input.offset_days, time: time(input.time) };
    if (Number.isInteger(input.offset_minutes) && input.offset_minutes >= 1 && input.offset_minutes <= 525600) return { type: "relative", offset_minutes: input.offset_minutes };
  }
  fail("reminder specification is invalid");
}
function specFromReminder(entry) { return entry.type === "absolute" ? { type: "absolute", at: entry.at } : "offset_days" in entry ? { type: "relative", offset_days: entry.offset_days, time: entry.time } : { type: "relative", offset_minutes: entry.offset_minutes }; }
async function scheduleReminder(itemValue, rawSpec, dependencies = defaultDeps) {
  const spec = normalizedReminderSpec(rawSpec);
  const at = spec.type === "absolute" ? spec.at : relativeAt(itemValue, spec);
  if (new Date(at).getTime() <= Date.now()) fail("reminder time must be in the future");
  const created = await dependencies.commitments.add({
    summary: `事项提醒：${itemValue.title}`,
    trigger_type: "time",
    trigger: `agenda:${itemValue.id}:${at}`,
    next_action: `请处理事项：${itemValue.title}`,
    due_at: at
  });
  const scheduled = await dependencies.scheduler.schedule({ commitmentId: created.commitment.id });
  if (!scheduled?.commitment?.external_ref?.startsWith("openclaw-cron:")) fail("reminder scheduler binding is invalid");
  return spec.type === "absolute" ? { type: "absolute", at, commitment_id: created.commitment.id } : "offset_days" in spec ? { type: "relative", offset_days: spec.offset_days, time: spec.time ?? itemValue.due?.time ?? "09:00", commitment_id: created.commitment.id } : { type: "relative", offset_minutes: spec.offset_minutes, commitment_id: created.commitment.id };
}
async function cancelReminder(entry, dependencies = defaultDeps) {
  const commitment = await dependencies.commitments.get(entry.commitment_id);
  if (commitment?.status === "active") await dependencies.scheduler.cancel({ commitmentId: entry.commitment_id });
}
async function cancelMany(entries, dependencies) {
  const cancelled = [];
  try { for (const entry of entries) { await cancelReminder(entry, dependencies); cancelled.push(entry); } }
  catch (error) { throw new Error(`reminder cancellation failed after ${cancelled.length} cancellation(s): ${error.message}`); }
}
async function rollbackScheduled(entries, dependencies) { for (const entry of entries) await cancelReminder(entry, dependencies).catch(() => {}); }

export async function createItem(input, { now = new Date() } = {}) {
  return await locked(async () => {
    const store = await readStore(); const at = timestamp(now);
    const created = { id: idFor(store.items, now), title: text(input?.title, "title"), due: due(input?.due ?? null), status: "active", reminders: [], created_at: at, updated_at: at };
    store.items.push(created); await persist(store); return created;
  });
}
export async function getItem(id) { return (await readStore()).items.find((entry) => entry.id === text(id, "id", true, 20)) ?? null; }
export async function listItems({ kind = "all", status = "active" } = {}) {
  if (!["all", "todo", "deadline"].includes(kind) || !["all", "active", "completed"].includes(status)) fail("query is invalid");
  return (await readStore()).items.filter((entry) => (kind === "all" || (kind === "todo") === !entry.due) && (status === "all" || entry.status === status));
}
export async function updateItem(id, changes, { now = new Date(), dependencies = defaultDeps } = {}) {
  return await locked(async () => {
    const store = await readStore(); const existing = ensureItem(store, id); const hasDue = Object.hasOwn(changes ?? {}, "due");
    const candidate = { ...existing, title: Object.hasOwn(changes ?? {}, "title") ? text(changes.title, "title") : existing.title, due: hasDue ? due(changes.due) : existing.due, updated_at: timestamp(now) };
    if (!hasDue) { Object.assign(existing, candidate); await persist(store); return existing; }
    const relative = existing.reminders.filter((entry) => entry.type === "relative");
    if (!candidate.due && relative.length) fail("remove relative reminders before clearing a deadline");
    const replacements = [];
    try { for (const entry of relative) replacements.push(await scheduleReminder(candidate, specFromReminder(entry), dependencies)); }
    catch (error) { await rollbackScheduled(replacements, dependencies); throw error; }
    candidate.reminders = [...existing.reminders.filter((entry) => entry.type !== "relative"), ...replacements];
    const index = store.items.indexOf(existing); store.items[index] = candidate;
    try { await persist(store); } catch (error) { await rollbackScheduled(replacements, dependencies); throw error; }
    try { await cancelMany(relative, dependencies); }
    catch (error) { throw new Error(`agenda due updated but old reminder cleanup is incomplete: ${error.message}`); }
    return candidate;
  });
}
export async function setReminder(id, rawSpec, { dependencies = defaultDeps } = {}) {
  return await locked(async () => {
    const store = await readStore(); const existing = ensureItem(store, id); if (existing.status !== "active") fail("completed item cannot receive a reminder");
    const scheduled = await scheduleReminder(existing, rawSpec, dependencies); existing.reminders.push(scheduled);
    try { await persist(store); } catch (error) { await rollbackScheduled([scheduled], dependencies); throw error; }
    return scheduled;
  });
}
export async function removeReminder(id, commitmentId, { dependencies = defaultDeps } = {}) {
  return await locked(async () => {
    const store = await readStore(); const existing = ensureItem(store, id); const index = existing.reminders.findIndex((entry) => entry.commitment_id === text(commitmentId, "commitment_id", true, 40));
    if (index < 0) fail("reminder not found"); await cancelReminder(existing.reminders[index], dependencies); existing.reminders.splice(index, 1); await persist(store); return existing;
  });
}
export async function completeItem(id, { now = new Date(), dependencies = defaultDeps } = {}) {
  return await locked(async () => {
    const store = await readStore(); const existing = ensureItem(store, id); if (existing.status === "completed") return existing;
    await cancelMany(existing.reminders, dependencies); existing.status = "completed"; existing.reminders = []; existing.updated_at = timestamp(now); await persist(store); return existing;
  });
}
export async function deleteItem(id, { dependencies = defaultDeps } = {}) {
  return await locked(async () => {
    const store = await readStore(); const existing = ensureItem(store, id); await cancelMany(existing.reminders, dependencies); store.items.splice(store.items.indexOf(existing), 1); await persist(store); return existing;
  });
}

function options(args, allowed) {
  const result = {}; for (let index = 0; index < args.length; index += 1) { const flag = args[index]; const key = flag.startsWith("--") ? flag.slice(2).replaceAll("-", "_") : ""; if (!allowed.has(key) || key in result) fail(`unsupported option: ${flag}`); const value = args[++index]; if (value === undefined || value.startsWith("--")) fail(`missing value for ${flag}`); result[key] = value; } return result;
}
const print = (value) => process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
const cliDue = (values) => values.clear_due === "true" ? null : values.due_date ? { date: values.due_date, time: values.due_time ?? null, timezone: "Asia/Shanghai" } : undefined;
const cliReminder = (values) => values.type === "absolute" ? { type: "absolute", at: values.at } : values.offset_days ? { type: "relative", offset_days: Number(values.offset_days), time: values.time } : { type: "relative", offset_minutes: Number(values.offset_minutes) };
export async function main(argv = process.argv.slice(2)) {
  const [action, ...rest] = argv;
  if (action === "create") { const values = options(rest, new Set(["title", "due_date", "due_time"])); return print({ item: await createItem({ title: values.title, due: cliDue(values) ?? null }) }); }
  if (action === "list") { const values = options(rest, new Set(["kind", "status"])); return print({ items: await listItems(values) }); }
  if (action === "get") { if (rest.length !== 1) fail("get requires one item id"); return print({ item: await getItem(rest[0]) }); }
  if (action === "update") { const values = options(rest, new Set(["id", "title", "due_date", "due_time", "clear_due"])); const changes = {}; if (values.title !== undefined) changes.title = values.title; const value = cliDue(values); if (value !== undefined) changes.due = value; return print({ item: await updateItem(values.id, changes) }); }
  if (action === "complete") { if (rest.length !== 1) fail("complete requires one item id"); return print({ item: await completeItem(rest[0]) }); }
  if (action === "delete") { if (rest.length !== 1) fail("delete requires one item id"); return print({ item: await deleteItem(rest[0]) }); }
  if (action === "set-reminder") { const values = options(rest, new Set(["id", "type", "at", "offset_days", "offset_minutes", "time"])); return print({ reminder: await setReminder(values.id, cliReminder(values)) }); }
  if (action === "remove-reminder") { const values = options(rest, new Set(["id", "commitment_id"])); return print({ item: await removeReminder(values.id, values.commitment_id) }); }
  fail("usage: agenda.mjs <create|list|get|update|complete|delete|set-reminder|remove-reminder>");
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch((error) => { process.stderr.write(`Error: ${error.message}\n`); process.exitCode = 1; });
