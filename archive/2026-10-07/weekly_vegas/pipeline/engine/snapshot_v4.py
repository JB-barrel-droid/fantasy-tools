"""Projection snapshots, v4 vintage: TD-inclusive freeze.

Reuses the v4 engine (v4/compute_v4.py):
- load_props(): latest line per (player, market, book, selection) with the
  median-line / closest-book odds fix; player_anytime_td -> per-book fair
  one-sided prob (hold estimated from two-sided markets, since No is never
  posted) -> median fair prob -> Poisson E[TDs] = -ln(1-p).
- ECR feed expert projections (loaders/fantasypros.py read_projections_dict,
  TD-inclusive). 2026-09-12: the ECR feed is the expert leg; ESPN rows are
  no longer written.

Row grain: one row per (batch_id, player_id, game_id, source, scoring_format).
Sources: 'vegas_implied', 'fantasypros'. Formats: 'standard', 'half_ppr', 'full_ppr'.
Coverage gate (same as v4): a Vegas number built from TD props alone (no
yardage line markets posted) is not comparable to a full expert projection,
so those players get no vegas_implied rows ("no TD-only ghosts").

ecr_rank rides along where an ECR entry exists; vegas_rank is the
player's rank by Vegas-implied PPR within their position group.
Writes to projection_snapshots if the table exists, else stages the payload
as pending JSON (same shape as the v3 batch).
"""
import os
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_vegas/pipeline root
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))
import sbclient  # noqa: E402

from engine.vegas import vegas_implied_points, vegas_provenance  # noqa: E402
from engine.fds_fallback import (  # noqa: E402
    load_payload as fds_load_payload, index_payload as fds_index_payload,
    compute_fds_points, fds_row_detail, fds_vintage_note, is_sunday_kickoff,
    FDS_PROVENANCE, FDS_PARTIAL, ALLOWED_PROVENANCE,
)
from engine.source_priority import (  # noqa: E402
    VEGAS_SOURCE_PRIORITY, check_priority,
)
from engine.snapshot import (  # noqa: E402
    load_ecr, load_players, load_week_games,
    norm, norm_loose, table_exists, write_rows,
)
from v4.compute_v4 import load_props, LINE_MARKETS  # noqa: E402
from loaders.fantasypros import read_projections_dict  # noqa: E402  (ECR feed expert points)

VINTAGE_V4 = "v4 TD-inclusive (Poisson E[TD], vig-corrected one-sided)"
POSITIONS = ("QB", "RB", "WR", "TE")
FMT_MAP = (("std", "standard", "standard"),
           ("half", "half_ppr", "half_ppr"),
           ("ppr", "full_ppr", "ppr"))


def load_odds_identity(game_ids=None):
    """uuid + game_id per raw prop player_name from odds_history metadata.

    game_ids: optional set of games.id to scope to (the intended week).
    When given, rows for other games are skipped, so a player's most
    recent prop row can never resolve to a game outside the week.
    """
    rows = sbclient.get_all(
        "odds_history",
        "?select=game_id,recorded_at,metadata&limit=100000",
    )
    uuid_by_name, game_by_name, seen_at = {}, {}, {}
    for r in rows:
        if game_ids is not None and r.get("game_id") not in game_ids:
            continue
        m = r.get("metadata") or {}
        nm = m.get("player_name") or ""
        if not nm:
            continue
        if m.get("player_id") and nm not in uuid_by_name:
            uuid_by_name[nm] = m["player_id"]
        ra = r.get("recorded_at") or ""
        if r.get("game_id") and ra >= seen_at.get(nm, ""):
            game_by_name[nm] = r["game_id"]
            seen_at[nm] = ra
    return uuid_by_name, game_by_name


def upcoming_game_ids(games_by_id, now=None):
    """IDs of week games not yet kicked off.

    Signals are pre-game only: a kicked-off game is unbettable, so the
    snapshot (like v4/compute_v4.py) scopes to games whose starts_at is
    still in the future. `now` is injectable for tests.
    """
    _now = now or datetime.now(timezone.utc)
    out = set()
    for _gid, _g in games_by_id.items():
        try:
            _sa = datetime.fromisoformat(str(_g.get("starts_at")))
        except (ValueError, TypeError):
            continue
        if _sa.tzinfo is None:
            _sa = _sa.replace(tzinfo=timezone.utc)
        if _sa > _now:
            out.add(_gid)
    return out


