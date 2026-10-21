#!/usr/bin/env bash
# Health check for the self-hosted data store (JEG-792).
#
#   ./healthcheck.sh                     check http://127.0.0.1:$GATEWAY_PORT
#   SUPABASE_URL=https://db.example.com ./healthcheck.sh   check through the tunnel
#
# Uses SUPABASE_SERVICE_KEY if set, else SERVICE_ROLE_KEY from ./.env.
# Checks:
#   1. GET /rest/v1/ with the service key -> 200 (PostgREST up, JWT accepted)
#   2. GET /rest/v1/players?select=player_key&limit=3 -> 200 with rows
#   3. GET /rest/v1/ with no key -> 401 (gateway refuses unknown callers)
#   4. if the relay runs: POST /functions/v1/usatoday-fetch with the ANON key
#      -> 401/403 (GAP-USAT-RELAY-ANON)
# Exits non-zero on the first failed check. Keys are passed to curl via
# stdin config, never on the command line.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
env_get() { [ -f "$HERE/.env" ] && awk -v k="$1" 'index($0, k "=") == 1 { print substr($0, length(k) + 2); exit }' "$HERE/.env"; }

PORT="$(env_get GATEWAY_PORT || true)"
URL="${SUPABASE_URL:-http://127.0.0.1:${PORT:-8000}}"
URL="${URL%/}"
KEY="${SUPABASE_SERVICE_KEY:-$(env_get SERVICE_ROLE_KEY || true)}"
ANON="$(env_get ANON_KEY || true)"
[ -n "$KEY" ] || { echo "health: no service key (set SUPABASE_SERVICE_KEY or create .env)" >&2; exit 2; }

# curl reading headers from a config on stdin keeps keys out of `ps`.
call() { # key method path [body]
  local key="$1" method="$2" path="$3" body="${4:-}"
  {
    if [ -n "$key" ]; then
      printf 'header = "apikey: %s"\nheader = "Authorization: Bearer %s"\n' "$key" "$key"
    fi
    printf 'header = "Content-Type: application/json"\n'
    if [ -n "$body" ]; then printf 'data = "%s"\n' "${body//\"/\\\"}"; fi
  } | curl -sS -m 20 -o "$TMP" -w '%{http_code}' -X "$method" -K - "$URL$path" || echo 000
}

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
fail() { echo "health: FAIL $*" >&2; exit 1; }

code="$(call "$KEY" GET /rest/v1/)"
[ "$code" = 200 ] || fail "GET /rest/v1/ with service key -> HTTP $code $(head -c 300 "$TMP")"
echo "health: ok   /rest/v1/ (service key) -> 200"

code="$(call "$KEY" GET '/rest/v1/players?select=player_key&limit=3')"
[ "$code" = 200 ] || fail "GET players -> HTTP $code $(head -c 300 "$TMP")"
rows="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$TMP" 2>/dev/null || echo "?")"
[ "$rows" != 0 ] && [ "$rows" != "?" ] || fail "players returned $rows rows (empty database? import not done?)"
echo "health: ok   players -> $rows rows"

code="$(call "" GET /rest/v1/)"
[ "$code" = 401 ] || fail "GET /rest/v1/ with no key -> HTTP $code (want 401)"
echo "health: ok   /rest/v1/ (no key) -> 401"

if [ -n "$ANON" ]; then
  code="$(call "$ANON" POST /functions/v1/usatoday-fetch '{"url":"https://www.usatoday.com/web-sitemap-index.xml"}')"
  case "$code" in
    401|403) echo "health: ok   usatoday-fetch refuses the anon key -> $code" ;;
    502)     echo "health: skip usatoday-fetch (relay profile not running)" ;;
    *)       fail "usatoday-fetch with ANON key -> HTTP $code (want 401/403)" ;;
  esac
fi
echo "health: all checks passed for $URL"
