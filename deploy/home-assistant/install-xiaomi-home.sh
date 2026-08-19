#!/usr/bin/env bash
set -euo pipefail

: "${AUTUMN_HA_CONFIG:?Set AUTUMN_HA_CONFIG to the host Home Assistant config directory}"
XIAOMI_HOME_VERSION="${XIAOMI_HOME_VERSION:-v0.4.7}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git clone --filter=blob:none --depth 1 https://github.com/XiaoMi/ha_xiaomi_home.git "$WORK/ha_xiaomi_home"
cd "$WORK/ha_xiaomi_home"
if [[ "$XIAOMI_HOME_VERSION" != "main" ]]; then
  git fetch --depth 1 origin "refs/tags/${XIAOMI_HOME_VERSION}:refs/tags/${XIAOMI_HOME_VERSION}"
  git checkout --detach "$XIAOMI_HOME_VERSION"
fi
./install.sh "$AUTUMN_HA_CONFIG"

echo "Xiaomi Home integration installed into: $AUTUMN_HA_CONFIG"
echo "Restart Home Assistant, then add the Xiaomi Home integration from the Home Assistant UI."
