#!/usr/bin/env bash
#
# Deploy the OOLY integration to a Home Assistant instance over SSH and restart HA.
# Syncs custom_components/ooly/ -> <HA>/config/custom_components/ooly/ (only changed files, removes
# files you've deleted locally), then restarts Home Assistant so the new code loads.
#
# Requirements on the HA side:
#   - the "Advanced SSH & Web Terminal" add-on (ships rsync; `/config` maps to the HA
#     config dir; the `ha` CLI is available for the restart).
#   - SSH key auth set up so this runs without a password prompt.
#
# Usage:
#   ./scripts/deploy.sh                # sync + restart HA
#   ./scripts/deploy.sh --no-restart   # just copy files (restart yourself later)
#
# Configure via env (or edit the defaults below):
#   OOLY_HA_HOST          SSH target              (default: root@homeassistant.local)
#   OOLY_HA_PORT          SSH port                (default: 22)
#   OOLY_HA_PATH          remote custom_components (default: /config/custom_components)
#   OOLY_HA_RESTART_CMD   restart command on host (default: ha core restart)
#
# Example for a fixed IP and a non-HAOS host:
#   OOLY_HA_HOST=root@192.168.0.10 OOLY_HA_RESTART_CMD='docker restart homeassistant' \
#     ./scripts/deploy.sh

set -euo pipefail

HOST="${OOLY_HA_HOST:-root@homeassistant.local}"
PORT="${OOLY_HA_PORT:-22}"
REMOTE_CC="${OOLY_HA_PATH:-/config/custom_components}"
RESTART_CMD="${OOLY_HA_RESTART_CMD:-ha core restart}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/custom_components/ooly/"
DEST="$HOST:$REMOTE_CC/ooly/"

restart=1
for arg in "$@"; do
  case "$arg" in
    --no-restart) restart=0 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg (try --help)" >&2; exit 2 ;;
  esac
done

echo "→ ensuring remote dir exists"
ssh -p "$PORT" "$HOST" "mkdir -p '$REMOTE_CC/ooly'"

echo "→ syncing ooly/ -> $DEST  (port $PORT)"
rsync -az --delete \
  --exclude '__pycache__' --exclude '*.pyc' \
  -e "ssh -p $PORT" \
  "$SRC" "$DEST"

if [ "$restart" -eq 1 ]; then
  echo "→ restarting Home Assistant ($RESTART_CMD)"
  ssh -p "$PORT" "$HOST" "$RESTART_CMD"
  echo "✓ done — Home Assistant is restarting"
else
  echo "✓ files synced (restart skipped) — restart HA to load the changes"
fi
