#!/usr/bin/env python3
"""JEG-1310 RESEARCH, read-only: how far CBS rest of season sits from the other
rest-of-season projections, why, and what three handling options would do to
DDF Value (projections).

Nothing in the repo is changed. Every rescored or reweighted input lives in
memory or a temp dir. Only rest-of-season sources are compared with each other
(ESPN ROS, Razzball ROS, CBS ROS); no weekly data enters (Jeremy, 2026-10-28:
"do not blend weekly data with ROS data, ever.").

    python3 docs/research/JEG-1310/cbs_options.py            # all tables
    python3 docs/research/JEG-1310/cbs_options.py --json OUT # also dump numbers

Inputs:
- data/history/week-{4..8}.json: the per-game points each ROS source was
  served at for that week (cbsros_ppg, espn_ppg, rz_ppg; [std, half, ppr]).
- data/fixtures/current/{players,comparison-sources-data}.json: week 8 build.
- cbsros_2026-10-29_components.txt (this folder): CBS's own week-8 stat line
  per player, scored on the 4-point fractional basis (see README).
"""
from __future__ import annotations

import copy
import json
import statistics as st
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "pipelines"))
import build_cbsros_ddf_leg as leg_mod  # noqa: E402
import check_source_divergence as sd  # noqa: E402
import value_reference as vr  # noqa: E402

FIXTURE = REPO / "data/fixtures/current/comparison-sources-data.json"
PLAYERS = REPO / "data/fixtures/current/players.json"
HISTORY = REPO / "data/history"
WEEKS = (4, 5, 6, 7, 8)
POS = ("QB", "RB", "WR", "TE")
HALF = 1  # index in the [std, half, ppr] triples
RELEVANT_PPG = 5.0  # mean of ESPN and Razzball, half PPR


def positions() -> dict:
    return {p["player_key"]: p["pos"] for p in json.loads(PLAYERS.read_text())["players"]
            if p.get("pos") in POS}


def names() -> dict:
    return {p["player_key"]: p.get("name") for p in json.loads(PLAYERS.read_text())["players"]}


def week_ppg(week: int) -> dict:
    doc = json.loads((HISTORY / f"week-{week}.json").read_text())
    out = {}
    for s in ("cbsros", "espn", "razzball"):
        sec = (doc.get("sources") or {}).get(s) or {}
        out[s] = {int(k): v for k, v in (sec.get("ppg") or {}).items() if isinstance(v, list)}
    return out


def components() -> dict:
    line = [x for x in (HERE / "cbsros_2026-10-29_components.txt").read_text().splitlines()
            if x and not x.startswith("#")][0]
    out = {}
    for rec in line.split(";"):
        k, gp, fpts, resc, recs, int_fl = rec.split()
        out[int(k)] = {"gp": float(gp), "fpts": float(fpts), "rescored": float(resc),
                       "rec": float(recs), "int_fl": float(int_fl)}
    return out


def gap_rows(cbs: dict, espn: dict, rz: dict, pos_of: dict, idx: int = HALF) -> dict:
    """Per position: CBS against the mean of ESPN and Razzball, and ESPN against
    Razzball as the yardstick for ordinary disagreement."""
    by = {p: [] for p in POS}
    for k, c in cbs.items():
        e, r = espn.get(k), rz.get(k)
        if k not in pos_of or e is None or r is None:
            continue
        c, e, r = c[idx], e[idx], r[idx]
        if None in (c, e, r) or min(c, e, r) <= 0:
            continue
        o = (e + r) / 2
        if o < RELEVANT_PPG:
            continue
        by[pos_of[k]].append((c, e, r, o))
    out = {}
    for p, xs in by.items():
        if not xs:
            continue
        out[p] = {
            "n": len(xs),
            "cbs_minus_others_ppg": round(st.median(c - o for c, e, r, o in xs), 2),
            "cbs_over_others": round(st.median(c / o for c, e, r, o in xs), 3),
            "cbs_off_25pct": round(sum(abs(c / o - 1) > 0.25 for c, e, r, o in xs) / len(xs), 3),
            "espn_vs_rz_off_25pct": round(sum(abs(e / r - 1) > 0.25 for c, e, r, o in xs) / len(xs), 3),
        }
    return out


def rescored_ppg(comp: dict) -> dict:
    """Option A per-game points: CBS's own stat line, 4-pt fractional, -2 INT/FL."""
    out = {}
    for k, c in comp.items():
        if c["gp"] <= 0:
            continue
        s = c["rescored"] / c["gp"]
        rpg = c["rec"] / c["gp"]
        out[k] = [round(s, 3), round(s + 0.5 * rpg, 3), round(s + rpg, 3)]
    return out


def ddf_rows(inp: vr.Inputs, scoring: str, teams: int = 12, superflex: int = 0) -> dict:
    s = vr.Setting(inp, scoring, teams, superflex)
    return s.result()["rows"]


def inputs_with_cbs(ppg: dict | None) -> vr.Inputs:
    inp = vr.Inputs.load(FIXTURE, PLAYERS)
    if ppg is not None:
        for k, p in inp.players.items():
            if k in ppg and p.get("cbsros_ppg"):
                t = ppg[k]
                p["cbsros_ppg"] = {"standard": t[0], "half_ppr": t[1], "ppr": t[2]}
    return inp


def proj(row: dict, cbs_weight: float = 1.0) -> float | None:
    """DDF Value (projections) for a row, with CBS at a weight (1 = as shipped)."""
    d = row["ddf"]["projections"]
    used = d["sources"]
    if not used:
        return None
    adj = row["adjusted"]
    w = {k: (cbs_weight if k == "cbsros" else 1.0) for k in used}
    tot = sum(w[k] for k in used)
    return sum(w[k] * adj[k] for k in used) / tot if tot else None


