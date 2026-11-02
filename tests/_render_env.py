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
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "pipelines" / "sync_dashboard_artifacts.py"

_built = False

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
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"make sync equivalent failed (rc={proc.returncode}): {proc.stderr[-800:]}")
    _built = True


def _registered_headless_shell():
    """Ask the active Python Playwright driver for its platform/revision path."""
    try:
        from playwright._impl._driver import compute_driver_executable
        node, cli = compute_driver_executable()
        registry = Path(cli).parent / "lib/server/registry/index.js"
        result = subprocess.run(
            [str(node), "-e",
             "console.log(require(process.argv[1]).registry.findExecutable('chromium-headless-shell').executablePath())",
             str(registry)], capture_output=True, text=True, check=True, timeout=10,
        )
        return Path(result.stdout.strip()) if result.stdout.strip() else None
    except (ImportError, OSError, subprocess.SubprocessError):
        return None


def chromium_executable(playwright=None):
    """Explicit override, installed headless shell, or Playwright's default.

    Never discover desktop Chrome, full Chromium, or a browser on PATH.
    The optional argument is retained for existing render harness callers.
    """
    env = os.environ.get("CHROMIUM_PATH")
    if env:
        return env
    registered = _registered_headless_shell()
    if registered is not None and registered.is_file():
        return str(registered)
    cache = Path.home() / "Library/Caches/ms-playwright"
    for candidate in sorted(cache.glob("chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell"), reverse=True):
        if candidate.is_file():
            return str(candidate)
    return None


def pin_data_week_script() -> str:
    """Init script pinning the page's clock (window.TRADE_VALUE_TODAY) to a day
    in the served data's content week, the JEG-787/JEG-791 pin. Without it,
    from the Tuesday flip until the new week's charts land, the page excludes
    every chart as not yet published (JEG-1152)."""
    import json
    from tests.test_week_history import _fixture_today
    return f"window.TRADE_VALUE_TODAY = {json.dumps(_fixture_today())};"


# JEG-1134: below 768 px the context row is one summary line; the roster, Edit league, Customize, the ⋯ menu and the
# "On the chart" line open under it. A test that uses those controls at phone width opens the row first. It does
# nothing on a wider screen, where the summary is not rendered, or when the row is already open.
OPEN_PHONE_CONTEXT_JS = """() => { const b = document.getElementById('v2ContextSummary');
  if (b && b.offsetParent && b.getAttribute('aria-expanded') !== 'true') b.click(); }"""


def open_phone_context(page) -> None:
    page.evaluate(OPEN_PHONE_CONTEXT_JS)
