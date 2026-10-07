"""Build inputs for the Vegas season-VORP view (idempotent).

1. yahoo_rostered_snapshot: rostered set from the local Yahoo snapshot JSON
   (managed-browser login is expired; snapshot 2026-09-11 is the source).
2. season_actuals_ytd: per-(player_norm, stat) actuals summed over FINAL 2026
   games in player_game_stats (nflverse loader).
3. vegas_player_map: player_norm -> player_id/position/display_name/team,
   resolving the few rows whose player_id is NULL at collector load time.

Usage: python3 bin/build_vegas_vorp_inputs.py
"""
import json
import re
import sys

sys.path.insert(0, "/home/hatch/workspace/skills/supabase-football-signal/bin")
import sbclient  # noqa: E402

sys.path.insert(0, "/home/hatch/workspace/football-signal")
from engine.canonical_players import norm_player_name as norm_loose  # noqa: E402  (canonical identity 2026-09-18; retired Vegas leg)

YAHOO_SNAPSHOT = ("/home/hatch/workspace/football-signal/data/yahoo_uso/"
                  "snapshot_2026-09-11.json")
SEASON = 2026

STAT_COLS = ("passing_yards", "passing_tds", "rushing_yards", "rushing_tds",
             "receptions", "receiving_yards", "receiving_tds")

MARKET_OF = {
    "passing_yards": "season_pass_yds", "passing_tds": "season_pass_tds",
    "rushing_yards": "season_rush_yds", "rushing_tds": "season_rush_tds",
    "receiving_yards": "season_rec_yds", "receiving_tds": "season_rec_tds",
    "receptions": "season_receptions",
}

# Manual position fixes for players not yet in the players table.
MANUAL_POS = {"cameron ward": "QB", "cameron skattebo": "RB"}


