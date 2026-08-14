# Autumn Companion Conversation V1

## Scope

Companion Conversation is the stable user-facing context for future Chat and Talk. It is distinct from a short-lived Voice Runtime.

## Identity

| Conversation type | Stable identity | Gateway session key |
| --- | --- | --- |
| Main | `main` | `agent:main:companion:main` |
| Project | future stable opaque ID, for example `c_<id>` | `agent:main:companion:c_<id>` |
| Temporary | future stable opaque ID, for example `c_<id>` | `agent:main:companion:c_<id>` |

The Voice Bridge passes `companion:<id>` and its existing helper adds the sole `agent:main:` prefix. A runtime UUID may identify one microphone run, but never determines the Gateway session key.

## Rules

- Quick and Continuous Voice default to Main.
- Stop and a later Start reuse Main.
- Future Chat and Talk use the same Conversation key when they address the same Conversation.
- A label is display metadata only; rename never changes the stable ID or key.
- Gateway session metadata and `sessions.patch` are the preferred lifecycle source. No Companion database or parallel transcript store exists.

## Lifecycle boundary

Gateway supports reset, delete and compact under their existing authority paths. Pin and direct archive are not current public Companion capabilities. This contract does not perform lifecycle actions or change Feishu session routing.
