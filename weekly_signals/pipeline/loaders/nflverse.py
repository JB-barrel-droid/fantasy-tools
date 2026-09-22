"""nflverse -> Supabase loader (idempotent).

Loads sports, leagues, teams, games, players, external_id_map,
player_game_stats. Auth goes through the vault-backed skill credential;
nothing secret lives in this file or the environment.

Usage: .venv/bin/python loaders/nflverse.py [--seasons 2024,2025,2026]
"""

import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, "/home/hatch/workspace/skills/supabase-football-signal/bin")
import sbclient  # noqa: E402

sys.path.insert(0, "/home/hatch/workspace/football-signal")
from engine.scoring import fantasy_points  # noqa: E402

import nflreadpy as nfl  # noqa: E402

ET = ZoneInfo("America/New_York")
SEASONS = [2024, 2025, 2026]

STAT_MAP = {  # weekly col -> (stats json key)
    "passing_yards": "passing_yards", "passing_tds": "passing_tds",
    "passing_interceptions": "interceptions",
    "rushing_yards": "rushing_yards", "rushing_tds": "rushing_tds",
    "rushing_fumbles_lost": None, "receiving_fumbles_lost": None,
    "sack_fumbles_lost": None,
    "receptions": "receptions", "targets": "targets",
    "receiving_yards": "receiving_yards", "receiving_tds": "receiving_tds",
}


def get_or_create(table, lookup, body):
    rows = sbclient.get(table, f"?{lookup}&limit=1")
    if rows:
        return rows[0]["id"]
    return sbclient.post(table, body)[0]["id"]


def bulk(table, rows, batch=400):
    for i in range(0, len(rows), batch):
        sbclient.post(table, rows[i:i + batch])
    print(f"  inserted {len(rows)} -> {table}", flush=True)


