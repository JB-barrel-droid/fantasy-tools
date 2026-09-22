"""Projection snapshots: freeze pre-game projections so the calibration loop
can score Vegas vs experts against actuals after games.

Batch #1 (2026-09-10): v3 methodology — yardage-and-catches floors on both
sides (no TD markets on the Vegas side, TD value stripped from ESPN).
Later batches (v4+) are TD-inclusive; vintage_note records the difference.

Row grain: one row per (batch_id, player_id, game_id, source, scoring_format).
Sources: 'vegas_implied', 'espn'. Formats: 'standard', 'half_ppr', 'full_ppr'.
ecr_rank rides along where a FantasyPros ECR entry exists; vegas_rank is the
player's rank by Vegas-implied PPR within their position group.
"""
import json
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_signals/pipeline root
SB = os.path.expanduser("~/workspace/skills/supabase-football-signal/bin")
for p in (BASE, SB):
    if p not in __import__("sys").path:
        __import__("sys").path.insert(0, p)
import sbclient  # noqa: E402

from engine.vegas import vegas_implied_points  # noqa: E402
from engine.scoring import fantasy_points  # noqa: E402

# v3: yardage/reception line markets only. TD markets did not exist in v3.
LINE_MARKETS = {"player_pass_yds", "player_rush_yds",
                "player_receptions", "player_reception_yds"}
PROP_TO_STAT = {
    "player_pass_yds": "passing_yards",
    "player_rush_yds": "rushing_yards",
    "player_receptions": "receptions",
    "player_reception_yds": "receiving_yards",
}

PENDING_DIR = os.path.join(BASE, "data", "snapshots_pending")


def norm(name):
    return re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).strip()


_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def norm_loose(name):
    """norm() plus suffix stripping: 'Brian Thomas Jr' == 'Brian Thomas'."""
    return _SUFFIX.sub("", norm(name)).strip()


def table_exists(name):
    try:
        sbclient.get(name, "?select=id&limit=1")
        return True
    except Exception as e:
        if "PGRST205" in str(e):
            return False
        raise


# ------------------------------------------------------------ Vegas (v3)
def load_props_v3():
    """Latest line per (player, market, book, selection); median line with
    odds from the closest book (the v3 averaging-bug fix). TD markets skipped.
    Returns {player_name: {market: {'line', 'over_odds', 'under_odds'}}}."""
    rows = sbclient.get_all(
        "odds_history",
        "?select=game_id,market,selection,line,odds,recorded_at,metadata"
        "&market=in.(player_pass_yds,player_rush_yds,player_receptions,"
        "player_reception_yds)&limit=100000",
    )
    latest = {}
    for r in rows:
        m = r.get("metadata") or {}
        key = (m.get("player_name") or "", r["market"], m.get("bookmaker"),
               r["selection"])
        if key not in latest or r["recorded_at"] > latest[key]["recorded_at"]:
            latest[key] = r
    per_pm = defaultdict(dict)
    for (player, market, book, sel), r in latest.items():
        d = per_pm[(player, market)].setdefault(book, {})
        if sel == "Over":
            d["over"], d["line"] = r["odds"], r["line"]
        else:
            d["under"] = r["odds"]
            d.setdefault("line", r["line"])
    out = defaultdict(dict)
    for (player, market), books in per_pm.items():
        entries = [(o["line"], o.get("over"), o.get("under"))
                   for o in books.values() if o.get("line") is not None]
        if not entries:
            continue
        med = median(e[0] for e in entries)
        line, over, under = min(entries, key=lambda e: abs(e[0] - med))
        entry = {"line": line}
        if over is not None and under is not None:
            entry["over_odds"], entry["under_odds"] = over, under
        out[player][market] = entry
    return out


# ------------------------------------------------------------ ESPN floor (v3)
def load_espn_floor():
    """ESPN Week 1 projections with TD value stripped (v3 apples-to-apples).
    Returns {norm_name: {'name', 'std', 'half', 'ppr'}}."""
    raw = json.load(open(os.path.join(BASE, "data", "espn_wk1_full.json")))
    out = {}
    for p in raw:
        name = p.get("fullName") or ""
        proj = None
        for s in p.get("stats", []):
            if s.get("scoringPeriodId") == 1 and s.get("statSplitTypeId") == 1:
                proj = s.get("stats", {})
                break
        if not proj:
            continue
        g = lambda k: float(proj.get(k, 0) or 0)
        stats = {
            "passing_yards": g("3"), "passing_tds": 0.0,
            "interceptions": g("20"),
            "rushing_yards": g("24"), "rushing_tds": 0.0,
            "receptions": g("53"), "receiving_yards": g("42"),
            "receiving_tds": 0.0,
        }
        if not any(stats.values()):
            continue
        out[norm(name)] = {
            "name": name,
            "std": fantasy_points(stats, "standard"),
            "half": fantasy_points(stats, "half_ppr"),
            "ppr": fantasy_points(stats, "ppr"),
        }
    return out


