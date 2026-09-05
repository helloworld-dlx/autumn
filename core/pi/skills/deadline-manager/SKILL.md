---
name: deadline-manager
version: 2.0.1
description: Canonical owner for the user's Agenda, todos and deadlines: list, create, complete, postpone, delete, and manage Agenda reminders. 用户说待办、todo、deadline、截止、完成或标记完成事项时必须使用此 Skill 和 tools/agenda.mjs，而不是 get_goal 或 general memory。
---

# Agenda / Deadline Manager

This Skill manages one Agenda. A todo has `due=null`; a deadline has a due date.

This Skill is the canonical owner of every user-owned Agenda CRUD intent. Before any general goal or memory tool, load this Skill and use `node tools/agenda.mjs`. `get_goal` is not an Agenda lookup or mutation tool.

## Safety contract

- Use only `node tools/agenda.mjs` for Agenda mutations and queries.
- Never edit `agenda.json` or `deadlines.md` directly. Do not use `echo`, `sed`, native cron commands, systemd, or `lark-cli` for Agenda work.
- `agenda.json` is canonical. `deadlines.md` is a generated read-only human view.
- A title is never mutation identity. Resolve every mutation to exactly one `ITM-YYYYMMDD-NNN`; if zero or multiple candidates match, ask instead of guessing.
- Only acknowledge a stored item after helper success. Only promise a reminder after `set-reminder` returns a verified `openclaw-cron:` binding. Only confirm reminder removal after helper success.

## Canonical helper

```bash
# Todo / deadline
node tools/agenda.mjs create --title "看看论文"
node tools/agenda.mjs create --title "比赛报名" --due-date 2026-09-20
node tools/agenda.mjs create --title "提交材料" --due-date 2026-09-20 --due-time 18:00

# Query and resolve an exact ID before mutating
node tools/agenda.mjs list --kind todo
node tools/agenda.mjs list --kind deadline
node tools/agenda.mjs get ITM-YYYYMMDD-NNN

# Update / complete / delete
node tools/agenda.mjs update --id ITM-YYYYMMDD-NNN --title "新标题"
node tools/agenda.mjs update --id ITM-YYYYMMDD-NNN --due-date 2026-10-03
node tools/agenda.mjs update --id ITM-YYYYMMDD-NNN --clear-due true
node tools/agenda.mjs complete ITM-YYYYMMDD-NNN
node tools/agenda.mjs delete ITM-YYYYMMDD-NNN
```

Complete/delete cancels associated future reminders first. On cancellation failure, report failure and do not claim the item changed.

## Reminder rules

Reminder-only requests do not enter Agenda. For “两分钟后提醒我喝水”, use the existing canonical path:

```text
Commitment → proactive_completion schedule-time → OpenClaw Cron
```

For an existing identified Agenda item:

```bash
# Absolute reminder for a todo or deadline.
node tools/agenda.mjs set-reminder --id ITM-YYYYMMDD-NNN --type absolute --at 2026-09-01T20:00:00+08:00

# Relative reminder. Date-only deadlines default to 09:00 Asia/Shanghai.
node tools/agenda.mjs set-reminder --id ITM-YYYYMMDD-NNN --type relative --offset-days 3
node tools/agenda.mjs set-reminder --id ITM-YYYYMMDD-NNN --type relative --offset-days 7 --time 09:00

# Timed deadlines may use minute offsets.
node tools/agenda.mjs set-reminder --id ITM-YYYYMMDD-NNN --type relative --offset-minutes 90
```

Each requested reminder is separate. Do not invent dynamic reminder frequency. Without an explicit request, create no reminder.

To remove a reminder while retaining the item, select its `commitment_id` from `get` and call:

```bash
node tools/agenda.mjs remove-reminder --id ITM-YYYYMMDD-NNN --commitment-id CMT-YYYYMMDD-NNN
```

Changing a due date only through `update` safely creates replacement bindings for relative reminders before writing the new due, then cancels old bindings. If cleanup is partial, say so clearly.

## Natural-language handling

- “记个待办：看看论文” → Todo only.
- “比赛 9 月 20 日截止” → Deadline only.
- “记个待办：看看论文，明晚八点提醒我” → create Todo, then absolute reminder after item write succeeds.
- “比赛 9 月 20 日截止，提前三天提醒我” → create Deadline, then relative reminder after item write succeeds.
- “前一周和前一天各提醒一次” → two relative reminders.
- “这个不用提醒” → resolve item, remove selected reminder(s), retain item.
- “这个做完了” / “把刚才那个删掉” → act only on a unique resolved ID; otherwise ask.

A deadline is not an automatic notification.

## Mirror boundary

`deadlines.md` is regenerated after successful Agenda writes. The protected existing `deadline_doc_sync` job mirrors it to the external human-readable document. Do not edit, rebuild, run, disable, or change that job.
