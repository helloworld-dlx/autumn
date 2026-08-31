import { randomUUID } from "node:crypto";

const fail = (code) => ({ ok: false, code, executed: false });
const message = (value) => typeof value === "string" && value.length >= 12 && value.length <= 180 && value.startsWith("checkpoint: ") && !/[\0\r\n]/.test(value);
const pathValue = (value) => typeof value === "string" && value.length > 0 && value.length <= 240 && !/[\0\\]/.test(value) && !value.startsWith("/") && !value.includes("..") && !value.split("/").includes(".git");
export function validateCheckpointPreview(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).some((key) => !["mode", "message", "paths", "tree_fingerprint"].includes(key))) return fail("REQUEST_INVALID");
  if (!message(value.message) || typeof value.tree_fingerprint !== "string" || !value.tree_fingerprint) return fail("REQUEST_INVALID");
  if (value.mode === "mark_current_state" && (!Array.isArray(value.paths) || value.paths.length !== 0)) return fail("REQUEST_INVALID");
  if (value.mode === "commit_changes" && (!Array.isArray(value.paths) || value.paths.length < 1 || value.paths.length > 50 || !value.paths.every(pathValue))) return fail("REQUEST_INVALID");
  if (!["mark_current_state", "commit_changes"].includes(value.mode)) return fail("REQUEST_INVALID");
  return { ok: true, preview: { ...value, confirmation_id: randomUUID(), expires_at: Date.now() + 120000, consumed: false } };
}
export function confirmCheckpoint(preview, confirmation, { now = Date.now() } = {}) {
  if (!preview || !confirmation?.confirmation_id) return fail("CONFIRMATION_REQUIRED");
  if (preview.consumed || now > preview.expires_at) return fail("CONFIRMATION_EXPIRED");
  if (confirmation.confirmation_id !== preview.confirmation_id) return fail("CONFIRMATION_MISMATCH");
  if (confirmation.mode !== preview.mode || confirmation.message !== preview.message || JSON.stringify(confirmation.paths ?? []) !== JSON.stringify(preview.paths) || confirmation.tree_fingerprint !== preview.tree_fingerprint) return fail("CONFIRMATION_MISMATCH");
  preview.consumed = true;
  return { ok: false, code: "PROVIDER_UNAVAILABLE", executed: false, mode: preview.mode, operations: preview.mode === "mark_current_state" ? [{ argv: ["git", "commit", "--allow-empty", "-m", preview.message] }] : [{ argv: ["git", "add", "--", ...preview.paths] }, { argv: ["git", "commit", "-m", preview.message] }] };
}
export function unavailableGitProvider() { return Object.freeze({ status: "unavailable", async status() { return { status: "unavailable" }; }, async recent() { return { status: "unavailable" }; }, preview: validateCheckpointPreview, confirm: confirmCheckpoint }); }
