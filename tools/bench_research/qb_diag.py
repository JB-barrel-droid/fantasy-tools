#!/usr/bin/env python3
"""QB 22.6% bench share diagnosis.

Reproduces: finding 1 (the 22.6% QB bench share was an artifact).

Runs bench_share_readout inputs at ppr/12, prints per-source waiver lines,
bench-tier split (start-worthy vs fill), sum of P(X > l) vs slots, and
QB1-QB32 with mean projection, VORP and blended value. That is how the
Lamar Jackson / Mahomes Razzball data bug (7.1 / 10.5 PPG) was found.

Source: 2026-10-10 bench research session (JEG-546).

Usage:
    python3 tools/bench_research/qb_diag.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO))

import expected_starts_model as es  # noqa: E402
import value_reference as ref  # noqa: E402
import derive_lineup_parameters as dl  # noqa: E402


def main():
    inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
    cfg = json.loads(dl.CONFIG.read_text())
    res = dl.resolve(cfg)
    params = {"bye": res["bye"], **{p: dict(res["positions"][p]) for p in es.POSITIONS}}
    names = {k: p.get("name") for k, p in inp.players.items()}

    teams = 12
    scoring = "ppr"
    sources, _ = es.load_sources(inp, scoring, teams)
    cs = es.chart_sigma_from(sources, teams)
    tiers = es.tiers_on_mean(sources, teams)
    run = es.run_setting(sources, teams, params, cs, "A")
    ddf = es.ddf_mean(run["adjusted"], sorted(tiers))

    # Per-source waiver/starter lines for QB
    print("=== Per-source QB waiver/starter lines ===")
    for s in sources:
        vals = [v for _, v in s.lists["QB"]]
        counts = es.alloc(
            {p: sorted((v for _, v in s.lists[p]), reverse=True) for p in es.POSITIONS},
            teams,
        )
        w_idx = counts["QB"]["rostered"]
        l_idx = counts["QB"]["starters"]
        w = vals[w_idx] if len(vals) > w_idx else vals[-1] if vals else 0
        l = vals[l_idx] if len(vals) > l_idx else w
        print(f"  {s.key:20s}  w={w:6.2f}  l={l:6.2f}  rostered={w_idx}  starters={l_idx}")

    # QB rankings with blended value and tiers
    print("\n=== QB1-QB32 by blended DDF value ===")
    qb_keys = sorted(
        (k for k, t in tiers.items() if t["pos"] == "QB"),
        key=lambda k: -(ddf.get(k) or 0),
    )
    print(f"  {'Rank':>4s}  {'Name':30s}  {'Mean':>6s}  {'DDF':>7s}  {'Tier':8s}")
    for i, k in enumerate(qb_keys[:32], 1):
        t = tiers[k]
        name = names.get(k, k)
        val = ddf.get(k, 0)
        print(f"  {i:4d}  {name:30s}  {t['mean']:6.2f}  {val:7.2f}  {t.get('tier', '?'):8s}")

    # Bench share: re-tier by DDF value (the JEG-546 fix)
    lists = {
        p: sorted((t["mean"] for t in tiers.values() if t["pos"] == p), reverse=True)
        for p in es.POSITIONS
    }
    counts = es.alloc(lists, teams)
    retiered = {}
    for p in es.POSITIONS:
        ranked = sorted(
            (k for k, t in tiers.items() if t["pos"] == p),
            key=lambda k: -(ddf.get(k) or 0),
        )
        for i, k in enumerate(ranked):
            retiered[k] = {
                **tiers[k],
                "tier": (
                    "starter" if i < counts[p]["starters"]
                    else "bench" if i < counts[p]["rostered"]
                    else "waiver"
                ),
            }
    met = es.shares_and_ratio(ddf, retiered, teams)
    print(f"\n=== Bench share by position ===")
    bench_shares = met.get("bench_tier_share", {})
    for p in es.POSITIONS:
        bs = bench_shares.get(p, 0)
        print(f"  {p:4s}  {bs * 100:5.1f}%")
    print(f"  Overall: {met.get('bench_tier_share_overall', 0) * 100:.1f}%")


if __name__ == "__main__":
    main()
