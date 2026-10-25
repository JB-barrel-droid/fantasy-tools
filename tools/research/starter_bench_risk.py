#!/usr/bin/env python3
"""Starter-vs-bench risk table: bench upside, starter downside, net, per position.

Uses the existing expected-starts model (no engine changes) to break out:
- For each starter: the probability-weighted value lost when projection
  uncertainty places them below the starter line (downside).
- For each bench player: the probability-weighted value gained when projection
  uncertainty places them above the starter line (upside).
- Net per position: sum of bench upside minus sum of starter downside.

Output: docs/research/data/starter_bench_risk.md and .json.

JEG-544 / JEG-550. Research only.

Usage:
    python3 tools/research/starter_bench_risk.py [--scoring ppr] [--teams 12]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines"))
import expected_starts_model as es  # noqa: E402

POSITIONS = es.POSITIONS
OUT_DIR = REPO / "docs" / "research" / "data"


def compute_risk_table(scoring: str = "ppr", teams: int = 12) -> dict:
    """Compute starter downside and bench upside per position."""
    import value_reference as ref

    inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
    hist = ref.History(ref.HISTORY) if ref.HISTORY.exists() else None
    params = es.load_params()
    sources, pos_of = es.load_sources(inp, scoring, teams)
    chart_sigma = es.chart_sigma_from(sources, teams)

    # Run the model (variant A = expected starts, form = share)
    run = es.run_setting(sources, teams, params, chart_sigma, "A", "share")

    # Get DDF mean values and tiers
    all_keys = set()
    for src in sources:
        for p in POSITIONS:
            all_keys.update(src.keys(p))
    ddf = es.ddf_mean(run["adjusted"], sorted(all_keys))
    ddf_tiers = es.tiers_on_values(
        {k: v for k, v in ddf.items() if v is not None}, pos_of, teams)

    # Now compute per-position risk from the model's components
    # We need per-source position_components to get the starter/bench parts
    # The key insight: for each player, position_components gives us
    # starter_part (value from being above the line) and bench_part (fill-in value).
    # For starters: their "lost" value = v * avail - (starter_part + bench_part)
    #   i.e., the gap between full availability and what the model gives them
    # For bench: their upside = starter_part (the portion above the line)

    results = {}
    for p in POSITIONS:
        starter_downside_total = 0.0
        bench_upside_total = 0.0
        starter_count = 0
        bench_count = 0
        starter_details = []
        bench_details = []

        # Use the blended (DDF) values to identify who is starter vs bench
        # But we need the raw components. Let's compute from the mean projection.
        # Actually, let's use the per-source average.
        src_components = []
        for src in sources:
            counts = es.alloc({q: src.values(q) for q in POSITIONS}, teams)
            pp = params[p]
            comp = es.position_components(
                src.values(p), counts[p]["starters"], counts[p]["rostered"],
                teams, pp["m"], params["bye"], pp["sigma_rel"], pp["sigma_floor"],
                form="share")
            src_components.append((src, counts, comp))

        # Average across sources: for each rank position, average the components
        # Use the first source's structure to identify starters vs bench
        if not src_components:
            results[p] = {"starter_downside": 0, "bench_upside": 0, "net": 0,
                          "starter_count": 0, "bench_count": 0}
            continue

        # Get the number of starters and rostered from convention allocation
        # (should be the same across sources for the same position)
        first_counts = src_components[0][1][p]
        n_starters = first_counts["starters"]
        n_rostered = first_counts["rostered"]

        # For each rank index, average the components
        max_players = min(len(c[2]["players"]) for c in src_components) if src_components else 0
        pie = es.PIE_PER_STARTING_SLOT * teams * es._starters_per_team()

        for i in range(max_players):
            # Average across sources
            avg_v = sum(c[2]["players"][i]["v"] for c in src_components) / len(src_components)
            avg_sp = sum(c[2]["players"][i]["starter_part"] for c in src_components) / len(src_components)
            avg_bp = sum(c[2]["players"][i]["bench_part"] for c in src_components) / len(src_components)
            avg_share = (avg_sp + avg_bp) / avg_v if avg_v > 0 else 0
            avg_avail = sum(c[2]["avail"] for c in src_components) / len(src_components)

            is_starter = i < n_starters
            if is_starter:
                # Starter downside: the value they lose due to projection uncertainty
                # pushing them below the line. Full value at availability = v * avail.
                # Model gives them starter_part + bench_part.
                # Downside = v * avail - (starter_part + bench_part)
                full_value = avg_v * avg_avail
                model_value = avg_sp + avg_bp
                downside = full_value - model_value
                if downside > 0:
                    starter_downside_total += downside
                starter_count += 1
                starter_details.append({
                    "rank": i + 1,
                    "value": round(avg_v, 2),
                    "full_avail_value": round(full_value, 2),
                    "model_value": round(model_value, 2),
                    "downside": round(max(0, downside), 2),
                    "share": round(avg_share, 4),
                })
            elif i < n_rostered:
                # Bench player upside: their starter_part
                bench_upside_total += avg_sp
                bench_count += 1
                bench_details.append({
                    "rank": i + 1,
                    "value": round(avg_v, 2),
                    "starter_part": round(avg_sp, 2),
                    "bench_part": round(avg_bp, 2),
                    "share": round(avg_share, 4),
                })

        results[p] = {
            "starter_downside": round(starter_downside_total, 2),
            "bench_upside": round(bench_upside_total, 2),
            "net": round(bench_upside_total - starter_downside_total, 2),
            "starter_count": starter_count,
            "bench_count": bench_count,
            "starter_downside_pct_of_pie": round(starter_downside_total / pie * 100, 2) if pie else 0,
            "bench_upside_pct_of_pie": round(bench_upside_total / pie * 100, 2) if pie else 0,
            "starters": starter_details,
            "bench": bench_details,
        }

    # Overall
    total_sd = sum(r["starter_downside"] for r in results.values())
    total_bu = sum(r["bench_upside"] for r in results.values())
    results["overall"] = {
        "starter_downside": round(total_sd, 2),
        "bench_upside": round(total_bu, 2),
        "net": round(total_bu - total_sd, 2),
        "starter_downside_pct_of_pie": round(total_sd / pie * 100, 2) if pie else 0,
        "bench_upside_pct_of_pie": round(total_bu / pie * 100, 2) if pie else 0,
    }

    return {"setting": {"scoring": scoring, "teams": teams}, "pie": round(pie, 1),
            "positions": results}


def write_outputs(data: dict):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # JSON
    (OUT_DIR / "starter_bench_risk.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # Markdown summary
    lines = [
        "# Starter-vs-bench risk table",
        "",
        f"Setting: {data['setting']['scoring']} / {data['setting']['teams']} teams. "
        f"Pie: {data['pie']} points.",
        "",
        "| Position | Starter downside | Bench upside | Net | Starter downside (% pie) | Bench upside (% pie) |",
        "|---|---|---|---|---|---|",
    ]
    for p in list(POSITIONS) + ["overall"]:
        r = data["positions"][p]
        label = p if p != "overall" else "**Overall**"
        lines.append(
            f"| {label} | {r['starter_downside']:.1f} | {r['bench_upside']:.1f} | "
            f"{r['net']:.1f} | {r['starter_downside_pct_of_pie']:.2f}% | "
            f"{r['bench_upside_pct_of_pie']:.2f}% |"
        )
    lines.append("")
    lines.append("Starter downside: value starters lose because projection uncertainty can push them below the starter line.")
    lines.append("Bench upside: value bench players gain because projection uncertainty can push them above the starter line.")
    lines.append("Net: bench upside minus starter downside.")
    lines.append("")
    lines.append(f"Generated by `tools/research/starter_bench_risk.py` on the current engine.")
    lines.append("")

    (OUT_DIR / "starter_bench_risk.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote starter_bench_risk.json and .md to docs/research/data/")


def main():
    parser = argparse.ArgumentParser(description="Starter-vs-bench risk table")
    parser.add_argument("--scoring", default="ppr")
    parser.add_argument("--teams", type=int, default=12)
    args = parser.parse_args()

    data = compute_risk_table(args.scoring, args.teams)
    write_outputs(data)

    # Print summary
    print()
    for p in list(POSITIONS) + ["overall"]:
        r = data["positions"][p]
        print(f"{p:>8}: starter_down={r['starter_downside']:6.1f}  bench_up={r['bench_upside']:6.1f}  net={r['net']:6.1f}")


if __name__ == "__main__":
    main()
