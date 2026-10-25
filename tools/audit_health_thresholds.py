#!/usr/bin/env python3
"""Derive and validate the Health check thresholds (JEG-1011) from the engine's output.

Input: the directory written by tools/audit_health_dump.py (one reduced inspection per
week x scoring x league size). The metrics come from audit-pie.js itself
(AuditPie.computeMetrics), so the thresholds are judged on the numbers the page shows.

Rule (docs/health-check-thresholds.md):
  * TRAIN weeks (default 5 6 7) x all 12 settings: take the largest healthy value of each metric.
  * threshold = 1.5 x that maximum, rounded up to a grid (1 point for spreads), but never below a
    floor for metrics that are zero by construction. A share cannot be scaled 1.5x (the largest
    filled-in share is already over 60%), so it gets +10 points of headroom on a 5-point grid.
  * HELD-OUT weeks (default 3 4): re-derive the same way; the threshold may move by at most 20%
    relative (stability rule). Also count how often each train threshold would fire on held-out data.

Usage:
  python3 tools/audit_health_thresholds.py --dump DIR [--train 5 6 7] [--held 3 4] [--out report.json]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIE_JS = ROOT / "app" / "v2" / "audit-pie.js"

HEADROOM = 1.5
SHARE_HEADROOM = 0.10
STABILITY = 0.20
# metric -> (grid, floor, accessor note). Floors are for numbers that are zero by construction.
RULES = {
    "starterSpread": (0.01, 0.0),
    "posStarterSpread": (0.01, 0.0),        # worst of RB, WR, TE (QB is informational, never flagged)
    "estShareMax": (0.05, 0.0),
    "posTotalSpreadMax": (0.01, 0.01),
    "pieDeltaMax": (0.5, 0.5),
    "reconcileProjectionDelta": (1.0, 1.0),
    "reconcileChartDelta": (1.0, 1.0),
}

EVAL = """(insp) => { const d = window.AuditPie.extract(insp); window.AuditPie.computeFlags(d); return window.AuditPie.computeMetrics(d); }"""


def value_of(metric: str, m: dict) -> float:
    if metric == "posStarterSpread":
        return max(m["posStarterSpread"][p] for p in ("RB", "WR", "TE"))
    return m[metric]


def derive(maxima: float, grid: float, floor: float, additive: bool = False) -> float:
    limit = maxima + SHARE_HEADROOM if additive else HEADROOM * maxima
    return max(floor, round(math.ceil(limit / grid - 1e-9) * grid, 6))


def collect(dump: Path, weeks: list[int]):
    from playwright.sync_api import sync_playwright
    out = []
    with sync_playwright() as pw:
        sys.path.insert(0, str(ROOT))
        from tests import _dist_server
        browser = pw.chromium.launch(executable_path=_dist_server.chromium_executable(pw))
        try:
            page = browser.new_page()
            page.goto("about:blank")
            page.add_script_tag(path=str(PIE_JS))
            for week in weeks:
                for path in sorted(dump.glob(f"w{week}_*.json")):
                    doc = json.loads(path.read_text())
                    m = page.evaluate(EVAL, doc["inspection"])
                    out.append({"week": week, "scoring": doc["scoring"], "teams": doc["teams"], "metrics": m})
        finally:
            browser.close()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump", required=True)
    ap.add_argument("--train", type=int, nargs="+", default=[5, 6, 7])
    ap.add_argument("--held", type=int, nargs="+", default=[3, 4])
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    dump = Path(args.dump)
    train = collect(dump, args.train)
    held = collect(dump, args.held)
    report = {"headroom": HEADROOM, "stability": STABILITY, "train_weeks": args.train, "held_weeks": args.held,
              "train_cases": len(train), "held_cases": len(held), "metrics": {}, "qb_reference": {}}
    ok = True
    for metric, (grid, floor) in RULES.items():
        tv = [value_of(metric, c["metrics"]) for c in train]
        hv = [value_of(metric, c["metrics"]) for c in held]
        additive = metric == "estShareMax"
        t_train = derive(max(tv), grid, floor, additive)
        t_held = derive(max(hv), grid, floor, additive)
        shift = abs(t_held - t_train) / t_train if t_train else 0.0
        # A by-construction metric sits on its floor in both sets: stable by definition.
        stable = shift <= STABILITY + 1e-9
        fires_held = sum(1 for v in hv if v > t_train)
        fires_train = sum(1 for v in tv if v > t_train)
        report["metrics"][metric] = {"train_max": max(tv), "held_max": max(hv), "threshold": t_train, "rederived_held": t_held,
                                     "relative_shift": round(shift, 4), "stable": stable,
                                     "fires_train": fires_train, "fires_held": fires_held,
                                     "train_median": sorted(tv)[len(tv) // 2]}
        ok = ok and stable and fires_held == 0
    qb = [c["metrics"]["posStarterSpread"]["QB"] for c in train + held]
    report["qb_reference"] = {"min": min(qb), "max": max(qb), "note": "informational, never flagged"}
    bench = [c["metrics"]["benchSpread"] for c in train + held]
    report["bench_reference"] = {"min": min(bench), "max": max(bench), "note": "informational, never flagged"}
    cases = {f"w{c['week']}_{c['scoring']}_{c['teams']}": c["metrics"] for c in train + held}
    report["cases"] = cases
    report["all_stable_and_quiet_on_held_out"] = ok
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).write_text(text)
    for metric, r in report["metrics"].items():
        print(f"{metric:26s} train max {r['train_max']:.4f}  T {r['threshold']:.4f}  held max {r['held_max']:.4f}  "
              f"re-derived {r['rederived_held']:.4f}  shift {r['relative_shift']:.0%}  stable={r['stable']}  "
              f"fires train/held {r['fires_train']}/{r['fires_held']}")
    print("QB starter spread (reference):", report["qb_reference"])
    print("Bench spread (reference):", report["bench_reference"])
    print("OK" if ok else "NOT OK")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
