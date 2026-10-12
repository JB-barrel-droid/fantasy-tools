#!/usr/bin/env python3
"""What a backup running back scores when his team's lead back misses (JEG-525 item a).

From data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz and the schedule:
for each team-season, the lead back (RB1) and the backup (RB2) are the two
running backs with the most full-PPR points on that team over weeks 1-9
(at least 3 games each; the lead back must have played the team's last game
of the window, the same "healthy at valuation" rule as ES-1). Over weeks 10
to the season's last week minus one, each team game is split into "lead back
played" and "lead back missed". Reported: the backup's mean points per game
in each state, the jump, and how often the jump lands him above the 12-team
starter line (RB31 points per game in the same season, weeks 1-9) and the
waiver line (RB55).

This is the measured size of the contingency a handcuff is held for. The
expected-starts share (ES-4) does not contain it: it puts a symmetric bell
curve on the backup's own projection, which cannot produce a jump this size.

Usage: python3 tools/handcuff_jump.py [--report output/handcuff-jump.md]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
import derive_lineup_parameters as dl  # noqa: E402

SEL = (1, 9)


def analyse(actuals, schedule, scoring="ppr"):
    rows = []
    lines = {}
    for season in dl.HISTORY_SEASONS:
        last = dl.last_measured_week(schedule, season)
        sched = schedule[season]
        sel, sel_teams = dl._player_weeks(actuals, season, SEL[0], SEL[1], scoring)
        meas, meas_teams = dl._player_weeks(actuals, season, SEL[1] + 1, last, scoring)
        rb_ppg = sorted((statistics.mean(v.values()) for k, v in sel.items()
                         if k[1] == "RB" and len(v) >= dl.MIN_GAMES), reverse=True)
        starter_line, waiver_line = rb_ppg[30], rb_ppg[54]
        lines[season] = (starter_line, waiver_line)
        by_team = defaultdict(list)
        for k, v in sel.items():
            if k[1] != "RB" or len(v) < dl.MIN_GAMES:
                continue
            team = sel_teams[k].most_common(1)[0][0]
            by_team[team].append((sum(v.values()), k, v))
        for team, cands in by_team.items():
            if team not in sched or len(cands) < 2:
                continue
            cands.sort(key=lambda c: -c[0])
            (_, k1, v1), (_, k2, v2) = cands[0], cands[1]
            team_sel = [w for w in sched[team] if w <= SEL[1]]
            if not team_sel or team_sel[-1] not in v1:
                continue
            # both must still be on this team in the measured window
            if meas_teams.get(k2) and meas_teams[k2].most_common(1)[0][0] != team:
                continue
            games = [w for w in sched[team] if SEL[1] + 1 <= w <= last]
            m1 = meas.get(k1, {})
            m2 = meas.get(k2, {})
            with_lead = [m2[w] for w in games if w in m1 and w in m2]
            without = [m2[w] for w in games if w not in m1 and w in m2]
            rows.append({"season": season, "team": team, "rb1_sel_ppg": statistics.mean(v1.values()),
                         "rb2_sel_ppg": statistics.mean(v2.values()),
                         "with_lead": with_lead, "without": without,
                         "starter_line": starter_line, "waiver_line": waiver_line})
    return rows, lines


def summarize(rows):
    w = [x for r in rows for x in r["with_lead"]]
    wo = [x for r in rows for x in r["without"]]
    # per backup, mean in each state, only where both states exist
    paired = [(statistics.mean(r["with_lead"]), statistics.mean(r["without"]), r)
              for r in rows if r["with_lead"] and r["without"]]
    above_start = sum(1 for _, b, r in paired if b > r["starter_line"])
    above_waiver_before = sum(1 for a, _, r in paired if a > r["waiver_line"])
    jump = [b - a for a, b, _ in paired]
    # the same split for backups behind a top-12 lead back
    top = [(a, b, r) for a, b, r in paired if r["rb1_sel_ppg"] >= sorted([q["rb1_sel_ppg"] for q in rows if q["season"] == r["season"]], reverse=True)[min(11, len([q for q in rows if q["season"] == r["season"]]) - 1)]]
    return {
        "team_seasons": len(rows),
        "games_with_lead": len(w), "games_without_lead": len(wo),
        "rb2_ppg_with_lead": statistics.mean(w), "rb2_ppg_without_lead": statistics.mean(wo),
        "paired_backups": len(paired),
        "median_jump": statistics.median(jump), "mean_jump": statistics.mean(jump),
        "share_above_starter_line_when_lead_out": above_start / len(paired),
        "share_above_waiver_line_with_lead": above_waiver_before / len(paired),
        "top12_paired": len(top),
        "top12_rb2_ppg_with": statistics.mean(a for a, _, _ in top) if top else None,
        "top12_rb2_ppg_without": statistics.mean(b for _, b, _ in top) if top else None,
        "top12_share_above_starter_line": (sum(1 for _, b, r in top if b > r["starter_line"]) / len(top)) if top else None,
        "mean_starter_line": statistics.mean(r["starter_line"] for r in rows),
        "mean_waiver_line": statistics.mean(r["waiver_line"] for r in rows),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=REPO / "output" / "handcuff-jump.md")
    ap.add_argument("--out", type=Path, default=REPO / "output" / "handcuff-jump.json")
    args = ap.parse_args(argv)
    rows, _ = analyse(dl.load_actuals_nflverse(), dl.load_schedule(dl.HISTORY_SCHEDULE))
    s = summarize(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(s, indent=1), encoding="utf-8")
    L = ["# Backup running back when the lead back misses (nflverse 2015-2025, full PPR)", "",
         f"Team-seasons: {s['team_seasons']}. Backup games with the lead back playing: {s['games_with_lead']}; "
         f"with the lead back out: {s['games_without_lead']}.", "",
         f"- Backup points per game, lead back playing: {s['rb2_ppg_with_lead']:.1f}",
         f"- Backup points per game, lead back out: {s['rb2_ppg_without_lead']:.1f}",
         f"- Median jump per backup (both states observed, {s['paired_backups']} backups): {s['median_jump']:+.1f}",
         f"- Share of those backups above the 12-team starter line (RB31, mean {s['mean_starter_line']:.1f}) when the lead back is out: "
         f"{100 * s['share_above_starter_line_when_lead_out']:.0f}%",
         f"- Share above the waiver line (RB55, mean {s['mean_waiver_line']:.1f}) with the lead back playing: "
         f"{100 * s['share_above_waiver_line_with_lead']:.0f}%",
         f"- Behind a top-12 lead back ({s['top12_paired']} backups): {s['top12_rb2_ppg_with']:.1f} -> "
         f"{s['top12_rb2_ppg_without']:.1f} points per game; above the starter line when the lead back is out: "
         f"{100 * s['top12_share_above_starter_line']:.0f}%"]
    args.report.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
