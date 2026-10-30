#!/usr/bin/env python3
"""Save CBS Rest-of-Season projections into the Supabase reference table.

Loads data/raw/sources/cbsros/<date>/snapshot.json (from
pipelines/pull_cbs_ros_projections.py) and upserts it into
public.cbs_ros_projections.

Table DDL: sql/migrations/002_cbs_ros_projections.sql (run in Supabase SQL
editor; PostgREST cannot DDL).

Grain (upsert key): (player_key, cbs_snapshot_date). Writes are idempotent.

Identity (fail closed, same rule as save_espn_cbs_references.py): numeric
player_key only, resolved through lib/canonical_players, the one resolver
(JEG-438; JEG-539): public.players is the naming authority, the nickname table
and the verified aliases (data/inputs/player_aliases.json) are applied before
lookup, and the printed position must be one the table holds for that name.
Jeremy 2026-10-12 (JEG-539): when a source's position conflicts with the
player's, the position is ESPN's or Sleeper's (where the game is played), as
public.players holds it, and there is no per-source exception. CBS rest of
season prints Connor Heyward in its TE table; public.players says RB, so that
row is a position conflict and is not stored. Unmatched, ambiguous or
position-conflicting names go to the review report -- never guessed, never
zero-filled. An inactive player whose listed position the table does not hold
is skipped without a flag (canonical_players.SILENT_REASONS).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import identity_queue  # noqa: E402 -- unresolved names, counted per source (JEG-438)
import canonical_players  # noqa: E402 -- the one name -> player_key rule (JEG-438)
import projection_capture as pc  # noqa: E402 -- JEG-944 append-only forward-projection history
from nfl_week import current_nfl_week  # noqa: E402


def season_for_vintage(vintage_date: date) -> int:
    """NFL season year for a snapshot vintage date.

    The season is named for its September: Sep 2026 - Feb 2027 is the 2026
    season, so Jan-Jul dates belong to the previous year's season.
    """
    return vintage_date.year if vintage_date.month >= 8 else vintage_date.year - 1


def latest_cbsros_snapshot() -> Path:
    """Resolve the newest data/raw/sources/cbsros/<date>/snapshot.json.

    Directory names are ISO dates, so lexicographic order is chronological.
    Fail closed when no snapshot exists.
    """
    base = ROOT / "data" / "raw" / "sources" / "cbsros"
    candidates = sorted(
        p for p in base.iterdir()
        if p.is_dir() and (p / "snapshot.json").is_file()
    )
    if not candidates:
        raise SystemExit(
            "Fail closed: no cbsros snapshot found under data/raw/sources/cbsros/."
        )
    return candidates[-1] / "snapshot.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sb():
    bin_dir = os.path.expanduser("~/workspace/skills/supabase-football-signal/bin")
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    import sbclient  # noqa: E402

    return sbclient


def _default_fetch_players() -> list[dict[str, Any]]:
    sbclient = _sb()
    rows = sbclient.get_all("players", params="?select=player_key,full_name,position,active")
    if not isinstance(rows, list):
        raise SystemExit("Unexpected Supabase response for players")
    return [r for r in rows if isinstance(r, dict)]


def _default_upsert(table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
    sbclient = _sb()
    for start in range(0, len(rows), 500):
        chunk = rows[start : start + 500]
        sbclient.post(
            table,
            chunk,
            params=f"?on_conflict={on_conflict}",
            prefer="resolution=merge-duplicates",
        )


def _default_count(table: str, params: str) -> int:
    sbclient = _sb()
    rows = sbclient.get_all(table, params=params)
    return len(rows) if isinstance(rows, list) else -1


def _default_delete(table: str, vintage: str, keep_keys: set[int]) -> None:
    """Delete rows for vintage where player_key is NOT in keep_keys."""
    sbclient = _sb()
    # Fetch all player_keys for this vintage
    rows = sbclient.get_all(
        table,
        params=f"?select=player_key&cbs_snapshot_date=eq.{vintage}",
    )
    if not isinstance(rows, list):
        return
    to_delete = [r["player_key"] for r in rows if r.get("player_key") not in keep_keys]
    # Delete in chunks of 500
    for start in range(0, len(to_delete), 500):
        chunk = to_delete[start : start + 500]
        sbclient.delete(
            table,
            params=f"?player_key=in.({','.join(map(str, chunk))})&cbs_snapshot_date=eq.{vintage}",
        )


fetch_players: Callable[[], list[dict[str, Any]]] = _default_fetch_players
upsert_rows: Callable[[str, list[dict[str, Any]], str], None] = _default_upsert
count_rows: Callable[[str, str], int] = _default_count
delete_rows: Callable[[str, str, set[int]], None] = _default_delete


def build_registry(players: list[dict[str, Any]]) -> "canonical_players.Registry":
    """The canonical resolver's registry over the fetched public.players rows."""
    return canonical_players.load_registry(rows=[
        r for r in players
        if isinstance(r.get("player_key"), int) and str(r.get("full_name") or "").strip()])


