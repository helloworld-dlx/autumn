import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";

const workspace = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const memoryDir = path.join(workspace, "memory");
export const COMMITMENTS_PATH = path.join(memoryDir, "COMMITMENTS.md");
const lockPath = path.join(memoryDir, ".COMMITMENTS.md.lock");
const HEADER = "# Commitments\n\nExplicit user follow-up commitments only. Storage alone does not create a scheduler, monitor, or notification.";
const FIELDS = ["id", "status", "created_at", "summary", "trigger_type", "trigger", "next_action", "due_at", "external_ref"];
const STATUS = new Set(["active", "completed", "cancelled"]);
const TRIGGER = new Set(["manual", "time", "condition", "job"]);
const ID = /^CMT-\d{8}-\d{3}$/;
const fail = (message) => { throw new Error(message); };
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function string(value, name, required = true) {
  if (typeof value !== "string") fail(`${name} must be a string`);
  const result = value.trim();
  if (required && !result) fail(`${name} is required`);
  if (result.length > 500) fail(`${name} exceeds 500 characters`);
  return result;
}

function record(value) {
  for (const key of FIELDS) if (!(key in value)) fail(`missing field: ${key}`);
  const normalized = {
    id: string(value.id, "id"), status: string(value.status, "status"), created_at: string(value.created_at, "created_at"),
    summary: string(value.summary, "summary"), trigger_type: string(value.trigger_type, "trigger_type"),
    trigger: string(value.trigger, "trigger"), next_action: string(value.next_action, "next_action"),
    due_at: string(value.due_at, "due_at", false), external_ref: string(value.external_ref, "external_ref", false)
  };
  if (!ID.test(normalized.id)) fail("id is invalid");
  if (!STATUS.has(normalized.status)) fail("status is invalid");
  if (!TRIGGER.has(normalized.trigger_type)) fail("trigger_type is invalid");
  if (Number.isNaN(Date.parse(normalized.created_at))) fail("created_at is invalid");
  if (normalized.due_at && Number.isNaN(Date.parse(normalized.due_at))) fail("due_at is invalid");
  return normalized;
}