def fds_legs_present(comp):
    """True when the FDS recompute produced at least one Vegas leg.

    A player whose FDS stats are all projection-attributed (or missing)
    has every leg null — there is no Vegas number to snapshot, so
    build_rows_v4 writes no row for them (recorded in
    gaps['fds_no_vegas_stats']). Mirrors validate_signal_rows'
    all-null-leg skip in engine.fds_fallback. This keeps
    validate_rows_v4's empty-detail block meaningful: any FDS row that
    IS written must carry non-empty per-stat detail.
    """
    return not (comp["std"] is None and comp["half"] is None
                and comp["ppr"] is None)


def rank_vegas_ppr(by_pos):
    """Positional rank over full-PPR Vegas numbers (union of local +
    FDS-derived legs; vegas_provenance tells them apart).

    A null leg (2026-09-18 rule: null — never zero — when no
    vegas-attributed stat can move a leg) has no rank: it is excluded
    from the ordering, so it can never TypeError the sort (crashed the
    2026-09-20 Sunday chain) and never inherits a bogus position. Such
    rows keep vegas_rank NULL downstream.
    """
    rank_of = {}
    for pos, lst in by_pos.items():
        ranked = sorted(((p, pid) for p, pid in lst if p is not None),
                        reverse=True)
        for i, (_, pid) in enumerate(ranked, 1):
            rank_of[pid] = i
    return rank_of


