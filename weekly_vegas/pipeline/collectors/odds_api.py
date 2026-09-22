"""The Odds API collector: player props snapshots -> Supabase odds_history.

Auth: vault-backed ``custom.the-odds-api`` credential via the the-odds-api
skill (bin/oddsclient.py). The real key never appears here.

Quota (free tier, 500/mo): event-odds calls cost (unique markets with data) x
regions. /v4/sports/{sport}/events is FREE. v1 strategy:
  - CORE_MARKETS (4): pass/rush/receiving yardage + receptions.
    ~4 credits per event -> ~64 per full 16-game snapshot.
  - 2 snapshots/week (Wed + Sun AM) ~= 130/week worst case; realistically less
    (early-week events have no props yet = free; Thu games drop out by Sun).
  - QUOTA_RESERVE = 60: the collector stops before burning the buffer.
Every paid response updates data/odds_quota.json from the x-requests-* headers.

Row mapping -> odds_history:
  market=prop market key, selection=Over/Under/Yes/No, line=point, odds=price,
  metadata={player_name, player_id, event_id, bookmaker, snapshot_at}.
odds_history is append-only: every snapshot adds rows (movement history).
"""

import json
import os
import sys
import time
import urllib.parse
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.expanduser("~/workspace/skills/the-odds-api/bin"))
sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))
import oddsclient  # noqa: E402
import sbclient  # noqa: E402

SPORT = "americanfootball_nfl"
# Pinnacle added 2026-09-11: the sharp book's props feed the pinnacle_implied
# projection source. Bookmakers do not add quota cost (up to 10 = 1 region).
BOOKMAKERS = "draftkings,fanduel,pinnacle"
CORE_MARKETS = [
    "player_pass_yds",
    "player_rush_yds",
    "player_receptions",
    "player_reception_yds",
    "player_anytime_td",  # binary Yes/No -> de-vigged TD probability (v4)
    "player_pass_tds",    # QBs lose ~6-8 pts without it (v4.1)
]
QUOTA_RESERVE = 60
CACHE_TTL_S = 12 * 3600

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "odds_cache")
QUOTA_FILE = os.path.join(BASE_DIR, "quota.json")


def _now():
    return datetime.now(timezone.utc)


def _load_quota():
    try:
        return json.load(open(QUOTA_FILE)).get("remaining", 500)
    except Exception:
        return 500


def _save_quota(quota):
    os.makedirs(BASE_DIR, exist_ok=True)
    json.dump({"remaining": int(quota.get("x-requests-remaining") or 0),
               "used": int(quota.get("x-requests-used") or 0),
               "last": int(quota.get("x-requests-last") or 0),
               "at": _now().isoformat()}, open(QUOTA_FILE, "w"))


def _cache_path(event_id):
    os.makedirs(BASE_DIR, exist_ok=True)
    return os.path.join(BASE_DIR, f"props_{event_id}.json")


def _cached(event_id):
    p = _cache_path(event_id)
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < CACHE_TTL_S:
        return json.load(open(p))
    return None


def _nick(full_name):
    """'Los Angeles Rams' -> 'Rams'. Nicknames are franchise-unique in our DB
    even though relocated franchises have several abbreviation rows
    (LA/LAR/STL Rams, LAC/SD Chargers, LV/OAK Raiders)."""
    return full_name.strip().split()[-1]


def _games_index():
    """(home_nickname, away_nickname) -> list of (starts_at, game_id)."""
    team_nick = {t["id"]: t["name"] for t in sbclient.get_all("teams") if t.get("name")}
    idx = {}
    for g in sbclient.get_all("games", "?select=id,home_team_id,away_team_id,starts_at"):
        key = (team_nick.get(g["home_team_id"]), team_nick.get(g["away_team_id"]))
        if key[0] and key[1]:
            idx.setdefault(key, []).append((g.get("starts_at"), g["id"]))
    return idx


def _player_map():
    """full_name -> player id.

    On a cross-position name collision (Lamar Jackson QB+DB, Justin
    Jefferson WR+LB, …) prefer the QB/RB/WR/TE row: player props are
    offensive data and must never attach to the defensive row's UUID.
    (Rule mirrors engine.snapshot.prefer_offensive_player; the collector
    can't import engine on its sys.path, so the tuple is repeated here —
    keep them in sync.)
    """
    m = {}
    for p in sbclient.get_all("players", "?select=id,full_name,position"):
        if not p.get("full_name"):
            continue
        cur = m.get(p["full_name"])
        if cur is None:
            m[p["full_name"]] = p
        elif ((p.get("position") or "").upper() in ("QB", "RB", "WR", "TE")
              and (cur.get("position") or "").upper()
              not in ("QB", "RB", "WR", "TE")):
            m[p["full_name"]] = p
    return {k: v["id"] for k, v in m.items()}