export function parseCommitments(source) {
  if (typeof source !== "string") fail("commitment store must be text");
  const text = source.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  if (!text.startsWith(HEADER)) fail("commitment store header is invalid");
  const lines = text.slice(HEADER.length).trim().split("\n");
  if (lines.length === 1 && !lines[0]) return [];
  const result = [];
  for (let index = 0; index < lines.length;) {
    while (index < lines.length && !lines[index].trim()) index += 1;
    if (index === lines.length) break;
    const heading = lines[index++].match(/^## (CMT-\d{8}-\d{3})$/);
    if (!heading) fail("invalid commitment heading");
    const values = {};
    while (index < lines.length && !lines[index].startsWith("## ")) {
      const line = lines[index++];
      if (!line.trim()) continue;
      const item = line.match(/^([a-z_]+):(.*)$/);
      if (!item || !FIELDS.includes(item[1]) || item[1] in values) fail("invalid commitment field");
      values[item[1]] = item[2].trim();
    }
    const parsed = record(values);
    if (parsed.id !== heading[1] || result.some((entry) => entry.id === parsed.id)) fail("commitment id is invalid");
    result.push(parsed);
  }
  return result;
}

export function serializeCommitments(records) {
  const blocks = records.map(record).map((item) => [
    `## ${item.id}`, `id: ${item.id}`, `status: ${item.status}`, `created_at: ${item.created_at}`,
    `summary: ${item.summary}`, `trigger_type: ${item.trigger_type}`, `trigger: ${item.trigger}`,
    `next_action: ${item.next_action}`, `due_at: ${item.due_at}`, `external_ref: ${item.external_ref}`
  ].join("\n"));
  return `${HEADER}${blocks.length ? `\n\n${blocks.join("\n\n")}` : ""}\n`;
}

async function assertStore() {
  const stat = await fs.lstat(COMMITMENTS_PATH).catch((error) => error.code === "ENOENT" ? null : Promise.reject(error));
  if (stat?.isSymbolicLink()) fail("canonical commitment store must not be a symlink");
}
async function readAll() {
  await assertStore();
  const text = await fs.readFile(COMMITMENTS_PATH, "utf8").catch((error) => error.code === "ENOENT" ? HEADER : Promise.reject(error));
  return parseCommitments(text);
}
async function locked(work) {
  await fs.mkdir(memoryDir, { recursive: true });
  let handle;
  for (let attempt = 0; attempt < 80; attempt += 1) {
    try { handle = await fs.open(lockPath, "wx", 0o600); break; }
    catch (error) { if (error.code !== "EEXIST") throw error; await wait(25); }
  }
  if (!handle) fail("commitment store is busy");
  try { return await work(); }
  finally { await handle.close().catch(() => {}); await fs.unlink(lockPath).catch(() => {}); }
}
async function writeAll(records) {
  await assertStore();
  const temporary = path.join(memoryDir, `.COMMITMENTS.md.tmp-${process.pid}-${randomUUID()}`);
  try { await fs.writeFile(temporary, serializeCommitments(records), { encoding: "utf8", mode: 0o600 }); await fs.rename(temporary, COMMITMENTS_PATH); }
  finally { await fs.unlink(temporary).catch(() => {}); }
}
function key(item) { return [item.summary, item.trigger_type, item.trigger].map((value) => value.trim().replace(/\s+/g, " ").toLowerCase()).join("\u0000"); }
function idFor(records, createdAt) {
  const day = createdAt.slice(0, 10).replaceAll("-", "");
  const highest = records.reduce((max, item) => { const match = item.id.match(new RegExp(`^CMT-${day}-(\\d{3})$`)); return match ? Math.max(max, Number(match[1])) : max; }, 0);
  if (highest >= 999) fail("daily commitment id space exhausted");
  return `CMT-${day}-${String(highest + 1).padStart(3, "0")}`;
}
export async function addCommitment(input) {
  return await locked(async () => {
    const records = await readAll();
    const now = input?.now instanceof Date ? input.now : new Date();
    if (Number.isNaN(now.getTime())) fail("now is invalid");
    const candidate = record({ id: "CMT-20000101-001", status: "active", created_at: now.toISOString(), summary: input?.summary, trigger_type: input?.trigger_type, trigger: input?.trigger, next_action: input?.next_action, due_at: input?.due_at ?? "", external_ref: input?.external_ref ?? "" });
    const existing = records.find((item) => item.status === "active" && key(item) === key(candidate));
    if (existing) return { commitment: existing, duplicate: true };
    const commitment = { ...candidate, id: idFor(records, candidate.created_at) };
    records.push(commitment); await writeAll(records); return { commitment, duplicate: false };
  });
}
export async function listActiveCommitments() { return (await readAll()).filter((item) => item.status === "active"); }
export async function getCommitment(id) { if (!ID.test(string(id, "id"))) fail("id is invalid"); return (await readAll()).find((item) => item.id === id) ?? null; }
export async function findCommitmentByExternalRef(externalRef) {
  const normalized = string(externalRef, "external_ref");
  return (await readAll()).find((item) => item.external_ref === normalized) ?? null;
}
async function transition(id, status) {
  if (!ID.test(string(id, "id"))) fail("id is invalid");
  return await locked(async () => { const records = await readAll(); const item = records.find((entry) => entry.id === id); if (!item) fail("commitment not found"); if (item.status !== "active") fail("commitment is not active"); item.status = status; await writeAll(records); return item; });
}
export const completeCommitment = async (id) => await transition(id, "completed");
export const cancelCommitment = async (id) => await transition(id, "cancelled");
export async function setCommitmentExternalRef(id, externalRef) {
  if (!ID.test(string(id, "id"))) fail("id is invalid");
  const normalized = string(externalRef, "external_ref", false);
  if (normalized && !normalized.startsWith("systemd:") && !normalized.startsWith("openclaw-cron:")) fail("external_ref is not a supported scheduler binding");
  return await locked(async () => {
    const records = await readAll();
    const item = records.find((entry) => entry.id === id);
    if (!item) fail("commitment not found");
    if (item.status !== "active") fail("commitment is not active");
    item.external_ref = normalized;
    await writeAll(records);
    return item;
  });
}
function options(args, allowed) {
  const result = {}; for (let index = 0; index < args.length; index += 1) { const flag = args[index]; const name = flag.startsWith("--") ? flag.slice(2).replaceAll("-", "_") : ""; if (!allowed.has(name) || name in result) fail(`unsupported option: ${flag}`); const value = args[++index]; if (value === undefined || value.startsWith("--")) fail(`missing value for ${flag}`); result[name] = value; } return result;
}
const print = (value) => process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
export async function main(argv = process.argv.slice(2)) {
  const [action, ...rest] = argv;
  if (action === "add") return print(await addCommitment(options(rest, new Set(["summary", "trigger_type", "trigger", "next_action", "due_at", "external_ref"]))));
  if (action === "list") { if (rest.length) fail("list accepts no options"); return print({ commitments: await listActiveCommitments() }); }
  if (["get", "complete", "cancel"].includes(action)) { if (rest.length !== 1) fail(`${action} requires exactly one commitment id`); const commitment = action === "get" ? await getCommitment(rest[0]) : action === "complete" ? await completeCommitment(rest[0]) : await cancelCommitment(rest[0]); if (!commitment) fail("commitment not found"); return print({ commitment }); }
  fail("usage: commitments.mjs <add|list|get|complete|cancel>");
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch((error) => { process.stderr.write(`Error: ${error.message}\n`); process.exitCode = 1; });