def build_rows_v4(batch_id, vintage_note=VINTAGE_V4, season=2026, week=1):
    games_by_id, games_by_team = load_week_games(season, week)
    # Week-scoping (2026-09-17): load_props() takes the latest row per
    # (player, market, book) with no week filter of its own, so an UNSCOPED
    # call happily builds a "week N" Vegas number from week N-1 prop rows
    # (observed: 206 of 222 vegas rows in a week-2 batch were priced from
    # week-1 lines and attached to week-2 games via the team fallback).
    # Scope to this week's not-yet-kicked-off games — the same pre-game rule
    # v4/compute_v4.py uses — so a player with no props for the current week
    # gets no vegas_implied row instead of a stale one.
    upcoming = upcoming_game_ids(games_by_id)
    player_props, td_cover, _prop_meta = load_props(game_ids=upcoming)
    ecr_proj = read_projections_dict(week)
    ecr = load_ecr()  # {norm_name: {pos_rank, pos}}
    by_name, by_loose, by_id = load_players()
    uuid_by_name, game_by_name = load_odds_identity(game_ids=upcoming)
    snap_at = datetime.now(timezone.utc).isoformat()

    # player_id -> pos_rank via the player crosswalk. More robust than the
    # raw-name lookup below: pid was already resolved through loose matching
    # and odds metadata, so this fills ECR ranks the strict name lookup misses
    # (v_latest_signals needs ecr_rank for rank_gap).
    ecr_by_pid = {}
    for nm, info in ecr.items():
        if info.get("pos_rank") is None:
            continue
        _pl = by_name.get(nm) or by_loose.get(norm_loose(nm))
        if _pl:
            ecr_by_pid.setdefault(_pl["id"], info["pos_rank"])

    rows = []
    gaps = {"vegas_no_uuid": [], "vegas_no_game": [],
            "vegas_td_only": [], "fp_no_match": [], "fp_no_game": []}

    # --- vegas_implied rows ---
    vegas_ppr_for_rank = defaultdict(list)  # pos -> [(ppr, player_uuid)]
    vegas_tmp = []  # (pid, pos, raw_name, pts dict, prov, leg)
    local_keys = set()

    for raw_name in sorted(player_props):
        props = player_props[raw_name]
        # coverage gate: TD-only ghosts get no Vegas number
        if not (set(props.keys()) & LINE_MARKETS):
            gaps["vegas_td_only"].append(raw_name)
            continue
        pid = uuid_by_name.get(raw_name)
        if not pid:
            fb = by_loose.get(norm_loose(raw_name))
            pid = fb["id"] if fb else None
        if not pid:
            gaps["vegas_no_uuid"].append(raw_name)
            continue
        pl = by_id.get(pid)
        pos = (ecr.get(norm(raw_name)) or {}).get("pos") or \
            (pl.get("position") if pl else None)
        if pos not in POSITIONS:
            continue
        gid = game_by_name.get(raw_name)
        if not gid or gid not in games_by_id:
            # fallback: player team -> week game
            g = games_by_team.get(pl.get("team_id")) if pl else None
            gid = g["id"] if g else None
        if not gid:
            gaps["vegas_no_game"].append(raw_name)
            continue
        try:
            full = {sc: vegas_implied_points(props, position=pos, scoring=sc)
                    for sc in ("standard", "half_ppr", "ppr")}
            raw = {sc: full[sc]["points"] for sc in full}
            _ppr = full["ppr"]
        except Exception:
            continue
        pts = {"std": raw["standard"], "half": raw["half_ppr"],
               "ppr": raw["ppr"]}
        # Completeness provenance (user-approved 2026-09-12): stored on every
        # vegas_implied row; only 'complete'/'td-filled' are publishable.
        prov = vegas_provenance(_ppr["markets_used"], _ppr["td_source"], pos)
        vegas_ppr_for_rank[pos].append((pts["ppr"], pid))
        vegas_tmp.append((pid, gid, raw_name, pts, prov, "local", None))
        local_keys.add(norm(raw_name))

    # --- FDS-derived fallback rows (user-approved 2026-09-17) ---
    # Players with no local props-derived number get fantasy points
    # recomputed LOCALLY from First Down Studio's vegas-attributed
    # translated stats only — never FDS's blended derived points, never a
    # projection-attributed stat. Labeled 'fds-derived' (publishable) or
    # 'fds-partial' (informational). Local wins wherever it exists, per
    # engine.source_priority. FDS numbers never touch odds_history/
    # engine.vegas.
    fds_payload = None
    fds_added = {FDS_PROVENANCE: 0, FDS_PARTIAL: 0}
    fds_notes = {}
    try:
        fds_payload = fds_load_payload(week)
    except ValueError as e:
        raise SystemExit(f"FDS fallback BLOCKED: {e}")
    if fds_payload is not None:
        check_priority(VEGAS_SOURCE_PRIORITY)
        for key, rec in sorted(fds_index_payload(fds_payload).items()):
            if key in local_keys:
                continue  # local wins
            if not is_sunday_kickoff(rec):
                # Authorized scope: Sunday games only (user 2026-09-17).
                gaps.setdefault("fds_not_sunday", []).append(rec["name"])
                continue
            pl = by_name.get(key) or by_loose.get(norm_loose(key))
            if not pl:
                gaps.setdefault("fds_no_match", []).append(rec["name"])
                continue
            pos = pl.get("position")
            if pos != rec["pos"]:
                # Fail-closed against bad player mappings: the FDS record's
                # position must agree with the players table (a mismatch
                # means the name resolved to the wrong player row).
                gaps.setdefault("fds_pos_mismatch", []).append(rec["name"])
                continue
            g = games_by_team.get(pl.get("team_id"))
            if not g:
                gaps.setdefault("fds_no_game", []).append(rec["name"])
                continue
            comp = compute_fds_points(rec)
            if not fds_legs_present(comp):
                # No vegas-attributed stat feeds any leg (every stat is
                # projection-attributed or missing): there is no Vegas
                # number to snapshot. Skip the row — mirrors
                # validate_signal_rows' all-null-leg skip — and keep the
                # attribution in the gap note. Writing the row would trip
                # validate_rows_v4's empty-detail block below.
                gaps.setdefault("fds_no_vegas_stats", []).append(rec["name"])
                continue
            pts = {"std": comp["std"], "half": comp["half"],
                   "ppr": comp["ppr"]}
            prov = comp["completeness"]
            vegas_ppr_for_rank[pos].append((pts["ppr"], pl["id"]))
            # Per-stat provenance travels with the row: the vegas-attributed
            # inputs that fed the Vegas leg, the full stat attribution, and
            # the projection-attributed stats kept separate. Mapped through
            # the shared fds_row_detail() helper (never hand-rolled keys —
            # a hand-rolled mapping KeyError'd this build on 2026-09-20).
            # A missing per-stat payload fails the build below in
            # validate_rows_v4 — never ships quietly.
            fds_detail = fds_row_detail(comp)
            vegas_tmp.append((pl["id"], g["id"], rec["name"], pts,
                              prov, "fds", fds_detail))
            fds_notes[pl["id"]] = fds_vintage_note(
                fds_payload, comp["vegas_stats_used"])
            fds_added[prov] += 1
        print(f"FDS fallback: {sum(fds_added.values())} players added "
              f"(derived={fds_added[FDS_PROVENANCE]}, "
              f"partial={fds_added[FDS_PARTIAL]})", flush=True)
    else:
        print("FDS fallback: no payload file — local-only snapshot",
              flush=True)

    rank_of = rank_vegas_ppr(vegas_ppr_for_rank)

    for pid, gid, raw_name, pts, prov, leg, fds_detail in vegas_tmp:
        for fkey, fmt, sc in FMT_MAP:
            row = {
                "batch_id": batch_id, "player_id": pid, "game_id": gid,
                "season": season, "week": week, "source": "vegas_implied",
                "scoring_format": fmt, "projected_points": pts[fkey],
                "vegas_provenance": prov,
                "ecr_rank": ecr_by_pid.get(
                    pid, (ecr.get(norm(raw_name)) or {}).get("pos_rank")),
                "vegas_rank": rank_of.get(pid),
                "snapshot_at": snap_at,
                "vintage_note": (fds_notes.get(pid, vintage_note)
                                 if leg == "fds" else vintage_note),
            }
            if leg == "fds":
                # Schema-level per-stat provenance (user 2026-09-17): the
                # vegas-attributed inputs behind the Vegas leg, the full
                # per-stat attribution, and the projection-attributed stats
                # labeled separately. Missing detail fails the build in
                # main(); it is never written silently.
                row["vegas_stats_used"] = (fds_detail or {}).get(
                    "vegas_stats_used")
                row["fds_stat_sources"] = (fds_detail or {}).get(
                    "fds_stat_sources")
                row["fds_projection_stats"] = (fds_detail or {}).get(
                    "fds_projection_stats")
            rows.append(row)

    # --- ECR feed expert rows (full projections, TDs included) ---
    for k in sorted(ecr_proj):
        e = ecr_proj[k]
        pl = by_name.get(k) or by_loose.get(norm_loose(k))
        if not pl or pl.get("position") not in POSITIONS:
            gaps["fp_no_match"].append(e["name"])
            continue
        g = games_by_team.get(pl.get("team_id"))
        if not g:
            gaps["fp_no_game"].append(e["name"])
            continue
        for fkey, fmt, _ in FMT_MAP:
            rows.append({
                "batch_id": batch_id, "player_id": pl["id"],
                "game_id": g["id"], "season": season, "week": week,
                "source": "fantasypros", "scoring_format": fmt,
                "projected_points": e[fkey],
                "ecr_rank": ecr_by_pid.get(
                    pl["id"], (ecr.get(k) or {}).get("pos_rank")),
                "vegas_rank": rank_of.get(pl["id"]),
                "snapshot_at": snap_at, "vintage_note": vintage_note,
            })
    return rows, gaps


