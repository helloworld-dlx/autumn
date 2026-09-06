# Autumn Model Provider Migration: MiMo Token Plan

**Date:** 2026-09-06
**Status:** PASS / CLOSED

## Decision

The prior MiniMax M2.7 / M3 production baseline was migrated because the legacy 29 CNY plan expired.

The new production baseline is:

- Autumn default: MiMo Token Plan `mimo-v2.5`
- Normal subagents: MiMo Token Plan `mimo-v2.5`
- Hermes default: MiMo Token Plan `mimo-v2.5-pro`
- Explicit complex planner / high-reasoning candidate: `mimo-v2.5-pro`
- Automatic cross-provider fallback: disabled (`[]`)
- DeepSeek: manual-only
- Codex OAuth: unchanged; engineering worker only
- Voice STT/TTS provider: unchanged

MiMo is configured as an independent, clearly named OpenAI-compatible Token Plan provider. Its credential is stored through the existing local OpenClaw auth-profile mechanism and Hermes environment mechanism; no credential is present in this repository or this decision record. MiniMax remains in the production configuration only as a rollback reference and is not an automatic fallback.

## Acceptance

- OpenClaw configuration validation passed before restart.
- The existing proactive-completion regression suite passed (26 tests).
- OpenClaw and Hermes static provider gates passed: OpenAI-compatible Token Plan endpoint, MiMo model IDs, disabled automatic fallbacks, and existing retry/delegation limits preserved.
- Only `openclaw-gateway.service` and `hermes-gateway.service` were restarted. Voice Bridge and Windows Runner were not restarted.
- Autumn completed a two-turn Companion conversation in one current session, completed a read-only `memory_search` tool call followed by its second model turn, and returned a normal natural-language reply.
- Hermes consult completed through the existing guarded tool. A Hermes session preserved a test marker across turns and was explicitly ended. Hermes private memory, SOUL, and tool boundaries were not copied into Autumn or otherwise changed.
- OpenClaw, Hermes, and Voice Bridge were active after restart; OpenClaw Memory remained FTS-only and indexed.

## Rollback

On the Pi, restore the timestamped pre-migration backups created under:

- `/home/xyzlh/.openclaw/backups/model-provider-mimo-20260906T122553Z/`
- `/home/xyzlh/.hermes/backups/model-provider-mimo-20260906T122553Z/`

Restore the backed-up OpenClaw and Hermes configuration/auth files with their original owner and restrictive modes, restart only `openclaw-gateway.service` and `hermes-gateway.service`, then validate the original MiniMax route and service health. Do not restart Voice Bridge or Windows Runner for this rollback.
