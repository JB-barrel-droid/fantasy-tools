#!/usr/bin/env python3
"""Decompose the bench share into fill-in and start-worthy components.

Shows why the overall bench share (8.9% at ppr/12 approved defaults) sits
near the fill-in-only floor (8.6%) even though individual bench players
derive a large fraction of their value from the start-worthy term.

The explanation is displacement: when a bench player becomes start-worthy,
they push the marginal starter's lineup probability down. The marginal
starter loses almost exactly what the bench player gains, so the net
effect on the bench tier's total share is nearly zero.

Usage:
    python3 tools/bench_research/bench_share_decomposition.py [--setting ppr/12]

Inputs: data/fixtures/current/players.json, config/lineup_parameters.json.
JEG-549: decompose the 8.9% bench share.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines"))
import expected_starts_model as es  # noqa: E402

POSITIONS = es.POSITIONS


def resolve_params_recent() -> dict:
    """Approved-defaults parameters (JEG-533 log)."""
    return {
        "bye": 0.078,
        "QB": {"m": 0.1177, "sigma_rel": 0.1490, "sigma_floor": 0.69},
        "RB": {"m": 0.1443, "sigma_rel": 0.2770, "sigma_floor": 0.84},
        "WR": {"m": 0.1180, "sigma_rel": 0.2160, "sigma_floor": 0.99},
        "TE": {"m": 0.1510, "sigma_rel": 0.1960, "sigma_floor": 0.65},
    }


def decompose(inp, scoring: str, teams: int, params: dict, names_map: dict | None = None) -> dict:
    """Decompose the bench tier's value into fill-in and start-worthy parts."""
    sources, pos_of = es.load_sources(inp, scoring, teams)
    chart_sigma = es.chart_sigma_from(sources, teams)
    tiers = es.tiers_on_mean(sources, teams)
    keys = sorted(tiers)
    pie = es.PIE_PER_STARTING_SLOT * teams * es._starters_per_team()

    # Run with full parameters (recommended)
    rec_run = es.run_setting(sources, teams, params, chart_sigma, "A")
    rec_ddf = es.ddf_mean(rec_run["adjusted"], keys)

    # Run with sigma=0 (fill-in only)
    fi_params = {"bye": params["bye"]}
    for p in POSITIONS:
        fi_params[p] = {"m": params[p]["m"], "sigma_rel": 0.0, "sigma_floor": 0.0}
    fi_run = es.run_setting(sources, teams, fi_params, chart_sigma, "A")
    fi_ddf = es.ddf_mean(fi_run["adjusted"], keys)

    # Decompose by tier (starter vs bench) and by source of value
    starter_keys = [k for k in keys if tiers[k]["tier"] == "starter"]
    bench_keys = [k for k in keys if tiers[k]["tier"] != "starter"]

    total_rec = sum(v for v in rec_ddf.values() if v is not None)
    total_fi = sum(v for v in fi_ddf.values() if v is not None)

    # Per-tier totals
    result = {"setting": f"{scoring}/{teams}", "pie": pie, "positions": {}}
    for p in POSITIONS:
        p_starter = [k for k in starter_keys if tiers[k]["pos"] == p]
        p_bench = [k for k in bench_keys if tiers[k]["pos"] == p]

        starter_rec = sum(rec_ddf.get(k, 0) or 0 for k in p_starter)
        starter_fi = sum(fi_ddf.get(k, 0) or 0 for k in p_starter)
        bench_rec = sum(rec_ddf.get(k, 0) or 0 for k in p_bench)
        bench_fi = sum(fi_ddf.get(k, 0) or 0 for k in p_bench)

        # The start-worthy effect: difference between recommended and fill-in-only
        # For bench players: bench_rec - bench_fi = value gained from start-worthy
        # For starters: starter_rec - starter_fi = value lost to displacement
        bench_sw_gain = bench_rec - bench_fi
        starter_sw_loss = starter_rec - starter_fi  # typically negative

        result["positions"][p] = {
            "n_starters": len(p_starter),
            "n_bench": len(p_bench),
            "starter_value_rec": starter_rec,
            "starter_value_fi": starter_fi,
            "bench_value_rec": bench_rec,
            "bench_value_fi": bench_fi,
            "bench_sw_gain": bench_sw_gain,
            "starter_displacement": starter_sw_loss,
            "net_sw_effect": bench_sw_gain + starter_sw_loss,
        }

    # Overall
    total_bench_rec = sum(r["bench_value_rec"] for r in result["positions"].values())
    total_bench_fi = sum(r["bench_value_fi"] for r in result["positions"].values())
    total_starter_rec = sum(r["starter_value_rec"] for r in result["positions"].values())
    total_starter_fi = sum(r["starter_value_fi"] for r in result["positions"].values())

    result["overall"] = {
        "bench_share_rec": total_bench_rec / pie,
        "bench_share_fi": total_bench_fi / pie,
        "bench_sw_gain": total_bench_rec - total_bench_fi,
        "starter_displacement": total_starter_rec - total_starter_fi,
        "net_sw_effect": (total_bench_rec - total_bench_fi) + (total_starter_rec - total_starter_fi),
    }

    # Per-player examples (ESPN, first projection source)
    proj_sources = [s for s in sources if s.family == "projection"]
    if proj_sources:
        src = proj_sources[0]
        result["player_examples"] = []
        for p in POSITIONS:
            comps = rec_run["per_source"][src.key][p]
            fi_comps = fi_run["per_source"][src.key][p]
            S = comps["counts"]["starters"]
            pl_rec = comps["es"]["players"]
            pl_fi = fi_comps["es"]["players"]
            names = {}
            if names_map:
                names = {k: names_map.get(k, str(k)) for k in
                         [src.lists[p][i][0] for i in range(min(len(src.lists[p]), S + 15))]}
            for i in range(min(len(pl_rec), S + 10)):
                if i >= len(pl_fi):
                    break
                k = src.lists[p][i][0]
                name = names.get(k, str(k))
                v_rec = pl_rec[i]["v"]
                share_rec = pl_rec[i]["share"]
                sw_rec = pl_rec[i]["starter_part"] / v_rec if v_rec > 0 else 0
                fi_share = pl_fi[i]["share"]
                tier = "starter" if i < S else "bench"
                if tier == "bench" and i < S + 6 and v_rec > 0:
                    result["player_examples"].append({
                        "name": name, "pos": p, "rank": i + 1,
                        "ppg": round(pl_rec[i]["x"], 2),
                        "surplus_ppg": round(v_rec, 2),
                        "lineup_share_rec": round(share_rec, 3) if share_rec else None,
                        "start_worthy_frac": round(sw_rec, 3),
                        "fill_in_frac": round((share_rec or 0) - sw_rec, 3) if share_rec else None,
                        "lineup_share_fi": round(fi_share, 3) if fi_share else None,
                    })

    return result