# ------------------------------------------------------------ ECR
def load_ecr():
    """Returns {norm_name: {'pos_rank': int, 'pos': str}}."""
    try:
        ecr = json.load(open(os.path.join(BASE, "data", "ecr_pos.json")))
    except FileNotFoundError:
        return {}
    return {k: {"pos_rank": v["pos_rank"], "pos": v["pos"]}
            for k, v in ecr.items() if v.get("pos_rank") is not None}


# ------------------------------------------------------------ players/games
# Positions that carry offensive fantasy value. Player props, ECR
# projections, and skill-slot salaries are offensive data: on a
# cross-position name collision (Lamar Jackson QB+DB, Justin Jefferson
# WR+LB, Anthony Brown QB+DB, Brandon Johnson WR+DB, …) the offensive row
# must win. Without this, first-match-wins silently attached props and
# projections to the defensive row's UUID. (Mirror of this tuple lives in
# collectors/odds_api.py::_player_map, which can't import engine.)
OFFENSIVE_POSITIONS = ("QB", "RB", "WR", "TE")


def prefer_offensive_player(cands):
    """Pick one player row from same-name candidates, preferring the
    QB/RB/WR/TE row. Falls back to the first candidate when none (or
    several) are offensive — callers matching defensive data don't exist
    in this pipeline."""
    for c in cands:
        if (c.get("position") or "").upper() in OFFENSIVE_POSITIONS:
            return c
    return cands[0]


def load_players():
    rows = sbclient.get_all("players", "?select=id,full_name,position,team_id&limit=20000")
    by_name_lists, by_loose_lists = {}, {}
    for r in rows:
        by_name_lists.setdefault(norm(r["full_name"]), []).append(r)
        by_loose_lists.setdefault(norm_loose(r["full_name"]), []).append(r)
    # Name collisions resolve here, once, for every consumer (ECR loader,
    # snapshot builders, compute_v4, sleeper/espn/dfs loaders).
    by_name = {k: prefer_offensive_player(v)
               for k, v in by_name_lists.items()}
    by_loose = {k: prefer_offensive_player(v)
                for k, v in by_loose_lists.items()}
    by_id = {r["id"]: r for r in rows}
    return by_name, by_loose, by_id


def load_week_games(season, week):
    rows = sbclient.get(
        "games", f"?select=id,home_team_id,away_team_id,starts_at,status&season=eq.{season}&week=eq.{week}")
    by_team = {}
    for g in rows:
        by_team[g["home_team_id"]] = g
        by_team[g["away_team_id"]] = g
    return {g["id"]: g for g in rows}, by_team


