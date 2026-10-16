"""JEG-616 step 4 parity test: the get-values edge function produces the same
DDF blended values as the headless engine page (engine_dump.py).

The test runs the edge function's pipeline logic in Node.js (loading
value-model.js directly, no browser) and compares every player's DDF blended
value against the Playwright-driven engine dump for the same setting.

Negative-tested: a deliberately wrong bench_per_team (99 instead of 6) must
produce at least one value that differs by more than 0.1 from the correct run.

Requires: a built dist/ (make sync), Playwright chromium.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import _dist_server  # noqa: E402


# The Node.js script that runs the edge function's pipeline logic headlessly.
EDGE_RUNNER = ROOT / "tests" / "_edge_pipeline_runner.cjs"

# Test a representative subset of settings (full sweep is slow).
SETTINGS = [
    ("ppr", 12, 0),
    ("half_ppr", 10, 0),
    ("standard", 14, 0),
    ("ppr", 12, 1),  # superflex
]


def run_engine_dump(setting):
    """Run engine_dump.py for one setting via Playwright and return {pk: blended_value}."""
    from playwright.sync_api import sync_playwright

    scoring, teams, sf = setting
    with _dist_server.serve() as base, sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=_dist_server.chromium_executable(pw),
            args=["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"],
        )
        try:
            page = browser.new_page()
            page.goto(f"{base}/{_dist_server.ENGINE_URL}")
            page.wait_for_function(
                "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()",
                timeout=120000,
            )
            # Extract DDF blended values.
            result = page.evaluate(
                """([scoring, teams, sf]) => {
                    const c = window.TradeValueCurveControls;
                    c.setScoring(scoring); c.setTeams(teams); c.setRosterSpot('SUPERFLEX', sf);
                    const H = window.TradeValueCurveHarness;
                    const result = H.pipeline();
                    const values = {};
                    Object.entries(result.rows).forEach(([pk, row]) => {
                        const v = row.ddfByVersion?.blended?.value;
                        if (typeof v === 'number' && Number.isFinite(v)) values[pk] = v;
                    });
                    return values;
                }""",
                [scoring, teams, sf],
            )
            return result
        finally:
            browser.close()


def run_edge_pipeline(setting, override_bench=None):
    """Run the edge function's pipeline in Node.js and return {pk: blended_value}."""
    scoring, teams, sf = setting
    args = [
        "node", str(EDGE_RUNNER),
        "--scoring", scoring,
        "--teams", str(teams),
        "--superflex", str(sf),
        "--dist", str(ROOT / "dist"),
    ]
    if override_bench is not None:
        args += ["--bench", str(override_bench)]
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"Edge pipeline runner failed: {result.stderr}")
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def engine_results():
    """Pre-compute engine dump results for all test settings."""
    results = {}
    for setting in SETTINGS:
        results[setting] = run_engine_dump(setting)
    return results


@pytest.mark.parametrize("setting", SETTINGS, ids=[f"{s}_{t}_sf{sf}" for s, t, sf in SETTINGS])
def test_parity(setting, engine_results):
    """Edge function pipeline values must match the headless engine page exactly."""
    engine = engine_results[setting]
    edge = run_edge_pipeline(setting)

    # Both must have players.
    assert len(engine) > 50, f"Engine returned too few players: {len(engine)}"
    assert len(edge) > 50, f"Edge returned too few players: {len(edge)}"

    # Every engine player with a non-zero value must appear in edge.
    # Players with value 0 may be absent from the edge (they're below waiver
    # in all sources and the edge function drops them as no-ops).
    mismatches = []
    missing_nonzero = []
    for pk, engine_val in engine.items():
        edge_val = edge.get(str(pk))
        if edge_val is None:
            if abs(engine_val) > 0.01:
                missing_nonzero.append((pk, engine_val))
            continue
        # Allow tiny floating point difference (< 0.01).
        if abs(engine_val - edge_val) > 0.01:
            mismatches.append((pk, engine_val, edge_val))

    assert not missing_nonzero, (
        f"{len(missing_nonzero)} non-zero players in engine but not in edge:\n"
        + "\n".join(f"  pk={pk}: engine={ev}" for pk, ev in missing_nonzero[:20])
    )
    assert not mismatches, (
        f"{len(mismatches)} value mismatches (engine vs edge):\n"
        + "\n".join(f"  pk={pk}: engine={ev}, edge={edv}" for pk, ev, edv in mismatches[:20])
    )


def test_negative_wrong_bench():
    """A wrong bench_per_team must produce different values, proving the test catches bugs."""
    setting = ("ppr", 12, 0)
    correct = run_edge_pipeline(setting)
    wrong = run_edge_pipeline(setting, override_bench=99)

    # At least one player's value must differ by more than 0.1.
    any_diff = False
    for pk in correct:
        c = correct[pk]
        w = wrong.get(pk)
        if w is not None and abs(c - w) > 0.1:
            any_diff = True
            break

    assert any_diff, (
        "Wrong bench_per_team=99 did not change any values — "
        "the parity test would not catch a bench bug."
    )
