#!/usr/bin/env python3
"""Pull all 24 FantasyCalc redraft combo configurations from the public API.

Fetches https://api.fantasycalc.com/values/current for all combinations of:
  numTeams: 8 | 10 | 12 | 14
  ppr:      0 (standard) | 0.5 (half_ppr) | 1 (ppr)
  numQbs:   1 | 2

Resolves player names to canonical player_key via the repo's players.json name
index, applies the isotonic chart-scale reindex (same contract as the Supabase
saver), and writes a multi-combo snapshot to
  data/raw/sources/fantasycalc/week-<N>/snapshot.json
with a companion snapshot-manifest.json.

The resulting snapshot is in the standard trade-value-source-snapshot-v1
format with one row per (player, scoring, teams, qb_slots) combination,
carrying both chart-scale `value` and raw `native_value`.  It can be fed
directly to the cascade pipeline via:
  cascade.cascade_from_snapshot(Path("data/raw/sources/fantasycalc/week-<N>/snapshot.json"))

Source vintage: the API returns "current" weekly values.  Content vintage is
derived from the NFL week parameter (same as the Supabase saver: week column,
not a dated article).

No Supabase reads or writes are performed.

Usage:
    python3 pull_fantasycalc_local.py [--week N] [--dry-run] [--output-dir DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "ops" / "watchdog"))

from save_espn_cbs_references import (  # noqa: E402
    build_name_index,
    fetch_players,
    resolve_name,
)
from _common import nfl_week  # noqa: E402

FC_API = "https://api.fantasycalc.com/values/current"
SCHEMA = "trade-value-source-snapshot-v1"
MANIFEST_SCHEMA = "trade-value-source-manifest-v1"
SEASON = 2026

# API parameter sets → (repo_scoring, teams, qb_slots)
# ppr=0 → standard, ppr=0.5 → half_ppr, ppr=1 → ppr
_COMBOS: list[tuple[str, int, int]] = [
    (scoring, teams, qbs)
    for scoring in ("standard", "half_ppr", "ppr")
    for teams in (8, 10, 12, 14)
    for qbs in (1, 2)
]
_SCORING_TO_PPR = {"standard": 0, "half_ppr": 0.5, "ppr": 1}


def _fetch_combo(scoring: str, teams: int, qbs: int) -> list[dict[str, Any]]:
    """Fetch one (scoring, teams, qbs) combo from the public API."""
    ppr = _SCORING_TO_PPR[scoring]
    url = (
        f"{FC_API}?isDynasty=false"
        f"&numTeams={teams}"
        f"&ppr={ppr}"
        f"&numQbs={qbs}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "fantasy-tools-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"Fail closed: unexpected API response shape for {url}")
    return data


def _parse_row(
    api_row: dict[str, Any],
    *,
    scoring: str,
    teams: int,
    qbs: int,
) -> dict[str, Any]:
    """Extract fields from one API row, preserving raw value as native_value."""
    player = api_row.get("player") or {}
    return {
        "player_name": str(player.get("name") or "").strip(),
        "pos": str(player.get("position") or "").strip().upper() or None,
        "team": str(player.get("maybeTeam") or "").strip() or None,
        "native_value": float(api_row["value"]) if api_row.get("value") is not None else None,
        "scoring": scoring,
        "teams": teams,
        "qb_slots": qbs,
    }


def build_snapshot(
    week: int,
    *,
    name_index: dict[str, Any],
    bake_id: str,
    pulled_at: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fetch all 24 combos, resolve names, reindex to chart scale.

    Returns (snapshot_dict, review_rows).
    """
    raw_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []

    for scoring, teams, qbs in _COMBOS:
        combo_label = f"{scoring}_{teams}_qb{qbs}"
        try:
            api_rows = _fetch_combo(scoring, teams, qbs)
        except Exception as exc:
            raise SystemExit(
                f"Fail closed: API fetch failed for {combo_label}: {exc}"
            ) from exc
        time.sleep(0.3)  # polite pacing between API calls

        for api_row in api_rows:
            parsed = _parse_row(api_row, scoring=scoring, teams=teams, qbs=qbs)
            name = parsed["player_name"]
            pos = parsed["pos"]
            if not name or parsed["native_value"] is None:
                review_rows.append(
                    {
                        "combo": combo_label,
                        "name": name,
                        "detail": "missing name or non-numeric value; skipped",
                    }
                )
                continue
            key, _rec, canonical_pos = resolve_name(name, pos, name_index)
            if key is None:
                review_rows.append(
                    {
                        "combo": combo_label,
                        "name": name,
                        "pos": pos,
                        "native_value": parsed["native_value"],
                        "detail": "no single canonical identity; never guessed",
                    }
                )
                continue
            raw_rows.append(
                {
                    "source": "fantasycalc",
                    "variant": "as_published",
                    "player_key": key,
                    "player_name": name,  # preserved for match stage
                    "pos": canonical_pos or pos,
                    "team": parsed["team"],
                    "scoring": scoring,
                    "teams": teams,
                    "qb_slots": qbs,
                    "season": SEASON,
                    "week": week,
                    "native_value": parsed["native_value"],
                    "value": parsed["native_value"],  # pre-reindex; will be replaced
                    "source_content_date": None,
                    "pulled_at": pulled_at,
                    "bake_id": bake_id,
                }
            )

    if not raw_rows:
        raise SystemExit(
            "Fail closed: all 24 combos resolved to zero clean rows. "
            f"({len(review_rows)} in review)"
        )

    # Note: chart-scale reindexing is NOT applied here.  The cascade's own
    # comparison-reindex stage performs the isotonic fit against the fixture's
    # ESPN anchor leg.  Native FantasyCalc values (~0-11000 scale) are carried
    # through; the cascade reindex produces the final chart-scale "reindexed"
    # values.  This is intentionally different from the Supabase saver path
    # (which pre-reindexes before writing); the native_movement review check
    # will therefore show 100% movement vs the prior fixture's chart-scale
    # native values, but that is an INFO check, not a FAIL.
    snapshot_rows = [
        {
            "native_value": r["native_value"],
            "player_name": r["player_name"],
            "pos": r["pos"],
            "scoring": r["scoring"],
            "source_player_id": r["player_key"],
            "team": r["team"],
            "teams": r["teams"],
            "qb_slots": r["qb_slots"],
            "value": r["native_value"],  # raw scale; cascade reindex converts
        }
        for r in raw_rows
    ]

    snapshot = {
        "schema": SCHEMA,
        "source": "fantasycalc",
        "scoring": None,
        "teams": None,
        "combos": [],
        "row_count": len(snapshot_rows),
        "review_count": len(review_rows),
        "rows": snapshot_rows,
    }
    return snapshot, review_rows


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week", type=int, default=None, help="NFL week (default: current)")
    parser.add_argument("--dry-run", action="store_true", help="Resolve and count without writing")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "raw" / "sources" / "fantasycalc",
        help="Parent of week-N/ output directory",
    )
    args = parser.parse_args(argv)

    week = args.week or nfl_week()
    pulled_at = datetime.now(timezone.utc).isoformat()
    bake_id = f"fcwk{week}_local_{pulled_at[:10].replace('-', '')}_v1"

    print(f"Fetching FantasyCalc Week {week} — all 24 combos (3 scorings × 4 team sizes × 2 QB slots)")
    print(f"bake_id: {bake_id}")

    name_index = build_name_index(fetch_players())
    snapshot, review_rows = build_snapshot(week, name_index=name_index, bake_id=bake_id, pulled_at=pulled_at)

    combo_set = set()
    for r in snapshot["rows"]:
        combo_set.add((r["scoring"], r["teams"], r["qb_slots"]))
    combo_count = len(combo_set)

    print(
        f"Resolved: {snapshot['row_count']} clean rows across {combo_count}/24 combos, "
        f"{snapshot['review_count']} in review"
    )

    if args.dry_run:
        print("[dry-run] Not writing. Combo coverage:")
        for scoring, teams, qbs in sorted(combo_set):
            n = sum(1 for r in snapshot["rows"] if r["scoring"] == scoring and r["teams"] == teams and r["qb_slots"] == qbs)
            print(f"  {scoring}_{teams}_qb{qbs}: {n} rows")
        return 0

    target_dir = args.output_dir / f"week-{week}"
    target_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = target_dir / "snapshot.json"
    manifest_path = target_dir / "snapshot-manifest.json"

    snapshot_bytes = (json.dumps(snapshot, indent=2, sort_keys=True) + "\n").encode("utf-8")
    sha = _sha256(snapshot_bytes)

    # Fail closed: refuse to silently overwrite a different-provenance snapshot.
    if snapshot_path.exists():
        existing_sha = _sha256(snapshot_path.read_bytes())
        if existing_sha == sha:
            print(f"Snapshot already current ({sha[:16]}…). Nothing to do.")
            return 0
        # Archive the old snapshot.
        stamp = pulled_at.replace("-", "").replace(":", "").replace(".", "")[:15]
        archive = target_dir / "_superseded" / stamp
        archive.mkdir(parents=True, exist_ok=True)
        snapshot_path.rename(archive / "snapshot.json")
        if manifest_path.exists():
            manifest_path.rename(archive / "snapshot-manifest.json")
        print(f"Archived prior snapshot to {archive}")

    snapshot_path.write_bytes(snapshot_bytes)

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "source": "fantasycalc",
        "content_vintage": f"Week {week}",
        "content_vintage_derived_from": "week parameter (fantasycalc publishes weekly redraft values)",
        "week_designated": week,
        "row_count": snapshot["row_count"],
        "review_count": snapshot["review_count"],
        "combo_count": combo_count,
        "combos": sorted(f"{s}_{t}_qb{q}" for s, t, q in combo_set),
        "snapshot_path": str(snapshot_path),
        "snapshot_schema": SCHEMA,
        "snapshot_sha256": sha,
        "source_url": f"{FC_API}?isDynasty=false&numTeams=<T>&ppr=<P>&numQbs=<Q>",
        "pulled_at": pulled_at,
        "pulled_at_note": "PULL TIME, not content vintage. Freshness gates must use content_vintage.",
        "bake_id": bake_id,
        "from_file": None,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Wrote {snapshot_path}")
    print(f"Wrote {manifest_path}")
    if review_rows:
        review_path = ROOT / "output" / "fantasycalc-save-review" / f"{bake_id}_review.json"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(json.dumps({"bake_id": bake_id, "review": review_rows}, indent=2) + "\n", encoding="utf-8")
        print(f"Review: {review_path} ({len(review_rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
