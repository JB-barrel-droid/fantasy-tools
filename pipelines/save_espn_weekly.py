#!/usr/bin/env python3
"""Store ESPN weekly actuals and weekly projections in Supabase (JEG-521 G4 a/b).

Input: the two JSON files pull_espn_projections.py writes with
`--weekly-out DIR` (espn_weekly_actuals.json, espn_weekly_projections.json).

(a) Actuals -> public.player_game_stats, one row per player per game, the
    table under public.v_player_game_actuals. The rows already there came
    from an nflverse loader that stopped after 2026 Week 4. Rules:
      - a (game, player) with no row gets ESPN's row;
      - a row ESPN wrote before (stats.source = 'espn') is updated, so stat
        corrections land;
      - a row from any other writer is never touched; ESPN's line for it is
        compared and the agreement is reported (that is the check that the
        stat ids, interceptions included, match the existing data).
    stats carries the nflverse keys plus source = 'espn' and espn_player_id;
    fantasy_points is the standard score, as in the existing rows.

(b) Weekly projections -> public.projection_snapshots (source 'espn', three
    scoring formats), for every played week and the next unplayed week.
    Change-only: a (player, week, format) gets a new row only when ESPN's
    number differs from the latest stored one, so the table is a history of
    what ESPN projected and when, without a copy per pull. Every row's
    vintage_note states the basis (MR-20: per scheduled team week; 0 when
    ESPN projects him out or on bye) and the ESPN id.

Fail closed: if fewer than MIN_RESOLVED of the actual rows resolve to a
player and a game, nothing is written and the run fails.

Writes a run summary to output/espn-weekly-store.json (committed by the
workflow, so the result is readable from the repo).

Usage:
  python3 pipelines/save_espn_weekly.py --in DIR [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import espn_weekly as ew  # noqa: E402
from player_key_index import PlayerIndex  # noqa: E402

SLEEPER_BASE = ROOT / "data" / "inputs" / "sleeper_identity_base.json"
SUMMARY = ROOT / "output" / "espn-weekly-store.json"
MIN_RESOLVED = 0.85
FORMATS = ("standard", "half_ppr", "full_ppr")
CHANGE_EPS = 0.005


# ---------------------------------------------------------------- pure parts

def norm_abbr(a: str) -> str:
    a = (a or "").upper()
    return ew.STALE_TEAM_ABBR.get(a, a)


def game_index(teams: list[dict], games: list[dict]) -> dict:
    """{(week, team abbr): {"game_id", "team_id", "starts_at"}} for one season."""
    abbr = {t["id"]: norm_abbr(t.get("abbreviation")) for t in teams}
    out = {}
    for g in games:
        for side in ("home_team_id", "away_team_id"):
            tid = g.get(side)
            if tid in abbr:
                out[(int(g["week"]), abbr[tid])] = {
                    "game_id": g["id"], "team_id": tid,
                    "starts_at": g.get("starts_at")}
    return out


def plan_actuals(rows: list[dict], index: PlayerIndex, games: dict,
                 existing: list[dict]):
    """-> (upserts, report). existing: player_game_stats rows for the weeks."""
    by_gp = {(r["game_id"], r["player_id"]): r for r in existing}
    upserts, unresolved, no_game = [], [], []
    cmp_rows = []  # (pos, espn_std, other_std)
    seen_espn_gp = set()
    how = Counter()
    no_line = 0
    for r in rows:
        e, why = index.resolve_espn(r["espn_id"], r["name"], r["pos"])
        if e is None:
            unresolved.append({"espn_id": r["espn_id"], "name": r["name"],
                               "pos": r["pos"], "week": r["week"], "why": why})
            continue
        how[why] += 1
        g = games.get((r["week"], norm_abbr(r["team"])))
        if g is None:
            no_game.append({"name": r["name"], "team": r["team"], "week": r["week"]})
            continue
        std = round(ew.points(r["stats"], "standard"), 2)
        gp = (g["game_id"], e["id"])
        seen_espn_gp.add(gp)
        prev = by_gp.get(gp)
        if prev is not None and (prev.get("stats") or {}).get("source") != "espn":
            other = ew.points(prev.get("stats") or {}, "standard")
            cmp_rows.append((r["pos"], r["week"], std, round(other, 2), r["name"]))
            continue
        if not any(r["stats"].get(k) for _sid, k in ew.STAT_KEYS):
            # ESPN gives a block with only games-played (210) and team
            # win/loss (155/156) to dressed backups with no offensive stat.
            # nflverse, the 2015-2025 history and the rest of
            # player_game_stats have no row for them, and a row reads as
            # "played" downstream, so it is not stored.
            no_line += 1
            continue
        upserts.append({
            "game_id": g["game_id"], "player_id": e["id"], "team_id": g["team_id"],
            "stats": dict(r["stats"], source="espn", espn_player_id=r["espn_id"]),
            "fantasy_points": std})
    # rows the other writer has that ESPN does not (same weeks, our positions)
    only_other = sum(1 for gp, x in by_gp.items()
                     if gp not in seen_espn_gp and (x.get("stats") or {}).get("source") != "espn")
    report = {
        "rows_in": len(rows), "resolved": len(rows) - len(unresolved),
        "resolved_by": dict(how), "n_unresolved": len(unresolved),
        "unresolved": unresolved[:60], "n_no_game": len(no_game), "no_game": no_game[:30],
        "to_upsert": len(upserts), "no_offensive_line_skipped": no_line,
        "comparison_with_existing": compare(cmp_rows, only_other),
    }
    return upserts, report


def compare(cmp_rows, only_other):
    by_pos = defaultdict(lambda: {"n": 0, "exact": 0, "abs_diff_sum": 0.0})
    worst = sorted(cmp_rows, key=lambda x: -abs(x[2] - x[3]))[:15]
    for pos, _wk, a, b, _n in cmp_rows:
        d = by_pos[pos]
        d["n"] += 1
        d["exact"] += abs(a - b) <= 0.011
        d["abs_diff_sum"] += abs(a - b)
    out = {}
    for pos, d in sorted(by_pos.items()):
        out[pos] = {"n": d["n"], "within_0.01": d["exact"],
                    "share_within_0.01": round(d["exact"] / d["n"], 4) if d["n"] else None,
                    "mean_abs_diff": round(d["abs_diff_sum"] / d["n"], 3) if d["n"] else None}
    return {"by_position": out, "existing_rows_without_espn_line": only_other,
            "largest_differences": [
                {"pos": p, "week": w, "espn_std": a, "existing_std": b, "name": n}
                for p, w, a, b, n in worst]}


def projection_weeks(played: list[int], ros_weeks: list[int]) -> set[int]:
    nxt = ros_weeks[:1]
    return set(played) | set(nxt)


def stored_projection_params(season: int, weeks) -> str:
    """PostgREST query for this writer's own earlier rows. Other writers also
    store source 'espn' rows for these weeks (v3/v4 notes); matching against
    them made the change-only check skip real weekly rows. Same filter as
    export_weekly_store.py."""
    return ("?select=id,player_key,week,scoring_format,projected_points,snapshot_at"
            f"&source=eq.espn&season=eq.{season}&week=in.({','.join(map(str, sorted(weeks)))})"
            f"&vintage_note=like.*basis={ew.BASIS}*")


def plan_projections(rows, index: PlayerIndex, games: dict, latest: dict,
                     weeks: set[int], now_iso: str, batch_id: str):
    """latest: {(player_key, week, format): projected_points} most recent stored."""
    inserts, unresolved, unchanged, no_game = [], 0, 0, 0
    for r in rows:
        if r["week"] not in weeks:
            continue
        e, why = index.resolve_espn(r["espn_id"], r["name"], r["pos"])
        if e is None:
            unresolved += 1
            continue
        g = games.get((r["week"], norm_abbr(r["team"])))
        if g is None:
            # bye, or a team the schedule does not place that week:
            # projection_snapshots.game_id is NOT NULL, so skip and count
            no_game += 1
            continue
        for fmt in FORMATS:
            pts = round(ew.points(r["stats"], fmt), 2)
            prev = latest.get((e["player_key"], r["week"], fmt))
            if prev is not None and abs(float(prev) - pts) < CHANGE_EPS:
                unchanged += 1
                continue
            inserts.append({
                "batch_id": batch_id, "player_id": e["id"], "player_key": e["player_key"],
                "game_id": g["game_id"], "season": r["season"],
                "week": r["week"], "source": "espn", "scoring_format": fmt,
                "projected_points": pts, "snapshot_at": now_iso,
                "vintage_note": (f"espn weekly projection block; basis={ew.BASIS} "
                                 f"(per scheduled team week, 0 when out or on bye); "
                                 f"espn_id={r['espn_id']}; scoring=v_player_game_actuals"),
            })
    return inserts, {"weeks": sorted(weeks), "rows_written": len(inserts),
                     "unchanged_skipped": unchanged, "unresolved_rows": unresolved,
                     "no_game_skipped": no_game}


# ---------------------------------------------------------------- IO

def _sb():
    try:
        import sbclient  # noqa: PLC0415
    except ImportError:
        sys.path.insert(0, str(ROOT / "pipelines"))
        import gh_sbclient as sbclient  # noqa: PLC0415
    return sbclient


def upsert(sb, table, rows, on_conflict=None, chunk=500):
    for i in range(0, len(rows), chunk):
        part = rows[i:i + chunk]
        if on_conflict:
            sb.post(table, part, params=f"?on_conflict={on_conflict}",
                    prefer="resolution=merge-duplicates,return=minimal")
        else:
            sb.post(table, part, prefer="return=minimal")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--in", dest="indir", required=True, type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--summary", type=Path, default=SUMMARY)
    a = ap.parse_args(argv)

    acts = json.load(open(a.indir / "espn_weekly_actuals.json"))
    projs = json.load(open(a.indir / "espn_weekly_projections.json"))
    season = acts["season"]
    sb = _sb()
    players = sb.get_all("players", "?select=id,player_key,full_name,position,active,metadata")
    teams = sb.get_all("teams", "?select=id,abbreviation")
    games_rows = sb.get_all("games", f"?select=id,week,home_team_id,away_team_id,starts_at&season=eq.{season}")
    index = PlayerIndex(players, json.load(open(SLEEPER_BASE)))
    games = game_index(teams, games_rows)

    act_weeks = sorted({r["week"] for r in acts["rows"]})
    gids = sorted({v["game_id"] for (w, _), v in games.items() if w in act_weeks})
    existing = []
    for i in range(0, len(gids), 40):
        existing += sb.get_all("player_game_stats",
                               "?select=id,game_id,player_id,stats&game_id=in.(" + ",".join(gids[i:i + 40]) + ")")
    act_up, act_rep = plan_actuals(acts["rows"], index, games, existing)

    pweeks = projection_weeks(projs["played_weeks"], projs["ros_weeks"])
    stored = sb.get_all("projection_snapshots", stored_projection_params(season, pweeks))
    latest, latest_at = {}, {}
    for s in stored:
        k = (s["player_key"], s["week"], s["scoring_format"])
        if k not in latest_at or s["snapshot_at"] > latest_at[k]:
            latest_at[k], latest[k] = s["snapshot_at"], s["projected_points"]
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    proj_ins, proj_rep = plan_projections(projs["rows"], index, games, latest, pweeks,
                                          now_iso, str(uuid.uuid4()))

    resolved_share = (act_rep["resolved"] - act_rep["n_no_game"]) / max(1, act_rep["rows_in"])
    summary = {"run_at": now_iso, "season": season, "dry_run": a.dry_run,
               "pulled_at": acts.get("pulled_at"), "played_weeks": acts.get("played_weeks"),
               "actual_weeks": act_weeks, "actuals": act_rep, "projections": proj_rep,
               "resolved_share": round(resolved_share, 4)}
    ok = resolved_share >= MIN_RESOLVED
    if ok and not a.dry_run:
        upsert(sb, "player_game_stats", act_up, on_conflict="game_id,player_id")
        upsert(sb, "projection_snapshots", proj_ins)
        summary["written"] = {"player_game_stats": len(act_up),
                              "projection_snapshots": len(proj_ins)}
    a.summary.parent.mkdir(parents=True, exist_ok=True)
    a.summary.write_text(json.dumps(summary, indent=1, default=str) + "\n")
    print(json.dumps({k: summary[k] for k in ("actual_weeks", "resolved_share")}
                     | {"to_upsert": act_rep["to_upsert"],
                        "comparison": act_rep["comparison_with_existing"]["by_position"],
                        "projection_rows": proj_rep["rows_written"]}, indent=1))
    if not ok:
        print(f"FAILED: only {resolved_share:.1%} of actual rows resolved to a player "
              f"and game (floor {MIN_RESOLVED:.0%}); nothing written", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
