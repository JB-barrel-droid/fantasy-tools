#!/usr/bin/env python3
"""Backfill no-market-read flags for a week WITHOUT touching post_queue.

Loads the same inputs as v4/compute_v4.py (ECR feed projections, ECR
ranks, week-scoped props) and persists the flags to no_market_read_flags.
Used for the preliminary Week 1 backfill (2026-09-12) and any manual
re-runs. The Sunday weekly chain persists flags via compute_v4.main().

Usage: python3 bin/backfill_no_market_read.py [--week N] [--season 2026]
"""
import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_signals/pipeline root
sys.path.insert(0, BASE)

from v4.compute_v4 import load_props, load_ecr  # noqa: E402
from loaders.fantasypros import read_projections_dict  # noqa: E402
from engine.snapshot import load_week_games  # noqa: E402
from engine import no_market_read as nmr  # noqa: E402


def main(week, season):
    from engine.week import current_week
    week = week or current_week(season)
    print(f"week: {week} | season: {season}", flush=True)
    ecr_proj = read_projections_dict(week)
    print("ECR expert projections:", len(ecr_proj), flush=True)
    ecr_by_pos, meta, official = load_ecr()
    games_by_id, _ = load_week_games(season, week)
    player_props, _td_cover, prop_meta = load_props(game_ids=set(games_by_id))
    print("prop players:", len(player_props),
          "| market as-of:", prop_meta.get("latest_at"), flush=True)
    flags = nmr.compute_flags(ecr_proj, meta, official, ecr_by_pos,
                              player_props, prop_meta.get("latest_at"),
                              started_teams=nmr.started_teams_for_week(
                                  season, week))
    n = nmr.persist_flags(flags, season, week)
    print(f"persisted {n} no-market-read flags for wk{week}", flush=True)
    print("\n=== NO-MARKET-READ (preliminary) ===")
    for f in flags:
        print(f"{f['name']} ({f['team']} {f['pos']}): "
              f"ECR {f['expert_ppr']:.1f} PPR, {f['ecr_official']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--season", type=int, default=2026)
    a = ap.parse_args()
    main(a.week, a.season)
