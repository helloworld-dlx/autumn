# Autumn Companion Reachability V1

## Boundary

The installed Companion PWA caches only its static app shell after a successful online load: HTML, JavaScript module, manifest, and icons. It never caches health responses, API responses, transcripts, audio, session state, or credentials.

## Connectivity

`CONNECTED`, `CONNECTING`, and `DISCONNECTED` are derived only from a same-origin `GET /health` probe. Browser internet status is not evidence that Autumn is reachable. Probes occur on load, foreground/return, explicit Retry, and successful Voice API activity; there is no periodic phone heartbeat or background keepalive.

Voice refuses a disconnected turn with “Autumn is disconnected. Connect first.” Presence remains non-critical telemetry.

## On-demand handoff

Connect is an explicit user gesture that makes a fixed Android intent handoff attempt limited to the Tailscale package. Opening or connecting Tailscale is not inferred as success; only a later health probe may show `CONNECTED`.

Xiaomi 15 smoke on Android 16 / HyperOS 3.0.302.0 / Tailscale 1.98.8: the offline shell, recovery, and Quick Voice passed. The handoff result was **C**: it did not open/connect Tailscale. No helper, Tasker, background daemon, public endpoint, or VPN automation was added. The handoff remains blocked for separate recon.
