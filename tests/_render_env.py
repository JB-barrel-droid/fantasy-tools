"""Shared setup for the headless render tests (tests/*render*.py and friends).

Two problems this fixes (2026-10-08, tests-hygiene):

1. A skipped render test is a silent pass. In CI the Python Playwright
   package was never installed, so every render test in `make validate`
   skipped on every deploy (Pages run 37761190813: disagreement_units_render
   skipped=3, main_table_engine_parity skipped=2, week_history skipped=5 ...).
   When RENDER_TESTS_REQUIRED=1 (CI sets it in the step that installs the
   browser) a missing browser or build is an error, not a skip.

2. The committed app/ and dist/ trees lag data/fixtures/current
   (GAP-APP-ASSETS-LAG), so on a fresh checkout the render tests read stale
   assets and fail until someone runs `make sync`. ensure_built() runs the
   same sync `make sync` runs, once per process, before a test reads dist/.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "pipelines" / "sync_dashboard_artifacts.py"

_built = False


def pinned_today() -> str:
    """The fixture's own date (players.json as_of), YYYY-MM-DD.

    The render tests read the committed fixture, so they must run on its day:
    on the real clock every chart reads one content week behind after the
    Tuesday flip and the prior-week badges, filters and rows change under the
    test (render suites red 2026-10-13, JEG-631 follow-up)."""
    import json
    return json.loads((ROOT / "data" / "fixtures" / "current" / "players.json").read_text())["meta"]["as_of"][:10]


def pin_today_script() -> str:
    """Init script that pins the page's calendar day (product-data.js reads
    window.TRADE_VALUE_TODAY). Pass to page.add_init_script() before goto."""
    return f"window.TRADE_VALUE_TODAY = {pinned_today()!r};"

# Hermetic browser (2026-10-08): every host but the local test server fails
# to resolve, so a test never waits on, or depends on, an external request
# (the Google Fonts fetch made networkidle waits time out intermittently).
HERMETIC_ARGS = ["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"]


def required() -> bool:
    return os.environ.get("RENDER_TESTS_REQUIRED", "").strip() not in ("", "0", "false")


def unavailable(reason: str) -> Exception:
    """The exception to raise when a render test cannot run.

    A skip locally; a hard error when RENDER_TESTS_REQUIRED is set, so a deploy
    gate never passes because its browser was missing."""
    if required():
        return RuntimeError(f"render test cannot run (RENDER_TESTS_REQUIRED=1): {reason}")
    return unittest.SkipTest(reason)


def ensure_built() -> None:
    """Build app/ and dist/ from the committed fixtures (same as `make sync`).

    Once per process. The sync is deterministic and takes about a second."""
    global _built
    if _built:
        return
    proc = subprocess.run(
        [sys.executable, str(SYNC)], cwd=str(ROOT),
        env={**os.environ, "FANTASY_TOOLS_TODAY": pinned_today()},
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"make sync equivalent failed (rc={proc.returncode}): {proc.stderr[-800:]}")
    _built = True


def chromium_executable(playwright=None):
    """First browser that exists: $CHROMIUM_PATH, Playwright's bundled
    Chromium, local Chrome, or a chromium/chrome on PATH. None lets Playwright
    use its own default."""
    candidates = []
    env = os.environ.get("CHROMIUM_PATH")
    if env:
        candidates.append(Path(env))
    if playwright is not None:
        try:
            candidates.append(Path(playwright.chromium.executable_path))
        except Exception:
            pass
    candidates.append(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _pin_clock_in_playwright() -> None:
    """Every page a render test opens reads the fixture's day.

    Wraps Browser.new_page / new_context so each page gets the pinned
    window.TRADE_VALUE_TODAY before any script runs; a test that sets its own
    day adds its script later and wins. Without it the suites go red every
    Tuesday when the real content week passes the committed fixture's week
    (JEG-675)."""
    try:
        from playwright.sync_api import Browser
    except Exception:
        return
    if getattr(Browser, "_clock_pinned", False):
        return
    new_page, new_context = Browser.new_page, Browser.new_context

    def pinned_new_page(self, *args, **kwargs):
        page = new_page(self, *args, **kwargs)
        page.add_init_script(pin_today_script())
        return page

    def pinned_new_context(self, *args, **kwargs):
        context = new_context(self, *args, **kwargs)
        context.add_init_script(pin_today_script())
        return context

    Browser.new_page, Browser.new_context, Browser._clock_pinned = pinned_new_page, pinned_new_context, True


_pin_clock_in_playwright()
