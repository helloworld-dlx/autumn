import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const contract = await fs.readFile(path.join(here, "AGENTS.md"), "utf8");

test("Presence Fusion contract covers conservative candidate selection", () => {
  for (const required of [
    "USER INTENT → EXPLICIT TARGET → CURRENT RELEVANT CONTEXT → PRESENCE → EXISTING AUTHORIZATION → EXISTING TOOL",
    "普通聊天、知识问答和不需要设备的任务不查询 `autumn_nodes`、`autumn_home` 或 Eyes",
    "目标 `OFFLINE` 或 `UNKNOWN` 时如实说明不可确认/不可用，**不得 silent fallback**",
    "没有明确目标的“帮我看看这个”仅在已有相关 Eyes context 时继续；否则请用户选择/打开 Eyes source，绝不自动打开 camera",
    "Home 不相关的请求不得读取 Home；Home 环境问题才按需读已授权状态",
    "`UNKNOWN` 既不是 ONLINE 也不是 OFFLINE，不能假设成功或失败",
    "不得以在线状态绕过它们",
    "Fusion 不得自动开启摄像头、恢复 Privacy Kill、后台 capture 或 ambient sensing"
  ]) assert.match(contract, new RegExp(required.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
});

test("Presence Fusion contract preserves authority and the shared Main policy", () => {
  for (const required of [
    "`PRESENCE != AUTHORIZATION`、`CAPABILITY != AUTHORIZATION`、`ONLINE != AUTHORIZED`、`HA_VISIBLE != AUTUMN_AUTHORIZED`",
    "Profile 不改变 Autumn identity、SOUL、Memory、model、Home allowlist、Worker authority、Windows C:/D: boundary、Scout、Hermes、Codex 或 Reminder authorization",
    "Talk 与 Chat 都遵循本节同一顺序；不建立 voice router 或 voice-only state machine",
    "Spatial/Activity 只展示真实 tool trace，不能反向成为 Main 的事实来源"
  ]) assert.match(contract, new RegExp(required.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
});
