#!/usr/bin/env python3
"""Build a source-reference artifact from matched source rows."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "output" / "source-references"
INPUT_SCHEMA = "trade-value-source-matches-v1"
OUTPUT_SCHEMA = "trade-value-source-reference-v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "source"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return payload


def combo_key(scoring: Any, teams: Any) -> str:
    score = str(scoring or "mixed")
    team_count = str(teams or "mixed")
    return f"{score}_{team_count}"


def unique_reference_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        player_key = row.get("player_key")
        value = row.get("value")
        if not isinstance(player_key, int) or not isinstance(value, (int, float)):
            continue
        grouped.setdefault(player_key, []).append(row)

    reference_rows = []
    duplicate_review = []
    for player_key, player_rows in grouped.items():
        distinct_values = {float(row["value"]) for row in player_rows}
        if len(distinct_values) > 1:
            duplicate_review.append(
                {
                    "reason": "duplicate_player_key",
                    "player_key": player_key,
                    "canonical_name": player_rows[0].get("canonical_name"),
                    "values": sorted(distinct_values, reverse=True),
                    "rows": player_rows,
                }
            )
            continue
        row = player_rows[0]
        reference_rows.append(
            {
                "player_key": player_key,
                "canonical_name": row.get("canonical_name"),
                "value": float(row["value"]),
                "scoring": row.get("scoring"),
                "teams": row.get("teams"),
                "pos": row.get("pos"),
                "team": row.get("team"),
                "source_player_name": row.get("source_player_name"),
                "source_player_id": row.get("source_player_id"),
            }
        )

    reference_rows.sort(key=lambda row: (-row["value"], str(row.get("canonical_name") or ""), row["player_key"]))
    return reference_rows, duplicate_review


def build_reference(match_path: Path) -> dict[str, Any]:
    matched = load_json(match_path)
    if matched.get("schema") != INPUT_SCHEMA:
        raise SystemExit(f"{match_path} is not a {INPUT_SCHEMA} file")
    matched_rows = matched.get("matched_rows")
    if not isinstance(matched_rows, list):
        raise SystemExit(f"{match_path} must contain matched_rows[]")

    reference_rows, duplicate_review = unique_reference_rows(matched_rows)
    inherited_review = matched.get("review_rows") if isinstance(matched.get("review_rows"), list) else []
    scoring = matched.get("default_scoring")
    teams = matched.get("default_teams")
    values_by_player_key = {
        str(row["player_key"]): row["value"]
        for row in reference_rows
    }
    player_key_by_source_name = {
        slug(str(row["source_player_name"])): row["player_key"]
        for row in reference_rows
        if row.get("source_player_name")
    }

    return {
        "schema": OUTPUT_SCHEMA,
        "generated_at": utc_now(),
        "input_match": str(match_path),
        "source": matched.get("source"),
        "fetched_at": matched.get("fetched_at"),
        "scoring": scoring,
        "teams": teams,
        "combo_key": combo_key(scoring, teams),
        "summary": {
            "matched_input_count": len(matched_rows),
            "reference_row_count": len(reference_rows),
            "inherited_review_count": len(inherited_review),
            "duplicate_review_count": len(duplicate_review),
        },
        "rows": reference_rows,
        "values_by_player_key": values_by_player_key,
        "player_key_by_source_name": player_key_by_source_name,
        "review_rows": inherited_review + duplicate_review,
    }


def default_output_path(reference: dict[str, Any], output_dir: Path) -> Path:
    fetched = str(reference.get("fetched_at") or utc_now())[:10]
    source = slug(str(reference.get("source") or "source"))
    combo = slug(str(reference.get("combo_key") or "mixed"))
    return output_dir / source / fetched / f"{source}-{combo}-reference.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    reference = build_reference(args.input)
    output = args.output or default_output_path(reference, args.output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(reference, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = reference["summary"]
    print(
        f"Built {summary['reference_row_count']} reference rows; "
        f"{len(reference['review_rows'])} total review rows. Wrote {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
