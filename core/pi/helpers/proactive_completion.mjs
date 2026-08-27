import { execFile } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { fileURLToPath, pathToFileURL } from "node:url";
import {
  getCommitment,
  findCommitmentByExternalRef,
  completeCommitment,
  setCommitmentExternalRef
} from "./commitments.mjs";

const execFileAsync = promisify(execFile);
const workspace = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const helperPath = path.join(workspace, "tools", "proactive_completion.mjs");
const fileSenderPath = path.join(workspace, "skills", "lark-file-sender", "send_file.sh");
export const USER_SYSTEMD_DIR = path.join(os.homedir(), ".config", "systemd", "user");
export const OPENCLAW_GATEWAY_RUNTIME = "/home/xyzlh/openclaw_workspace/node_modules/openclaw/dist/plugin-sdk/gateway-runtime.js";
export const OPENCLAW_MODEL = "minimax/MiniMax-M2.7";
export const OPENCLAW_CONFIG_PATH = "/home/xyzlh/.openclaw/openclaw.json";
export const OPENCLAW_MAIN_SESSIONS_PATH = "/home/xyzlh/.openclaw/agents/main/sessions/sessions.json";
export const TIME_OUTCOME = "Time trigger reached.";
export const OPENCLAW_REF_PREFIX = "openclaw-cron:";
export const NOTIFICATION_TOOLS = Object.freeze(["jarvis_system_status"]);
const ID = /^CMT-\d{8}-\d{3}$/;
const CRON_ID = /^[A-Za-z0-9._-]{1,160}$/;
const FEISHU_OPEN_ID = /^ou_[A-Za-z0-9]+$/;
const FEISHU_USER_TARGET = /^user:ou_[A-Za-z0-9]+$/;
const SYSTEMD_PREFIX = "systemd:";

const fail = (message) => { throw new Error(message); };
function string(value, name, required = true, max = 500) {
  if (typeof value !== "string") fail(`${name} must be a string`);
  const result = value.trim();
  if (required && !result) fail(`${name} is required`);
  if (result.length > max) fail(`${name} exceeds ${max} characters`);
  return result;
}
function commitmentId(value) {
  const result = string(value, "commitment_id");
  if (!ID.test(result)) fail("commitment_id is invalid");
  return result;
}
function cronId(value) {
  const result = string(value, "cron_id", true, 160);
  if (!CRON_ID.test(result)) fail("cron_id is invalid");
  return result;
}
function eventId(value) {
  const result = string(value, "event_id", true, 300);
  if (!result.startsWith(SYSTEMD_PREFIX)) fail("event_id is not a supported scheduler identity");
  return result;
}
function dueAt(value) {
  const parsed = new Date(string(value, "due_at"));
  if (Number.isNaN(parsed.getTime())) fail("due_at is invalid");
  return parsed;
}
function assertSchedulable(record, now) {
  if (!record) fail("commitment not found");
  if (record.status !== "active") fail("commitment is not active");
  if (record.trigger_type !== "time") fail("commitment is not a time trigger");
  if (record.external_ref) fail("commitment already has a scheduler binding");
  const when = dueAt(record.due_at);
  if (when.getTime() <= now.getTime()) fail("due_at must be in the future");
  return when;
}

