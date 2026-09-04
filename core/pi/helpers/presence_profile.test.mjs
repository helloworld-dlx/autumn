import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { getProfile, parseProfile, setProfile } from "./presence_profile.mjs";

async function fixture(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "autumn-presence-profile-"));
  t.after(async () => await fs.rm(root, { recursive: true, force: true }));
  return path.join(root, "memory", "presence-profile.json");
}

test("missing profile has the safe unknown default", async (t) => {
  const profilePath = await fixture(t);
  assert.deepEqual(await getProfile({ profilePath }), { profile: "unknown" });
});

test("manual home and dorm selection persists only the selected profile", async (t) => {
  const profilePath = await fixture(t);
  assert.deepEqual(await setProfile("home", { profilePath }), { profile: "home" });
  assert.deepEqual(await getProfile({ profilePath }), { profile: "home" });
  assert.deepEqual(await setProfile("dorm", { profilePath }), { profile: "dorm" });
  assert.deepEqual(await getProfile({ profilePath }), { profile: "dorm" });
});

test("profile store rejects unrecognized values and extra authority-like fields", async (t) => {
  await assert.rejects(Promise.resolve().then(() => setProfile("office")), /profile is invalid/);
  assert.throws(() => parseProfile('{"profile":"home","authorization":"allow"}'), /shape is invalid/);
});

test("profile write is private and leaves no temporary file", async (t) => {
  const profilePath = await fixture(t);
  await setProfile("home", { profilePath });
  if (process.platform !== "win32") assert.equal((await fs.stat(profilePath)).mode & 0o777, 0o600);
  const entries = await fs.readdir(path.dirname(profilePath));
  assert.deepEqual(entries, ["presence-profile.json"]);
});
