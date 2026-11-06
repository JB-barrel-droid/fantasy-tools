#!/bin/bash
# JEG-621: daily Fantasy Sharks pull (60 s between requests), then save to Supabase.
# The database login is read from the macOS Keychain by the saver; nothing secret lives here.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${FANTASYSHARKS_PYTHON:-/Users/botcomp/code/fantasy-tools/.venv/bin/python}"
DAY="$(TZ=America/Chicago date +%F)"
cd "$REPO"
echo "[$(date -u +%FT%TZ)] fantasysharks daily start, vintage $DAY"
"$PY" pipelines/pull_fantasysharks.py --out-dir "data/raw/sources/fantasysharks/$DAY" --delay 60
"$PY" pipelines/save_fantasysharks_references.py --snapshot "data/raw/sources/fantasysharks/$DAY/snapshot.json"
echo "[$(date -u +%FT%TZ)] fantasysharks daily done"