// Legacy/deferred zero-token systemd path. It remains available for audit and
// compatibility but is no longer the production default for time commitments.
export function systemdBindingFor(id) {
  const stem = `autumn-proactive-completion-${commitmentId(id)}`;
  return { serviceName: `${stem}.service`, timerName: `${stem}.timer`, eventId: `${SYSTEMD_PREFIX}${stem}.timer` };
}
export function renderNotification(commitment, outcome = TIME_OUTCOME) {
  return `Autumn：你之前让我跟进的事情有结果了：\n${string(commitment?.summary, "summary")}\n\n${string(outcome, "outcome")}`;
}
export function idempotencyKey(id, event) {
  return `proactive-${createHash("sha256").update(`${commitmentId(id)}\u0000${eventId(event)}`).digest("hex").slice(0, 32)}`;
}
export async function existingPersonalRecipient() {
  const source = await fs.readFile(fileSenderPath, "utf8");
  const match = source.match(/^TARGET_USER="(ou_[A-Za-z0-9]+)"$/m);
  if (!match) fail("existing personal Feishu recipient is unavailable");
  return match[1];
}
export async function deliverWithLark({ commitment, eventId: event, outcome }) {
  const recipient = await existingPersonalRecipient();
  const key = idempotencyKey(commitment.id, event);
  await execFileAsync("/usr/bin/lark-cli", ["im", "+messages-send", "--user-id", recipient, "--text", renderNotification(commitment, outcome), "--as", "user", "--idempotency-key", key], { timeout: 30000, maxBuffer: 1048576 });
  return { idempotencyKey: key };
}
export const canonicalStore = {
  get: async (id) => await getCommitment(id),
  findByExternalRef: async (ref) => await findCommitmentByExternalRef(ref),
  complete: async (id) => await completeCommitment(id),
  setExternalRef: async (id, ref) => await setCommitmentExternalRef(id, ref)
};
export async function fireCompletion({ commitmentId: rawId, eventId: rawEvent, outcome = TIME_OUTCOME, store = canonicalStore, deliver = deliverWithLark }) {
  const id = commitmentId(rawId);
  const event = eventId(rawEvent);
  const record = await store.get(id);
  if (!record) fail("commitment not found");
  if (record.status !== "active") return { fired: false, status: record.status };
  if (record.trigger_type !== "time") fail("commitment trigger_type cannot auto-fire");
  if (record.external_ref !== event) fail("event_id does not match commitment external_ref");
  try {
    const delivery = await deliver({ commitment: record, eventId: event, outcome, idempotencyKey: idempotencyKey(id, event), text: renderNotification(record, outcome) });
    const completed = await store.complete(id);
    return { fired: true, status: completed.status, delivery };
  } catch (error) {
    return { fired: false, status: "delivery_failed", error: error instanceof Error ? error.message : String(error) };
  }
}

export function openClawCronRef(rawCronId) {
  return `${OPENCLAW_REF_PREFIX}${cronId(rawCronId)}`;
}
export function renderCronNotification(commitment) {
  return `Autumn：你之前让我跟进的事情到时间了：\n${string(commitment?.summary, "summary")}\n\n${string(commitment?.next_action, "next_action")}`;
}
export function renderCronPrompt(commitment) {
  const id = commitmentId(commitment?.id);
  return `只向用户发送下面这句话，不解释，不调用任何工具：\n\n${renderCronNotification(commitment)}\n\ncommitment_id = ${id}`;
}
function feishuTarget(value) {
  const result = string(value, "trusted_feishu_target", true, 200);
  if (!FEISHU_USER_TARGET.test(result)) fail("trusted Feishu target is invalid");
  return result;
}
export async function resolveTrustedFeishuTarget({ configPath = OPENCLAW_CONFIG_PATH, sessionsPath = OPENCLAW_MAIN_SESSIONS_PATH } = {}) {
  let config;
  let sessions;
  try {
    config = JSON.parse(await fs.readFile(configPath, "utf8"));
    sessions = JSON.parse(await fs.readFile(sessionsPath, "utf8"));
  } catch {
    fail("trusted Feishu context is unavailable");
  }
  const feishu = config?.channels?.feishu;
  if (feishu?.enabled !== true || feishu?.dmPolicy !== "allowlist" || !Array.isArray(feishu?.allowFrom)) fail("trusted Feishu channel policy is unavailable");
  const allowed = new Set(feishu.allowFrom.filter((value) => typeof value === "string" && FEISHU_OPEN_ID.test(value)));
  const direct = Object.keys(sessions ?? {}).map((key) => key.match(/^agent:main:feishu:direct:(ou_[A-Za-z0-9]+)$/)?.[1]).filter(Boolean);
  const matches = [...new Set(direct.filter((value) => allowed.has(value)))];
  if (matches.length !== 1) fail("trusted Feishu target is missing or ambiguous");
  return feishuTarget(`user:${matches[0]}`);
}
export function buildCronCreateParams(commitment, trustedTarget, now = new Date()) {
  const when = assertSchedulable(commitment, now);
  const id = commitmentId(commitment.id);
  const target = feishuTarget(trustedTarget);
  return {
    name: `autumn-proactive-completion-${id}`,
    description: `Autumn one-shot proactive notification for ${id}`,
    enabled: true,
    deleteAfterRun: true,
    agentId: "main",
    schedule: { kind: "at", at: when.toISOString() },
    sessionTarget: "isolated",
    wakeMode: "now",
    payload: {
      kind: "agentTurn",
      message: renderCronPrompt(commitment),
      model: OPENCLAW_MODEL,
      thinking: "minimal",
      timeoutSeconds: 60,
      lightContext: true,
      toolsAllow: [...NOTIFICATION_TOOLS]
    },
    delivery: {
      mode: "announce",
      channel: "feishu",
      to: target,
      accountId: "default",
      bestEffort: false
    }
  };
}

