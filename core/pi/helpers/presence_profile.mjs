import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";

export const PROFILE_VALUES = Object.freeze(["home", "dorm", "unknown"]);
const allowed = new Set(PROFILE_VALUES);
const workspace = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const PROFILE_PATH = path.join(workspace, "memory", "presence-profile.json");

function fail(message) { throw new Error(message); }

export function normalizeProfile(value) {
  if (typeof value !== "string" || !allowed.has(value)) fail("profile is invalid");
  return value;
}

export function parseProfile(source) {
  let parsed;
  try { parsed = JSON.parse(source); } catch { fail("profile store is invalid JSON"); }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed) || Object.keys(parsed).length !== 1) fail("profile store shape is invalid");
  return { profile: normalizeProfile(parsed.profile) };
}

export const serializeProfile = (store) => `${JSON.stringify({ profile: normalizeProfile(store?.profile) }, null, 2)}\n`;

async function assertRegular(target) {
  const stat = await fs.lstat(target).catch((error) => error.code === "ENOENT" ? null : Promise.reject(error));
  if (stat?.isSymbolicLink()) fail("profile path must not be a symlink");
}

export async function getProfile({ profilePath = PROFILE_PATH } = {}) {
  await assertRegular(profilePath);
  const source = await fs.readFile(profilePath, "utf8").catch((error) => error.code === "ENOENT" ? null : Promise.reject(error));
  return source === null ? { profile: "unknown" } : parseProfile(source);
}

export async function setProfile(profile, { profilePath = PROFILE_PATH } = {}) {
  const normalized = { profile: normalizeProfile(profile) };
  await fs.mkdir(path.dirname(profilePath), { recursive: true, mode: 0o700 });
  await assertRegular(profilePath);
  const temporary = `${profilePath}.tmp-${process.pid}-${randomUUID()}`;
  try {
    await fs.writeFile(temporary, serializeProfile(normalized), { encoding: "utf8", mode: 0o600 });
    await fs.rename(temporary, profilePath);
  } finally {
    await fs.unlink(temporary).catch(() => {});
  }
  return normalized;
}

function options(args) {
  if (args.length !== 2 || args[0] !== "--profile") fail("usage: set --profile <home|dorm>");
  return args[1];
}

export async function main(argv = process.argv.slice(2)) {
  const [action, ...rest] = argv;
  if (action === "get" && rest.length === 0) return getProfile();
  if (action === "set") return setProfile(options(rest));
  fail("usage: get | set --profile <home|dorm>");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().then((result) => process.stdout.write(`${JSON.stringify(result)}\n`)).catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