def resolve_name(
    name: str,
    pos: str | None,
    registry: "canonical_players.Registry",
    norm_hint: str | None = None,
) -> tuple[int | None, str | None]:
    """Return (player_key, None), or (None, reason) with reason one of
    unmatched | ambiguous | position_conflict | inactive.

    Only lib/canonical_players resolves (JEG-539). The snapshot's own
    `player_norm` is tried, through the same resolver, only when the printed
    name matches no player. A position conflict or an ambiguity is final.
    """
    key, reason = canonical_players.resolve_with_reason(name, position=pos or None, registry=registry)
    if key is None and reason == "unmatched" and norm_hint and norm_hint != name:
        key, reason = canonical_players.resolve_with_reason(norm_hint, position=pos or None, registry=registry)
    return (key, None) if key is not None else (None, reason)


def parse_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def build_cbsros_rows(snapshot_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    vintage = snap.get("vintage_date")
    if not vintage:
        raise SystemExit("Fail closed: CBS ROS snapshot has no vintage_date.")
    try:
        vintage_date = date.fromisoformat(vintage)
    except ValueError:
        raise SystemExit(
            f"Fail closed: CBS ROS snapshot vintage_date is not an ISO date: {vintage!r}."
        )
    # Season and content week describe the SNAPSHOT's vintage, never the run
    # date -- the saver must stamp the data it actually read.
    season = season_for_vintage(vintage_date)
    week = current_nfl_week(vintage_date)
    rows = snap.get("rows", [])
    if not rows:
        raise SystemExit("Fail closed: CBS ROS snapshot has no rows.")

    registry = build_registry(fetch_players())
    clean: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    pulled_at = utc_now()

    for row in rows:
        name = str(row.get("player_name") or "").strip()
        pos = str(row.get("pos") or "").strip().upper() or None
        if not name:
            review.append({"reason": "missing_player_name", "row": row})
            continue
        key, reason = resolve_name(name, pos, registry, row.get("player_norm"))
        if key is None:
            if reason in canonical_players.SILENT_REASONS:
                continue  # an inactive player at another position: no value, no flag (JEG-539)
            review.append(
                {
                    "reason": reason,
                    "player_name": name,
                    "player_norm": row.get("player_norm"),
                    "pos": pos,
                }
            )
            continue
        clean.append(
            {
                "player_key": key,
                "player_norm": row.get("player_norm"),
                "ros_standard": parse_float(row.get("ros_standard")),
                "ros_half_ppr": parse_float(row.get("ros_half_ppr")),
                "ros_ppr": parse_float(row.get("ros_ppr")),
                "per_game_standard": parse_float(row.get("per_game_standard")),
                "per_game_half_ppr": parse_float(row.get("per_game_half_ppr")),
                "per_game_ppr": parse_float(row.get("per_game_ppr")),
                "gp": parse_float(row.get("gp")),
                "receptions": parse_float(row.get("receptions")),
                "raw_stats": row.get("raw_stats"),
                "cbs_snapshot_date": vintage,
                "pulled_at": pulled_at,
                "scoring": "half_ppr",
                "season": season,
                "week": week,
                "source_content_date": vintage,
                "_run_id": f"cbsros-save-{vintage}",
                "_writer_identity": "save_cbsros_references.py",
            }
        )

    return clean, review, vintage


def capture_rows(snap_rows: list, weekly: dict | None, registry: "canonical_players.Registry",
                 **common: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """JEG-944 capture rows for CBS, resolved through resolve_name over `registry`.
    The one place the resolver is injected into pc.cbs_capture_rows, so the save and
    the Sunday dry run (capture_projections_only.py) resolve names the same way
    (JEG-1386; the identity guard pins this file as the only caller)."""
    return pc.cbs_capture_rows(
        snap_rows, weekly,
        lambda n, p, norm: resolve_name(str(n or "").strip(), (p or "").upper() or None, registry, norm)[0],
        **common)


def save_captures(snapshot_path: Path, vintage: str) -> None:
    """JEG-944: append CBS's ROS rows and per-week rows to source_projection_captures.
    Never raises and never changes cbs_ros_projections (see pc.save_capture_or_flag)."""
    if upsert_rows is not _default_upsert:
        return  # the writer is stubbed (tests): never open a live client from here
    try:
        snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
        weekly_path = snapshot_path.with_name("weekly_snapshot.json")
        weekly = json.loads(weekly_path.read_text(encoding="utf-8")) if weekly_path.exists() else None
        registry = build_registry(fetch_players())
        today = datetime.now(timezone.utc).date()
        source_week = current_nfl_week(today)
        phase = pc.capture_phase(datetime.now(timezone.utc))
        rows, rep = capture_rows(
            snap.get("rows", []), weekly, registry,
            season=season_for_vintage(today), source_week=source_week, capture_at=utc_now(),
            phase=phase, batch_id=pc.new_batch(), vintage=vintage)
        print(f"capture plan: {json.dumps(rep, default=str)}")
        if weekly is None or not weekly.get("weeks"):
            print("::error title=projection capture cbs week::no CBS per-week pages in the pull "
                  f"({(weekly or {}).get('errors')}); only ROS is captured this run")
        for line in pc.save_capture_or_flag(_sb(), rows, "cbs", season_for_vintage(today),
                                            source_week, phase, ("ros", "week")):
            print(line)
    except Exception as exc:  # noqa: BLE001
        print(f"::error title=projection capture cbs::{type(exc).__name__}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Save CBS ROS snapshot to Supabase.")
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        help="Path to the cbsros snapshot.json (default: latest under data/raw/sources/cbsros/)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build rows but do not write.")
    args = parser.parse_args()

    snapshot_path = args.snapshot or latest_cbsros_snapshot()
    clean, review, vintage = build_cbsros_rows(snapshot_path)
    table = "cbs_ros_projections"  # bare name: PostgREST path is /rest/v1/<table>
    conflict = "player_key,cbs_snapshot_date"

    print(f"cbsros {vintage}: {len(clean)} clean rows, {len(review)} review rows")
    for r in review[:10]:
        print(f"  review: {r.get('reason')}: {r.get('player_name')}")

    if args.dry_run:
        print(f"[dry-run] would upsert {len(clean)} rows into {table}")
        return

    if not clean:
        raise SystemExit("Fail closed: zero clean rows, not writing.")

    # Upsert the clean rows first
    upsert_rows(table, clean, conflict)

    # Prune: delete rows for this vintage whose player_key is NOT in the new clean set
    clean_keys = {row["player_key"] for row in clean}
    delete_rows(table, vintage, clean_keys)

    # Verify: after prune, table must hold exactly len(clean) rows for the vintage
    live = count_rows(table, f"?select=id&cbs_snapshot_date=eq.{vintage}")
    print(f"Verified: {table} holds {live} rows for vintage {vintage}")
    if live != len(clean):
        raise SystemExit(
            f"Fail closed: {table} holds {live} rows for vintage {vintage} "
            f"after prune, expected {len(clean)}."
        )
    identity_queue.record_misses("cbsros", review)
    print("CBS ROS save complete.")
    save_captures(snapshot_path, vintage)


if __name__ == "__main__":
    main()
