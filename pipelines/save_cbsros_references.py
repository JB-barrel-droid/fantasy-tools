#!/usr/bin/env python3
"""Save CBS Rest-of-Season projections into the Supabase reference table.

Loads data/raw/sources/cbsros/<date>/snapshot.json (from
pipelines/pull_cbs_ros_projections.py) and upserts it into
public.cbs_ros_projections.

Table DDL: sql/migrations/002_cbs_ros_projections.sql (run in Supabase SQL
editor; PostgREST cannot DDL).

Grain (upsert key): (player_key, cbs_snapshot_date). Writes are idempotent.

Identity (fail closed, same rule as save_espn_cbs_references.py): numeric
player_key only, resolved via public.players (full_name is the naming
authority). The verified spelling ALIASES (shared with
build_ddf_two_tier_leg.py) are applied before lookup. Unmatched or ambiguous
names go to the review report -- never guessed, never zero-filled.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "pipelines"))
from match_source_snapshot import normalize_name  # noqa: E402
from build_ddf_two_tier_leg import ALIASES  # noqa: E402


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
    rows = sbclient.get_all("players", params="?select=player_key,full_name,position")
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


fetch_players: Callable[[], list[dict[str, Any]]] = _default_fetch_players
upsert_rows: Callable[[str, list[dict[str, Any]], str], None] = _default_upsert
count_rows: Callable[[str, str], int] = _default_count


def build_name_index(players: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for record in players:
        key = record.get("player_key")
        name = str(record.get("full_name") or "").strip()
        if not isinstance(key, int) or not name:
            continue
        index.setdefault(normalize_name(name), []).append(
            {
                "player_key": key,
                "full_name": name,
                "position": str(record.get("position") or "").strip().upper() or None,
            }
        )
    return index


def resolve_name(
    name: str, pos: str | None, index: dict[str, list[dict[str, Any]]]
) -> tuple[int | None, str | None]:
    """Return (player_key, reason). Unresolved -> (None, reason)."""
    norm = normalize_name(name)
    norm = ALIASES.get(norm, norm)
    candidates = index.get(norm, [])
    if not candidates:
        return None, "no_match"
    if len(candidates) == 1:
        return candidates[0]["player_key"], None
    wanted = (pos or "").strip().upper()
    if wanted:
        filtered = [c for c in candidates if c.get("position") == wanted]
        if len(filtered) == 1:
            return filtered[0]["player_key"], None
    return None, "ambiguous"


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
    rows = snap.get("rows", [])
    if not rows:
        raise SystemExit("Fail closed: CBS ROS snapshot has no rows.")

    index = build_name_index(fetch_players())
    clean: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    pulled_at = utc_now()

    for row in rows:
        name = str(row.get("player_name") or "").strip()
        pos = str(row.get("pos") or "").strip().upper() or None
        if not name:
            review.append({"reason": "missing_player_name", "row": row})
            continue
        key, reason = resolve_name(name, pos, index)
        if key is None:
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
                "season": 2026,
                "week": 4,
                "source_content_date": vintage,
                "_run_id": f"cbsros-save-{vintage}",
                "_writer_identity": "save_cbsros_references.py",
            }
        )

    return clean, review, vintage


def main() -> None:
    parser = argparse.ArgumentParser(description="Save CBS ROS snapshot to Supabase.")
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=ROOT / "data" / "raw" / "sources" / "cbsros" / "2026-09-30" / "snapshot.json",
        help="Path to the cbsros snapshot.json",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build rows but do not write.")
    args = parser.parse_args()

    clean, review, vintage = build_cbsros_rows(args.snapshot)
    table = "public.cbs_ros_projections"
    conflict = "player_key,cbs_snapshot_date"

    print(f"cbsros {vintage}: {len(clean)} clean rows, {len(review)} review rows")
    for r in review[:10]:
        print(f"  review: {r.get('reason')}: {r.get('player_name')}")

    if args.dry_run:
        print(f"[dry-run] would upsert {len(clean)} rows into {table}")
        return

    if not clean:
        raise SystemExit("Fail closed: zero clean rows, not writing.")

    upsert_rows(table, clean, conflict)

    # Verify
    live = count_rows(table, f"?select=id&cbs_snapshot_date=eq.{vintage}")
    print(f"Verified: {table} holds {live} rows for vintage {vintage}")
    if live != len(clean):
        raise SystemExit(
            f"Fail closed: {table} holds {live} rows for vintage {vintage} "
            f"after upsert, expected {len(clean)}."
        )
    print("CBS ROS save complete.")


if __name__ == "__main__":
    main()
