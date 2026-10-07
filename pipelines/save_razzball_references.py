#!/usr/bin/env python3
"""Save Razzball rest-of-season projections into the Supabase reference table.

Loads data/raw/sources/razzball/<date>/snapshot.json and upserts it into
public.razzball_projections. Mirrors pipelines/save_cbsros_references.py (JEG-18).

Table DDL: sql/migrations/003_razzball_projections.sql (run in the Supabase SQL
editor; PostgREST cannot DDL). That migration needs Jeremy's explicit approval
before it is run; this saver never creates or alters the table.

Grain (upsert key): (player_key, razzball_snapshot_date). Writes are idempotent.

Values: Razzball's published per-game columns (rz_std_ppg, rz_half_ppr_ppg,
rz_ppr_ppg) are the canonical values the DDF leg prices from (its Games column
and counting totals are doubled), so they are stored as per_game_standard /
per_game_half_ppr / per_game_ppr. Every other row field is kept verbatim in
raw_stats so the importer can rebuild the snapshot row exactly.

Identity (fail closed, JEG-438): numeric player_key only, resolved by the one
player resolver (pipelines/lib/player_resolver.py) over the live public.players
rows plus the committed alias map; the snapshot's own player_norm is a second
spelling to try. Suffixes (Jr/Sr/II-V) match automatically; nickname variants
only through a verified alias (decision identity-name-variants-001). Unmatched,
ambiguous or position-conflicting names go to the review report, never guessed,
never zero-filled. A fuzzy (provisional) match is never written; with
--record-pending it goes to player_name_aliases for the nightly reconcile.
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
from lib.player_resolver import (  # noqa: E402  -- JEG-438: the one resolver
    PlayerResolver, lookup_for_saver, resolver_for_players,
)
from nfl_week import current_nfl_week  # noqa: E402

TABLE = "razzball_projections"  # bare name: PostgREST path is /rest/v1/<table>
CONFLICT = "player_key,razzball_snapshot_date"

# Snapshot row field -> table column. Everything not listed here (and not an
# identity field) goes to raw_stats verbatim.
PER_GAME_FIELDS = {
    "rz_std_ppg": "per_game_standard",
    "rz_half_ppr_ppg": "per_game_half_ppr",
    "rz_ppr_ppg": "per_game_ppr",
}
IDENTITY_FIELDS = {"player_name", "player", "player_norm", "pos", "team"}
COLUMN_FIELDS = {"health", "games_reported"}


def season_for_vintage(vintage_date: date) -> int:
    """NFL season year for a snapshot vintage date (Sep-Feb is one season)."""
    return vintage_date.year if vintage_date.month >= 8 else vintage_date.year - 1


def latest_razzball_snapshot() -> Path:
    """Newest data/raw/sources/razzball/<date>/snapshot.json (ISO dir names)."""
    base = ROOT / "data" / "raw" / "sources" / "razzball"
    candidates = sorted(
        p for p in base.iterdir() if p.is_dir() and (p / "snapshot.json").is_file()
    ) if base.is_dir() else []
    if not candidates:
        raise SystemExit(
            "Fail closed: no razzball snapshot found under data/raw/sources/razzball/."
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
    rows = _sb().get_all("players", params="?select=player_key,full_name,position,active")
    if not isinstance(rows, list):
        raise SystemExit("Unexpected Supabase response for players")
    return [r for r in rows if isinstance(r, dict)]


def _default_upsert(table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
    sbclient = _sb()
    for start in range(0, len(rows), 500):
        sbclient.post(
            table,
            rows[start : start + 500],
            params=f"?on_conflict={on_conflict}",
            prefer="resolution=merge-duplicates",
        )


def _default_count(table: str, params: str) -> int:
    rows = _sb().get_all(table, params=params)
    return len(rows) if isinstance(rows, list) else -1


fetch_players: Callable[[], list[dict[str, Any]]] = _default_fetch_players
upsert_rows: Callable[[str, list[dict[str, Any]], str], None] = _default_upsert
count_rows: Callable[[str, str], int] = _default_count


# Every resolver built by this run (main --record-pending flushes them).
RESOLVERS: list[PlayerResolver] = []


def player_index(players: list[dict[str, Any]]) -> PlayerResolver:
    """The resolver over these canonical rows (+ the committed alias map)."""
    rows = [p for p in players if isinstance(p.get("player_key"), int)
            and str(p.get("full_name") or "").strip()]
    resolver = resolver_for_players(rows)
    RESOLVERS.append(resolver)
    return resolver


def resolve_player(
    name: str,
    pos: str | None,
    index: PlayerResolver,
    norm_hint: str | None = None,
) -> tuple[int | None, str | None]:
    """Return (player_key, None) or (None, reason).

    The name first; when it has no match, the snapshot's own ``player_norm``
    (the spelling the DDF leg joins on). The hint never overrides a name that
    resolves, and a hint that also fails leaves the name's own reason.
    """
    pos = (pos or "").strip().upper() or None
    key, reason = lookup_for_saver(index, name, source="razzball", pos=pos, record=False)
    if key is not None or reason != "no_match":
        if key is None:
            lookup_for_saver(index, name, source="razzball", pos=pos)  # record the review name
        return key, reason
    if norm_hint:
        key, _ = lookup_for_saver(index, norm_hint, source="razzball", pos=pos, record=False)
        if key is not None:
            return key, None
    return lookup_for_saver(index, name, source="razzball", pos=pos)


def parse_float(raw: Any) -> float | None:
    if raw is None or raw == "" or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value == value and value not in (float("inf"), float("-inf")) else None


def build_razzball_rows(
    snapshot_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    vintage = snap.get("vintage_date")
    if not vintage:
        raise SystemExit("Fail closed: Razzball snapshot has no vintage_date.")
    try:
        vintage_date = date.fromisoformat(vintage)
    except ValueError:
        raise SystemExit(
            f"Fail closed: Razzball snapshot vintage_date is not an ISO date: {vintage!r}."
        )
    # Season and content week describe the SNAPSHOT's vintage, never the run date.
    season = season_for_vintage(vintage_date)
    week = current_nfl_week(vintage_date)
    rows = snap.get("rows", [])
    if not rows:
        raise SystemExit("Fail closed: Razzball snapshot has no rows.")

    index = player_index(fetch_players())
    clean: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    pulled_at = utc_now()

    for row in rows:
        name = str(row.get("player_name") or row.get("player") or "").strip()
        pos = str(row.get("pos") or "").strip().upper() or None
        if not name:
            review.append({"reason": "missing_player_name", "pos": pos, "team": row.get("team")})
            continue
        key, reason = resolve_player(name, pos, index, row.get("player_norm"))
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
        per_game = {col: parse_float(row.get(src)) for src, col in PER_GAME_FIELDS.items()}
        raw_stats = {
            k: v
            for k, v in row.items()
            if k not in PER_GAME_FIELDS and k not in IDENTITY_FIELDS and k not in COLUMN_FIELDS
        }
        clean.append(
            {
                "player_key": key,
                "player_norm": row.get("player_norm"),
                "pos": pos,
                "team": str(row.get("team") or "").strip() or None,
                "health": row.get("health"),  # verbatim: an empty string stays an empty string
                "games_reported": parse_float(row.get("games_reported")),
                **per_game,
                "raw_stats": raw_stats,
                "razzball_snapshot_date": vintage,
                "pulled_at": pulled_at,
                "scoring": "half_ppr",
                "season": season,
                "week": week,
                "source_content_date": vintage,
                "_run_id": f"razzball-save-{vintage}",
                "_writer_identity": "save_razzball_references.py",
            }
        )

    return clean, review, vintage


def main() -> None:
    parser = argparse.ArgumentParser(description="Save Razzball snapshot to Supabase.")
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        help="Path to the razzball snapshot.json (default: latest under data/raw/sources/razzball/)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build rows but do not write.")
    parser.add_argument("--record-pending", action="store_true",
                        help="After a live save, send provisional/unmatched names to "
                             "public.player_name_aliases for the nightly reconcile (JEG-438).")
    args = parser.parse_args()

    snapshot_path = args.snapshot or latest_razzball_snapshot()
    clean, review, vintage = build_razzball_rows(snapshot_path)

    print(f"razzball {vintage}: {len(clean)} clean rows, {len(review)} review rows")
    for r in review[:10]:
        print(f"  review: {r.get('reason')}: {r.get('player_name')}")

    if args.dry_run:
        print(f"[dry-run] would upsert {len(clean)} rows into {TABLE}")
        return

    if not clean:
        raise SystemExit("Fail closed: zero clean rows, not writing.")

    upsert_rows(TABLE, clean, CONFLICT)

    live = count_rows(TABLE, f"?select=id&razzball_snapshot_date=eq.{vintage}")
    print(f"Verified: {TABLE} holds {live} rows for vintage {vintage}")
    if live != len(clean):
        raise SystemExit(
            f"Fail closed: {TABLE} holds {live} rows for vintage {vintage} "
            f"after upsert, expected {len(clean)}."
        )
    if args.record_pending:
        sent = sum(r.flush_pending(_sb()) for r in RESOLVERS)
        print(f"identity: recorded {sent} pending names")
    print("Razzball save complete.")


if __name__ == "__main__":
    main()
