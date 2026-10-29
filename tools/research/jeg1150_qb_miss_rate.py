"""JEG-1150 research: what the QB miss_rate does to bench seats and values.

Research only. Patches roster_convention._BENCH_MISS_RATE["QB"] in memory
for each run; nothing in config or the published model changes.

Usage: python3 tools/research/jeg1150_qb_miss_rate.py [--out file.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines"))

import value_reference as vr  # noqa: E402
from lib import roster_convention as rc  # noqa: E402

RATES = (0.06, 0.09, 0.12, 0.15)  # 0.12 is live
POS = ("QB", "RB", "WR", "TE")


def run(inp, hist, rate, setting):
    old = rc._BENCH_MISS_RATE["QB"]
    rc._BENCH_MISS_RATE["QB"] = rate
    try:
        out = vr.compute(inp, setting, views=("adj",), hist=hist)
    finally:
        rc._BENCH_MISS_RATE["QB"] = old
    alloc = {p: out["pipeline"]["allocation"][p] for p in POS}
    rows = out["views"]["adj"]
    vals = {}
    for i, r in rows.items():
        pl = inp.players.get(i) or inp.players.get(str(i)) or {}
        pos = pl.get("pos")
        if pos in POS and r.get("ddf_value") is not None:
            vals[i] = {"pos": pos, "name": pl.get("name") or str(i),
                       "value": r["ddf_value"], "tier": r.get("ddf_tier")}
    return {"alloc": alloc, "vals": vals,
            "benchShare": out["pipeline"]["benchShareApplied"]}


def summary(result):
    """Compact figures for docs/research/data: seats everywhere, and at
    standard/12 the tier totals and the value of each player whose value
    moved by 0.01 or more under any rate."""
    std = result["std12"]
    base = std["0.12"]["vals"]
    totals = {}
    for rate, r in std.items():
        t = {}
        for v in r["vals"].values():
            k = f"{v['pos']}|{v['tier']}"
            t[k] = round(t.get(k, 0.0) + v["value"], 2)
        totals[rate] = t
    moved = {}
    for i, v in base.items():
        by = {rate: round(r["vals"][i]["value"], 2) for rate, r in std.items() if i in r["vals"]}
        if max(by.values()) - min(by.values()) >= 0.01:
            moved[v["name"]] = {"pos": v["pos"], "values": by,
                                "tiers": {rate: r["vals"][i]["tier"] for rate, r in std.items() if i in r["vals"]}}
    return {"rates": list(RATES), "live_rate": 0.12, "bench_seats": result["seats"],
            "standard_12": {"tier_totals": totals, "players_moved": moved}}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    inp = vr.Inputs.load(vr.FIXTURE, vr.PLAYERS)
    hist = vr.History(vr.HISTORY)
    result = {"seats": {}, "std12": {}}
    for scoring in ("standard", "half_ppr", "ppr"):
        for teams in (8, 10, 12, 14):
            key = f"{scoring}/{teams}"
            result["seats"][key] = {}
            for rate in RATES:
                r = run(inp, hist, rate, {"scoring": scoring, "teams": teams, "superflex": 0})
                result["seats"][key][str(rate)] = {p: r["alloc"][p]["bench"] for p in POS}
                if key == "standard/12":
                    result["std12"][str(rate)] = r
    if a.out:
        a.out.write_text(json.dumps(summary(result), indent=1, default=str) + "\n")
    for key, by in result["seats"].items():
        print(key, {k: v for k, v in by.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