async function gatewayCall(method, params) {
  const { callGatewayFromCli } = await import(pathToFileURL(OPENCLAW_GATEWAY_RUNTIME).href);
  return await callGatewayFromCli(
    method,
    { timeout: "30000", json: true },
    params,
    { scopes: ["operator.admin"], clientName: "gateway-client", mode: "backend", progress: false }
  );
}
export const canonicalCronScheduler = {
  create: async (params) => await gatewayCall("cron.add", params),
  remove: async (id) => await gatewayCall("cron.remove", { id })
};
function createdCronId(result) {
  return cronId(result?.id ?? result?.job?.id);
}
export async function scheduleTimeCommitment({ commitmentId: rawId, store = canonicalStore, scheduler = canonicalCronScheduler, resolveTarget = resolveTrustedFeishuTarget, now = new Date() }) {
  const id = commitmentId(rawId);
  const record = await store.get(id);
  assertSchedulable(record, now);
  const target = await resolveTarget();
  const params = buildCronCreateParams(record, target, now);
  const created = await scheduler.create(params);
  const jobId = createdCronId(created);
  const externalRef = openClawCronRef(jobId);
  try {
    const bound = await store.setExternalRef(id, externalRef);
    return { commitment: bound, cron: { id: jobId, externalRef }, params };
  } catch (error) {
    await scheduler.remove(jobId).catch(() => {});
    throw error;
  }
}

export async function finalizeCronCompletion({ cronId: rawCronId, runStatus, deliveryStatus, delivered, store = canonicalStore }) {
  const jobId = cronId(rawCronId);
  const externalRef = openClawCronRef(jobId);
  const record = await store.findByExternalRef(externalRef);
  if (!record) return { matched: false, completed: false, reason: "unbound" };
  if (record.status !== "active") return { matched: true, completed: false, status: record.status, reason: "not-active" };
  if (record.trigger_type !== "time") fail("bound commitment is not a time trigger");
  if (runStatus !== "ok" || deliveryStatus !== "delivered" || delivered !== true) {
    return { matched: true, completed: false, status: "active", reason: "delivery-not-confirmed" };
  }
  const completed = await store.complete(record.id);
  return { matched: true, completed: true, status: completed.status, commitmentId: completed.id };
}