def validate_rows_v4(rows):
    """Fail-closed guards over a built snapshot batch (no DB writes here).

    - Every vegas_implied row must carry a valid completeness provenance
      label ('complete'/'td-filled'/'partial'/'fds-derived'/'fds-partial').
    - Every FDS-leg row must carry schema-level per-stat provenance: the
      vegas-attributed stats that fed its Vegas leg plus the full per-stat
      attribution. Missing or empty detail blocks the batch.
    Raises SystemExit on the first violation — a missing label or missing
    per-stat detail never ships quietly.
    """
    bad = [r for r in rows
           if r.get("source") == "vegas_implied"
           and r.get("vegas_provenance") not in ALLOWED_PROVENANCE]
    if bad:
        raise SystemExit(
            f"snapshot BLOCKED: {len(bad)} vegas_implied rows with missing/"
            f"invalid vegas_provenance (e.g. {bad[0].get('player_id')})")
    bad_fds = [r for r in rows
               if r.get("vegas_provenance") in (FDS_PROVENANCE, FDS_PARTIAL)
               and (not r.get("vegas_stats_used")
                    or not r.get("fds_stat_sources"))]
    if bad_fds:
        raise SystemExit(
            f"snapshot BLOCKED: {len(bad_fds)} FDS-leg rows missing per-stat "
            f"provenance (e.g. {bad_fds[0].get('player_id')})")


def main(week=None, season=2026):
    from engine.week import current_week
    week = week or current_week(season)
    batch_id = str(uuid.uuid4())
    rows, gaps = build_rows_v4(batch_id, season=season, week=week)
    validate_rows_v4(rows)
    dest, info = write_rows(rows, batch_id)
    print("batch_id:", batch_id)
    print("dest:", dest, info)
    c = Counter((r["source"], r["scoring_format"]) for r in rows)
    for k in sorted(c):
        print(f"  {k}: {c[k]}")
    games = set(r["game_id"] for r in rows)
    print("games covered:", len(games))
    for g, names in gaps.items():
        print(f"gap {g}: {len(names)}", names[:6] if names else "")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--season", type=int, default=2026)
    a = ap.parse_args()
    main(week=a.week, season=a.season)
