#!/usr/bin/env python3
"""Build source-reference artifact(s) from matched source rows.

One artifact is emitted per (scoring, teams, qb) group found in the matched
rows. Grouping is by each row's own scoring/teams/qb (falling back to the
match file's defaults), because a source can publish the same player_key
under several scorings (e.g. USA Today's standard/half_ppr/ppr rows) with
different values -- grouping by player_key alone turned those into spurious
"duplicate_player_key" review groups.

Load-bearing guards:
- genuine duplicates (same player_key AND same scoring/teams/qb with
  conflicting values) still become duplicate review rows -- that guard is
  never relaxed;
- rows whose scoring cannot be resolved (neither row-level nor match-file
  defaults) are never placed and never guessed: they become missing_scoring
  review rows. This is the same fail-closed convention as the match stage's
  no_match/ambiguous rows and the comparison-section stage's review rows --
  data that cannot be attributed is reviewed, never silently filed;
- a single homogeneous (scoring, teams, qb) group produces byte-identical
  output to the pre-split builder (same artifact shape, same default path).
"""

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


def combo_key(scoring: Any, teams: Any, qb: Any = None) -> str:
    score = str(scoring or "mixed")
    team_count = str(teams or "mixed")
    base = f"{score}_{team_count}"
    try:
        q = int(qb)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return base
    return f"{base}_qb{q}" if q in (1, 2) else base


def normalize_teams(value: Any) -> Any:
    """Coerce integral team counts to int so 12 and "12" land in one group."""
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return str(value).strip()


def normalize_qb(value: Any) -> Any:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return value


def group_key_for(row: dict[str, Any], defaults: dict[str, Any]) -> tuple[Any, Any, Any]:
    """Resolve the (scoring, teams, qb) group key for one matched row.

    Row-level values win; the match file's defaults fill gaps (this mirrors
    match_source_snapshot, which already falls back the same way). Scoring
    with no resolution anywhere stays None and is handled fail-closed by
    split_scoring_groups.
    """
    scoring = row.get("scoring") or defaults.get("scoring")
    teams = normalize_teams(row.get("teams") or defaults.get("teams"))
    qb = row.get("qb")
    if qb is None:
        qb = defaults.get("qb")
    return scoring, teams, normalize_qb(qb)


def split_scoring_groups(
    matched_rows: list[dict[str, Any]], defaults: dict[str, Any]
) -> tuple[dict[tuple[Any, Any, Any], list[dict[str, Any]]], list[dict[str, Any]]]:
    """Split matched rows into per-(scoring, teams, qb) groups.

    Rows whose scoring cannot be resolved become missing_scoring review rows:
    without a scoring they cannot be attributed to any group, so they are
    never placed and never guessed into one. Groups keep first-seen order.
    """
    groups: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = {}
    missing_scoring: list[dict[str, Any]] = []
    for row in matched_rows:
        scoring, teams, qb = group_key_for(row, defaults)
        if scoring is None:
            missing_scoring.append(
                {
                    "reason": "missing_scoring",
                    "player_key": row.get("player_key"),
                    "canonical_name": row.get("canonical_name"),
                    "source_player_name": row.get("source_player_name"),
                    "value": row.get("value"),
                    "note": (
                        "scoring unresolvable from the row and the match "
                        "defaults; never placed, never guessed into a group"
                    ),
                }
            )
            continue
        groups.setdefault((scoring, teams, qb), []).append(row)
    return groups, missing_scoring


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
                "qb": row.get("qb"),
                "pos": row.get("pos"),
                "team": row.get("team"),
                "source_player_name": row.get("source_player_name"),
                "source_player_id": row.get("source_player_id"),
            }
        )

    reference_rows.sort(key=lambda row: (-row["value"], str(row.get("canonical_name") or ""), row["player_key"]))
    return reference_rows, duplicate_review


