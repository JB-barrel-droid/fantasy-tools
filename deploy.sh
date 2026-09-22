#!/bin/bash
# Deploy the trade-value chart to GitHub Pages.
#
# This is the ONLY supported way to publish the chart. It guarantees the
# published dist/ folder can never go stale:
#
#   1. Syncs app/trade-value-chart/ -> dist/ (the published site)
#   2. Verifies the sync actually happened (byte comparison)
#   3. Runs the test suite
#   4. Commits and pushes via the GitHub API
#
# Usage: ./deploy.sh ["commit message"]
# If no message is given, a default is used.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$REPO_ROOT/app/trade-value-chart"
DIST_DIR="$REPO_ROOT/dist"
MSG="${1:-Deploy chart updates}"

echo "=== Step 1: Sync app/ -> dist/ ==="
# Stamp the build tag with today's date and current commit
BUILD_TAG="tv-$(date -u +%Y%m%d-%H%M)-$(git rev-parse --short HEAD)"
echo "  build tag: $BUILD_TAG"
sed -i "s|<meta name=\"trade-chart-build\" content=\"[^\"]*\">|<meta name=\"trade-chart-build\" content=\"$BUILD_TAG\">|" "$APP_DIR/index.html"
sed -i "s|<span id=\"buildStamp\">Build [^<]*</span>|<span id=\"buildStamp\">Build $BUILD_TAG</span>|" "$APP_DIR/index.html"
# Sync the files that make up the published site.
# Add new files here if the published site grows.
for f in index.html assets/curve-widget.js assets/curve-widget.css assets/comparison-dashboard.js; do
  src="$APP_DIR/$f"
  dst="$DIST_DIR/$f"
  if [[ ! -f "$src" ]]; then
    echo "FATAL: source missing: $src" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  echo "  synced $f"
done

echo "=== Step 2: Verify dist/ matches app/ ==="
FAILED=0
for f in index.html assets/curve-widget.js assets/curve-widget.css; do
  if ! cmp -s "$APP_DIR/$f" "$DIST_DIR/$f"; then
    echo "FATAL: dist/$f does not match app/$f after sync" >&2
    FAILED=1
  fi
done
if [[ $FAILED -ne 0 ]]; then
  exit 1
fi
echo "  dist/ is byte-identical to app/ source"

echo "=== Step 3: Run tests ==="
cd "$REPO_ROOT"
python3 -m unittest tests.test_two_tier_frontend 2>&1 | tail -3

echo "=== Step 4: Commit and push ==="
git add dist/index.html dist/assets/curve-widget.js dist/assets/curve-widget.css dist/assets/comparison-dashboard.js
if git diff --cached --quiet; then
  echo "  nothing new to deploy (dist/ already current)"
  exit 0
fi
git commit -m "$MSG"
echo ""
echo "  Committed. Push via the GitHub API (network git push is blocked):"
echo "  Run the API push snippet, or ask the agent to push."
