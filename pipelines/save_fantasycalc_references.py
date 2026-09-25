#!/usr/bin/env python3
"""Save a FantasyCalc weekly snapshot into public.source_trade_values.

Reads the weekly snapshot cache written by ops/watchdog/pull_fantasycalc.py
--fc-week "Week N" (fantasycalc_{standard,half,full}_12_qb1.json under the
goal workspace's lottery/data/sources_cache/) and upserts one row per
(player, scoring) into public.source_trade_values as:

    source='fantasycalc', variant='as_published'

Only the 12-team / 1-QB combos are saved (the chart's canonical league
config); the other 21 cached combos are the raw pull, not the saved grain.

Identity: names resolve through the canonical public.players registry
(numeric player_key), fail closed -- unmatched/ambiguous names go to the
review report, never guessed. Same rule as the other savers.

Values: the DB's `value` column always carries chart-scale numbers.
FantasyCalc publishes on its own ~0-11000 scale, so at write time the
published numbers are translated onto the chart's canonical scale with the
repo's isotonic reindex (pipelines/reindex_comparison_section.reindex_section,
anchored to the fixture's ESPN leg -- shared with save_usatoday_references).
`native_value` preserves the raw published number; `value` is the reindexed
chart-scale number. The dashboard builder (import_supabase_references) reads
`value` directly with no reindex step, so writing raw published numbers
into `value` would corrupt the chart.

Variant scope: ONLY as_published is written. The table's bias_adjusted
variant is a derived calibration (fit_source_variants bake) whose fit target
(the Monday reassessed methodology leg) is stale in-season -- re-fitting it
now would be dishonest, and the importer never consumes bias_adjusted
(import_supabase_references.py: "as_published only"). The bias-adjusted
display stays on its last honest fit bake until the methodology leg is
fresh enough to re-fit.

source_content_date is NULL by design: FantasyCalc is a weekly snapshot
tied to the NFL week (the `week` column), not a dated article.

Grain: (source, variant, scoring, league_teams, qb_slots, season, week,
player_norm) -- the shared table's source_trade_values_grain constraint.
Rows also carry the resolved numeric player_key for downstream matching.
Upserts are idempotent per weekly grain; prior weeks are retained.

Usage:
    python3 save_fantasycalc_references.py [--week 3] [--dry-run]
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
from import_source_snapshot import parse_float  # noqa: E402
from build_ddf_two_tier_leg import ALIASES  # noqa: E402
sys.path.insert(0, str(ROOT / "ops" / "watchdog"))
from _common import nfl_week  # noqa: E402
# Reuse the Supabase plumbing, the fail-closed identity resolution, and the
# shared isotonic reindex (same chart-scale contract as USA Today).
from save_espn_cbs_references import (  # noqa: E402
    build_name_index,
    resolve_name,
    fetch_players,
    upsert_rows,
    count_rows,
)
from save_usatoday_references import (  # noqa: E402
    apply_reindex,
    USAT_UPSERT_CONFLICT as FC_UPSERT_CONFLICT,
)

GOAL = Path(os.path.expanduser("~")) / "workspace" / "goals" / "football-signal-database-and-app"
CACHE_DIR = GOAL / "lottery" / "data" / "sources_cache"

# Cache file stem -> repo scoring label. Only the 12-team / 1-QB combos are
# the saved grain (the chart's canonical league config).
FC_COMBOS = {
    "fantasycalc_standard_12_qb1": "std",
    "fantasycalc_half_12_qb1": "half",
    "fantasycalc_full_12_qb1": "full",
}

SEASON = 2026


def _read_combo(stem: str) -> tuple[list[dict[str, Any]], str]:
    """-> (rows, fetched_at) from one cache file. Fail closed on missing/empty."""
    path = CACHE_DIR / f"{stem}.json"
    if not path.exists():
        raise SystemExit(
            f"Fail closed: FantasyCalc cache file missing: {path}. "
            "Refresh with ops/watchdog/pull_fantasycalc.py --fc-week \"Week N\" first."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows") or []
    if not rows:
        raise SystemExit(
            f"Fail closed: {path.name} holds zero rows -- refusing to overwrite "
            "a good snapshot with an empty one."
        )
    return rows, str(payload.get("fetched_at") or "")


def build_fantasycalc_rows(
    week: int, bake_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """-> (clean_rows, review_rows, pulled_at). Values raw (pre-reindex)."""
    index = build_name_index(fetch_players())

    clean: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    pulled_at = ""
    for stem, scoring in FC_COMBOS.items():
        rows, fetched_at = _read_combo(stem)
        pulled_at = pulled_at or fetched_at
        for r in rows:
            name = str(r.get("name") or "").strip()
            pos = str(r.get("pos") or "").strip().upper() or None
            value = parse_float(r.get("value"))
            if not name or value is None:
                review.append(
                    {
                        "name": name,
                        "position": pos,
                        "scoring": scoring,
                        "value": r.get("value"),
                        "detail": "missing name or non-numeric value; never guessed",
                    }
                )
                continue
            key, _rec, canonical_pos = resolve_name(name, pos, index)
            if key is None:
                review.append(
                    {
                        "name": name,
                        "position": pos,
                        "scoring": scoring,
                        "value": value,
                        "detail": "no single canonical players-table identity; never guessed",
                    }
                )
                continue
            clean.append(
                {
                    "source": "fantasycalc",
                    "variant": "as_published",
                    "player_key": key,
                    "player_norm": normalize_name(name),
                    "scoring": scoring,
                    "league_teams": 12,
                    "qb_slots": 1,
                    "season": SEASON,
                    "week": week,
                    "position": canonical_pos or pos,
                    "team": None,  # FantasyCalc cache rows carry no team column
                    "value": value,
                    "native_value": value,  # as published; reindexing is bake-time
                    "source_content_date": None,  # weekly snapshot; NULL by design
                    "pulled_at": fetched_at or datetime.now(timezone.utc).isoformat(),
                    "bake_id": bake_id,
                }
            )
    return clean, review, pulled_at


def build_fantasycalc_rows_final(
    week: int, bake_id: str, *, reindex: bool = True
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """-> (clean_rows, review_rows, pulled_at), values on chart scale."""
    clean, review, pulled_at = build_fantasycalc_rows(week, bake_id)
    if reindex:
        clean, review = apply_reindex(clean, review, bake_id)
    return clean, review, pulled_at


def save_fantasycalc(
    *,
    dry_run: bool,
    week: int | None = None,
    bake_id: str | None = None,
    reindex: bool = True,
) -> dict[str, Any]:
    week = week or nfl_week()
    today = datetime.now(timezone.utc).date().isoformat()
    bake_id = bake_id or f"fcwk{week}_{today}_v1"

    clean, review, pulled_at = build_fantasycalc_rows_final(
        week, bake_id, reindex=reindex
    )

    if not clean:
        raise SystemExit(
            "Fail closed: FantasyCalc resolved to zero clean rows "
            f"({len(review)} in review). Never writing an empty save."
        )

    if dry_run:
        print(
            f"[dry-run] fantasycalc: would upsert {len(clean)} rows into "
            f"source_trade_values ({len(review)} review), bake_id={bake_id}"
        )
        return {
            "source": "fantasycalc",
            "dry_run": True,
            "written": 0,
            "review_count": len(review),
            "review": review,
            "bake_id": bake_id,
            "pulled_at": pulled_at,
        }

    upsert_rows("source_trade_values", clean, FC_UPSERT_CONFLICT)
    live = count_rows(
        "source_trade_values",
        f"?select=player_key&source=eq.fantasycalc&variant=eq.as_published"
        f"&bake_id=eq.{bake_id}&season=eq.{SEASON}&week=eq.{week}",
    )
    if live != len(clean):
        raise SystemExit(
            f"Fail closed: source_trade_values holds {live} rows for the "
            f"(fantasycalc, as_published, {bake_id}) grain after upsert, expected "
            f"{len(clean)}. The write did not land as planned; investigate before re-running."
        )

    return {
        "source": "fantasycalc",
        "dry_run": False,
        "written": len(clean),
        "review_count": len(review),
        "review": review,
        "bake_id": bake_id,
        "pulled_at": pulled_at,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--week",
        type=int,
        default=None,
        help="NFL week for the save grain (default: current week from ops/watchdog/_common.nfl_week).",
    )
    parser.add_argument(
        "--bake-id",
        default=None,
        help="Override the bake_id (default: fcwk<week>_<utc-date>_v1).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and report without writing (default is a live, idempotent write).",
    )
    parser.add_argument(
        "--no-reindex",
        action="store_true",
        help="Skip the isotonic chart-scale reindex (debugging only: values stay raw).",
    )
    parser.add_argument(
        "--review-out",
        type=Path,
        default=None,
        help="Write the review report JSON here.",
    )
    args = parser.parse_args()

    result = save_fantasycalc(
        dry_run=args.dry_run,
        week=args.week,
        bake_id=args.bake_id,
        reindex=not args.no_reindex,
    )

    print(
        f"fantasycalc -> source_trade_values: {result['written']} rows "
        f"(dry_run={result['dry_run']}), {result['review_count']} in review, "
        f"bake_id={result['bake_id']}"
    )
    if result["review"]:
        review_path = args.review_out or (
            ROOT / "output" / "fantasycalc-save-review" / f"{result['bake_id']}.json"
        )
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(
            json.dumps(
                {"bake_id": result["bake_id"], "review": result["review"]},
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"review report: {review_path} ({len(result['review'])} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
