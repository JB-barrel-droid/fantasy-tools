#!/usr/bin/env python3
"""JEG-969 step 4: 12-combo sweep comparing promotion model ON vs OFF.

Reports bench share readout, applied bench share, and top player
movements for each scoring x teams combination.

Usage:
    python3 tools/bench_research/promotion_sweep.py [--out /path/to/output.md]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipelines"))

import value_reference as vr  # noqa: E402

SCORINGS = ("standard", "half_ppr", "ppr")
TEAMS = (8, 10, 12, 14)


def run_setting(scoring: str, teams: int, promotion_model: bool = False):
    """Run one setting and return (result, diagnostics, bench_share_readout)."""
    inp = vr.Inputs.load()
    s = vr.Setting(inp, scoring, teams, promotion_model=promotion_model)
    res = s.result()
    diag = s.diagnostics()
    return res, diag


def compare_player_movements(res_off, res_on, top_n=10):
    """Find players whose DDF Value changes most with the promotion model."""
    moves = []
    for key in res_off["rows"]:
        off_row = res_off["rows"][key]
        on_row = res_on["rows"].get(key)
        if on_row is None:
            continue
        off_val = off_row["ddf"]["blended"]["value"]
        on_val = on_row["ddf"]["blended"]["value"]
        if off_val is None or on_val is None:
            continue
        delta = on_val - off_val
        if abs(delta) > 0.01:
            pos = off_row.get("pos") or on_row.get("pos", "?")
            name = off_row.get("name") or on_row.get("name") or str(key)
            moves.append({
                "key": key, "name": name, "pos": pos,
                "off": round(off_val, 2), "on": round(on_val, 2),
                "delta": round(delta, 2), "pct": round(100 * delta / off_val, 1) if off_val else 0,
            })
    moves.sort(key=lambda m: -abs(m["delta"]))
    return moves[:top_n]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="-", help="Output file (- for stdout)")
    args = parser.parse_args()

    lines = ["# JEG-969 step 4: promotion model 12-combo sweep", ""]
    lines.append("## Bench share comparison (flag OFF vs ON)")
    lines.append("")
    lines.append("| Scoring | Teams | BS Readout OFF | BS Readout ON | Delta | BS Applied OFF | BS Applied ON | Delta |")
    lines.append("|---|---|---|---|---|---|---|---|")

    all_moves = []
    for scoring in SCORINGS:
        for teams in TEAMS:
            res_off, diag_off = run_setting(scoring, teams, promotion_model=False)
            res_on, diag_on = run_setting(scoring, teams, promotion_model=True)

            bs_off = res_off["bench_share_readout"]["overall"]
            bs_on = res_on["bench_share_readout"]["overall"]
            bsa_off = res_off["bench_share_applied"]
            bsa_on = res_on["bench_share_applied"]
            bs_delta = bs_on - bs_off
            bsa_delta = bsa_on - bsa_off

            lines.append(f"| {scoring} | {teams} | {100*bs_off:.2f}% | {100*bs_on:.2f}% | "
                         f"{100*bs_delta:+.2f}pp | {100*bsa_off:.2f}% | {100*bsa_on:.2f}% | "
                         f"{100*bsa_delta:+.2f}pp |")

            moves = compare_player_movements(res_off, res_on)
            if moves:
                all_moves.append((scoring, teams, moves))

    # Position-level bench share comparison for ppr/12
    lines.append("")
    lines.append("## Position-level bench share (ppr/12)")
    lines.append("")
    res_off, _ = run_setting("ppr", 12, promotion_model=False)
    res_on, _ = run_setting("ppr", 12, promotion_model=True)
    bs_off = res_off["bench_share_readout"]
    bs_on = res_on["bench_share_readout"]
    lines.append("| Position | OFF | ON | Delta |")
    lines.append("|---|---|---|---|")
    for pos in ("QB", "RB", "WR", "TE"):
        off_v = bs_off.get(pos, 0)
        on_v = bs_on.get(pos, 0)
        lines.append(f"| {pos} | {100*off_v:.2f}% | {100*on_v:.2f}% | {100*(on_v-off_v):+.2f}pp |")
    lines.append(f"| Overall | {100*bs_off['overall']:.2f}% | {100*bs_on['overall']:.2f}% | "
                 f"{100*(bs_on['overall']-bs_off['overall']):+.2f}pp |")

    # Player movements
    if all_moves:
        lines.append("")
        lines.append("## Top player DDF Value movements (ppr/12)")
        lines.append("")
        _, _, moves = next((s, t, m) for s, t, m in all_moves if s == "ppr" and t == 12)
        lines.append("| Player | Pos | OFF | ON | Delta | % |")
        lines.append("|---|---|---|---|---|---|")
        for m in moves:
            lines.append(f"| {m['name']} | {m['pos']} | {m['off']} | {m['on']} | "
                         f"{m['delta']:+.2f} | {m['pct']:+.1f}% |")

    output = "\n".join(lines) + "\n"
    if args.out == "-":
        print(output)
    else:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Written to {args.out}")


if __name__ == "__main__":
    main()
