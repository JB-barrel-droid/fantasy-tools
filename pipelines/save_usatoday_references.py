#!/usr/bin/env python3
"""Save a USA Today trade-value pull into public.source_trade_values.

Reads the repo pull JSON written by ops/watchdog/pull_usatoday.py --write
({"url", "fetched_at", "tables": [...]}) and upserts one row per
(player, scoring) into public.source_trade_values as:

    source='usatoday', variant='as_published'

Identity: names resolve through the canonical public.players registry
(numeric player_key), fail closed -- unmatched/ambiguous names go to the
review report, never guessed. Same rule as save_espn_cbs_references.py.

Scoring: USA Today publishes one QB column (1QB); it is reused for all
three scorings (documented as IMPLIED, mirroring the CBS fixture). RB/WR/TE
use the STD / Half / PPR columns.

Values: value == native_value == the published number (USA Today's ~0-75
chart scale). Reindexing onto the canonical chart scale is a bake-time
operation (see the dashboard builder), not a pull-time one. The one-off
fit-bake rows (bake_id like 'fitwk2_...') carry reindexed values; pull rows
use bake_id like 'pullwk2_2026-09-22' so the two are never confused.

Grain: (source, variant, scoring, league_teams, qb_slots, season, week,
player_key). Upserts are idempotent per weekly grain; prior weeks are
retained.

Usage:
    python3 save_usatoday_references.py --usatoday-json ops/watchdog/pulls/usatoday-2026-09-22.json [--week 2] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
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
# Reuse the Supabase plumbing and the fail-closed identity resolution.
from save_espn_cbs_references import (  # noqa: E402
    build_name_index,
    resolve_name,
    fetch_players,
    upsert_rows,
    count_rows,
)

USAT_UPSERT_CONFLICT = "source,variant,scoring,league_teams,qb_slots,season,week,player_key"

# scoring label used in source_trade_values for USA Today (matches the fit-bake).
SCORING_LABELS = ("std", "half", "full")

POS_BY_TITLE = {
    "quarterback": "QB",
    "running back": "RB",
    "wide receiver": "WR",
    "tight end": "TE",
}

QB_SPLIT_NOTE = (
    "IMPLIED: USA Today publishes one QB column (1QB), no per-scoring split; "
    "the 1QB value is reused for std/half/full (mirrors the CBS fixture convention)"
)


def _strip_html(text: str) -> str:
    return re.sub(r"<.*?>", "", text or "").strip()


def source_content_date(url: str) -> str | None:
    """Extract the article publish date from the USA Today URL path (/YYYY/MM/DD/)."""
    m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def parse_tables(payload: dict[str, Any]) -> dict[str, list[tuple[str, str, float]]]:
    """-> {scoring_label: [(name, pos, published_value)]}.

    Raises SystemExit fail-closed on zero parsed rows: never writing an empty save.
    """
    combos: dict[str, list[tuple[str, str, float]]] = {s: [] for s in SCORING_LABELS}
    tables = payload.get("tables") or []
    for table in tables:
        title = str(table.get("title") or "").lower()
        pos = None
        for key, p in POS_BY_TITLE.items():
            if key in title:
                pos = p
                break
        if not pos:
            continue
        headers = [str(h or "").lower() for h in (table.get("headers") or [])]
        for cells in (table.get("rows") or []):
            if len(cells) < 3:
                continue
            name = _strip_html(cells[1])
            if not name:
                continue
            vals: dict[str, float] = {}
            for header, cell in zip(headers[2:], cells[2:]):
                try:
                    vals[header] = float(_strip_html(cell))
                except ValueError:
                    continue
            if pos == "QB":
                v = vals.get("1qb")
                if v is None:
                    continue
                for scoring in SCORING_LABELS:
                    combos[scoring].append((name, pos, v))
            else:
                std = vals.get("std")
                half = vals.get("half")
                full = vals.get("ppr", vals.get("full"))
                if std is None or half is None or full is None:
                    continue
                combos["std"].append((name, pos, std))
                combos["half"].append((name, pos, half))
                combos["full"].append((name, pos, full))
    total = sum(len(v) for v in combos.values())
    if total == 0:
        raise SystemExit(
            "Fail closed: USA Today pull parsed zero rows. Never writing an empty save."
        )
    return combos


def build_usatoday_rows(
    json_path: Path, week: int, bake_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str]:
    """-> (clean_rows, review_rows, pulled_at, url)."""
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    url = str(payload.get("url") or "")
    pulled_at = str(payload.get("fetched_at") or datetime.now(timezone.utc).isoformat())
    content_date = source_content_date(url)

    combos = parse_tables(payload)
    index = build_name_index(fetch_players())

    clean: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    for scoring in SCORING_LABELS:
        for name, pos, value in combos[scoring]:
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
                    "source": "usatoday",
                    "variant": "as_published",
                    "player_key": key,
                    "player_norm": normalize_name(name),
                    "scoring": scoring,
                    "league_teams": 12,
                    "qb_slots": 1,
                    "season": 2026,
                    "week": week,
                    "position": canonical_pos or pos,
                    "team": None,  # USA Today tables carry no team column
                    "value": value,
                    "native_value": value,  # as published; reindexing is bake-time
                    "source_content_date": content_date,
                    "pulled_at": pulled_at,
                    "bake_id": bake_id,
                }
            )
    return clean, review, pulled_at, url


def save_usatoday(
    json_path: Path,
    *,
    dry_run: bool,
    week: int | None = None,
    bake_id: str | None = None,
) -> dict[str, Any]:
    week = week or nfl_week()
    today = datetime.now(timezone.utc).date().isoformat()
    bake_id = bake_id or f"pullwk{week}_{today}"

    clean, review, pulled_at, url = build_usatoday_rows(json_path, week, bake_id)

    if not clean:
        raise SystemExit(
            "Fail closed: USA Today resolved to zero clean rows "
            f"({len(review)} in review). Never writing an empty save."
        )

    if dry_run:
        print(
            f"[dry-run] usatoday: would upsert {len(clean)} rows into "
            f"source_trade_values ({len(review)} review), bake_id={bake_id}"
        )
        return {
            "source": "usatoday",
            "dry_run": True,
            "written": 0,
            "review_count": len(review),
            "review": review,
            "bake_id": bake_id,
            "url": url,
        }

    upsert_rows("source_trade_values", clean, USAT_UPSERT_CONFLICT)
    live = count_rows(
        "source_trade_values",
        f"?select=player_key&source=eq.usatoday&variant=eq.as_published"
        f"&bake_id=eq.{bake_id}&season=eq.2026&week=eq.{week}",
    )
    if live != len(clean):
        raise SystemExit(
            f"Fail closed: source_trade_values holds {live} rows for the "
            f"(usatoday, as_published, {bake_id}) grain after upsert, expected "
            f"{len(clean)}. The write did not land as planned; investigate before re-running."
        )

    return {
        "source": "usatoday",
        "dry_run": False,
        "written": len(clean),
        "review_count": len(review),
        "review": review,
        "bake_id": bake_id,
        "url": url,
        "pulled_at": pulled_at,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--usatoday-json",
        type=Path,
        required=True,
        help="Pull JSON from ops/watchdog/pull_usatoday.py --write.",
    )
    parser.add_argument(
        "--week",
        type=int,
        default=None,
        help="NFL week for the save grain (default: current week from ops/watchdog/_common.nfl_week).",
    )
    parser.add_argument(
        "--bake-id",
        default=None,
        help="Override the bake_id (default: pullwk<week>_<utc-date>).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and report without writing (default is a live, idempotent write).",
    )
    parser.add_argument(
        "--review-out",
        type=Path,
        default=None,
        help="Write the review report JSON here.",
    )
    args = parser.parse_args()

    result = save_usatoday(
        args.usatoday_json,
        dry_run=args.dry_run,
        week=args.week,
        bake_id=args.bake_id,
    )

    print(
        f"usatoday -> source_trade_values: {result['written']} rows "
        f"(dry_run={result['dry_run']}), {result['review_count']} in review, "
        f"bake_id={result['bake_id']}"
    )
    if result["review"]:
        review_path = args.review_out or (
            ROOT / "output" / "usatoday-save-review" / f"{result['bake_id']}.json"
        )
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(
            json.dumps(
                {"bake_id": result["bake_id"], "url": result["url"], "review": result["review"]},
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"review report: {review_path} ({len(result['review'])} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
