#!/usr/bin/env python3
"""JEG-859: why bench totals differ across sources while starters agree.

Loads the built engine page headless, reads getInspection() at one league
setting, and sums each source's Adjusted values per position two ways:

  role cut   the Health check tab's cut (app/v2/audit-pie.js): a player's whole
             Adjusted value goes to "bench" when the source ranks him between
             the starter line and the rostered line (value-model.js `role`).
  slice cut  the engine's own budget cut: rate[pos|bench] x benchSlice and
             rate[pos|starter] x starterSlice (value-model.js VP-5), so every
             player contributes to both parts.

The slice cut is fixed by the shared group budgets (pie x W[g]), so it matches
across every source with weights; the script exits 1 if it does not. The role
cut is not budgeted, so it shows how each source spreads its value between its
top S and its next N - S players.

Usage (build first: `make sync`, or any render test):
  python3 tools/research/bench_spread_by_cut.py [--scoring ppr] [--teams 12]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests import _dist_server  # noqa: E402

POSITIONS = ("QB", "RB", "WR", "TE")

READ = """([scoring, teams]) => {
  const C = window.TradeValueCurveControls;
  C.setScoring(scoring); C.setTeams(teams);
  const ins = C.getInspection(), vp = ins.valuePipeline;
  const out = {pie: vp.pie, method: vp.method, sources: {}};
  for (const [src, ps] of Object.entries(ins.players)) {
    const rates = (vp.sources[src] || {}).rates || {};
    const s = {rates, players: []};
    for (const p of Object.values(ps)) {
      s.players.push({pos: p.pos, role: p.role, adjusted: p.adjusted || 0,
        benchPart: (rates[p.pos + '|bench'] || 0) * (p.benchSlice || 0),
        starterPart: (rates[p.pos + '|starter'] || 0) * (p.starterSlice || 0)});
    }
    out.sources[src] = s;
  }
  return out;
}"""


def spread(values):
    """Same definition as audit-pie.js spread(): (max - min) / median."""
    vals = sorted(v for v in values)
    if len(vals) < 2:
        return 0.0
    n = len(vals)
    med = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    return (vals[-1] - vals[0]) / abs(med) if med else 0.0


def summarize(doc):
    table = {}
    for src, s in doc["sources"].items():
        t = {}
        for pos in POSITIONS:
            rows = [p for p in s["players"] if p["pos"] == pos]
            t[pos] = {
                "role_starter": sum(p["adjusted"] for p in rows if p["role"] == "starter"),
                "role_bench": sum(p["adjusted"] for p in rows if p["role"] == "bench"),
                "slice_starter": sum(p["starterPart"] for p in rows),
                "slice_bench": sum(p["benchPart"] for p in rows),
            }
        table[src] = t
    return table


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scoring", default="ppr")
    parser.add_argument("--teams", type=int, default=12)
    args = parser.parse_args(argv)
    from playwright.sync_api import sync_playwright
    with _dist_server.serve() as base, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=_dist_server.chromium_executable(pw),
                                     args=["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"])
        try:
            page = browser.new_page()
            page.goto(f"{base}/{_dist_server.ENGINE_URL}")
            page.wait_for_function("() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()", timeout=120000)
            doc = page.evaluate(READ, [args.scoring, args.teams])
        finally:
            browser.close()

    table = summarize(doc)
    srcs = [s for s in table if any(table[s][p]["slice_bench"] or table[s][p]["slice_starter"] for p in POSITIONS)]
    print(f"pie {doc['pie']}  method {doc['method']}  {args.scoring} {args.teams}-team  sources {', '.join(srcs)}")
    bad = []
    for cut in ("role", "slice"):
        print(f"\n{cut} cut (sum of Adjusted)")
        print("pos  part     " + "".join(f"{s[:10]:>11}" for s in srcs) + "   spread")
        for part in ("starter", "bench"):
            for pos in POSITIONS + ("all",):
                vals = [sum(table[s][p][f"{cut}_{part}"] for p in POSITIONS) if pos == "all" else table[s][pos][f"{cut}_{part}"] for s in srcs]
                sp = spread(vals)
                print(f"{pos:4} {part:8} " + "".join(f"{v:11.1f}" for v in vals) + f"   {sp:6.1%}")
                if cut == "slice" and max(vals) - min(vals) > 1e-6 * max(1.0, max(vals)):
                    bad.append((pos, part, vals))
    if bad:
        print("\nslice cut differs across sources (budgets not shared?):", json.dumps(bad), file=sys.stderr)
        return 1
    print("\nslice cut identical across sources: the bench budget is shared; the role-cut spread is how sources shape value around the starter line.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