def main():
    import subprocess
    mgmt = [sys.executable,
            "/home/hatch/workspace/skills/supabase-mgmt/bin/mgmt.py"]

    def sql(s):
        r = subprocess.run(mgmt + [s], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"SQL failed: {r.stderr[:400]}\nSQL: {s[:200]}")
        return json.loads(r.stdout)

    # ---- 0. schema ----
    sql("""
    CREATE TABLE IF NOT EXISTS yahoo_rostered_snapshot (
      snapshot_date date NOT NULL,
      team_name text NOT NULL,
      player_name text NOT NULL,
      player_norm text NOT NULL,
      pos text NOT NULL,
      nfl_team text,
      UNIQUE (snapshot_date, team_name, player_norm));
    CREATE TABLE IF NOT EXISTS season_actuals_ytd (
      season int NOT NULL,
      player_norm text NOT NULL,
      stat_key text NOT NULL,
      actual double precision NOT NULL DEFAULT 0,
      UNIQUE (season, player_norm, stat_key));
    CREATE TABLE IF NOT EXISTS vegas_player_map (
      player_norm text PRIMARY KEY,
      player_id uuid,
      position text,
      display_name text,
      team text);
    """)
    print("schema ok", flush=True)

    # ---- 1. rostered set ----
    snap = json.load(open(YAHOO_SNAPSHOT))
    snap_date = "2026-09-11"
    vals = []
    for team, plist in snap["rosters"].items():
        for p in plist:
            if p.get("pos") == "DEF":
                continue
            vals.append((snap_date, team.replace("'", "''"),
                         p["player"].replace("'", "''"),
                         norm_loose(p["player"]),
                         p.get("pos") or "", (p.get("nfl") or "")))
    ins = ",".join(
        f"('{d}','{t}','{n}','{nn}','{pos}','{tm}')" for d, t, n, nn, pos, tm in vals)
    sql(f"""INSERT INTO yahoo_rostered_snapshot
            (snapshot_date, team_name, player_name, player_norm, pos, nfl_team)
            VALUES {ins}
            ON CONFLICT (snapshot_date, team_name, player_norm) DO NOTHING;""")
    n_ros = sql("SELECT count(*) AS n FROM yahoo_rostered_snapshot "
                f"WHERE snapshot_date='{snap_date}';")[0]["n"]
    print(f"rostered rows: {n_ros} (source entries: {len(vals)})", flush=True)

    # ---- 2. YTD actuals (final 2026 games only) ----
    games = sbclient.get_all(
        "games", f"?select=id&season=eq.{SEASON}&status=eq.final")
    gids = [g["id"] for g in games]
    print(f"final {SEASON} games: {len(gids)}", flush=True)
    players = {p["id"]: p["full_name"]
               for p in sbclient.get_all("players", "?select=id,full_name&limit=100000")}
    agg = {}
    for gid in gids:
        rows = sbclient.get_all(
            "player_game_stats",
            f"?select=player_id,stats&game_id=eq.{gid}&limit=100000")
        for r in rows:
            name = players.get(r["player_id"])
            if not name:
                continue
            nn = norm_loose(name)
            st = r.get("stats") or {}
            for col in STAT_COLS:
                v = st.get(col) or 0
                if v:
                    key = (nn, MARKET_OF[col])
                    agg[key] = agg.get(key, 0.0) + float(v)
    avals = ",".join(
        f"({SEASON},'{nn.replace(chr(39), chr(39)*2)}','{m}',{v})"
        for (nn, m), v in agg.items())
    if avals:
        sql(f"""INSERT INTO season_actuals_ytd (season, player_norm, stat_key, actual)
                VALUES {avals}
                ON CONFLICT (season, player_norm, stat_key)
                DO UPDATE SET actual = EXCLUDED.actual;""")
    print(f"actuals rows: {len(agg)} across {len(set(k[0] for k in agg))} players",
          flush=True)

    # ---- 3. player map ----
    vrows = sbclient.get_all(
        "vegas_season_totals",
        "?select=player_norm,player_id,player_name,team&limit=100000")
    vnorms = {}
    for r in vrows:
        d = vnorms.setdefault(r["player_norm"],
                               {"player_id": r["player_id"],
                                "display_name": r["player_name"],
                                "team": r["team"]})
        if not d["player_id"] and r["player_id"]:
            d["player_id"] = r["player_id"]
    # resolve positions: when several players share a norm (e.g. Lamar Jackson
    # the DB and the QB), prefer a skill position, then the Vegas team.
    players_all = sbclient.get_all(
        "players", "?select=id,full_name,position,metadata&limit=100000")
    pos_by_id = {p["id"]: p["position"] for p in players_all}
    by_norm = {}
    for p in players_all:
        by_norm.setdefault(norm_loose(p["full_name"]), []).append(p)

    def team_of(p):
        return ((p.get("metadata") or {}).get("team") or "")

    def resolve(nn, vegas_team):
        cands = by_norm.get(nn, [])
        if not cands:
            return None, MANUAL_POS.get(nn)
        skill = [c for c in cands if c["position"] in ("QB", "RB", "WR", "TE")]
        pool = skill or cands
        same_team = [c for c in pool if team_of(c) == vegas_team] if vegas_team else []
        best = (same_team or pool)[0]
        return best["id"], best["position"]

    mvals = []
    for nn, d in sorted(vnorms.items()):
        pid, pos = d["player_id"], None
        if pid:
            pos = pos_by_id.get(pid)
        if pos not in ("QB", "RB", "WR", "TE"):
            # stored player_id may point at a same-name player at another
            # position (e.g. Lamar Jackson the DB); re-resolve by norm.
            pid2, pos2 = resolve(nn, d["team"])
            if pos2:
                pid, pos = pid2, pos2
        if not pos:
            pos = MANUAL_POS.get(nn)
        team = d["team"] or ""
        if not team and pid:
            prow = next((p for p in players_all if p["id"] == pid), None)
            team = team_of(prow) if prow else ""
        mvals.append((nn, pid, pos, d["display_name"].replace("'", "''"), team))
    parts = []
    for nn, pid, pos, dn, tm in mvals:
        pid_s = "'" + pid + "'" if pid else "NULL"
        pos_s = "'" + pos + "'" if pos else "NULL"
        parts.append("('" + nn + "'," + pid_s + "," + pos_s
                     + ",'" + dn + "','" + tm + "')")
    mins = ",".join(parts)
    sql(f"""INSERT INTO vegas_player_map
            (player_norm, player_id, position, display_name, team)
            VALUES {mins}
            ON CONFLICT (player_norm) DO UPDATE SET
              player_id = EXCLUDED.player_id,
              position = EXCLUDED.position,
              display_name = EXCLUDED.display_name,
              team = EXCLUDED.team;""")
    missing = [nn for nn, _, pos, _, _ in mvals if not pos]
    print(f"player map rows: {len(mvals)}; missing position: {missing}",
          flush=True)


if __name__ == "__main__":
    main()