def divergence_with_cbs(ppg: dict) -> dict:
    """Re-run the unchanged divergence check with CBS legs rebuilt from ppg."""
    combos = (("standard", "standard_12", 0), ("half_ppr", "half_12", 1), ("ppr", "full_12", 2))
    with tempfile.TemporaryDirectory() as tmp:
        w = Path(tmp)
        fx = json.loads(FIXTURE.read_text())
        out = copy.deepcopy(fx)
        for sc, ck, idx in combos:
            leg = json.loads((REPO / f"data/ddf-two-tier/ddf-20261029-cbsros-{sc}-12t-0p15/ddf_leg_cbsros.json").read_text())
            rows = []
            for v in leg["values"]:
                t = ppg.get(v["player_key"])
                x = t[idx] if t else v["ppg"]
                rows.append({"player_name": v["player"], "player_norm": v["player_norm"], "pos": v["pos"],
                             "team": v["team"], "per_game_standard": x, "per_game_half_ppr": x, "per_game_ppr": x})
            snap = w / f"cf_{sc}.json"
            snap.write_text(json.dumps({"vintage_date": "2026-10-29", "rows": rows}))
            new = leg_mod.build_leg(snap, FIXTURE, sc, 12, 0.15)
            out["sources"]["cbsros"]["combos"][ck]["values"] = {v["player_norm"]: round(v["value"], 1) for v in new["values"]}
        cf = w / "cf_fixture.json"
        cf.write_text(json.dumps(out))
        rep = sd.run(fixture_path=cf, players_path=PLAYERS, history_dir=HISTORY, resolutions_path=w / "none.json")
    return {s: {"status": rep["sources"][s]["status"],
                **{k: [c["n"], c["outlier_rate"], c["bias"]] for k, c in rep["sources"][s]["combos"].items()}}
            for s in ("espn", "cbsros", "razzball")}


def main() -> None:
    pos_of, nm = positions(), names()
    report: dict = {"gap_by_week": {}, "rescore_fit": {}, "options": {}}

    print("## Gap by week, half PPR, players the others put at 5+ ppg")
    for wk in WEEKS:
        p = week_ppg(wk)
        report["gap_by_week"][wk] = gap_rows(p["cbsros"], p["espn"], p["razzball"], pos_of)
        print(wk, json.dumps(report["gap_by_week"][wk]))

    comp = components()
    resc = rescored_ppg(comp)
    w8 = week_ppg(8)
    report["gap_week8_rescored"] = gap_rows(resc, w8["espn"], w8["razzball"], pos_of)
    print("\n## Week 8 after rescoring CBS's stat line (Option A)")
    print(json.dumps(report["gap_week8_rescored"]))

    # How far CBS's printed points sit from its own stat line.
    fit = {p: [] for p in POS}
    for k, c in comp.items():
        if k in pos_of and c["fpts"] >= 30:
            fit[pos_of[k]].append(c)
    for p, xs in fit.items():
        report["rescore_fit"][p] = {
            "n": len(xs),
            "cbs_over_4pt_basis": round(st.median(c["fpts"] / c["rescored"] for c in xs), 3),
            "cbs_minus_4pt_ppg": round(st.median((c["fpts"] - c["rescored"]) / c["gp"] for c in xs), 2),
        }
    print("\n## CBS printed points against its own stat line (4-pt basis), week 8")
    print(json.dumps(report["rescore_fit"]))

    print("\n## Divergence check, week 8")
    report["divergence_now"] = divergence_with_cbs({})
    report["divergence_rescored"] = divergence_with_cbs(resc)
    print("now     ", json.dumps(report["divergence_now"]["cbsros"]))
    print("rescored", json.dumps(report["divergence_rescored"]["cbsros"]))

    for scoring, sf in (("ppr", 0), ("half_ppr", 0), ("ppr", 1)):
        label = f"{scoring}_12" + ("_superflex" if sf else "")
        base = ddf_rows(inputs_with_cbs(None), scoring, 12, sf)
        alt = ddf_rows(inputs_with_cbs(resc), scoring, 12, sf)
        top = sorted((k for k in base if proj(base[k]) is not None), key=lambda k: -proj(base[k]))
        table = []
        for k in top:
            b = proj(base[k])
            table.append({"key": k, "name": nm.get(k), "pos": base[k]["pos"],
                          "cbs_listed": "cbsros" in base[k]["ddf"]["projections"]["sources"],
                          "now": round(b, 1),
                          "A_rescore": round(proj(alt[k]), 1) if k in alt and proj(alt[k]) is not None else None,
                          "B_half_weight": round(proj(base[k], 0.5), 1),
                          "C_exclude": round(proj(base[k], 0.0), 1) if proj(base[k], 0.0) is not None else None})
        report["options"][label] = table
        print(f"\n## DDF Value (projections), {label}: top 25")
        for r in table[:25]:
            print(r)
        top100 = table[:100]
        for opt in ("A_rescore", "B_half_weight", "C_exclude"):
            moves = sorted((r for r in top100 if r[opt] is not None), key=lambda r: -abs(r[opt] - r["now"]))[:5]
            print(opt, "biggest moves in top 100:",
                  [(r["name"], r["pos"], r["now"], r[opt], round(r[opt] - r["now"], 1)) for r in moves])
            mad = st.mean(abs(r[opt] - r["now"]) for r in top100 if r[opt] is not None)
            print(opt, "mean abs move in top 100:", round(mad, 2))

    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
