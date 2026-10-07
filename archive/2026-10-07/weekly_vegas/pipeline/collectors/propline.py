#!/usr/bin/env python3
"""PropLine player-prop collector — the PRIMARY raw-price leg.

Pulls the current NFL event slate from PropLine, then per-game player
props for the prop markets our translation consumes. Writes one
Odds-API-compatible JSON per game:

    data/propline_cache/props_{event_id}.json

Each file has the shape The Odds API uses so downstream readers can be
shared::

    {"id","sport_key","commence_time","home_team","away_team",
     "bookmakers":[{"key","title","last_update",
        "markets":[{"key","last_update",
          "outcomes":[{"name","description","price","point"}]}]}]}

A run manifest is written to data/propline_cache/pull_meta.json with the
pull timestamp, week, games, request count and the bookmakers requested.

Week scoping uses the same NFL-week window as lottery/bin/driving_prop.py
(Tuesday 00:00 -> next Tuesday 00:00, America/Chicago). Quota: 1 events
call + 1 odds call per game (~16 calls/week), far under PropLine's
1,000/day free tier.

2026-09-18 fixes: refresh is the DEFAULT (recurring pulls re-fetch
current prices; --skip-cached for fill-gaps mode only); full
per-outcome provenance is preserved (player_id/ESPN ID, liquidity,
last_change_at, last_seen_at, book outcome IDs); week window uses
ZoneInfo("America/Chicago"), not a fixed -05:00 offset.

Auth reuses the workspace propline skill's client (bin/pl.py) which
applies the stored custom.propline credential via the authd surrogate.
This collector never reads, prints, or persists the raw API key.
"""
import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

COLLECTOR_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(COLLECTOR_DIR)
sys.path.insert(0, os.path.join(os.path.expanduser("~"), "workspace",
                               "skills", "propline", "bin"))
from pl import call  # noqa: E402  (reuses surrogate auth; key never surfaces)

CACHE_DIR = os.path.join(REPO_ROOT, "data", "propline_cache")

# Prop markets our translation consumes (engine/vegas.py keys).
PROP_MARKETS = [
    "player_pass_yds",
    "player_pass_tds",
    "player_pass_interceptions",
    "player_rush_yds",
    "player_rush_tds",
    "player_receptions",
    "player_reception_yds",
    "player_reception_tds",
    "player_anytime_td",
]

# Consensus books for the primary leg (mirrors the old Odds API pair,
# plus the two extra sharp books PropLine carries).
BOOKS = ["draftkings", "fanduel", "betmgm", "pinnacle"]

CT = ZoneInfo("America/Chicago")


def tuesday_of_nfl_week(now=None):
    """Tuesday 00:00 America/Chicago of the NFL week containing `now`."""
    now = now or dt.datetime.now(CT)
    monday = now - dt.timedelta(days=now.weekday())
    tuesday = (monday + dt.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    if tuesday > now:
        tuesday -= dt.timedelta(days=7)
    return tuesday


def in_scope(commence_iso, week_start):
    try:
        kick = dt.datetime.fromisoformat(
            commence_iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    return week_start <= kick.astimezone(CT) < week_start + dt.timedelta(days=7)


def fetch_events():
    data = call("/sports/football_nfl/events")
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    return data


def fetch_game_odds(event_id):
    return call(
        f"/sports/football_nfl/events/{event_id}/odds",
        {"markets": ",".join(PROP_MARKETS),
         "bookmakers": ",".join(BOOKS)})


def to_cache_doc(game):
    """Keep the per-game doc in the exact Odds-API-compatible shape, WITH
    full per-outcome provenance.

    2026-09-18: the original stripped everything but name/price/point.
    The user requires preserving player/ESPN IDs, liquidity,
    last_change_at / last_seen_at, and every other per-outcome field —
    the play gate's freshness and audit checks depend on them.
    """
    bookmakers = []
    for b in game.get("bookmakers", []):
        markets = []
        for m in b.get("markets", []):
            outcomes = []
            for o in m.get("outcomes", []):
                # Preserve the full outcome record; the four canonical
                # keys stay top-level for Odds-API-compatible readers.
                rec = dict(o)
                rec.setdefault("name", o.get("name"))
                rec.setdefault("description", o.get("description"))
                rec.setdefault("price", o.get("price"))
                rec.setdefault("point", o.get("point"))
                outcomes.append(rec)
            markets.append({
                "key": m.get("key"),
                "description": m.get("description"),
                "period": m.get("period"),
                "team": m.get("team"),
                "last_update": m.get("last_update"),
                "suspended_at": m.get("suspended_at"),
                "outcomes": outcomes,
            })
        bookmakers.append({
            "key": b.get("key"),
            "title": b.get("title"),
            "last_update": b.get("last_update"),
            "book_event_id": b.get("book_event_id"),
            "pregame_only": b.get("pregame_only"),
            "markets": markets,
        })
    return {
        "id": game.get("id"),
        "sport_key": game.get("sport_key", "football_nfl"),
        "commence_time": game.get("commence_time"),
        "home_team": game.get("home_team"),
        "away_team": game.get("away_team"),
        "bookmakers": bookmakers,
    }


def run(week=None, season=2026, skip_cached=False):
    os.makedirs(CACHE_DIR, exist_ok=True)
    now = dt.datetime.now(CT)
    week_start = tuesday_of_nfl_week(now)
    # Derive the season week number from the Tuesday window (approx).
    if week is None:
        season_tue = dt.datetime(2026, 9, 8, tzinfo=CT)  # Tue of Week 1
        week = max(1, int(((week_start - season_tue).days // 7) + 1))

    events = fetch_events()
    scoped = [e for e in events
              if in_scope(e.get("commence_time", ""), week_start)]
    request_count = 1
    written = []
    for ev in scoped:
        eid = ev.get("id")
        path = os.path.join(CACHE_DIR, f"props_{eid}.json")
        # 2026-09-18: refresh is the DEFAULT — recurring line-movement
        # pulls must re-fetch current prices, never silently reuse stale
        # cache. Pass --skip-cached only for a fill-gaps run.
        if os.path.exists(path) and skip_cached:
            written.append((eid, path, "cached"))
            continue
        game = fetch_game_odds(eid)
        request_count += 1
        doc = to_cache_doc(game)
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(doc, fh, indent=1)
        os.replace(tmp, path)
        outcomes = sum(len(m["outcomes"])
                       for b in doc["bookmakers"] for m in b["markets"])
        written.append((eid, path, f"{len(doc['bookmakers'])} books, "
                                  f"{outcomes} outcomes"))

    meta = {
        "pulled_at": now.isoformat(),
        "week": week,
        "season": season,
        "week_window_ct": [week_start.isoformat(),
                           (week_start + dt.timedelta(days=7)).isoformat()],
        "games": len(scoped),
        "request_count": request_count,
        "bookmakers_requested": BOOKS,
        "markets": PROP_MARKETS,
        "files": [w[1] for w in written],
    }
    with open(os.path.join(CACHE_DIR, "pull_meta.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    return meta, written


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--skip-cached", action="store_true",
                    help="do not re-pull games already cached (fill-gaps "
                         "mode; default is to refresh every game)")
    ap.add_argument("--force", action="store_true",
                    help="deprecated alias: refresh is now the default")
    args = ap.parse_args()
    meta, written = run(week=args.week, season=args.season,
                        skip_cached=args.skip_cached)
    print(json.dumps(meta, indent=1)[:1500])
    for eid, path, note in written:
        print(f"  {eid}: {note}")


if __name__ == "__main__":
    main()
