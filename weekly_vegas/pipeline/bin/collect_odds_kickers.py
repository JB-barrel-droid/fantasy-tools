#!/usr/bin/env python3
"""Odds API kicker markets collector (quota-capped, fail-closed).

Pulls player kicking-points / field-goals / PATs markets for NFL games from
The Odds API. This gives kickers a REAL weekly Vegas leg (unlike DST, which
has no direct market and must be derived from team totals).

Markets (verified live 2026-09-16, Week 2):
  - player_kicking_points (+ alternates)
  - player_field_goals (+ alternates)
  - player_pats (+ alternates)
Books observed: DraftKings, BetMGM, Bovada (kicking points).

Quota model: /v4/sports/{sport}/events/{eventId}/odds costs
(unique markets WITH data) x (regions). 3 kicker markets x 1 region
(us) = ~3 credits per game with data, ~48 for a full 16-game slate.
Books do not add cost.

QUOTA GUARD: refuses to spend when remaining < QUOTA_RESERVE (60). The
reserve protects the core Wednesday/Sunday prop snapshots. As of 2026-09-16
the account sat at 58/500 (below reserve) after research spent 7 credits --
do NOT run live pulls until the quota resets or the user raises the budget.

Usage:
  collect_odds_kickers.py --week 2 [--dry-run] [--out DIR]

--dry-run lists the events and markets it WOULD pull (free: events endpoint
costs 0) without spending quota. Default is live (guarded).

Output: lottery/data/odds_kickers_<week>.json:
  {event_id, home, away, commence_time, markets: {market_key: {book: [
     {name, line, over_price, under_price}]}}}
plus quota before/after from the x-requests-* headers.

Downstream: the kicker opportunity model (Upright logic) consumes the
consensus kicking-points line per kicker as the market-implied expectation,
blended with team implied total + red-zone stall rate.
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/workspace/skills/the-odds-api/bin"))
import oddsclient  # noqa: E402

KICKER_MARKETS = ["player_kicking_points", "player_field_goals", "player_pats"]
QUOTA_RESERVE = 60
QUOTA_FILE = os.path.expanduser(
    "~/workspace/football-signal/data/odds_cache/quota.json")
OUT_DIR = Path("/home/hatch/workspace/goals/football-signal-database-and-app"
               "/lottery/data")


def quota_remaining():
    try:
        return int(json.load(open(QUOTA_FILE)).get("remaining", 500))
    except Exception:
        return 500


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="list events/markets without spending quota")
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args()

    events, _ = oddsclient.events()  # free endpoint
    now = datetime.now(timezone.utc)
    evs = [e for e in events
           if (datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
               - now).total_seconds() < 8 * 86400]
    cost_est = len(evs) * len(KICKER_MARKETS)  # 1 region
    print(f"{len(evs)} upcoming events; est. cost {cost_est} credits; "
          f"cached remaining {quota_remaining()}")

    if args.dry_run:
        for e in evs:
            print(f"  {e['id'][:8]} {e['away_team']} @ {e['home_team']} "
                  f"{e['commence_time']}")
        print(f"dry-run: would pull {', '.join(KICKER_MARKETS)} "
              f"for {len(evs)} events (~{cost_est} credits)")
        return 0

    if quota_remaining() < QUOTA_RESERVE + cost_est:
        print(f"FAIL-CLOSED: quota guard refuses the pull "
              f"(remaining {quota_remaining()} < reserve {QUOTA_RESERVE} + "
              f"est {cost_est}). Run --dry-run or wait for reset.",
              file=sys.stderr)
        return 2

    out = {"week": args.week, "fetched": date.today().isoformat(),
           "markets": KICKER_MARKETS, "events": []}
    for e in evs:
        data, quota = oddsclient.event_odds(e["id"], KICKER_MARKETS)
        mkts = {}
        for bm in data.get("bookmakers", []):
            for m in bm.get("markets", []):
                mkts.setdefault(m["key"], {})[bm["key"]] = [
                    {"name": o.get("description") or o.get("name"),
                     "line": o.get("point"),
                     "over_price": next(
                         (x["price"] for x in o.get("outcomes", [])
                          if x["name"] == "Over"), None),
                     "under_price": next(
                         (x["price"] for x in o.get("outcomes", [])
                          if x["name"] == "Under"), None)}
                    for o in m.get("outcomes", [])]
        out["events"].append({
            "event_id": e["id"], "home": e["home_team"], "away": e["away_team"],
            "commence_time": e["commence_time"], "markets": mkts,
            "quota_after": quota.get("x-requests-remaining")})
        have = [k for k in KICKER_MARKETS if k in mkts]
        print(f"  {e['away_team']} @ {e['home_team']}: "
              f"{', '.join(have) or 'no kicker markets'} "
              f"(quota {quota.get('x-requests-remaining')})")

    fp = Path(args.out) / f"odds_kickers_{args.week}.json"
    fp.write_text(json.dumps(out, indent=1))
    print(f"wrote {fp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