def main():
    seasons = SEASONS
    if "--seasons" in sys.argv:
        seasons = [int(s) for s in sys.argv[sys.argv.index("--seasons") + 1].split(",")]

    print("== reference rows ==", flush=True)
    sport_id = get_or_create("sports", "code=eq.football",
                             {"code": "football", "name": "Football"})
    league_id = get_or_create("leagues", "code=eq.nfl",
                              {"code": "nfl", "name": "NFL", "sport_id": sport_id})
    source_id = get_or_create(
        "data_sources", "name=eq.nflverse",
        {"name": "nflverse", "source_type": "stats",
         "base_url": "https://github.com/nflverse/nflverse-data"})

    print("== teams ==", flush=True)
    team_ids = {}
    for r in nfl.load_teams().iter_rows(named=True):
        if not r["team_abbr"]:
            continue
        tid = get_or_create(
            "teams", f"abbreviation=eq.{r['team_abbr']}",
            {"abbreviation": r["team_abbr"], "name": r["team_nick"],
             "league_id": league_id})
        team_ids[r["team_abbr"]] = tid
    print(f"  {len(team_ids)} teams", flush=True)

    print("== games ==", flush=True)
    sched = nfl.load_schedules(seasons)
    # Crash-safe existence check: consult the entity table directly (via the
    # nflverse id stashed in metadata), not just external_id_map, so a crash
    # between the games insert and the map insert can't double-insert on retry.
    # Existing game rows are deliberately never updated (no upserts): status
    # and scores stay as first recorded.
    existing_ngids = {
        (g.get("metadata") or {}).get("nflverse_game_id")
        for g in sbclient.get_all("games", f"?league_id=eq.{league_id}&select=metadata")
    } - {None}
    existing_ngids |= {r["external_id"] for r in sbclient.get_all(
        "external_id_map",
        f"?entity_type=eq.game&source_id=eq.{source_id}&select=external_id")}
    sched_lookup = {}
    new_games = []
    for r in sched.iter_rows(named=True):
        if r["game_type"] not in ("REG", "POST"):
            continue
        gid = r["game_id"]
        sched_lookup[(int(r["season"]), int(r["week"]), r["away_team"], r["home_team"])] = gid
        sched_lookup[(int(r["season"]), int(r["week"]), r["home_team"], r["away_team"])] = gid
        if gid in existing_ngids or r["away_team"] not in team_ids or r["home_team"] not in team_ids:
            continue
        starts = None
        if r["gameday"]:
            try:
                starts = datetime.strptime(
                    f"{r['gameday']} {(r['gametime'] or '13:00').strip()}",
                    "%Y-%m-%d %H:%M").replace(tzinfo=ET).isoformat()
            except ValueError:
                starts = f"{r['gameday']}T12:00:00-04:00"
        new_games.append({
            "season": int(r["season"]), "week": int(r["week"]), "starts_at": starts,
            "league_id": league_id,
            "home_team_id": team_ids[r["home_team"]],
            "away_team_id": team_ids[r["away_team"]],
            "status": "final" if r["home_score"] is not None else "scheduled",
            "venue": r["stadium"],
            "metadata": {"nflverse_game_id": gid, "game_type": r["game_type"],
                         "spread_line": r["spread_line"], "total_line": r["total_line"],
                         "home_score": r["home_score"], "away_score": r["away_score"],
                         "away_moneyline": r["away_moneyline"],
                         "home_moneyline": r["home_moneyline"],
                         "temp": r.get("temp"), "wind": r.get("wind"),
                         "roof": r.get("roof"), "surface": r.get("surface")},
        })
    game_rows = []
    for i in range(0, len(new_games), 400):
        game_rows.extend(sbclient.post("games", new_games[i:i + 400]))
    print(f"  inserted {len(game_rows)} games", flush=True)
    if game_rows:
        bulk("external_id_map", [
            {"entity_type": "game", "entity_id": g["id"],
             "source_id": source_id, "external_id": g["metadata"]["nflverse_game_id"]}
            for g in game_rows])

    print("== players ==", flush=True)
    # Same crash-safe rule as games: skip anything already in the players
    # table (by gsis_id in metadata) or the id map. No upserts -- a player's
    # team/position stays as first recorded.
    existing_gsis = {
        (p.get("metadata") or {}).get("gsis_id")
        for p in sbclient.get_all("players", f"?league_id=eq.{league_id}&select=metadata")
    } - {None}
    existing_gsis |= {r["external_id"] for r in sbclient.get_all(
        "external_id_map",
        f"?entity_type=eq.player&source_id=eq.{source_id}&select=external_id")}
    seen, new_players = set(), []
    for r in nfl.load_rosters(seasons).iter_rows(named=True):
        gsis = r["gsis_id"]
        if not gsis or gsis in existing_gsis or gsis in seen:
            continue
        seen.add(gsis)
        new_players.append({"full_name": r["full_name"] or f"{r['first_name']} {r['last_name']}",
                            "position": r["position"], "league_id": league_id,
                            "team_id": team_ids.get(r["team"]),
                            "active": (r["status"] or "").upper() == "ACT",
                            "metadata": {"gsis_id": gsis, "team": r["team"]}})
    player_rows = []
    for i in range(0, len(new_players), 400):
        player_rows.extend(sbclient.post("players", new_players[i:i + 400]))
    print(f"  inserted {len(player_rows)} players", flush=True)
    if player_rows:
        bulk("external_id_map", [
            {"entity_type": "player", "entity_id": p["id"],
             "source_id": source_id, "external_id": p["metadata"]["gsis_id"]}
            for p in player_rows])

    print("== player_game_stats ==", flush=True)
    pmap = {r["external_id"]: r["entity_id"] for r in sbclient.get_all(
        "external_id_map",
        f"?entity_type=eq.player&source_id=eq.{source_id}&select=external_id,entity_id")}
    gmap = {}
    for g in sbclient.get_all("games",
                             f"?league_id=eq.{league_id}&select=id,metadata"):
        ngid = (g["metadata"] or {}).get("nflverse_game_id")
        if ngid:
            gmap[ngid] = g["id"]
    have_stats = {(r["player_id"], r["game_id"]) for r in
                  sbclient.get_all("player_game_stats", "?select=player_id,game_id")}

    pw = nfl.load_player_stats(seasons)
    inserts, seen_pg, skipped = [], set(), 0
    for r in pw.iter_rows(named=True):
        ngid = sched_lookup.get((int(r["season"]), int(r["week"]),
                                 r["team"], r["opponent_team"]))
        guid = gmap.get(ngid) if ngid else None
        puid = pmap.get(r["player_id"])
        if not guid or not puid:
            continue
        key = (puid, guid)
        if key in have_stats or key in seen_pg:
            skipped += 1
            continue
        seen_pg.add(key)
        stats = {}
        fum = 0.0
        for col, dest in STAT_MAP.items():
            v = r.get(col)
            if v is None:
                continue
            if dest is None:
                fum += float(v)
            else:
                stats[dest] = float(v)
        if fum:
            stats["fumbles_lost"] = round(fum, 2)
        inserts.append({"player_id": puid, "game_id": guid,
                        "team_id": team_ids.get(r["team"]),
                        "stats": stats,
                        "fantasy_points": fantasy_points(stats, "ppr")})
    bulk("player_game_stats", inserts)
    print(f"  skipped {skipped} already-loaded player-game rows", flush=True)
    print("DONE", flush=True)


