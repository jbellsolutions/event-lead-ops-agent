#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf 'usage: %s craigslist|facebook_marketplace\n' "$0" >&2
  exit 64
fi

SOURCE="$1"
ROOT="${EVENT_LEAD_OPS_ROOT:-/home/hermes/event-lead-ops}"
case "$SOURCE" in
  craigslist)
    PROFILE="${CRAIGSLIST_PROFILE_DIR:?CRAIGSLIST_PROFILE_DIR is required}"
    ;;
  facebook|facebook_marketplace)
    SOURCE="facebook_marketplace"
    PROFILE="${FACEBOOK_PROFILE_DIR:?FACEBOOK_PROFILE_DIR is required}"
    ;;
  *)
    printf 'unsupported source: %s\n' "$SOURCE" >&2
    exit 64
    ;;
esac

cd "$ROOT"
BROWSER=("$ROOT/.venv/bin/event-lead-ops-browser" "$SOURCE" --profile "$PROFILE")
if [[ "${EVENT_LEAD_OPS_HEADLESS:-false}" == "true" ]]; then
  BROWSER+=(--headless)
fi

# Headed Linux operation requires a certified DISPLAY supplied by the host's
# VNC/noVNC/desktop service. Headless operation is a different route and must
# receive its own read-only certification.
exec "${BROWSER[@]}"