def format_pct(x, d=1):
    return f"{100 * x:.{d}f}%" if x is not None else "n/a"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Decompose bench share into fill-in and start-worthy")
    parser.add_argument("--setting", default="ppr/12", help="Setting (default: ppr/12)")
    args = parser.parse_args()

    import value_reference as ref
    inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
    params = resolve_params_recent()

    scoring, teams = args.setting.split("/")
    teams = int(teams)
    names_map = {k: p.get("name", str(k)) for k, p in inp.players.items()}
    r = decompose(inp, scoring, teams, params, names_map=names_map)

    print(f"# Bench share decomposition: {r['setting']}")
    print(f"\nPie: {r['pie']:.0f} value units")
    print()
    print("## By position: fill-in vs start-worthy effect\n")
    print("| Position | Starters | Bench | Bench (fill-in) | Bench (rec) | SW gain | Starter displacement | Net SW |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for p in POSITIONS:
        d = r["positions"][p]
        print(f"| {p} | {d['n_starters']} | {d['n_bench']} | "
              f"{d['bench_value_fi']:.1f} | {d['bench_value_rec']:.1f} | "
              f"{d['bench_sw_gain']:+.1f} | {d['starter_displacement']:+.1f} | "
              f"{d['net_sw_effect']:+.1f} |")
    o = r["overall"]
    print(f"\nOverall bench share: fill-in {format_pct(o['bench_share_fi'])} -> "
          f"recommended {format_pct(o['bench_share_rec'])} "
          f"(gap {100*(o['bench_share_rec'] - o['bench_share_fi']):+.1f}pp)")
    print(f"Bench SW gain: {o['bench_sw_gain']:+.1f}, Starter displacement: {o['starter_displacement']:+.1f}, "
          f"Net: {o['net_sw_effect']:+.1f}")
    displacement_pct = abs(o['starter_displacement']) / o['bench_sw_gain'] * 100 if o['bench_sw_gain'] > 0 else 0
    print(f"Displacement absorbs {displacement_pct:.0f}% of the gross start-worthy gain")

    if "player_examples" in r:
        print("\n## Bench player examples (ESPN projection)\n")
        print("| Player | Pos | Rank | PPG | Surplus | Lineup share | Start-worthy | Fill-in | Fill-in-only share |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for ex in r["player_examples"]:
            print(f"| {ex['name']} | {ex['pos']} | {ex['rank']} | {ex['ppg']} | {ex['surplus_ppg']} | "
                  f"{format_pct(ex['lineup_share_rec'])} | {format_pct(ex['start_worthy_frac'])} | "
                  f"{format_pct(ex['fill_in_frac'])} | {format_pct(ex['lineup_share_fi'])} |")


if __name__ == "__main__":
    main()
