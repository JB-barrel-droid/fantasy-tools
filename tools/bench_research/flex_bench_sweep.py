#!/usr/bin/env python3
"""MR-28 / JEG-969: 12-combo sweep comparing flex_bench_seats ON vs OFF.

Reports bench seat allocation, bench share readout, position weights,
and top player value movements for each scoring x teams combination.

Usage:
    python3 tools/bench_research/flex_bench_sweep.py [--out /path/to/output.md]
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


def run_setting(scoring: str, teams: int, flex_bench_seats: bool = False,
                superflex: int = 0):
    """Run one setting and return (result, diagnostics)."""
    inp = vr.Inputs.load()
    s = vr.Setting(inp, scoring, teams, superflex=superflex,
                   flex_bench_seats=flex_bench_seats)
    res = s.result()
    diag = s.diagnostics()
    return res, diag


def bench_alloc_summary(res):
    """Extract bench seat counts per position from slot_fill."""
    sf = res.get("slot_fill", {})
    return {p: sf.get(p, {}).get("bench", 0) for p in ("QB", "RB", "WR", "TE")}


def compare_player_movements(res_off, res_on, top_n=15):
    """Find players whose DDF Value changes most."""
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
                "delta": round(delta, 2),
                "pct": round(100 * delta / off_val, 1) if off_val else 0,
            })
    moves.sort(key=lambda m: -abs(m["delta"]))
    return moves[:top_n]


def tier_changes(res_off, res_on):
    """Count players whose Buy/Sell tier changes."""
    changes = {"promoted": 0, "demoted": 0, "total": 0}
    tiers_off = {}
    tiers_on = {}
    for key, row in res_off["rows"].items():
        t = row.get("tier")
        if t:
            tiers_off[key] = t
    for key, row in res_on["rows"].items():
        t = row.get("tier")
        if t:
            tiers_on[key] = t
    for key in set(tiers_off) & set(tiers_on):
        if tiers_off[key] != tiers_on[key]:
            changes["total"] += 1
    return changes


def main():
    out_path = None
    if "--out" in sys.argv:
        out_path = sys.argv[sys.argv.index("--out") + 1]

    lines = ["# MR-28: flex_bench_seats impact sweep\n"]
    lines.append("Comparing bench_seats() with and without flex_filled starters.\n")
    lines.append("When flex_bench_seats=True, bench-seat weights count superflex+flex")
    lines.append("starters (matching allocate_league in the ES model).\n")

    all_combos = []
    for scoring in SCORINGS:
        for teams in TEAMS:
            label = f"{scoring}/{teams}"
            print(f"  {label} ...", end=" ", flush=True)
            res_off, diag_off = run_setting(scoring, teams, flex_bench_seats=False)
            res_on, diag_on = run_setting(scoring, teams, flex_bench_seats=True)

            bench_off = bench_alloc_summary(res_off)
            bench_on = bench_alloc_summary(res_on)
            bs_off = res_off.get("bench_share_readout", {})
            bs_on = res_on.get("bench_share_readout", {})
            movers = compare_player_movements(res_off, res_on)
            tiers = tier_changes(res_off, res_on)

            combo = {
                "label": label, "scoring": scoring, "teams": teams,
                "bench_off": bench_off, "bench_on": bench_on,
                "bs_off": bs_off, "bs_on": bs_on,
                "movers": movers, "tier_changes": tiers,
                "fpi_off": diag_off.get("fixedPieIndexed", {}),
                "fpi_on": diag_on.get("fixedPieIndexed", {}),
            }
            all_combos.append(combo)
            print("done")

    # Also do superflex
    print("  ppr/12 superflex ...", end=" ", flush=True)
    res_off_sf, diag_off_sf = run_setting("ppr", 12, flex_bench_seats=False, superflex=1)
    res_on_sf, diag_on_sf = run_setting("ppr", 12, flex_bench_seats=True, superflex=1)
    sf_combo = {
        "label": "ppr/12/SF", "scoring": "ppr", "teams": 12,
        "bench_off": bench_alloc_summary(res_off_sf),
        "bench_on": bench_alloc_summary(res_on_sf),
        "bs_off": res_off_sf.get("bench_share_readout", {}),
        "bs_on": res_on_sf.get("bench_share_readout", {}),
        "movers": compare_player_movements(res_off_sf, res_on_sf),
        "tier_changes": tier_changes(res_off_sf, res_on_sf),
        "fpi_off": diag_off_sf.get("fixedPieIndexed", {}),
        "fpi_on": diag_on_sf.get("fixedPieIndexed", {}),
    }
    all_combos.append(sf_combo)
    print("done")

    # Write summary
    lines.append("\n## Bench seat allocation changes\n")
    lines.append("| Setting | QB off->on | RB off->on | WR off->on | TE off->on |")
    lines.append("|---------|-----------|-----------|-----------|-----------|")
    for c in all_combos:
        row = f"| {c['label']}"
        for pos in ("QB", "RB", "WR", "TE"):
            off_v = c["bench_off"].get(pos, 0)
            on_v = c["bench_on"].get(pos, 0)
            marker = " **" if off_v != on_v else ""
            row += f" | {off_v}->{on_v}{marker}"
        row += " |"
        lines.append(row)

    lines.append("\n## Bench share readout changes\n")
    lines.append("| Setting | Overall off | Overall on | Delta |")
    lines.append("|---------|------------|------------|-------|")
    for c in all_combos:
        off_o = c["bs_off"].get("overall")
        on_o = c["bs_on"].get("overall")
        if off_o is not None and on_o is not None:
            delta = on_o - off_o
            lines.append(f"| {c['label']} | {off_o:.4f} | {on_o:.4f} | {delta:+.4f} |")
        else:
            lines.append(f"| {c['label']} | N/A | N/A | N/A |")

    lines.append("\n## Per-position bench share\n")
    lines.append("| Setting | QB off/on | RB off/on | WR off/on | TE off/on |")
    lines.append("|---------|----------|----------|----------|----------|")
    for c in all_combos:
        row = f"| {c['label']}"
        for pos in ("QB", "RB", "WR", "TE"):
            off_v = c["bs_off"].get(pos)
            on_v = c["bs_on"].get(pos)
            if off_v is not None and on_v is not None:
                row += f" | {off_v:.3f}/{on_v:.3f}"
            else:
                row += " | N/A"
        row += " |"
        lines.append(row)

    lines.append("\n## fixedPieIndexed invariant\n")
    all_pass = True
    for c in all_combos:
        fpi_off = c["fpi_off"]
        fpi_on = c["fpi_on"]
        off_ok = all(v.get("ok", False) for v in fpi_off.values()) if fpi_off else True
        on_ok = all(v.get("ok", False) for v in fpi_on.values()) if fpi_on else True
        status = "PASS" if (off_ok and on_ok) else "FAIL"
        if status == "FAIL":
            all_pass = False
        lines.append(f"- {c['label']}: {status}")
    lines.append(f"\nAll pass: {'YES' if all_pass else 'NO'}")

    lines.append("\n## Top movers (ppr/12, representative)\n")
    ppr12 = next((c for c in all_combos if c["label"] == "ppr/12"), None)
    if ppr12 and ppr12["movers"]:
        lines.append("| Rank | Name | Pos | Off | On | Delta | Pct |")
        lines.append("|------|------|-----|-----|-----|-------|-----|")
        for i, m in enumerate(ppr12["movers"], 1):
            lines.append(f"| {i} | {m['name']} | {m['pos']} | {m['off']} | {m['on']} | {m['delta']:+.2f} | {m['pct']:+.1f}% |")
    else:
        lines.append("No movers above threshold.")

    lines.append("\n## Movement summary\n")
    lines.append("| Setting | Players moved (>0.01) | Tier changes |")
    lines.append("|---------|----------------------|--------------|")
    for c in all_combos:
        n_moved = len([1 for key in (next(iter(c.get("movers", [])), {}) or {}) if True])
        # Recount from actual data
        n_moved = len(c["movers"])
        lines.append(f"| {c['label']} | {n_moved}+ | {c['tier_changes']['total']} |")

    text = "\n".join(lines)
    print(text)
    if out_path:
        Path(out_path).write_text(text)
        print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
