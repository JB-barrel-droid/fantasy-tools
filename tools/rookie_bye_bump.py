#!/usr/bin/env python3
"""Is there a post-bye rookie bump? (Jeremy, JEG-525 2026-10-09; MR-22)

nflverse 2016-2025 (2015 is the first season in the file, so its rookies
cannot be told apart). A rookie is a player whose first row in the file is
that season. For each RB/WR/TE with at least 3 games before and 3 games after
his team's bye (weeks 1 .. last week minus one), the change in full-PPR
points per game after the bye. The bump is the rookies' change minus the
veterans' change (difference in differences), with a player-bootstrap 95%
interval. Both groups carry the same selection (they kept playing after the
bye), so the comparison isolates what is special about rookies.

Usage: python3 tools/rookie_bye_bump.py [--report output/rookie-bye-bump.md]
"""
from __future__ import annotations

import argparse
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
import derive_lineup_parameters as dl  # noqa: E402


def changes(actuals, schedule):
    first = {}
    for r in actuals:
        k = r["player_key"]
        first[k] = min(first.get(k, 9999), r["season"])
    games = defaultdict(dict)
    team = defaultdict(lambda: defaultdict(int))
    for r in actuals:
        if r["pos"] in ("RB", "WR", "TE"):
            games[(r["player_key"], r["season"], r["pos"])][r["week"]] = r["pts"]["ppr"]
            team[(r["player_key"], r["season"], r["pos"])][r["team"]] += 1
    out = []
    for key, wk in games.items():
        pid, season, pos = key
        if season < 2016:
            continue
        sched = schedule[season]
        t = max(team[key], key=team[key].get)
        if t not in sched:
            continue
        last = max(w for weeks in sched.values() for w in weeks) - 1
        played = set(sched[t])
        byes = [w for w in range(1, last + 1) if w not in played]
        if len(byes) != 1:
            continue
        bye = byes[0]
        pre = [v for w, v in wk.items() if w < bye]
        post = [v for w, v in wk.items() if bye < w <= last]
        if len(pre) < 3 or len(post) < 3:
            continue
        out.append({"rookie": first[pid] == season, "pos": pos, "season": season,
                    "pre": statistics.mean(pre), "post": statistics.mean(post), "bye": bye})
    return out


def did(rows, rng=None, boot=2000):
    rk = [r["post"] - r["pre"] for r in rows if r["rookie"]]
    vt = [r["post"] - r["pre"] for r in rows if not r["rookie"]]
    est = statistics.mean(rk) - statistics.mean(vt)
    rng = rng or random.Random(525)
    bs = sorted(statistics.mean(rng.choices(rk, k=len(rk))) - statistics.mean(rng.choices(vt, k=len(vt)))
                for _ in range(boot))
    return {"rookies": len(rk), "veterans": len(vt), "rookie_change": statistics.mean(rk),
            "veteran_change": statistics.mean(vt), "bump": est,
            "ci95": [bs[int(.025 * boot)], bs[int(.975 * boot) - 1]],
            "rookie_pre": statistics.mean(r["pre"] for r in rows if r["rookie"])}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=REPO / "output" / "rookie-bye-bump.md")
    args = ap.parse_args(argv)
    rows = changes(dl.load_actuals_nflverse(), dl.load_schedule(dl.HISTORY_SCHEDULE))
    L = ["# Post-bye rookie bump (nflverse 2016-2025, full PPR, RB/WR/TE with 3+ games each side of the bye)", "",
         "| Group | Rookies | Veterans | Rookie change after bye | Veteran change | Bump (difference) | 95% interval |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
    groups = [("all", rows)] + [(p, [r for r in rows if r["pos"] == p]) for p in ("RB", "WR", "TE")]
    # Level-matched: low pre-bye scorers regress up and high ones down for
    # everyone, so compare rookies with veterans at the same pre-bye level.
    for lo, hi in ((0, 4), (4, 8), (8, 99)):
        label = f"pre-bye {lo}-{hi} points per game" if hi < 99 else f"pre-bye {lo}+ points per game"
        groups.append((label, [r for r in rows if lo <= r["pre"] < hi]))
    for label, g in groups:
        d = did(g)
        L.append(f"| {label} | {d['rookies']} | {d['veterans']} | {d['rookie_change']:+.2f} | {d['veteran_change']:+.2f} | "
                 f"{d['bump']:+.2f} | {d['ci95'][0]:+.2f} to {d['ci95'][1]:+.2f} |")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
