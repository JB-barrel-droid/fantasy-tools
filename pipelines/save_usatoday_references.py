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

Values: the DB's `value` column always carries chart-scale numbers. USA Today
publishes on its own ~0-75 chart scale, so at write time the published
numbers are translated onto the chart's canonical scale with the repo's
isotonic reindex (pipelines/reindex_comparison_section.reindex_section,
anchored to the fixture's ESPN leg -- the repo-owned equivalent of the old
build_sources_dashboard.reindex_values). `native_value` preserves the raw
published number; `value` is the reindexed chart-scale number. This matches
the existing fit-bake rows (bake_id like 'fitwk2_...'), whose `value` is
also reindexed -- the dashboard builder (import_supabase_references)
reads `value` directly with no reindex step, so writing raw published
numbers into `value` would corrupt the chart. New pulls use bake_id like
'usatwk2_2026-09-22_v1' (wrapper-generated; the saver's standalone default
mirrors the scheme) so pulls are never confused with fit-bakes.

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


# Repo scoring label -> ESPN fixture combo stem. The fixture's combos are
# named like standard_12 / half_12 / full_12 (scoring_teams); the anchor
# lookup is an exact match, so the mapping is explicit, never guessed.
FIXTURE_SCORING = {"std": "standard", "half": "half", "full": "full"}


def build_reindex_candidate(
    clean_rows: list[dict[str, Any]], bake_id: str
) -> dict[str, Any]:
    """Build a trade-value-source-reference-v1 candidate from clean pull rows.

    One combo per (fixture scoring, league_teams); native values are the raw
    published numbers keyed by fixture-style slug (player_norm). Fail closed
    when a row's shape has no valid anchor mapping (unexpected scoring,
    qb_slots != 1, or league_teams with no fixture combo): the reindex math
    is only defined against the ESPN anchor for the standard 1QB shapes.
    """
    combos: dict[str, dict[str, Any]] = {}
    for r in clean_rows:
        stem = FIXTURE_SCORING.get(r["scoring"])
        if stem is None:
            raise SystemExit(
                f"Fail closed: scoring {r['scoring']!r} has no ESPN fixture "
                "combo mapping -- refusing to guess an anchor."
            )
        if r.get("qb_slots") != 1:
            raise SystemExit(
                f"Fail closed: qb_slots={r.get('qb_slots')} has no ESPN anchor "
                "mapping (fixture combos are 1QB) -- refusing to guess."
            )
        combo = f"{stem}_{r['league_teams']}"
        slot = combos.setdefault(combo, {"native": {}, "player_keys": {}})
        slot["native"][r["player_norm"]] = r["native_value"]
        slot["player_keys"][r["player_norm"]] = r["player_key"]
    return {
        "schema": "trade-value-source-reference-v1",
        "source_key": "usatoday",
        "asof": bake_id,
        "combos": combos,
    }


def apply_reindex(
    clean_rows: list[dict[str, Any]], review_rows: list[dict[str, Any]],
    bake_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Translate clean rows' `value` onto the chart scale via reindex_section.

    `native_value` is untouched (raw published number). Rows with no
    reindexed value (no ESPN anchor pair -- reported in the reindex review)
    move to review: never written with an un-reindexed value, never guessed.
    Uses pipelines/reindex_comparison_section.reindex_section directly --
    the isotonic math lives in exactly one place.
    """
    import tempfile

    from reindex_comparison_section import reindex_section

    candidate = build_reindex_candidate(clean_rows, bake_id)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", prefix="usatoday-reindex-", delete=False
    ) as fh:
        json.dump(candidate, fh)
        tmp = fh.name
    try:
        section, reindex_review = reindex_section(tmp)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

    reindexed: dict[tuple[str, str], float] = {}
    for combo_name, combo in section.get("combos", {}).items():
        for slug, val in (combo.get("reindexed") or {}).items():
            reindexed[(combo_name, slug)] = val

    final_clean: list[dict[str, Any]] = []
    final_review: list[dict[str, Any]] = list(review_rows)
    for r in reindex_review:
        final_review.append(
            {
                "player_key": r.get("player_key"),
                "player_norm": r.get("slug"),
                "scoring": None,
                "reason": f"reindex: {r.get('reason')}",
                "detail": f"combo {r.get('combo')}; value left unwritten, never guessed",
            }
        )
    for r in clean_rows:
        combo = f"{FIXTURE_SCORING[r['scoring']]}_{r['league_teams']}"
        val = reindexed.get((combo, r["player_norm"]))
        if val is None:
            final_review.append(
                {
                    "player_key": r["player_key"],
                    "player_norm": r["player_norm"],
                    "scoring": r["scoring"],
                    "reason": "reindex: no reindexed value (no ESPN anchor pair)",
                    "detail": "value left unwritten, never guessed",
                }
            )
            continue
        row = dict(r)
        row["value"] = val
        final_clean.append(row)
    return final_clean, final_review


def build_usatoday_rows_final(
    json_path: Path, week: int, bake_id: str, *, reindex: bool = True
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str]:
    """-> (clean_rows, review_rows, pulled_at, url), values on chart scale.

    Single entry point for both the cron wrapper's verification pass and
    save_usatoday's write pass, so the counted rows and the written rows
    are always the same objects.
    """
    clean, review, pulled_at, url = build_usatoday_rows(json_path, week, bake_id)
    if reindex:
        clean, review = apply_reindex(clean, review, bake_id)
    return clean, review, pulled_at, url


def save_usatoday(
    json_path: Path,
    *,
    dry_run: bool,
    week: int | None = None,
    bake_id: str | None = None,
    reindex: bool = True,
) -> dict[str, Any]:
    week = week or nfl_week()
    today = datetime.now(timezone.utc).date().isoformat()
    bake_id = bake_id or f"usatwk{week}_{today}_v1"

    clean, review, pulled_at, url = build_usatoday_rows_final(
        json_path, week, bake_id, reindex=reindex
    )

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
        help="Override the bake_id (default: usatwk<week>_<utc-date>_v1).",
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

    result = save_usatoday(
        args.usatoday_json,
        dry_run=args.dry_run,
        week=args.week,
        bake_id=args.bake_id,
        reindex=not args.no_reindex,
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
