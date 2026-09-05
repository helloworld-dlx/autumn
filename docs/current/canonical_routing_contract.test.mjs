import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

test("Agenda intent has an explicit helper-first and no-memory-first contract", async () => {
  const contract = await fs.readFile(path.join(here, "AGENTS.md"), "utf8");
  assert.match(contract, /Agenda routing is a hard first-source rule/);
  assert.match(contract, /MUST first load `deadline-manager`/);
  assert.match(contract, /MUST NOT call `memory_search`, `memory_get`, or search `deadlines\.md`/);
  assert.match(contract, /`get_goal` MUST NOT query or mutate Agenda Items/);
  assert.match(contract, /zero or multiple Items.*ask the user/i);
});

test("general memory failure cannot overwrite canonical-source facts", async () => {
  const contract = await fs.readFile(path.join(here, "AGENTS.md"), "utf8");
  assert.match(contract, /Canonical data isolation/);
  assert.match(contract, /MUST NOT be used to infer that Agenda, Commitment, device presence, Home, Journal, or current file\/device state is empty or unavailable/);
});

test("production Main memory force reindex requires a stopped Gateway", async () => {
  const contract = await fs.readFile(path.join(here, "AGENTS.md"), "utf8");
  assert.match(contract, /Never run a Main memory force reindex while OpenClaw Gateway is active/);
  assert.match(contract, /stop Gateway, verify it is stopped, rebuild Main only, verify index metadata, then start Gateway/);
});