def _match_game(event, games_idx):
    """Match an Odds API event to our games row via nicknames + kickoff time."""
    cands = games_idx.get((_nick(event["home_team"]), _nick(event["away_team"])), [])
    try:
        commence = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))
    except Exception:
        return cands[0][1] if cands else None
    best, best_dt = None, timedelta(days=3)
    for starts_at, gid in cands:
        if not starts_at:
            continue
        try:
            dt = abs(datetime.fromisoformat(starts_at.replace("Z", "+00:00")) - commence)
        except Exception:
            continue
        if dt < best_dt:
            best, best_dt = gid, dt
    return best


def parse_props(event_data, game_id, book_ids, players, snapshot_at):
    rows = []
    for bm in event_data.get("bookmakers", []):
        sb_id = book_ids.get(bm["key"])
        if not sb_id:
            continue
        for mkt in bm.get("markets", []):
            for o in mkt.get("outcomes", []):
                player = o.get("description") or o.get("name")
                side = o.get("name")
                if side not in ("Over", "Under", "Yes", "No"):
                    continue
                rows.append({
                    "game_id": game_id,
                    "sportsbook_id": sb_id,
                    "market": mkt["key"],
                    "selection": side,
                    "line": o.get("point"),
                    "odds": o.get("price"),
                    "recorded_at": snapshot_at,
                    # Typed FK column (odds_history.player_id); metadata copy
                    # kept for existing readers (engine/snapshot.py, dedupe).
                    "player_id": players.get(player),
                    "metadata": {
                        "player_name": player,
                        "player_id": players.get(player),
                        "event_id": event_data.get("id"),
                        "bookmaker": bm["key"],
                        "data_source": "the-odds-api",
                    },
                })
    return rows


def _dedupe_rows(event_id, rows):
    """Idempotent inserts: drop rows whose line observation already exists for
    this event. A genuine line/odds move is a new tuple -> new row (movement
    history is preserved); an identical re-run of a cached snapshot writes
    nothing."""
    try:
        col = urllib.parse.quote("metadata->>event_id", safe="")
        existing = sbclient.get_all(
            "odds_history",
            f"?{col}=eq.{event_id}"
            "&select=sportsbook_id,market,selection,line,odds,metadata",
        )
    except Exception as e:
        # Fail closed: a failed lookup must never write blind duplicates.
        print("dedupe lookup failed, skipping insert for this event:", str(e)[:100])
        return []
    seen = {
        (r["sportsbook_id"], r["market"], r["selection"],
         (r.get("metadata") or {}).get("player_name"), r["line"], r["odds"])
        for r in existing
    }
    before = len(rows)
    kept = [r for r in rows
            if (r["sportsbook_id"], r["market"], r["selection"],
                r["metadata"]["player_name"], r["line"], r["odds"]) not in seen]
    if before - len(kept):
        print(f"dedupe: skipped {before - len(kept)} already-recorded rows")
    return kept


def snapshot(event_ids=None, markets=None, max_events=None, force=False):
    """Snapshot props for upcoming events. Returns (rows_written, quota_remaining).

    force=True bypasses the 12h per-event cache (game-day refresh pulls
    genuinely fresh lines; the fresh payload still rewrites the cache)."""
    markets = markets or CORE_MARKETS
    players = _player_map()
    games_idx = _games_index()
    book_ids = {b["code"]: b["id"] for b in sbclient.get("sportsbooks")}

    events, _ = oddsclient.events()
    now = _now()
    upcoming = [e for e in events
                if datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) > now]
    if event_ids:
        upcoming = [e for e in upcoming if e["id"] in set(event_ids)]
    upcoming.sort(key=lambda e: e["commence_time"])
    if max_events:
        upcoming = upcoming[:max_events]

    written, snap_at = 0, now.isoformat()
    for ev in upcoming:
        if _load_quota() < QUOTA_RESERVE + len(markets):
            print(f"quota guard: stopping with {_load_quota()} remaining")
            break
        cached = None if force else _cached(ev["id"])
        if cached is not None:
            data, fresh = cached, False
        else:
            try:
                data, quota = oddsclient.event_odds(ev["id"], markets, bookmakers=BOOKMAKERS)
            except oddsclient.OddsApiError as e:
                print("skip event", ev["id"], str(e)[:120])
                continue
            _save_quota(quota)
            json.dump(data, open(_cache_path(ev["id"]), "w"))
            fresh = True
            time.sleep(1)
        game_id = _match_game(ev, games_idx)
        rows = parse_props(data, game_id, book_ids, players, snap_at)
        rows = _dedupe_rows(ev["id"], rows)
        for i in range(0, len(rows), 200):
            sbclient.post("odds_history", rows[i:i + 200])
        written += len(rows)
        print(f"{ev['away_team']} @ {ev['home_team']}: {len(rows)} rows "
              f"(cached={not fresh}, game={'ok' if game_id else 'UNMATCHED'})")
    return written, _load_quota()


if __name__ == "__main__":
    ids = sys.argv[1:] or None
    n, remaining = snapshot(event_ids=ids)
    print(f"snapshot complete: {n} rows written, quota remaining: {remaining}")
