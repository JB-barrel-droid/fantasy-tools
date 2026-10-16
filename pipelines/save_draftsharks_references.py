#!/usr/bin/env python3
"""Save Draft Sharks trade value chart snapshots into public.draftsharks_trade_values (JEG-620).

Loads data/raw/sources/draftsharks/<date>/snapshot.json (from pipelines/pull_draftsharks.py)
and upserts it. Mirrors pipelines/save_razzball_references.py: same canonical
resolver (lib/canonical_players via resolve_name), same fail-closed identity
(unmatched/ambiguous/position-conflict names go to the review report, never
guessed, never zero-filled), same save verification (every row of this save
landed whole) and the same per-save pulled_at stamp.

Table DDL: sql/migrations/008_draftsharks_trade_values.sql (create-only, approved by Jeremy 2026-10-15).
Grain (upsert key): (player_key, draftsharks_snapshot_date). Writes are idempotent.
Values are Draft Sharks' own 0-100 trade values (a null stays null, never zero). The three
redraft non-superflex formats get typed columns; every format is kept verbatim in ds_values / market_values.
Nothing here wires the source into published DDF Value; that waits for a green
fidelity pulse (pipelines/fidelity_sources/draftsharks.py).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import identity_queue  # noqa: E402
import save_razzball_references as base  # noqa: E402 -- shared resolver glue and Supabase hooks
from nfl_week import current_nfl_week  # noqa: E402

SOURCE = "draftsharks"
TABLE = "draftsharks_trade_values"
SNAPSHOT_COLUMN = "draftsharks_snapshot_date"
CONFLICT = f"player_key,{SNAPSHOT_COLUMN}"

fetch_players: Callable[[], list[dict[str, Any]]] = base._default_fetch_players
upsert_rows: Callable[[str, list[dict[str, Any]], str], None] = base._default_upsert
count_rows: Callable[[str, str], int] = base._default_count


def latest_snapshot() -> Path:
    root = ROOT / "data" / "raw" / "sources" / SOURCE
    found = sorted(p for p in root.iterdir() if p.is_dir() and (p / "snapshot.json").is_file()) if root.is_dir() else []
    if not found:
        raise SystemExit(f"Fail closed: no {SOURCE} snapshot found under data/raw/sources/{SOURCE}/.")
    return found[-1] / "snapshot.json"


def parse_float(raw: Any) -> float | None:
    return base.parse_float(raw)


def build_rows(snapshot_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    vintage = snap.get("vintage_date")
    if not vintage:
        raise SystemExit("Fail closed: Draft Sharks trade value chart snapshot has no vintage_date.")
    try:
        vintage_date = date.fromisoformat(vintage)
    except ValueError:
        raise SystemExit(f"Fail closed: Draft Sharks trade value chart snapshot vintage_date is not an ISO date: {vintage!r}.")
    season = base.season_for_vintage(vintage_date)
    week = current_nfl_week(vintage_date)
    rows = snap.get("rows", [])
    if not rows:
        raise SystemExit("Fail closed: Draft Sharks trade value chart snapshot has no rows.")
    registry = base.build_registry(fetch_players())
    clean: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    pulled_at = base.utc_now()
    for row in rows:
        name = str(row.get("player_name") or "").strip()
        pos = str(row.get("pos") or "").strip().upper() or None
        if not name:
            review.append({"reason": "missing_player_name", "pos": pos, "team": row.get("team")})
            continue
        key, reason = base.resolve_name(name, pos, registry, row.get("player_norm"))
        if key is None:
            if reason in base.canonical_players.SILENT_REASONS:
                continue
            review.append({"reason": reason, "player_name": name, "player_norm": row.get("player_norm"), "pos": pos})
            continue
        clean.append({
            "player_key": key, "player_norm": row.get("player_norm"), "pos": pos,
            "team": str(row.get("team") or "").strip() or None,
            "draftsharks_id": row.get("draftsharks_id"),
            "ds_redraft_no_ppr": parse_float((row.get("ds") or {}).get("redraft_no_ppr")),
            "ds_redraft_half_ppr": parse_float((row.get("ds") or {}).get("redraft_half_ppr")),
            "ds_redraft_one_ppr": parse_float((row.get("ds") or {}).get("redraft_one_ppr")),
            "ds_values": row.get("ds"), "market_values": row.get("market"),
            SNAPSHOT_COLUMN: vintage, "pulled_at": pulled_at, "_written_at": pulled_at,
            "scoring": "half_ppr", "season": season, "week": week, "source_content_date": vintage,
            "_run_id": f"{SOURCE}-save-{vintage}", "_writer_identity": "save_draftsharks_references.py",
        })
    return clean, review, vintage


def main() -> None:
    parser = argparse.ArgumentParser(description="Save Draft Sharks trade value chart snapshot to Supabase.")
    parser.add_argument("--snapshot", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Build rows but do not write.")
    args = parser.parse_args()
    clean, review, vintage = build_rows(args.snapshot or latest_snapshot())
    print(f"{SOURCE} {vintage}: {len(clean)} clean rows, {len(review)} review rows")
    for r in review[:10]:
        print(f"  review: {r.get('reason')}: {r.get('player_name')}")
    if args.dry_run:
        print(f"[dry-run] would upsert {len(clean)} rows into {TABLE}")
        return
    if not clean:
        raise SystemExit("Fail closed: zero clean rows, not writing.")
    upsert_rows(TABLE, clean, CONFLICT)
    pulled_at = quote(clean[0]["pulled_at"], safe="")
    live = count_rows(TABLE, f"?select=id&{SNAPSHOT_COLUMN}=eq.{vintage}&pulled_at=eq.{pulled_at}")
    print(f"Verified: {TABLE} holds {live} rows from this save for vintage {vintage}")
    if live != len(clean):
        raise SystemExit(f"Fail closed: {TABLE} holds {live} rows from this save for vintage {vintage} "
                         f"after upsert, expected {len(clean)}.")
    identity_queue.record_misses(SOURCE, review)
    print("Draft Sharks trade value chart save complete.")


if __name__ == "__main__":
    main()