# ------------------------------------------------------------ build + write
def build_rows(batch_id, vintage_note, season=2026, week=1):
    props = load_props_v3()
    espn = load_espn_floor()
    ecr = load_ecr()
    by_name, by_loose, by_id = load_players()
    games_by_id, games_by_team = load_week_games(season, week)
    snap_at = datetime.now(timezone.utc).isoformat()

    rows, gaps = [], {"prop_players_no_uuid": [], "espn_no_match": [],
                      "game_missing": []}

    # --- vegas_implied rows: player_id + game_id come from odds row metadata.
    # (uuid mapping built from a single scan of latest odds rows below)
    vegas_ppr_for_rank = defaultdict(list)  # pos -> [(ppr, player_uuid)]
    latest_rows = sbclient.get_all(
        "odds_history",
        "?select=game_id,market,metadata&market=in.(player_pass_yds,"
        "player_rush_yds,player_receptions,player_reception_yds)&limit=100000")
    uuid_by_name, game_by_name = {}, {}
    for r in latest_rows:
        m = r.get("metadata") or {}
        nm = m.get("player_name") or ""
        if m.get("player_id"):
            uuid_by_name[nm] = m["player_id"]
        if r.get("game_id"):
            game_by_name[nm] = r["game_id"]

    for player_name, markets in sorted(props.items()):
        pid = uuid_by_name.get(player_name)
        if not pid:
            # fallback: odds rows lacking metadata.player_id -> loose name match
            fb = by_loose.get(norm_loose(player_name))
            pid = fb["id"] if fb else None
        gid = game_by_name.get(player_name)
        if not pid:
            gaps["prop_players_no_uuid"].append(player_name)
            continue
        pl = by_id.get(pid)
        if not pl or pl.get("position") not in ("QB", "RB", "WR", "TE"):
            continue
        if not gid or gid not in games_by_id:
            gaps["game_missing"].append(player_name)
            continue
        pos = pl["position"]
        try:
            pts = {f: vegas_implied_points(
                markets, position=pos,
                scoring={"std": "standard", "half": "half_ppr",
                         "ppr": "ppr"}[f])["points"]
                for f in ("std", "half", "ppr")}
        except Exception:
            continue
        vegas_ppr_for_rank[pos].append((pts["ppr"], pid))
        vegas_tmp_rows = []
        for fmt_key, fmt in (("std", "standard"), ("half", "half_ppr"),
                             ("ppr", "full_ppr")):
            vegas_tmp_rows.append({
                "batch_id": batch_id, "player_id": pid, "game_id": gid,
                "season": season, "week": week, "source": "vegas_implied",
                "scoring_format": fmt, "projected_points": pts[fmt_key],
                "ecr_rank": (ecr.get(norm(player_name)) or {}).get("pos_rank"),
                "vegas_rank": None,  # filled below
                "snapshot_at": snap_at, "vintage_note": vintage_note,
            })
        rows.extend(vegas_tmp_rows)

    # fill vegas_rank within position (by Vegas PPR)
    rank_of = {}
    for pos, lst in vegas_ppr_for_rank.items():
        for i, (_, pid) in enumerate(sorted(lst, reverse=True), 1):
            rank_of[pid] = i
    for r in rows:
        if r["source"] == "vegas_implied":
            r["vegas_rank"] = rank_of.get(r["player_id"])

    # --- espn rows: name -> players uuid -> team -> week game
    for k, e in sorted(espn.items()):
        pl = by_name.get(k) or by_loose.get(norm_loose(k))
        if not pl or pl.get("position") not in ("QB", "RB", "WR", "TE"):
            gaps["espn_no_match"].append(e["name"])
            continue
        g = games_by_team.get(pl.get("team_id"))
        if not g:
            gaps["game_missing"].append(e["name"])
            continue
        for fmt_key, fmt in (("std", "standard"), ("half", "half_ppr"),
                             ("ppr", "full_ppr")):
            rows.append({
                "batch_id": batch_id, "player_id": pl["id"],
                "game_id": g["id"], "season": season, "week": week,
                "source": "espn", "scoring_format": fmt,
                "projected_points": e[fmt_key],
                "ecr_rank": (ecr.get(k) or {}).get("pos_rank"),
                "vegas_rank": rank_of.get(pl["id"]),
                "snapshot_at": snap_at, "vintage_note": vintage_note,
            })
    return rows, gaps


def write_rows(rows, batch_id):
    """Write to projection_snapshots if the table exists, else stash the
    payload as pending JSON. Returns ('table', n) or ('pending', path)."""
    if table_exists("projection_snapshots"):
        # PostgREST (PGRST102) requires every object in a batch to carry the
        # same keys; v4 builds mix vegas/espn/fantasypros rows with different
        # key sets, so normalize to the union of keys before posting.
        keys = sorted(set().union(*(r.keys() for r in rows)))
        for i in range(0, len(rows), 200):
            batch = [{k: r.get(k) for k in keys} for r in rows[i:i + 200]]
            sbclient.post("projection_snapshots", batch)
        return "table", len(rows)
    os.makedirs(PENDING_DIR, exist_ok=True)
    path = os.path.join(PENDING_DIR, f"{batch_id}.json")
    json.dump({"batch_id": batch_id, "rows": rows}, open(path, "w"))
    return "pending", path


def main():
    batch_id = str(uuid.uuid4())
    vintage = "v3 yardage-only, no TDs (pre-v4 rebuild)"
    rows, gaps = build_rows(batch_id, vintage)
    dest, info = write_rows(rows, batch_id)
    print("batch_id:", batch_id)
    print("dest:", dest, info)
    from collections import Counter
    c = Counter((r["source"], r["scoring_format"]) for r in rows)
    for k in sorted(c):
        print(f"  {k}: {c[k]}")
    print("games covered:", len(set(r["game_id"] for r in rows)))
    for g, names in gaps.items():
        print(f"gap {g}: {len(names)}", names[:8] if names else "")


if __name__ == "__main__":
    main()
