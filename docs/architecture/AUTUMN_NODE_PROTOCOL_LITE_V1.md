# Autumn Node Protocol Lite V1

**Status:** Phase 3A-1 contract only.  No Node runtime or production behaviour is introduced by this document.

## 1. Purpose

Node Protocol Lite is the small, transport-independent language for describing an Autumn production device: its stable identity, kind, version, observed presence and technically available capabilities.  It does not replace Pi Core, Pi Bridge, Windows Runner, Voice Bridge or their existing protocols.

## 2. Non-goals

- No generic RPC framework, message bus, MQTT, gRPC, new public port or new transport.
- No authority, authorization, job execution, discovery, enrollment or heartbeat implementation.
- No Pi4, Xiaomi Home, earbuds, room camera, Eyes API or future realtime-voice capability.
- No migration or refactor of frozen V0.2 Core, Runner, Bridge or Voice code.

## 3. Node descriptor

Descriptors are JSON-serializable and contain neither secrets, private conversation/session data nor runtime dumps.

```json
{
  "protocol_version": "1",
  "node_id": "pi5-core",
  "node_type": "core",
  "node_version": "v0.2-frozen",
  "online": "ONLINE",
  "last_seen": "2026-08-14T00:00:00Z",
  "capabilities": ["agent.main", "gateway", "bridge.forward"],
  "metadata": {}
}
```

`last_seen` is an RFC 3339 UTC observation time, or `null` when unavailable. `online` is one of `ONLINE`, `OFFLINE`, `RECENT`, or `UNKNOWN`; reliable service/health sources use the first two, while a browser companion may use `RECENT` or `UNKNOWN`.

## 4. Stable node identities

| Node ID | Type | Canonical identity |
| --- | --- | --- |
| `pi5-core` | `core` | Raspberry Pi 5 Autumn Core |
| `windows-main` | `windows` | main Windows laptop / Runner |
| `xiaomi15` | `phone` | Xiaomi 15 Companion / Voice PWA |

These IDs are human-readable and stable across reboot. Hardware replacement is a future re-enrollment/mapping decision, not a per-boot UUID change.

## 5. Capability naming and current matrix

Capability names are lower-case, dot-separated technical declarations. They describe an existing surface, not a promise that every call succeeds or is authorized.

| Node | Active capabilities | Evidence / current interface |
| --- | --- | --- |
| `pi5-core` | `agent.main`, `gateway`, `bridge.forward` | OpenClaw `agent:main`; `openclaw-gateway.service`; `jarvis-bridge.service` forwards existing legacy, Job, authorization and Worker-control routes. Live 2026-08-14: all active. Pi Bridge health is `GET 127.0.0.1:27901/v1/health`. |
| `windows-main` | `system.status`, `file.search`, `file.return`, `job.submit`, `job.status`, `job.cancel`, `codex.submit` | Existing signed Runner endpoints and Pi Bridge routes. Everything ES is a fixed-argv D: filename/path metadata backend; `/v1/file` is the controlled file-export surface. Live Runner `GET /v1/health` returned 200. |
| `xiaomi15` | `voice.listen`, `voice.speak`, `open_url`, `clipboard.set` | Existing Voice PWA provides microphone capture/STT submission, response playback/TTS, HTTP(S) links, and explicit reply copy. Quick Voice and Continuous Voice are existing modes, not additional protocol capabilities. |

`camera.capture` is **not active**: Xiaomi camera has not entered an Autumn unified interface. No capability is asserted merely because a source file or a planned V0.3 specification exists.

## 6. Authority relationship

**CAPABILITY != AUTHORIZATION.** A descriptor only says that a Node has a technical, already-existing surface. The Core continues to use the frozen authority and authorization path for every operation.

For Windows specifically: raw arbitrary shell, arbitrary `cmd.exe`/`powershell.exe` shell use and `shell=True` remain denied; Python/Node are structured catalog L3 and remain `AUTHORIZATION_REQUIRED`; delete and L5 remain hard-deny; `C:\` remains outside approved Windows file authority and the D: boundary remains. Node Protocol Lite changes none of this.

## 7. Online semantics (design only)

- Pi: `ONLINE` when the Core/service health source is current; otherwise `OFFLINE`.
- Windows: `ONLINE` when Runner heartbeat or `GET /v1/health` is current; otherwise `OFFLINE`.
- Phone: use `RECENT` only after recent PWA/Voice Bridge activity; use `UNKNOWN` when no reliable current observation exists. Do not infer a persistent connection.

Suggested initial TTLs for a later implementation: Pi/Windows 90 seconds after a successful health observation; Phone 10 minutes after a PWA/Bridge activity observation. Expiry changes state only; it must not start a new presence framework.

## 8. Existing transport mapping

| Path | Existing transport retained |
| --- | --- |
| Pi Core ↔ Windows Runner | Pi Bridge → Tailscale → Runner (`100.84.13.42:27891`) |
| Xiaomi 15 ↔ Autumn | existing Voice PWA / Voice Bridge with Tailscale Serve |

The Pi Bridge remains loopback on `127.0.0.1:27901`; Voice Bridge remains loopback on `127.0.0.1:18791`. No public port, MQTT, gRPC or new message bus is part of V1.

Phase 3A-2 adds read-only loopback Pi Bridge queries: `GET /v1/nodes` and `GET /v1/nodes/{node_id}`. They expose only bounded safe descriptors; registration remains internal.

Phase 3A-3 adds a Pi-side, read-only `GET /v1/health` probe to the existing Runner transport every 30 seconds. A valid health response registers or touches `windows-main`; a failed probe is quiet and lets the 90-second Registry TTL derive `OFFLINE`.

## 9. Phase 3A implementation boundary

- **3A-2 — Pi Node Registry Core:** store and expose this descriptor shape only.
- **3A-3 — Windows Node Adapter:** adapt existing Runner health and declared capabilities; do not alter Runner security or Job protocol.
- **3A-4 — Xiaomi 15 Node Adapter:** adapt existing Companion/PWA observations only.
- **3A-5 — Autumn integration + real acceptance:** integrate the adapters and run real acceptance.

No item above is started by Phase 3A-1.

## 10. Deferred capabilities

Pi4, Xiaomi Home, earbuds, room camera, `camera.capture`, Eyes APIs and future realtime voice are FUTURE / NOT_ACTIVE. They require a later explicit contract and acceptance before appearing in an active capability list.
