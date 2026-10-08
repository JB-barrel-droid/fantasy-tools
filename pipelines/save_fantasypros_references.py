#!/usr/bin/env python3
"""Save the FantasyPros weekly trade-value chart CSV to Supabase.

Reads files/fantasypros_trade_chart.csv (written by
lottery/bin/pull_fantasypros_chart.py --week N --write; the puller already
resolves every row through the canonical players registry, fail closed),
expands the scoring-agnostic base value to std/half/full rows, and writes
variant='as_published' to public.source_trade_values.

`native_value` preserves the raw FP base value; `value` is the isotonic-
reindexed chart-scale number (shared apply_reindex from the USA Today
saver -- the math lives in exactly one place). This matches the Week 2
bake (fp as_published rows carry native_value=raw, value=reindexed).

as_published only: like FantasyCalc, the bias_adjusted FP fit is a derived
calibration whose fit target is stale in-season; the importer never
consumes bias_adjusted, so this saver never writes it.

Fail-closed: zero clean rows aborts; the post-upsert count check must
match or the save aborts loudly.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "ops" / "watchdog"))
from match_source_snapshot import normalize_name  # noqa: E402
from _common import content_week  # noqa: E402
from save_espn_cbs_references import (  # noqa: E402
    fetch_players,
    upsert_rows,
    count_rows,
)
from save_usatoday_references import (  # noqa: E402
    USAT_UPSERT_CONFLICT_VERSIONED,
    SCORING_LABELS,
    apply_reindex,
)

GOAL_DIR = Path(
    os.environ.get(
        "FANTASY_GOAL_DIR",
        str(Path.home() / "workspace" / "goals" / "football-signal-database-and-app"),
    )
)
FP_CSV = GOAL_DIR / "files" / "fantasypros_trade_chart.csv"

# The FP article's publication date is the source-content vintage. Derive it
# from the puller's fetch log (latest ok entry for the week) -- never
# hardcode it here. A hardcoded date is the same class of staleness as the
# board-week labels: it silently survives the next week.
FP_FETCH_LOG = (
    GOAL_DIR / "lottery" / "hidden_files" / "fantasypros_chart_fetch_log.jsonl"
)


def fetch_log_content_date(week: int) -> str:
    """Return the article publication date from the fetch log (fail closed)."""
    with FP_FETCH_LOG.open(encoding="utf-8") as fh:
        entries = [json.loads(line) for line in fh if line.strip()]
    cands = [
        e
        for e in entries
        if e.get("ok") and e.get("week") == week and e.get("published")
    ]
    if not cands:
        raise SystemExit(
            f"FAIL-CLOSED: no ok fetch-log entry with a published date for "
            f"week {week} in {FP_FETCH_LOG}"
        )
    return cands[-1]["published"]


def build_fp_rows(
    csv_path: Path, week: int, bake_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """-> (clean_rows, review_rows), values pre-reindex.

    The puller guarantees canonical player_keys, but we re-verify every key
    against the live players table -- a key the table doesn't know is
    review, never guessed.
    """
    index = {p["player_key"]: p for p in fetch_players()}
    content_date = fetch_log_content_date(week)
    clean: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    pulled_at = datetime.now(timezone.utc).isoformat()

    with csv_path.open(newline="", encoding="utf-8") as fh:
        for lineno, row in enumerate(csv.DictReader(fh), start=2):
            try:
                key = int(row["player_key"])
                value = float(row["value_1"])
            except (KeyError, TypeError, ValueError):
                review.append(
                    {
                        "lineno": lineno,
                        "row": row,
                        "reason": "unparseable player_key/value_1",
                    }
                )
                continue
            rec = index.get(key)
            if rec is None:
                review.append(
                    {
                        "player_key": key,
                        "name": row.get("name"),
                        "reason": "player_key not in canonical players table",
                        "detail": "never guessed",
                    }
                )
                continue
            for scoring in SCORING_LABELS:
                clean.append(
                    {
                        "source": "fantasypros",
                        "variant": "as_published",
                        "player_key": key,
                        "player_norm": normalize_name(rec["full_name"]),
                        "scoring": scoring,
                        "league_teams": 12,
                        "qb_slots": 1,
                        "season": 2026,
                        "week": week,
                        "position": rec["position"],
                        "team": (row.get("team") or None),
                        "value": value,
                        "native_value": value,  # as published; reindexing is bake-time
                        "source_content_date": content_date,
                        "pulled_at": pulled_at,
                        "bake_id": bake_id,
                    }
                )
    return clean, review


def save_fantasypros(
    csv_path: Path,
    *,
    dry_run: bool,
    week: int | None = None,
    bake_id: str | None = None,
    reindex: bool = True,
) -> dict[str, Any]:
    week = week or content_week()
    today = datetime.now(timezone.utc).date().isoformat()
    bake_id = bake_id or f"fpwk{week}_{today}_v1"

    clean, review = build_fp_rows(csv_path, week, bake_id)
    if reindex:
        clean, review = apply_reindex(clean, review, bake_id)

    if not clean:
        raise SystemExit(
            "Fail closed: FantasyPros resolved to zero clean rows "
            f"({len(review)} in review). Never writing an empty save."
        )

    if dry_run:
        print(
            f"[dry-run] fantasypros: would upsert {len(clean)} rows into "
            f"source_trade_values ({len(review)} review), bake_id={bake_id}"
        )
        return {
            "source": "fantasypros",
            "dry_run": True,
            "written": 0,
            "review_count": len(review),
            "review": review,
            "bake_id": bake_id,
        }

    upsert_rows("source_trade_values", clean, USAT_UPSERT_CONFLICT_VERSIONED)
    live = count_rows(
        "source_trade_values",
        f"?select=player_key&source=eq.fantasypros&variant=eq.as_published"
        f"&bake_id=eq.{bake_id}&season=eq.2026&week=eq.{week}",
    )
    if live != len(clean):
        raise SystemExit(
            f"Fail closed: source_trade_values holds {live} rows for the "
            f"(fantasypros, as_published, {bake_id}) grain after upsert, expected "
            f"{len(clean)}. The write did not land as planned; investigate before re-running."
        )

    review_path = (
        ROOT / "output" / "fantasypros-save-review" / f"{bake_id}.json"
    )
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(json.dumps(review, indent=1), encoding="utf-8")

    return {
        "source": "fantasypros",
        "dry_run": False,
        "written": len(clean),
        "review_count": len(review),
        "bake_id": bake_id,
        "review_path": str(review_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fp-csv", type=Path, default=FP_CSV)
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--bake-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-reindex",
        action="store_true",
        help="write raw FP values as value (testing only)",
    )
    args = parser.parse_args()

    if not args.fp_csv.exists():
        raise SystemExit(f"FP CSV not found: {args.fp_csv}")

    result = save_fantasypros(
        args.fp_csv,
        dry_run=args.dry_run,
        week=args.week,
        bake_id=args.bake_id,
        reindex=not args.no_reindex,
    )
    print(
        f"fantasypros -> source_trade_values: {result['written']} rows "
        f"(dry_run={result['dry_run']}), {result['review_count']} in review, "
        f"bake_id={result['bake_id']}"
    )
    if result.get("review_path"):
        print(f"review report: {result['review_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