// Legacy systemd implementation retained as an explicit deferred adapter.
function calendarUtc(value) {
  return value.toISOString().replace("T", " ").replace(/\.\d{3}Z$/, " UTC");
}
function serviceText(id, event) {
  return ["[Unit]", `Description=Autumn proactive completion for ${id}`, "", "[Service]", "Type=oneshot", `ExecStart=/usr/bin/node ${helperPath} fire --commitment-id ${id} --event-id ${event}`, ""].join("\n");
}
function timerText(binding, value) {
  return ["[Unit]", `Description=Autumn proactive completion timer for ${binding.timerName}`, "", "[Timer]", `OnCalendar=${calendarUtc(value)}`, "Persistent=true", `Unit=${binding.serviceName}`, "", "[Install]", "WantedBy=timers.target", ""].join("\n");
}
async function atomicWrite(file, value) {
  const temp = `${file}.tmp-${process.pid}-${randomUUID()}`;
  try { await fs.writeFile(temp, value, { encoding: "utf8", mode: 0o600 }); await fs.rename(temp, file); }
  finally { await fs.unlink(temp).catch(() => {}); }
}
async function systemctlDefault(args) {
  await execFileAsync("systemctl", ["--user", ...args], { timeout: 30000, maxBuffer: 1048576 });
}
export async function bindTimeCommitmentSystemd({ commitmentId: rawId, store = canonicalStore, systemdDir = USER_SYSTEMD_DIR, systemctl = systemctlDefault, now = new Date() }) {
  const id = commitmentId(rawId);
  const record = await store.get(id);
  const when = assertSchedulable(record, now);
  const binding = systemdBindingFor(id);
  const servicePath = path.join(systemdDir, binding.serviceName);
  const timerPath = path.join(systemdDir, binding.timerName);
  await fs.mkdir(systemdDir, { recursive: true, mode: 0o700 });
  await atomicWrite(servicePath, serviceText(id, binding.eventId));
  await atomicWrite(timerPath, timerText(binding, when));
  try {
    await systemctl(["daemon-reload"]);
    await store.setExternalRef(id, binding.eventId);
    await systemctl(["enable", "--now", binding.timerName]);
    return { binding, dueAt: when.toISOString() };
  } catch (error) {
    await store.setExternalRef(id, "").catch(() => {});
    await systemctl(["disable", "--now", binding.timerName]).catch(() => {});
    await fs.unlink(servicePath).catch(() => {});
    await fs.unlink(timerPath).catch(() => {});
    await systemctl(["daemon-reload"]).catch(() => {});
    throw error;
  }
}
export const bindTimeCommitment = bindTimeCommitmentSystemd;

function options(args, allowed) {
  const result = {};
  for (let index = 0; index < args.length; index += 1) {
    const flag = args[index], key = flag.startsWith("--") ? flag.slice(2).replaceAll("-", "_") : "";
    if (!allowed.has(key) || key in result) fail(`unsupported option: ${flag}`);
    const value = args[++index];
    if (value === undefined || value.startsWith("--")) fail(`missing value for ${flag}`);
    result[key] = value;
  }
  return result;
}
const print = (value) => process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
export async function main(argv = process.argv.slice(2)) {
  const [action, ...rest] = argv;
  if (action === "fire") {
    const values = options(rest, new Set(["commitment_id", "event_id", "outcome"]));
    const result = await fireCompletion({ commitmentId: values.commitment_id, eventId: values.event_id, outcome: values.outcome ?? TIME_OUTCOME });
    if (result.status === "delivery_failed") fail(`delivery failed: ${result.error}`);
    return print(result);
  }
  if (action === "schedule-time") {
    if (rest.length !== 1) fail("schedule-time requires exactly one commitment id");
    return print(await scheduleTimeCommitment({ commitmentId: rest[0] }));
  }
  if (action === "schedule-systemd") {
    if (rest.length !== 1) fail("schedule-systemd requires exactly one commitment id");
    return print(await bindTimeCommitmentSystemd({ commitmentId: rest[0] }));
  }
  fail("usage: proactive_completion.mjs <schedule-time|schedule-systemd|fire>");
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch((error) => { process.stderr.write(`Error: ${error.message}\n`); process.exitCode = 1; });