def build_references(match_path: Path) -> list[dict[str, Any]]:
    """Build one reference artifact per (scoring, teams, qb) group."""
    matched = load_json(match_path)
    if matched.get("schema") != INPUT_SCHEMA:
        raise SystemExit(f"{match_path} is not a {INPUT_SCHEMA} file")
    matched_rows = matched.get("matched_rows")
    if not isinstance(matched_rows, list):
        raise SystemExit(f"{match_path} must contain matched_rows[]")

    defaults = {
        "scoring": matched.get("default_scoring"),
        "teams": matched.get("default_teams"),
        "qb": matched.get("default_qb"),
    }
    groups, missing_scoring = split_scoring_groups(matched_rows, defaults)
    if not groups:
        raise SystemExit(
            f"{match_path}: no (scoring, teams, qb) groups -- "
            f"{len(missing_scoring)} row(s) lack resolvable scoring; refusing "
            "to write an empty reference"
        )
    inherited_review = matched.get("review_rows") if isinstance(matched.get("review_rows"), list) else []

    artifacts = []
    for (scoring, teams, qb), group_rows in groups.items():
        reference_rows, duplicate_review = unique_reference_rows(group_rows)
        values_by_player_key = {
            str(row["player_key"]): row["value"]
            for row in reference_rows
        }
        player_key_by_source_name = {
            slug(str(row["source_player_name"])): row["player_key"]
            for row in reference_rows
            if row.get("source_player_name")
        }
        summary: dict[str, Any] = {
            "matched_input_count": len(group_rows),
            "reference_row_count": len(reference_rows),
            "inherited_review_count": len(inherited_review),
            "duplicate_review_count": len(duplicate_review),
        }
        # The key appears only when nonzero so a single homogeneous group
        # keeps the exact pre-split summary shape.
        if missing_scoring:
            summary["missing_scoring_review_count"] = len(missing_scoring)

        artifacts.append(
            {
                "schema": OUTPUT_SCHEMA,
                "generated_at": utc_now(),
                "input_match": str(match_path),
                "source": matched.get("source"),
                "fetched_at": matched.get("fetched_at"),
                "scoring": scoring,
                "teams": teams,
                "qb": qb,
                "combo_key": combo_key(scoring, teams, qb),
                "summary": summary,
                "rows": reference_rows,
                "values_by_player_key": values_by_player_key,
                "player_key_by_source_name": player_key_by_source_name,
                # Input-level review context is replicated per group so every
                # artifact is self-describing; the comparison-section stage
                # dedupes identical inherited rows when consuming several
                # reference artifacts at once.
                "review_rows": inherited_review + missing_scoring + duplicate_review,
            }
        )
    return artifacts


def default_output_path(reference: dict[str, Any], output_dir: Path) -> Path:
    fetched = str(reference.get("fetched_at") or utc_now())[:10]
    source = slug(str(reference.get("source") or "source"))
    combo = slug(str(reference.get("combo_key") or "mixed"))
    return output_dir / source / fetched / f"{source}-{combo}-reference.json"


def write_artifact(reference: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(reference, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    artifacts = build_references(args.input)
    if args.output and len(artifacts) > 1:
        combos = ", ".join(artifact["combo_key"] for artifact in artifacts)
        raise SystemExit(
            f"--output cannot hold {len(artifacts)} reference artifacts "
            f"({combos}); pass --output-dir instead so each group gets its "
            "own combo-suffixed path"
        )

    if len(artifacts) == 1:
        (artifact,) = artifacts
        output = args.output or default_output_path(artifact, args.output_dir)
        write_artifact(artifact, output)
        summary = artifact["summary"]
        print(
            f"Built {summary['reference_row_count']} reference rows; "
            f"{len(artifact['review_rows'])} total review rows. Wrote {output}"
        )
        return 0

    print(f"Built {len(artifacts)} reference artifacts from {args.input}:")
    for artifact in artifacts:
        output = default_output_path(artifact, args.output_dir)
        write_artifact(artifact, output)
        summary = artifact["summary"]
        print(
            f"  {artifact['combo_key']}: {summary['reference_row_count']} "
            f"reference rows; {len(artifact['review_rows'])} review rows. "
            f"Wrote {output}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
