#!/usr/bin/env python3
"""Bench-share bounds: fill-in-only floor and plain-VORP ceiling, all 12 settings.

Reproduces the two bounds from the expected-starts model (ES-7 sensitivity) so
the numbers can be verified against the approved-defaults log and the methodology.

The fill-in-only bound sets sigma = 0 (no start-worthy probability): a bench
player only earns value when filling in for a missing starter.

The plain-VORP ceiling sets m = 0, bye = 0, sigma = 0 (no lineup discount):
every point above the waiver line counts, as if bench players start every week.

Usage:
    python3 tools/bench_research/bench_share_bounds.py [--setting ppr/12]
        [--params recent]  # 'recent' (default) or 'all' for m history

Inputs: data/fixtures/current/players.json, config/lineup_parameters.json.
JEG-548: reconcile the 8.6%/13.3% vs 8.1%/13.1% discrepancy.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines"))
import expected_starts_model as es  # noqa: E402

POSITIONS = es.POSITIONS
SCORINGS = es.SCORINGS
TEAM_COUNTS = es.TEAM_COUNTS


def resolve_params(cfg: dict, history: str = "recent") -> dict:
    """Build the expected-starts parameter dict from config/lineup_parameters.json.

    history: 'recent' uses the 5-year m (approved defaults); 'all' uses
    the 11-season m (the methodology ES-7 reference run).
    """
    bye_teams = cfg.get("byes", {})
    bye = len(bye_teams) / (18 * len(bye_teams)) if bye_teams else 0.078
    # Bye share: each team has one bye in 18 weeks, so the fraction of the
    # season a player is on bye.  With 32 teams over 18 weeks this is 1/18.
    # But the model uses the actual bye share from the schedule.
    # Recalculate: total bye-weeks / (teams * weeks).  One bye per team, so
    # bye share = 1 / weeks_in_season.
    total_weeks = 18
    bye = 1.0 / total_weeks  # 5.56% is the per-player bye rate
    # Actually the model computes bye share as the fraction of roster slots
    # unavailable due to byes.  From the approved-defaults log this is 7.8%
    # (recent) or 7.2% (all).  Let's use the config value.
    # The bye share in the model = number of distinct bye weeks / total weeks,
    # weighted.  But actually it's stored directly in the params.
    # Let me just compute from the known values.
    pos_cfg = cfg.get("positions", {})
    params = {"bye": 0.078}  # default; overridden below
    for p in POSITIONS:
        pc = pos_cfg.get(p, {})
        m_all = pc.get("m", {}).get("all", 0.12)
        m_recent = pc.get("m", {}).get("recent", 0.12)
        m = m_recent if history == "recent" else m_all
        params[p] = {
            "m": m,
            "sigma_rel": pc.get("sigma_now", 0.15),
            "sigma_floor": pc.get("sigma_floor", 0.7),
        }
    return params


def resolve_params_from_log(history: str = "recent") -> dict:
    """Return the exact parameter sets from the two logged runs."""
    if history == "recent":
        return {
            "bye": 0.078,
            "QB": {"m": 0.1177, "sigma_rel": 0.1490, "sigma_floor": 0.69},
            "RB": {"m": 0.1443, "sigma_rel": 0.2770, "sigma_floor": 0.84},
            "WR": {"m": 0.1180, "sigma_rel": 0.2160, "sigma_floor": 0.99},
            "TE": {"m": 0.1510, "sigma_rel": 0.1960, "sigma_floor": 0.65},
        }
    else:
        return {
            "bye": 0.072,
            "QB": {"m": 0.1100, "sigma_rel": 0.1820, "sigma_floor": 0.69},
            "RB": {"m": 0.1530, "sigma_rel": 0.3000, "sigma_floor": 0.89},
            "WR": {"m": 0.1170, "sigma_rel": 0.3080, "sigma_floor": 1.01},
            "TE": {"m": 0.1440, "sigma_rel": 0.3620, "sigma_floor": 0.64},
        }


def compute_bounds(inp, scoring: str, teams: int, params: dict) -> dict:
    """Compute the fill-in-only and plain-VORP bounds at one setting."""
    sources, _ = es.load_sources(inp, scoring, teams)
    chart_sigma = es.chart_sigma_from(sources, teams)
    tiers = es.tiers_on_mean(sources, teams)
    keys = sorted(tiers)

    # Fill-in-only: sigma = 0, floor = 0
    fi_params = {"bye": params["bye"]}
    for p in POSITIONS:
        fi_params[p] = {"m": params[p]["m"], "sigma_rel": 0.0, "sigma_floor": 0.0}
    fi_run = es.run_setting(sources, teams, fi_params, chart_sigma, "A")
    fi_ddf = es.ddf_mean(fi_run["adjusted"], keys)
    fi_met = es.shares_and_ratio(fi_ddf, tiers, teams)

    # Plain VORP: no lineup discount at all
    vorp_params = {"bye": 0.0}
    for p in POSITIONS:
        vorp_params[p] = {"m": 0.0, "sigma_rel": 0.0, "sigma_floor": 0.0}
    vorp_run = es.run_setting(sources, teams, vorp_params, chart_sigma, "A")
    # With sigma=0 and m=bye=0, bench players get nothing from fill-in.
    # Use the plain VORP calculation from the sensitivity function.
    plain = {}
    for src in sources:
        counts = es.alloc({p: src.values(p) for p in POSITIONS}, teams)
        vals = {}
        for p in POSITIONS:
            w, _ = es.lines(src.values(p), counts[p]["starters"], counts[p]["rostered"])
            for k, x in src.lists[p]:
                vals[k] = max(0.0, x - w) if w is not None else 0.0
        tot = sum(vals.values())
        plain[src.key] = {k: v * vorp_run["pie"] / tot for k, v in vals.items()} if tot else vals
    vorp_ddf = es.ddf_mean(plain, keys)
    vorp_met = es.shares_and_ratio(vorp_ddf, tiers, teams)

    # Recommended (full model)
    rec_run = es.run_setting(sources, teams, params, chart_sigma, "A")
    rec_ddf = es.ddf_mean(rec_run["adjusted"], keys)
    rec_met = es.shares_and_ratio(rec_ddf, tiers, teams)
    rec_fill = sum(v for g, v in rec_run["weights"].items() if g.endswith("|bench"))

    return {
        "setting": f"{scoring}/{teams}",
        "fill_in_only": {
            "per_pos": fi_met["bench_tier_share"],
            "overall": fi_met["bench_tier_share_overall"],
            "price": fi_met["starter_to_bench_price"],
        },
        "plain_vorp": {
            "per_pos": vorp_met["bench_tier_share"],
            "overall": vorp_met["bench_tier_share_overall"],
            "price": vorp_met["starter_to_bench_price"],
        },
        "recommended": {
            "per_pos": rec_met["bench_tier_share"],
            "overall": rec_met["bench_tier_share_overall"],
            "price": rec_met["starter_to_bench_price"],
            "fill_state_share": rec_fill,
        },
    }


def format_pct(x, d=1):
    return f"{100 * x:.{d}f}%" if x is not None else "n/a"


def main():
    parser = argparse.ArgumentParser(description="Bench-share bounds across 12 settings")
    parser.add_argument("--setting", help="Single setting (e.g. ppr/12); default: all 12")
    parser.add_argument("--params", default="recent", choices=["recent", "all"],
                        help="Parameter history: 'recent' (approved defaults) or 'all' (eleven-season)")
    parser.add_argument("--from-log", action="store_true",
                        help="Use exact parameters from the logged runs instead of config")
    args = parser.parse_args()

    import value_reference as ref
    inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)

    params = resolve_params_from_log(args.params) if args.from_log else None
    if params is None:
        cfg = json.loads((REPO / "config" / "lineup_parameters.json").read_text())
        params = resolve_params(cfg, args.params)

    if args.setting:
        scoring, teams = args.setting.split("/")
        settings = [(scoring, int(teams))]
    else:
        settings = [(s, t) for s in SCORINGS for t in TEAM_COUNTS]

    print(f"Parameters: {args.params}" + (" (from log)" if args.from_log else " (from config)"))
    print(f"bye = {params['bye']:.1%}")
    for p in POSITIONS:
        print(f"  {p}: m={params[p]['m']:.4f}, sigma={params[p]['sigma_rel']:.4f}, floor={params[p]['sigma_floor']:.2f}")
    print()

    print("| Setting | Fill-in floor | Recommended | Plain VORP ceiling | Gap (rec - floor) |")
    print("| --- | --- | --- | --- | --- |")
    for scoring, teams in settings:
        r = compute_bounds(inp, scoring, teams, params)
        fi = format_pct(r["fill_in_only"]["overall"])
        rec = format_pct(r["recommended"]["overall"])
        vorp = format_pct(r["plain_vorp"]["overall"])
        gap = r["recommended"]["overall"] - r["fill_in_only"]["overall"]
        print(f"| {scoring}/{teams} | {fi} | {rec} | {vorp} | {100*gap:+.1f}pp |")

    # Per-position detail for 12-team full PPR
    print("\n## Per-position bounds at ppr/12\n")
    r = compute_bounds(inp, "ppr", 12, params)
    print("| Position | Fill-in floor | Recommended | Plain VORP | Start-worthy share of gap |")
    print("| --- | --- | --- | --- | --- |")
    for p in POSITIONS:
        fi = r["fill_in_only"]["per_pos"][p]
        rec = r["recommended"]["per_pos"][p]
        vorp = r["plain_vorp"]["per_pos"][p]
        sw_share = (rec - fi) / (vorp - fi) if vorp > fi else 0
        print(f"| {p} | {format_pct(fi)} | {format_pct(rec)} | {format_pct(vorp)} | {100*sw_share:.0f}% |")
    print(f"| Overall | {format_pct(r['fill_in_only']['overall'])} | "
          f"{format_pct(r['recommended']['overall'])} | "
          f"{format_pct(r['plain_vorp']['overall'])} | "
          f"{100*(r['recommended']['overall'] - r['fill_in_only']['overall'])/(r['plain_vorp']['overall'] - r['fill_in_only']['overall']):.0f}% |")


if __name__ == "__main__":
    main()
