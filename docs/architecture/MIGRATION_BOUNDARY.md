# Migration Boundary

This repository is a source and documentation baseline. It does not replace a running Pi or Windows deployment.

## TRACKED_IN_GIT

- Autumn-maintained source, tests, safe example configuration, systemd unit templates, and canonical architecture/acceptance documentation.
- The plugin `dist/index.js` files are tracked because each current plugin package declares that file as its only runtime extension entrypoint; they are retained as source snapshots, not regenerated in this baseline.

## NOT_TRACKED_SECRETS

- Real `.env` values, API keys, OAuth/Feishu tokens, OpenClaw authentication or pairing data, Tailscale credentials/state, and private recipient identifiers.

## BACKUP_ONLY_STATE

- Live backups, transfer payloads, job/audit/runtime state, logs, generated media, caches, and historical `.pre-*` snapshots.

## DEVICE_LOCAL_CONFIG

- Pi and Windows production configuration stays in its existing runtime location. The repository contains only non-sensitive examples/templates; it does not implement backup, restore, deployment, or service changes.