def load_injuries(seasons=(2026,)):
    """nflverse weekly injury + practice reports -> injuries table.

    Complements the Sleeper injuries (which carry news_updated recency);
    nflverse adds practice_status and the official report_status.
    Idempotent: upserts on (player_name, team, source).

    Week semantics (2026-09-19): the feed is a weekly log, oldest week
    first. The row written per player is the LATEST week available —
    first-wins left 18 rows stuck on week-1 designations (e.g. Patrick
    Jones II "Out" when week 2 said "Questionable"). A player whose team
    filed a max-week report but who isn't on it has no current designation,
    so their old nflverse row is cleared; bye-week / not-yet-reporting
    teams are never cleared.
    """
    from datetime import datetime, timezone
    inj = nfl.load_injuries(list(seasons))
    now = datetime.now(timezone.utc).isoformat()
    batch = []
    for r in inj.iter_rows(named=True):
        status = r.get("report_status") or r.get("practice_status")
        if not status:
            continue
        batch.append({
            "player_id": None,
            "player_name": r.get("full_name"),
            "team": r.get("team"), "position": r.get("position"),
            "status": status,
            "body_part": r.get("report_primary_injury"),
            "report_date": None, "source": "nflverse",
            "fetched_at": now,
            "week": r.get("week"),
        })
    # resolve player_ids by name
    from engine.snapshot import norm
    by_name = {}
    for p in sbclient.get_all("players", "?select=id,full_name"):
        by_name.setdefault(norm(p["full_name"]), p["id"])
    for b in batch:
        b["player_id"] = by_name.get(norm(b["player_name"] or ""))
    # Latest week wins per (player_name, team, source). The injuries table
    # has no week column, so resolve here and strip it before upsert.
    max_week = max([b["week"] or 0 for b in batch], default=0)
    best, week_of = {}, {}
    for b in batch:
        k = (b["player_name"], b["team"], b["source"])
        if k not in best or (b["week"] or 0) > (week_of[k] or 0):
            best[k] = b
            week_of[k] = b["week"]
    # Clear designations the official report dropped: the player's latest
    # feed row is older than the max week, but their team filed a max-week
    # report — the official report no longer designates them. Bye-week /
    # not-yet-reporting teams are never cleared. Stale keys skip the upsert
    # (nothing current to write) and go straight to the clear.
    n_cleared = 0
    stale_keys = set()
    if max_week:
        max_week_teams = {k[1] for k, w in week_of.items()
                          if (w or 0) == max_week}
        stale_keys = {k for k, w in week_of.items()
                      if (w or 0) < max_week and k[1] in max_week_teams}
    uniq = []
    for k, b in best.items():
        b.pop("week", None)
        if k not in stale_keys:
            uniq.append(b)
    for i in range(0, len(uniq), 200):
        sbclient._request("POST", "/rest/v1/injuries", body=uniq[i:i + 200],
                          params="?on_conflict=player_name,team,source",
                          prefer="resolution=merge-duplicates")
    if stale_keys:
        clear_ids = [
            r["id"] for r in sbclient.get_all(
                "injuries", "?select=id,player_name,team,status"
                            "&source=eq.nflverse")
            if r.get("status") is not None
            and (r["player_name"], r["team"], "nflverse") in stale_keys]
        if clear_ids:
            # DELETE, not status=NULL: injuries.status is NOT NULL, and a
            # player the official report dropped carries no designation.
            sbclient.delete(
                "injuries",
                "?id=in.(" + ",".join(clear_ids) + ")")
            n_cleared = len(clear_ids)
    print(f"nflverse injuries: {len(uniq)} upserted, {n_cleared} cleared",
          flush=True)
    return {"upserted": len(uniq), "cleared": n_cleared}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--injuries-only", action="store_true")
    a = ap.parse_args()
    if a.injuries_only:
        load_injuries()
    else:
        main()
