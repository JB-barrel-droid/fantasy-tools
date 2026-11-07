#!/usr/bin/env python3
"""Verify the live GitHub Pages deployment matches the expected repo state.

Usage: python3 verify_live.py [expected_build_tag]
Fetches the live site and checks:
  1. HTTP 200
  2. Build tag in HTML matches expected (or reports what it found)
  3. Key fix markers present in HTML/JS
Exit 0 = live matches expected. Exit 1 = mismatch or fetch failure.
"""
import re
import sys
import urllib.request
from pipelines.lib.repository import SITE_URL as BASE


# Markers that must be present in the deployed files for the current fix set.
# JEG-1539 step 5: dist/index.html is now the redesigned front door, not the v2 shell.
HTML_MARKERS = [
    ('src="legacy-routes.js', "legacy-routes.js loaded first in index.html"),
    ('src="site.js', "site.js in index.html"),
]
JS_MARKERS = {
    "assets/curve-widget.js": [
        ("activeKeysForGuard", "paused/empty sources skipped by the peak guard"),
        ("peaksAboveCollapseFloor", "collapse guard (replaced the hardcoded >70 that blanked the chart)"),
        ("quadraticCurveTo", "curve smoothing"),
    ],
    "assets/comparison-dashboard.js": [
        ("function sourceFreshness", "source freshness labels"),
        ("function loadComparisonData", "comparison data loader"),
    ],
}


def fetch(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8", errors="replace")


def main(argv=None, fetch_fn=None):
    """fetch_fn(path) -> (status, text) is injectable so tests can point at dist/."""
    global fetch
    argv = sys.argv[1:] if argv is None else argv
    if fetch_fn is not None:
        fetch = fetch_fn
    expected = argv[0] if argv else None
    ok = True

    try:
        status, html = fetch("")
    except Exception as e:
        print(f"FAIL: could not fetch live page: {e}")
        return 1
    print(f"HTTP {status}, {len(html)} bytes")
    if status != 200:
        print("FAIL: non-200 status")
        return 1

    m = re.search(r'trade-chart-build" content="([^"]+)"', html)
    live_tag = m.group(1) if m else None
    print(f"Live build tag: {live_tag}")
    if expected:
        if live_tag == expected:
            print(f"PASS: build tag matches expected {expected}")
        else:
            print(f"FAIL: expected {expected}, live has {live_tag}")
            ok = False
    elif not live_tag:
        print("FAIL: no build tag found in live HTML")
        ok = False

    for marker, desc in HTML_MARKERS:
        if marker in html:
            print(f"PASS: {desc}")
        else:
            print(f"FAIL: missing {desc}")
            ok = False

    for js_path, markers in JS_MARKERS.items():
        try:
            _, js = fetch(js_path)
        except Exception as e:
            print(f"FAIL: could not fetch {js_path}: {e}")
            ok = False
            continue
        for marker, desc in markers:
            if marker in js:
                print(f"PASS: {desc} ({js_path})")
            else:
                print(f"FAIL: missing {desc} ({js_path})")
                ok = False

    print("RESULT: LIVE OK" if ok else "RESULT: LIVE MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
