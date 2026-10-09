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

Identity (fail closed, same rule as the other savers): numeric player_key only,
resolved via public.players (full_name is the naming authority) after the
verified aliases (data/inputs/player_aliases.json, shared by every resolver). Unmatched or ambiguous names go to the review report,
never guessed, never zero-filled.
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
from match_source_snapshot import normalize_name  # noqa: E402
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import player_aliases  # noqa: E402 -- the one verified alias list
import identity_queue  # noqa: E402 -- unresolved names, counted per source (JEG-438)
from canonical_players import narrow_candidates  # noqa: E402
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


def compact(norm: str) -> str:
    """A normalized name with its spaces removed.

    public.players spells "Ja'Marr Chase" with a straight apostrophe, which
    normalize_name turns into a space ("ja marr chase"); the Razzball snapshot spells
    it with a typographic one, which normalize_name drops ("jamarr chase"). Comparing
    the space-free form makes the two meet without guessing any spelling.
    """
    return norm.replace(" ", "")


def build_name_index(players: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for record in players:
        key = record.get("player_key")
        name = str(record.get("full_name") or "").strip()
        if not isinstance(key, int) or not name:
            continue
        entry = {
            "player_key": key,
            "full_name": name,
            "position": str(record.get("position") or "").strip().upper() or None,
            "active": record.get("active"),
        }
        norm = normalize_name(name)
        index.setdefault(norm, []).append(entry)
        index.setdefault("\0" + compact(norm), []).append(entry)  # space-free fallback
    return index


def resolve_name(
    name: str,
    pos: str | None,
    index: dict[str, list[dict[str, Any]]],
    norm_hint: str | None = None,
) -> tuple[int | None, str | None]:
    """Return (player_key, reason). Unresolved -> (None, reason).

    Order: the shared verified aliases (lib/player_aliases), the normalized name, the space-free form, then the
    snapshot's own `player_norm` (the join key the DDF leg uses; it catches "David
    Sills V" -> "david sills"). Several players under one form are narrowed by
    position; still more than one is "ambiguous" and goes to review. Nothing is guessed.
    """
    forms = [normalize_name(name)]
    if norm_hint:
        forms.append(normalize_name(norm_hint))
    candidates: list[dict[str, Any]] = []
    for norm in forms:
        norm = normalize_name(player_aliases.canonical_spelling(norm))
        candidates = index.get(norm) or index.get("\0" + compact(norm), [])
        if candidates:
            break
    rec, reason = narrow_candidates(candidates, pos)
    return (rec["player_key"], None) if rec else (None, reason)


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

    index = build_name_index(fetch_players())
    clean: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    pulled_at = utc_now()

    for row in rows:
        name = str(row.get("player_name") or row.get("player") or "").strip()
        pos = str(row.get("pos") or "").strip().upper() or None
        if not name:
            review.append({"reason": "missing_player_name", "pos": pos, "team": row.get("team")})
            continue
        key, reason = resolve_name(name, pos, index, row.get("player_norm"))
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
                # An upsert never moves the column default forward; a re-save of
                # the same date must show when its values were written
                # (GAP-RAZZBALL-CHART-BEHIND-STORED).
                "_written_at": pulled_at,
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

    # One save = one pulled_at on every row. Rows of the same date from an
    # earlier save (players Razzball dropped since) stay in the table but are
    # superseded: the import reads only the newest save (lib/latest_save.py).
    # The check is that this save landed whole, not that the date holds
    # nothing else (GAP-RAZZBALL-CHART-BEHIND-STORED: 690 vs 688 failed the
    # 03:25 save after its upsert had already landed).
    pulled_at = quote(clean[0]["pulled_at"], safe="")
    live = count_rows(TABLE, f"?select=id&razzball_snapshot_date=eq.{vintage}&pulled_at=eq.{pulled_at}")
    total = count_rows(TABLE, f"?select=id&razzball_snapshot_date=eq.{vintage}")
    print(f"Verified: {TABLE} holds {live} rows from this save for vintage {vintage} "
          f"({total - live} superseded rows from earlier saves of the date)")
    if live != len(clean):
        raise SystemExit(
            f"Fail closed: {TABLE} holds {live} rows from this save for vintage {vintage} "
            f"after upsert, expected {len(clean)}."
        )
    identity_queue.record_misses("razzball", review)
    print("Razzball save complete.")


if __name__ == "__main__":
    main()
