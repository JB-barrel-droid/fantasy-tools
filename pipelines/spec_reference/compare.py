"""Build the spec reference's series and diff them against the engine dump.

Inputs are data files only: the built fixture (comparison-sources-data.json),
players.json and the built ESPN two-tier legs (data/ddf-two-tier). The engine
side is value_check.py's engine dump (`value-check-engine.json`, black box).

Run: python pipelines/spec_reference/compare.py --engine-json <dump> [--out <json>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "spec_reference"  # noqa: A001

from spec_reference import VERSION  # noqa: E402
from spec_reference import twotier as tt  # noqa: E402
from spec_reference import value_model as vm  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
TOL = 0.05
SCORINGS = ("standard", "half_ppr", "ppr")
TEAMS = (8, 10, 12, 14)
COMBO_SCORING = {"standard": "standard", "half_ppr": "half", "ppr": "full"}
PUBLISHED = ("usatoday", "fantasycalc", "fantasypros", "cbs")
SAVED_VIEWS = ("usatoday", "fantasycalc", "fantasypros")
PROJ_PPG = {"espn": "espn_ppg", "cbsros": "cbsros_ppg", "razzball": "rz_ppg"}
VIEW_SERIES = {
    "indexed": ("espn", "cbsros", "razzball") + PUBLISHED,
    "vorp": ("espn_vorp", "cbsros_vorp", "razzball_vorp") + PUBLISHED,
    "adj": PUBLISHED,
}

# Where the written spec is silent, the choice made here (also MR-18 in
# docs/math-review-agenda.md). Ids are referenced from the report.
SPEC_GAPS = {
    "SG-1": "Two-tier slice exposures and glide are not written (only 'softplus glide' / "
            "'slice pricing'). Chosen: starter slice = min(surplus, softplus_tau(ppg - rs)), "
            "bench slice = the rest of the surplus over the waiver line.",
    "SG-2": "Two-tier starter line rs and glide width tau are not written. Taken from the leg "
            "artifact's recorded fields: rs midway between the last starter and first bench "
            "player, tau = (rs - rw) / 4.",
    "SG-3": "Requested bench share above the feasible window: the docs say only that it 'falls "
            "back down'. Chosen: one point inside the upper edge (halving if narrower), "
            "symmetric to the written lower-edge rule.",
    "SG-4": "Which per-game projection a live CBS ROS / Razzball leg prices: players.json "
            "cbsros_ppg / rz_ppg (not rz_filled_ppg), every listed player.",
    "SG-5": "Raw projection value-above-waivers series: bench count not written. Chosen: the "
            "shared allocator's teams x BENCH 6 by the 12-team mix (D'Hondt); flex by "
            "projected points.",
    "SG-6": "Published VORP vs waivers factor: 'the anchor's total over the players that chart "
            "ranks' read literally (anchor values summed over the chart's players; chart total "
            "over all its players). VA-2 records the engine uses the anchor's starter+bench "
            "group totals instead.",
    "SG-7": "Adjusted values: 'the anchor's total for that group' does not say whose roles or "
            "which players. Chosen: the anchor's own two-tier tiers, over every player the "
            "anchor prices.",
    "SG-8": "Adjusted values at the saved setup (full PPR 12): the 70 factor 'across all "
            "published charts' when three charts show saved views. Chosen: across the charts "
            "derived at that setting (CBS only).",
    "SG-9": "Translation: rounding of the slot-proportional preliminary flex count, D'Hondt "
            "tie order, and whether hidden imputed players are flex candidates are not "
            "written. Chosen: round half up, position order QB/RB/WR/TE, yes.",
    "SG-11": "Which anchor players count as 'priced' in a total-match factor (Indexed "
             "published at derived settings, CBS ROS / Razzball, raw *_vorp). The contract keeps "
             "genuine 0.0 as a value, so anchor zeros count here. The engine counts only anchor > 0 "
             "at derived settings but counts zeros in the saved 12-team factor.",
    "SG-12": "Row membership: a player only ESPN lists, at 0.0, has no row on the page. The ESPN "
             "zero rule (GAP-025) says 0.0 with a badge; the spec does not say whether a row with "
             "no other source is shown. Counted as no_engine_row, not as a disagreement.",
    "SG-10": "Anchor in the value model: the spec says the built ESPN leg; the engine applies "
             "live refit cells on top of it (within about 0.05). The built leg is used.",
}


def setting_id(scoring: str, teams: int) -> str:
    return f"{scoring}/{teams}/sf0"


def default_paths(repo: Path = REPO) -> dict:
    fixture = repo / "dist" / "assets" / "comparison-sources-data.json"
    if not fixture.exists():
        fixture = repo / "app" / "trade-value-chart" / "assets" / "comparison-sources-data.json"
    return {"fixture": fixture,
            "players": repo / "data" / "fixtures" / "current" / "players.json",
            "legs": repo / "data" / "ddf-two-tier"}


def load_inputs(paths: dict | None = None) -> dict:
    paths = paths or default_paths()
    fixture = json.loads(Path(paths["fixture"]).read_text(encoding="utf-8"))
    players = json.loads(Path(paths["players"]).read_text(encoding="utf-8"))["players"]
    return {"fixture": fixture, "players": players, "legs_dir": Path(paths["legs"])}


def find_leg(legs_dir: Path, scoring: str, teams: int, snapshot: str | None) -> dict | None:
    cands = sorted(legs_dir.glob(f"ddf-*-espn-{scoring}-{teams}t-0p15/ddf_leg.json"))
    if snapshot:
        tag = snapshot.replace("-", "")
        exact = [p for p in cands if p.parent.name.startswith(f"ddf-{tag}-")]
        if exact:
            cands = exact
    if not cands:
        return None
    return json.loads(cands[-1].read_text(encoding="utf-8"))


def _keyed(name_values: dict | None, name_keys: dict) -> dict:
    out = {}
    for name, v in (name_values or {}).items():
        k = name_keys.get(name)
        if k is not None and v is not None:
            out[int(k)] = float(v)
    return out


def _combo(source: dict, scoring: str, teams: int, suffix: str = "") -> dict | None:
    combos = source.get("combos") or {}
    key = f"{COMBO_SCORING[scoring]}_{teams}"
    return combos.get(key + suffix) or combos.get(key)


def build_setting(inputs: dict, scoring: str, teams: int) -> dict:
    """Every spec series at one setting: {view: {series: {key: value}}} plus
    diagnostics (calibrations, waiver lines, implied weights)."""
    fx, players = inputs["fixture"], inputs["players"]
    sources = fx["sources"]
    name_keys = fx.get("player_keys") or {}
    pos_of = {int(p["player_key"]): p.get("pos") for p in players}
    snapshot = (sources.get("espn") or {}).get("espn_snapshot")
    leg = find_leg(inputs["legs_dir"], scoring, teams, snapshot)
    diag: dict = {"leg": leg.get("bake_id") if leg else None}
    views = {"indexed": {}, "vorp": {}, "adj": {}}
    if leg is None:
        return {"views": views, "diag": diag}
    anchor = {int(r["player_key"]): float(r["value"]) for r in leg["values"]
              if r.get("pos") in tt.POSITIONS}
    anchor_tier = {int(r["player_key"]): r.get("tier") for r in leg["values"]}
    for r in leg["values"]:
        pos_of.setdefault(int(r["player_key"]), r.get("pos"))

    # -- two-tier: ESPN re-priced from the leg's own pool (checks the leg math)
    pool = [(int(r["player_key"]), r["pos"], r["ppg"]) for r in leg["values"] if r["pos"] in tt.POSITIONS]
    espn_disp, _, tiers, cals, _ = tt.price_leg(pool, teams)
    views["indexed"]["espn"] = espn_disp
    diag["espn_calibration"] = {p: _cal_diag(cals[p], tiers[p], leg["calibration"].get(p))
                                for p in tt.POSITIONS}
    leg_diffs = [abs(espn_disp[k] - anchor[k]) for k in anchor if k in espn_disp]
    diag["espn_vs_built_leg"] = {"compared": len(leg_diffs),
                                 "over_tol": sum(1 for d in leg_diffs if d > TOL),
                                 "max_abs_diff": max(leg_diffs, default=0.0)}

    # -- projections: CBS ROS / Razzball legs matched to the anchor by total
    diag["projection_calibration"] = {}
    for src in ("cbsros", "razzball"):
        field = PROJ_PPG[src]
        pl = [(int(p["player_key"]), p.get("pos"), (p.get(field) or {}).get(scoring))
              for p in players if p.get("pos") in tt.POSITIONS and (p.get(field) or {}).get(scoring) is not None]
        disp, _, tiers_s, cals_s, _ = tt.price_leg(pl, teams)
        views["indexed"][src] = vm.match_total(disp, anchor)
        diag["projection_calibration"][src] = {p: _cal_diag(cals_s[p], tiers_s[p], None) for p in tt.POSITIONS}
    for v in ("vorp", "adj"):
        for src in ("espn", "cbsros", "razzball"):
            views[v][src] = views["indexed"][src]

    # -- raw value above waivers for the three projections
    diag["projection_waiver"] = {}
    for src, field in PROJ_PPG.items():
        ppg = {int(p["player_key"]): (p.get(field) or {}).get(scoring) for p in players
               if (p.get(field) or {}).get(scoring) is not None}
        res = vm.projection_vaw(ppg, pos_of, teams)
        series = vm.match_total(res["vaw"], anchor)
        diag["projection_waiver"][src] = res["waiver"]
        for v in views:
            views[v][f"{src}_vorp"] = series

    # -- published charts
    natives = {}
    for src in PUBLISHED:
        combo = _combo(sources.get(src) or {}, scoring, 12, "_qb1" if src == "fantasycalc" else "")
        natives[src] = (combo, _keyed((combo or {}).get("native"), name_keys) if combo else {})
    trs, diag["published"] = {}, {}
    for src in PUBLISHED:
        combo, nat = natives[src]
        if not nat:
            continue
        saved = _keyed(combo.get("reindexed"), name_keys) if teams == 12 else None
        fit = ((combo.get("fit") or {}).get("order_preserving_rescale") or {})
        views["indexed"][src] = vm.indexed_published(nat, anchor, saved, fit.get("factor"), teams)
        peers = [natives[o][1] for o in PUBLISHED if o != src and natives[o][1]]
        tr = vm.translate(nat, pos_of, teams, peers)
        trs[src] = tr
        diag["published"][src] = {k: tr[k] for k in ("waiver", "waiver_method", "n_imputed", "flex",
                                                      "rostered", "implied_weights")}
    saved_setup = scoring == "ppr" and teams == 12
    derived = {}
    for src, tr in trs.items():
        vv = (sources.get(src) or {}).get("vorp_views") or {}
        if saved_setup and src in SAVED_VIEWS and vv.get("views"):
            views["vorp"][src] = _keyed(vv["views"].get("vorp"), name_keys)
            views["adj"][src] = _keyed(vv["views"].get("adj_values"), name_keys)
        else:
            views["vorp"][src] = vm.vorp_view_published(tr, anchor)
            derived[src] = tr
    budgets = vm.anchor_groups(anchor, anchor_tier, pos_of)
    diag["anchor_group_budgets"] = budgets
    by_chart = None
    if vm.ADJ_BUDGET_BASIS == "chart":
        by_chart = {src: vm.anchor_groups(anchor, anchor_tier, pos_of, set(tr["vaw"]))
                    for src, tr in derived.items()}
    for src, vals in vm.adjusted_published(derived, budgets, pos_of,
                                           budgets_by_chart=by_chart).items():
        views["adj"][src] = vals
    return {"views": views, "diag": diag}


def _cal_diag(cal, tier, leg_cal: dict | None) -> dict:
    out = {"pie": cal.pie, "share_used": cal.share_used, "window": [cal.lo, cal.hi],
           "ps": cal.ps, "pb": cal.pb, "rw": tier.rw, "rs": tier.rs, "tau": tier.tau,
           "n_starters": len(tier.starters), "n_bench": len(tier.bench), "error": cal.error}
    if leg_cal:
        out["built_leg"] = {k: leg_cal.get(k) for k in ("pie", "bench_share_used", "ps", "pb", "rw",
                                                         "rs", "tau", "n_starters", "n_bench")}
    return out


def diff_setting(engine_view: dict, spec_series: dict, series: str, tol: float = TOL) -> dict:
    eng = {int(k): row.get(series) for k, row in engine_view.items()}
    keys = {k for k, v in eng.items() if v is not None} | set(spec_series)
    out = {"compared": 0, "mismatches": 0, "presence": 0, "no_engine_row": 0,
           "max_abs_diff": 0.0, "examples": []}
    for k in sorted(keys):
        if k not in eng:
            # The page has no row for this player at all (SG-12): not a value
            # the page shows, so counted apart, not as a disagreement.
            out["no_engine_row"] += 1
            continue
        e, s = eng.get(k), spec_series.get(k)
        out["compared"] += 1
        if (e is None) != (s is None):
            out["mismatches"] += 1
            out["presence"] += 1
            out["examples"].append({"player_key": k, "engine": e, "spec": s, "kind": "presence"})
            continue
        d = abs(e - s)
        out["max_abs_diff"] = max(out["max_abs_diff"], d)
        if d > tol:
            out["mismatches"] += 1
            out["examples"].append({"player_key": k, "engine": round(e, 4), "spec": round(s, 4),
                                    "diff": round(s - e, 4), "kind": "value"})
    out["examples"].sort(key=lambda x: -abs(x.get("diff") or 999))
    out["examples"] = out["examples"][:5]
    return out


def compare(engine_settings: dict, inputs: dict | None = None, tol: float = TOL,
            keep_diag: bool = False) -> dict:
    """The `spec_reference` section of value-check.json (non-blocking)."""
    inputs = inputs or load_inputs()
    by_cell, totals = [], {}
    diags = {}
    for scoring in SCORINGS:
        for teams in TEAMS:
            sid = setting_id(scoring, teams)
            eng = engine_settings.get(sid)
            if not eng:
                continue
            built = build_setting(inputs, scoring, teams)
            diags[sid] = built["diag"]
            for view, series_list in VIEW_SERIES.items():
                ev = (eng.get("views") or {}).get(view) or {}
                for series in series_list:
                    spec = built["views"][view].get(series)
                    if spec is None:
                        continue
                    d = diff_setting(ev, spec, series, tol)
                    by_cell.append({"setting": sid, "view": view, "series": series, **d})
                    t = totals.setdefault(f"{view}:{series}", {"compared": 0, "mismatches": 0,
                                                               "no_engine_row": 0, "max_abs_diff": 0.0,
                                                               "cells_disagreeing": 0})
                    t["no_engine_row"] += d["no_engine_row"]
                    t["compared"] += d["compared"]
                    t["mismatches"] += d["mismatches"]
                    t["max_abs_diff"] = max(t["max_abs_diff"], d["max_abs_diff"])
                    t["cells_disagreeing"] += 1 if d["mismatches"] else 0
    compared = sum(c["compared"] for c in by_cell)
    mism = sum(c["mismatches"] for c in by_cell)
    report = {
        "schema": "spec-reference/1",
        "version": VERSION,
        "blocking": False,
        "note": ("Clean-room reference written from the methodology text only; it never holds a "
                 "source. Disagreements are classified in docs/math-review-agenda.md MR-18."),
        "tolerance": tol,
        "values_compared": compared,
        "mismatches": mism,
        "agreement": (1 - mism / compared) if compared else None,
        "by_series": totals,
        "cells": [c for c in by_cell if c["mismatches"]],
        "spec_gaps": SPEC_GAPS,
        "two_tier_vs_built_leg": {sid: d.get("espn_vs_built_leg") for sid, d in diags.items()},
    }
    if keep_diag:
        report["diagnostics"] = diags
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engine-json", required=True)
    ap.add_argument("--out")
    ap.add_argument("--tol", type=float, default=TOL)
    ap.add_argument("--diag", action="store_true")
    ap.add_argument("--priced-basis", choices=("listed", "positive"), default="listed",
                    help="diagnostic only: read SG-11 the engine's way to see what else differs")
    ap.add_argument("--above-window", choices=("step_inside", "edge"), default="step_inside",
                    help="diagnostic only: read SG-3 the other way")
    ap.add_argument("--adj-budget", choices=("all", "chart"), default="all",
                    help="diagnostic only: read SG-7 the other way")
    args = ap.parse_args(argv)
    vm.ADJ_BUDGET_BASIS = args.adj_budget
    vm.PRICED_BASIS = args.priced_basis
    tt.ABOVE_WINDOW = args.above_window
    engine = json.loads(Path(args.engine_json).read_text(encoding="utf-8"))
    rep = compare(engine["settings"], tol=args.tol, keep_diag=args.diag)
    text = json.dumps(rep, indent=1, default=str)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(f"spec reference: {rep['values_compared']} compared, {rep['mismatches']} over {args.tol}")
    for k, t in sorted(rep["by_series"].items()):
        print(f"  {k:28s} {t['mismatches']:6d}/{t['compared']:6d}  max {t['max_abs_diff']:.4f}  "
              f"cells {t['cells_disagreeing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
