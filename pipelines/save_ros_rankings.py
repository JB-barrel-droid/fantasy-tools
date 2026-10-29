#!/usr/bin/env python3
"""Save the ROS rankings snapshot into public.ros_rankings (JEG-1198 option C).

Reads the snapshot pipelines/pull_ros_rankings.py writes and upserts it into
public.ros_rankings. Mirrors pipelines/save_razzball_references.py.

Table DDL: sql/migrations/015_ros_rankings.sql, a DRAFT that needs Jeremy's explicit
approval before it is applied; this saver never creates or alters the table. Until it is
applied, run with --dry-run only.

Rankings only: nothing here feeds DDF Value or DDF Projections, and the trade-value
importer never reads this table (tests/test_ros_rankings.py).

Grain (upsert key): (source, analyst, scoring, pos, player_key, source_vintage). Idempotent.
The analyst is part of the key because fantasypros_expert_ros carries one list per expert.

ROS only (Jeremy, 2026-10-29: "do not blend weekly data with ROS data, ever"): every
source here is a rest-of-season list; no weekly ranking is ever saved into this table.

Identity (fail closed): numeric player_key only, through lib/canonical_players (the one
name rule, curated nicknames, verified aliases, position check). Unmatched, ambiguous or
position-conflicting names go to the review report, never guessed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import canonical_players  # noqa: E402 -- the one name -> player_key rule (JEG-438)
from nfl_week import current_nfl_week  # noqa: E402

TABLE = "ros_rankings"
CONFLICT = "source,analyst,scoring,pos,player_key,source_vintage"
SOURCES = {"fantasypros_ros_ecr", "fantasypros_expert_ros", "yahoo_pianowski_ros"}
COLUMNS = ("source", "analyst", "scoring", "pos", "player_name", "team", "pos_rank", "overall_rank",
           "source_value", "tier", "rank_min", "rank_max", "rank_avg", "rank_std", "experts",
           "source_vintage", "source_url")


def season_for_vintage(vintage_date: date) -> int:
    return vintage_date.year if vintage_date.month >= 8 else vintage_date.year - 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sb():
    bin_dir = os.path.expanduser("~/workspace/skills/supabase-football-signal/bin")
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    import sbclient  # noqa: E402

    return sbclient


def _default_fetch_players() -> list[dict[str, Any]]:
    rows = _sb().get_all("players", params="?select=player_key,full_name,position,active")
    if not isinstance(rows, list):
        raise SystemExit("Unexpected Supabase response for players")
    return [r for r in rows if isinstance(r, dict)]


def _default_upsert(table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
    sbclient = _sb()
    for start in range(0, len(rows), 500):
        sbclient.post(table, rows[start:start + 500], params=f"?on_conflict={on_conflict}",
                      prefer="resolution=merge-duplicates")


def _default_count(table: str, params: str) -> int:
    rows = _sb().get_all(table, params=params)
    return len(rows) if isinstance(rows, list) else -1


fetch_players: Callable[[], list[dict[str, Any]]] = _default_fetch_players
upsert_rows: Callable[[str, list[dict[str, Any]], str], None] = _default_upsert
count_rows: Callable[[str, str], int] = _default_count


def build_rows(snap: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if snap.get("schema") != "ros-rankings-snapshot-v1":
        raise SystemExit(f"Fail closed: unexpected snapshot schema {snap.get('schema')!r}.")
    rows = snap.get("rows") or []
    if not rows:
        raise SystemExit("Fail closed: ROS rankings snapshot has no rows.")
    registry = canonical_players.load_registry(rows=[
        r for r in fetch_players()
        if isinstance(r.get("player_key"), int) and str(r.get("full_name") or "").strip()])
    clean: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = list(snap.get("review_rows") or [])
    pulled_at = utc_now()
    for row in rows:
        if row.get("source") not in SOURCES:
            raise SystemExit(f"Fail closed: unknown source {row.get('source')!r} in snapshot.")
        if not str(row.get("analyst") or "").strip():
            raise SystemExit(f"Fail closed: {row['source']} row without an analyst.")
        name, pos = str(row.get("player_name") or "").strip(), str(row.get("pos") or "").upper()
        key, reason = canonical_players.resolve_with_reason(name, position=pos or None, registry=registry)
        if key is None:
            if reason not in canonical_players.SILENT_REASONS:
                review.append({"source": row["source"], "reason": reason, "player_name": name, "pos": pos})
            continue
        vintage = date.fromisoformat(row["source_vintage"])
        clean.append({
            **{c: row.get(c) for c in COLUMNS}, "pos": pos, "player_key": key,
            "season": season_for_vintage(vintage), "week": current_nfl_week(vintage),
            "pulled_at": pulled_at, "_written_at": pulled_at,
            "_run_id": f"ros-rankings-save-{pulled_at[:10]}", "_writer_identity": "save_ros_rankings.py",
        })
    # Two printed names can resolve to one player_key: keep the better (lower) rank, flag it.
    best: dict[tuple, dict[str, Any]] = {}
    for r in clean:
        ck = (r["source"], r["analyst"], r["scoring"], r["pos"], r["player_key"], r["source_vintage"])
        if ck in best:
            review.append({"source": r["source"], "reason": "duplicate_player_key",
                           "player_name": r["player_name"], "pos": r["pos"],
                           "other": best[ck]["player_name"]})
            if r["pos_rank"] >= best[ck]["pos_rank"]:
                continue
        best[ck] = r
    return list(best.values()), review


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Save the ROS rankings snapshot to Supabase.")
    ap.add_argument("--snapshot", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true", help="Resolve and count rows; write nothing.")
    args = ap.parse_args(argv)
    snap = json.loads(args.snapshot.read_text(encoding="utf-8"))
    clean, review = build_rows(snap)
    by: dict[tuple, int] = {}
    lists: dict[tuple, set] = {}
    for r in clean:
        k = (r["source"], r["scoring"], r["pos"])
        by[k] = by.get(k, 0) + 1
        lists.setdefault(k, set()).add(r["analyst"])
    for k in sorted(by):
        print(f"ros {k[0]} {k[1]} {k[2]}: {by[k]} rows from {len(lists[k])} list(s)")
    print(f"ros rankings: {len(clean)} clean rows, {len(review)} review rows")
    for r in review[:15]:
        print(f"  review: {r.get('source')} {r.get('reason')}: {r.get('player_name')} ({r.get('pos')})")
    if args.dry_run:
        print(f"[dry-run] would upsert {len(clean)} rows into {TABLE}")
        return 0
    if not clean:
        raise SystemExit("Fail closed: zero clean rows, not writing.")
    upsert_rows(TABLE, clean, CONFLICT)
    pulled = quote(clean[0]["pulled_at"], safe="")
    live = count_rows(TABLE, f"?select=id&pulled_at=eq.{pulled}")
    print(f"Verified: {TABLE} holds {live} rows from this save")
    if live != len(clean):
        raise SystemExit(f"Fail closed: {TABLE} holds {live} rows from this save, expected {len(clean)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
