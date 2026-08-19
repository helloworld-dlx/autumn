# Autumn 3E · Home Assistant + Xiaomi Home

This is the minimum Home sidecar for Autumn V0.3. Home Assistant is the Xiaomi-device integration layer; Autumn still exposes only its own local allowlist through `autumn_home`.

## 1. Start Home Assistant Container

Keep the Home Assistant config directory outside the Autumn repository, for example:

```bash
mkdir -p ~/.local/share/autumn/home-assistant
export AUTUMN_HA_CONFIG="$HOME/.local/share/autumn/home-assistant"
export TZ="Asia/Shanghai"
docker compose -f deploy/home-assistant/compose.yaml up -d
```

Open `http://<pi-address>:8123` and complete Home Assistant onboarding.

## 2. Install the official Xiaomi Home integration

```bash
export AUTUMN_HA_CONFIG="$HOME/.local/share/autumn/home-assistant"
./deploy/home-assistant/install-xiaomi-home.sh

docker compose -f deploy/home-assistant/compose.yaml restart homeassistant
```

Then in Home Assistant: Settings → Devices & services → Add integration → `Xiaomi Home`, complete Xiaomi OAuth, and import only the Home/devices you want Home Assistant to know about.

## 3. Give Autumn only a second-layer allowlist

Create a Home Assistant long-lived access token from the Home Assistant profile, then store it outside Git:

```bash
mkdir -p ~/.config/autumn
printf '%s' '<PASTE_TOKEN_HERE>' > ~/.config/autumn/home-assistant.token
chmod 600 ~/.config/autumn/home-assistant.token
cp deploy/home-assistant/home.example.json ~/.config/autumn/home.json
chmod 600 ~/.config/autumn/home.json
```

Edit only the local `~/.config/autumn/home.json` and replace example entity IDs with the real Home Assistant entity IDs. Never commit this file or the token.

V0.3 first cut intentionally accepts only low-risk `light.*` / `switch.*` controls (`turn_on`, `turn_off`, `toggle`) plus read-only sensors/attributes. Locks, alarm/security entities and cameras are rejected by the adapter even if accidentally added to the local config.

## 4. Acceptance smoke

Use one safe actuator and one read-only sensor:

1. `autumn_home {"action":"list"}` — only aliases from Autumn's local allowlist are visible; no HA entity IDs appear.
2. `autumn_home {"action":"state","device":"room_temperature"}` — read succeeds.
3. `autumn_home {"action":"state","device":"desk_lamp"}` — initial state succeeds.
4. `autumn_home {"action":"control","device":"desk_lamp","command":"on"}` (or `off`) — control succeeds and returns a read-back state.
5. Query an unallowlisted alias such as `door_lock` — result must be `HOME_DEVICE_NOT_FOUND`, with no Home Assistant request for that device.

Do not mark Phase 3E closed yet: Huawei Buds entry and final Device Presence acceptance remain separate 3E work.
