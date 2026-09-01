---
name: ysyx-engineering-journal
version: 0.1.1
description: "Canonical 一生一芯 / YSYX D/C 学习日志：记录今天学习、学习进度、最近日志、两周总结、D/C 复习。命中这些组合时先 journal_context，不走 general memory。"
---

# 一生一芯工程学习日志

只处理日志、状态、最近两周总结和 D/C 复习。不要分析技术问题、不要代写事实、不要连接 VM 或执行 Git。

## Activation

以下表达（或同义组合）必须使用本 Skill，而不是 general memory：

- “记录一下一生一芯”“记录今天的一生一芯”“今天一生一芯学了……”
- “帮我记一下今天 YSYX”“一生一芯学习日志”“我今天 D1 学了……”
- “看看我一生一芯进度”“最近一生一芯学了什么”“帮我整理最近两周一生一芯”
- “帮我复习 D 阶段”“帮我复习 C 阶段”——仅在语境明确指一生一芯时。

只有“记录一下我今天的随想”或一般“复习”等不含一生一芯 / YSYX 语境的请求，不属于本 Skill。

## First-turn hard gate

对于任何“一生一芯”请求，在回答、总结、提问或引用阶段之前，必须先运行：

```bash
node tools/ysyx_journal.mjs journal_context "{}"
```

只把这个命令返回的 `state`、已有日志，以及用户**本轮明确说出**的内容当作 Journal 事实。不得把 `USER.md`、general memory、旧会话、profile、其他 Skill 或自己的推测当作学习事实；不要调用 memory 工具来补 Journal 内容。

- 若 context 调用失败：如实报告“Journal context 暂不可读取”，停止，不猜测当前阶段、历史完成项或下一阶段。
- 不得说 E/F 阶段已完成，也不得提及 E/F 阶段，除非用户本轮明确提出；本 Skill 的记录范围是 D/C。
- `state` 显示 D1 `in_progress` 只表示当前所在阶段，绝不等于今天已经学习、完成任务或通过测试。

## Fixed flow

在成功读取 context 后，若用户第一条没有覆盖全部信息，只问下面缺失的问题，不重复已回答内容：

1. 今天学了多久？主要做到哪里了？
2. 今天最值得以后记住的一个理解、发现或者坑是什么？
3. 现在还有什么没解决？下次准备做什么？

把上一条 `default_goal` 作为可编辑的“目标”；用户改写时立即以用户文字为准。只有用户已确认有价值 Bug 时，才补问缺少的现象、定位、根因、修复、验证。简单问题不强制五段式。

## Facts rule

用户提供 actual completion、understanding、problem、root cause、test PASS 与完成状态。Autumn 只能追问、去重、整理、结构化、写入、索引。

- 用户说“可能是符号扩展” → `root_cause_status="possible"`，渲染“可能原因”，不是“原因”。
- 用户没说测试通过 → 不写 PASS。
- 不知道的字段留空；不为日志完整而猜测。
- 不保存内部推理、命令记录或 VM 凭据。

确认事实后仅调用 `journal_record`。同日已有记录时，如实提示，不能静默覆盖。

只有在 `journal_record` 成功返回后，才能说“已记录”。绝不能把草稿、推测或模型回复当成已写入日志。

## Other intents

- “做到哪里了” → `journal_progress`
- “最近日志” → `journal_recent`
- “最近两周总结/组会” → `journal_summary`
- “D 阶段复习”或“C 阶段复习” → `journal_review`

Git provider 当前为 `unavailable`。即使用户事实表明稳定节点，也只说“适合 manual checkpoint”，并给出建议 message 和手动 fallback；不得声称执行、不得连接 VM。手动 fallback 可说明：`git add .` 后 `git commit --allow-empty -m "checkpoint: ..."`。
