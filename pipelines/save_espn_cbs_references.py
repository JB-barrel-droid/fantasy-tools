#!/usr/bin/env python3
"""Save ESPN/CBS scraped references into their Supabase reference tables.

Stage 1b close-out: the tables were DDL'd 2026-09-22 (empty) and the
importer treats espn/cbs as file-backed with save_gap='no-supabase-table-stage1b'.
This script loads the saved file caches into the tables, after which the
stage-1 importer becomes DB-backed for espn/cbs (save_gap=None).

Tables (grain = upsert key; writes are idempotent on the grain):
  ESPN -> public.espn_season_projections (season, week, player_key):
    season=2026, week=2 (designated pull week), scoring='half_ppr',
    r_* component columns verbatim, ros_half_ppr, weeks_covered,
    espn_snapshot_date (the CSV's unanimous vintage = source-content vintage,
    never pull time), pulled_at=now, player_norm as join label.
  CBS  -> public.cbs_trade_values (source, variant, scoring, league_teams,
    qb_slots, season, week, player_key):
    source='cbs', variant='as_published', season=2026, week=2,
    league_teams=12, qb_slots=1, scoring from the non / 0.5 / PPR columns,
    value + native_value (same scale for CBS), position/team from the cache,
    source_content_date=NULL (article date unknown; vintage carried by week),
    pulled_at=now, player_norm as join label.

Identity (fail closed, same rule as the chart bake): numeric player_key only,
resolved via public.players (full_name is the naming authority). Four
verified spelling aliases are applied to the normalized name before lookup
(the ALIASES map shared with pipelines/build_ddf_two_tier_leg.py, verified
against players.full_name 2026-09-22): 'cameron ward' -> 'cam ward' (697),
'cameron skattebo' -> 'cam skattebo' (3664), 'travis etienne jr' ->
'travis etienne' (810), 'michael pittman jr' -> 'michael pittman' (561).
The map is exact-match only: any other spelling is looked up verbatim and
still fails closed. Unmatched or ambiguous names go to the review report --
never guessed, never zero-filled.

CBS QB SCORING DECISION (the known wrinkle):
  CBS publishes ONE QB column ("1QB-4") with no per-scoring split, but the
  cbs_trade_values CHECK requires scoring in ('standard','half_ppr','ppr'),
  so a NULL/absent scoring cannot be stored.
  Representation chosen: one row per QB per scoring (standard / half_ppr /
  ppr), all carrying the published 1QB-4 value, documented as IMPLIED -- the
  single 1QB-4 column reused for every scoring mode. This exactly mirrors the
  live fixture's own cbs convention: data/fixtures/current/
  comparison-sources-data.json provenance_note says "QB values are IMPLIED:
  CBS publishes 1QB-4 / 1QB-6 / 2QB, so the 1QB-4 column is reused for every
  scoring mode", and the cbs combos standard_12 / half_12 / full_12 each
  carry the same QB values.
  Alternatives rejected:
    - one row with scoring='half_ppr' only: silently drops QBs from the
      standard/full combos, a regression vs the fixture convention;
    - scoring=NULL: violates the table CHECK, cannot be stored;
    - inventing per-scoring QB variation: fabrication, never done.
  The implication is labeled in this script's docstring and in the importer
  manifest filter; the value is never presented as a CBS-published
  per-scoring number.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
GOAL_DIR = Path(os.path.expanduser("~/workspace/goals/football-signal-database-and-app"))
DEFAULT_ESPN_CSV = GOAL_DIR / "files" / "espn_projections.csv"
DEFAULT_ESPN_META = GOAL_DIR / "hidden_files" / "espn_projections_meta.json"
DEFAULT_CBS_JSON = GOAL_DIR / "lottery" / "data" / "sources_cache" / "cbs.json"

sys.path.insert(0, str(ROOT / "pipelines"))
from match_source_snapshot import normalize_name  # noqa: E402
from import_source_snapshot import parse_float  # noqa: E402
# Single source of truth for the verified spelling aliases (shared with the
# DDF two-tier leg). Verified against players.full_name 2026-09-22; the map
# here and in build_ddf_two_tier_leg.py must never diverge.
from build_ddf_two_tier_leg import ALIASES  # noqa: E402
sys.path.insert(0, str(ROOT / "ops" / "watchdog"))
from _common import nfl_week  # noqa: E402 -- current week for the CBS save grain


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Supabase access (vault-backed skill client). Module-level callables so tests
# can inject recorded fixtures without touching the network.
# ---------------------------------------------------------------------------

def _sb():
    sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))
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


# ---------------------------------------------------------------------------
# Identity: names -> player_key, fail closed
# ---------------------------------------------------------------------------

def build_name_index(players: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for record in players:
        key = record.get("player_key")
        name = str(record.get("full_name") or "").strip()
        if not isinstance(key, int) or not name:
            continue
        index.setdefault(normalize_name(name), []).append(
            {"player_key": key, "full_name": name, "position": str(record.get("position") or "").strip().upper() or None}
        )
    return index


def resolve_name(
    name: str, pos: str | None, index: dict[str, list[dict[str, Any]]]
) -> tuple[int | None, dict[str, Any] | None, str | None]:
    """Return (player_key, player_record, pos). Unresolved -> (None, None, reason).

    pos comes back as the canonical players-table position (the DB write's
    position source; the file's own spelling is never trusted for pos).

    Verified spelling aliases (ALIASES, shared with the DDF two-tier leg) are
    applied to the normalized name BEFORE lookup, so the import and the leg
    resolve the same identities. The map is exact-match only: any spelling not
    in ALIASES is looked up verbatim and still fails closed (no fuzzy
    matching, no guessing).
    """
    norm = normalize_name(name)
    norm = ALIASES.get(norm, norm)
    candidates = index.get(norm, [])
    if not candidates:
        return None, None, "no_match"
    if len(candidates) == 1:
        rec = candidates[0]
        return rec["player_key"], rec, rec["position"]
    wanted = (pos or "").strip().upper()
    if wanted:
        filtered = [c for c in candidates if c.get("position") == wanted]
        if len(filtered) == 1:
            rec = filtered[0]
            return rec["player_key"], rec, rec["position"]
    return None, None, "ambiguous"


# ---------------------------------------------------------------------------
# ESPN
# ---------------------------------------------------------------------------

ESPN_COMPONENT_COLS = (
    "r_pass_yds",
    "r_pass_tds",
    "r_rush_yds",
    "r_rush_tds",
    "r_receptions",
    "r_rec_yds",
    "r_rec_tds",
)


def espn_vintage(csv_path: Path, meta_path: Path) -> str:
    """Source-content vintage: meta sidecar first, else the CSV column."""
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("vintage"):
            return str(meta["vintage"])
    with csv_path.open(newline="", encoding="utf-8") as handle:
        dates = {r.get("espn_snapshot_date") for r in csv.DictReader(handle) if r.get("espn_snapshot_date")}
    if len(dates) == 1:
        return next(iter(dates))
    raise SystemExit(
        "Fail closed: ESPN content vintage undeterminable "
        "(no meta sidecar vintage and no unanimous espn_snapshot_date)."
    )


def build_espn_rows(csv_path: Path, meta_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    vintage = espn_vintage(csv_path, meta_path)
    with csv_path.open(newline="", encoding="utf-8") as handle:
        raw = list(csv.DictReader(handle))

    index = build_name_index(fetch_players())
    clean: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    pulled_at = utc_now()
    for row in raw:
        name = str(row.get("player") or "").strip()
        projected = str(row.get("has_espn_projection") or "").strip().lower() in ("true", "1", "yes")
        eligible = str(row.get("eligible") or "").strip().lower() in ("true", "1", "yes")
        if not name or not projected or not eligible:
            review.append({"reason": "no_espn_projection", "player": name or None})
            continue
        value = parse_float(row.get("ros_half_ppr"))
        if value is None:
            review.append({"reason": "missing_or_non_numeric_value", "player": name})
            continue
        key, _rec, pos = resolve_name(name, str(row.get("pos") or ""), index)
        if key is None:
            review.append(
                {
                    "reason": "unresolved_name",
                    "player": name,
                    "pos": str(row.get("pos") or "") or None,
                    "team": str(row.get("team") or "") or None,
                    "detail": "no single canonical players-table identity; never guessed",
                }
            )
            continue
        clean.append(
            {
                "player_key": key,
                "player_norm": str(row.get("player_norm") or normalize_name(name)),
                "season": 2026,
                "week": 2,
                "scoring": "half_ppr",
                **{col: parse_float(row.get(col)) for col in ESPN_COMPONENT_COLS},
                "ros_half_ppr": value,
                "weeks_covered": str(row.get("weeks_covered") or "") or None,
                "espn_snapshot_date": str(row.get("espn_snapshot_date") or vintage),
                "pulled_at": pulled_at,
            }
        )
    return clean, review, vintage


# ---------------------------------------------------------------------------
# CBS
# ---------------------------------------------------------------------------

# CBS header -> repo scoring. QBs publish a single 1QB-4 column with no
# per-scoring split: per the docstring decision, the 1QB-4 value is written
# once per scoring (standard/half_ppr/ppr) and labeled IMPLIED downstream.
CBS_TABLES = {
    "Quarterback": ("QB", [("1QB-4", "standard"), ("1QB-4", "half_ppr"), ("1QB-4", "ppr")]),
    "Running back": ("RB", [("non", "standard"), ("0.5", "half_ppr"), ("PPR", "ppr")]),
    "Wide receiver": ("WR", [("non", "standard"), ("0.5", "half_ppr"), ("PPR", "ppr")]),
    "Tight end": ("TE", [("non", "standard"), ("0.5", "half_ppr"), ("PPR", "ppr")]),
}
CBS_QB_SPLIT_NOTE = (
    "IMPLIED: CBS publishes one QB column (1QB-4), no per-scoring split; "
    "the 1QB-4 value is reused for standard/half_ppr/ppr (fixture cbs convention)"
)


def build_cbs_rows(json_path: Path, week: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    index = build_name_index(fetch_players())
    clean: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    pulled_at = utc_now()
    for table in payload.get("tables", []):
        mapping = CBS_TABLES.get(str(table.get("title")))
        if not mapping:
            review.append({"reason": "unknown_table", "title": table.get("title")})
            continue
        pos, columns = mapping
        headers = [str(h) for h in table.get("headers", [])]
        for raw_row in table.get("rows", []):
            cells = list(raw_row) if isinstance(raw_row, (list, tuple)) else []
            name = str(cells[0]).strip() if len(cells) > 0 else ""
            team = str(cells[1]).strip() if len(cells) > 1 else ""
            if not name:
                review.append({"reason": "missing_player_name", "row": cells})
                continue
            key, _rec, canonical_pos = resolve_name(name, pos, index)
            if key is None:
                review.append(
                    {
                        "reason": "unresolved_name",
                        "player": name,
                        "pos": pos,
                        "team": team or None,
                        "detail": "no single canonical players-table identity; never guessed",
                    }
                )
                continue
            for header, scoring in columns:
                try:
                    col_idx = headers.index(header)
                except ValueError:
                    review.append({"reason": "missing_column", "header": header, "player": name})
                    continue
                value = parse_float(cells[col_idx]) if col_idx < len(cells) else None
                if value is None:
                    review.append(
                        {"reason": "missing_or_non_numeric_value", "player": name, "column": header}
                    )
                    continue
                clean.append(
                    {
                        "source": "cbs",
                        "variant": "as_published",
                        "player_key": key,
                        "player_norm": normalize_name(name),
                        "scoring": scoring,
                        "league_teams": 12,
                        "qb_slots": 1,
                        "season": 2026,
                        "week": week,
                        "position": canonical_pos or pos,
                        "team": team or None,
                        "value": value,
                        "native_value": value,  # same scale for CBS
                        "source_content_date": None,  # article date unknown; vintage = week
                        "pulled_at": pulled_at,
                    }
                )
    return clean, review, pulled_at, str(payload.get("url") or "")


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

ESPN_UPSERT_CONFLICT = "season,week,player_key"
CBS_UPSERT_CONFLICT = "source,variant,scoring,league_teams,qb_slots,season,week,player_key"


def save_source(source: str, *, dry_run: bool, espn_csv: Path, espn_meta: Path,
                cbs_json: Path, week: int | None = None) -> dict[str, Any]:
    name = str(source or "").strip().lower()
    if name not in ("espn", "cbs"):
        raise SystemExit(f"Unknown source '{source}': save_espn_cbs_references.py handles espn|cbs only.")

    if name == "espn":
        table = "espn_season_projections"
        clean, review, vintage = build_espn_rows(espn_csv, espn_meta)
        conflict = ESPN_UPSERT_CONFLICT
        count_params = "?select=player_key&season=eq.2026&week=eq.2"
    else:
        week = week or nfl_week()
        table = "cbs_trade_values"
        clean, review, _pulled_at, _url = build_cbs_rows(cbs_json, week)
        conflict = CBS_UPSERT_CONFLICT
        count_params = ("?select=player_key&source=eq.cbs&variant=eq.as_published"
                        f"&season=eq.2026&week=eq.{week}")

    if not clean:
        raise SystemExit(f"Fail closed: source '{name}' resolved to zero clean rows. Never writing an empty save.")

    if dry_run:
        print(f"[dry-run] {name}: would upsert {len(clean)} rows into {table} ({len(review)} review)")
        return {"source": name, "table": table, "dry_run": True, "written": 0, "review_count": len(review), "review": review}

    upsert_rows(table, clean, conflict)
    live = count_rows(table, count_params)
    if live != len(clean):
        raise SystemExit(
            f"Fail closed: {table} holds {live} rows for the (2026, week {week if name == 'cbs' else 2}) grain after upsert, "
            f"expected {len(clean)}. The write did not land as planned; investigate before re-running."
        )

    return {
        "source": name,
        "table": table,
        "dry_run": False,
        "written": len(clean),
        "review_count": len(review),
        "review": review,
        "vintage": vintage if name == "espn" else f"Week {week}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=("espn", "cbs"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and report without writing (default is a live, idempotent write).",
    )
    parser.add_argument("--espn-csv", type=Path, default=DEFAULT_ESPN_CSV)
    parser.add_argument("--espn-meta", type=Path, default=DEFAULT_ESPN_META)
    parser.add_argument("--cbs-json", type=Path, default=DEFAULT_CBS_JSON)
    parser.add_argument(
        "--week",
        type=int,
        default=None,
        help="NFL week for the CBS save grain (default: current week from ops/watchdog/_common.nfl_week). ESPN path ignores this.",
    )
    parser.add_argument(
        "--review-out",
        type=Path,
        default=None,
        help="Write the review report JSON here (default: output/espn-cbs-save-review/<source>.json).",
    )
    args = parser.parse_args()

    result = save_source(
        args.source,
        dry_run=args.dry_run,
        espn_csv=args.espn_csv,
        espn_meta=args.espn_meta,
        cbs_json=args.cbs_json,
        week=args.week,
    )

    if result["review"]:
        review_path = args.review_out or (
            ROOT / "output" / "espn-cbs-save-review" / f"{args.source}-review.json"
        )
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(json.dumps(result["review"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"review report ({len(result['review'])} rows): {review_path}")

    status = "dry-run" if result["dry_run"] else "saved"
    print(
        f"{status}: {result['written']} {result['source']} rows -> {result['table']} "
        f"({result['review_count']} review, vintage {result.get('vintage')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
