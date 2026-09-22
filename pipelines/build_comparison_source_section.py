#!/usr/bin/env python3
"""Build a candidate comparison source section from a source-reference artifact.

Reads a trade-value-source-reference-v1 artifact and emits a candidate
comparison-source section shaped like one entry of the comparison fixture's
``sources{}`` map.

The candidate carries NATIVE source values only. Fixed-pie reindexing and any
other reference-compute math are intentionally NOT applied here; they must be
reviewed before any promotion into data/fixtures/current/.

Identity rules (fail closed):
- every player_key is resolved to a canonical fixture slug through the current
  comparison fixture's own player_keys map (never recomputed, so legacy slug
  quirks are preserved byte-for-byte);
- player_keys with no canonical slug go to review_rows, never guessed;
- rows with missing/non-numeric values go to review_rows, never zero-filled;
- conflicting duplicate values for the same player_key go to review_rows,
  never silently merged.

Writes only under output/. Never touches data/fixtures/current/.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPARISON = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "comparison-candidates"
INPUT_SCHEMA = "trade-value-source-reference-v1"
OUTPUT_SCHEMA = "trade-value-comparison-section-candidate-v1"

# Reference artifacts normalize scoring to ppr / half_ppr / standard; the
# comparison fixture's combo vocabulary is full / half / standard.
SCORING_WORDS = {"ppr": "full", "half_ppr": "half", "standard": "standard"}


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


def canonical_slugs(comparison_path: Path) -> dict[int, str]:
    """Invert the fixture's player_keys map: player_key -> canonical slug."""
    comparison = load_json(comparison_path)
    player_keys = comparison.get("player_keys")
    if not isinstance(player_keys, dict) or not player_keys:
        raise SystemExit(f"{comparison_path} must contain player_keys{{}}")
    inverted: dict[int, str] = {}
    for name, key in player_keys.items():
        if not isinstance(key, int):
            raise SystemExit(f"{comparison_path} has a non-integer player_key for {name!r}")
        if key in inverted:
            raise SystemExit(f"{comparison_path} maps player_key {key} to multiple names")
        inverted[key] = str(name)
    return inverted


def combo_key_for(scoring: Any, teams: Any) -> str:
    word = SCORING_WORDS.get(str(scoring or "").strip().lower(), str(scoring or "mixed").strip().lower())
    return f"{word}_{teams or 'mixed'}"


def build_section(
    reference_path: Path,
    comparison_path: Path,
    *,
    section_key: str | None,
    meta: dict[str, Any],
) -> dict[str, Any]:
    reference = load_json(reference_path)
    if reference.get("schema") != INPUT_SCHEMA:
        raise SystemExit(f"{reference_path} is not a {INPUT_SCHEMA} file")
    rows = reference.get("rows")
    if not isinstance(rows, list):
        raise SystemExit(f"{reference_path} must contain rows[]")

    slugs = canonical_slugs(comparison_path)
    source = str(reference.get("source") or "source")
    key = section_key or slug(source)

    combos: dict[str, dict[str, float]] = {}
    review_rows: list[dict[str, Any]] = []
    seen_keys: set[int] = set()
    placed = 0

    for row in rows:
        player_key = row.get("player_key")
        value = row.get("value")
        if not isinstance(player_key, int):
            review_rows.append({"reason": "missing_player_key", "row": row})
            continue
        if player_key in seen_keys:
            review_rows.append(
                {
                    "reason": "duplicate_player_key",
                    "player_key": player_key,
                    "canonical_name": row.get("canonical_name"),
                    "stage": "comparison-section",
                }
            )
            continue
        name = slugs.get(player_key)
        if name is None:
            review_rows.append(
                {
                    "reason": "no_canonical_slug",
                    "player_key": player_key,
                    "canonical_name": row.get("canonical_name"),
                    "source_player_name": row.get("source_player_name"),
                    "stage": "comparison-section",
                }
            )
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            # Missing values stay missing. Never zero-fill.
            review_rows.append(
                {
                    "reason": "non_numeric_value",
                    "player_key": player_key,
                    "canonical_name": row.get("canonical_name"),
                    "stage": "comparison-section",
                }
            )
            continue
        seen_keys.add(player_key)
        combo = combo_key_for(row.get("scoring"), row.get("teams"))
        combos.setdefault(combo, {})[name] = float(value)
        placed += 1

    inherited = reference.get("review_rows") if isinstance(reference.get("review_rows"), list) else []
    for row in inherited:
        review_rows.append({**row, "stage": row.get("stage", "source-reference")})

    combo_payload = {
        combo: {
            "native": dict(sorted(values.items())),
            "n": len(values),
            "value_provenance": "published",
        }
        for combo, values in sorted(combos.items())
    }

    return {
        "schema": OUTPUT_SCHEMA,
        "generated_at": utc_now(),
        "input_reference": str(reference_path),
        "section_key": key,
        "reindex_status": "pending",
        "name": meta.get("name") or source,
        "kind": meta.get("kind") or "candidate source section (kind unspecified)",
        "position_coverage": meta.get("position_coverage"),
        "claimed_settings": meta.get("claimed_settings"),
        "value_provenance": "published",
        "provenance_note": meta.get("provenance_note")
        or (
            "Candidate section built from a source-reference artifact. Carries native "
            "source values only; fixed-pie reindexing has NOT been applied. Not reviewed; "
            "not safe to publish."
        ),
        "update_cadence": meta.get("update_cadence"),
        "week_designated": meta.get("week_designated"),
        "url": meta.get("url") or reference.get("source_url"),
        "fetched_at": reference.get("fetched_at"),
        "native_unit": meta.get("native_unit") or "source published value (as scraped)",
        "combos": combo_payload,
        "summary": {
            "reference_row_count": len(rows),
            "placed_count": placed,
            "combo_count": len(combo_payload),
            "inherited_review_count": len(inherited),
            "section_review_count": len(review_rows) - len(inherited),
            "review_row_count": len(review_rows),
        },
        "review_rows": review_rows,
    }


def default_output_path(section: dict[str, Any], output_dir: Path) -> Path:
    fetched = str(section.get("fetched_at") or utc_now())[:10]
    key = slug(str(section.get("section_key") or "source"))
    first_combo = next(iter(section.get("combos", {})), "mixed")
    return output_dir / key / fetched / f"{key}-{slug(first_combo)}-section.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="trade-value-source-reference-v1 file")
    parser.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON,
                        help="current comparison fixture (canonical slug authority, read-only)")
    parser.add_argument("--section-key", help="key under sources{}; defaults to the slugged source name")
    parser.add_argument("--name")
    parser.add_argument("--kind")
    parser.add_argument("--url")
    parser.add_argument("--native-unit")
    parser.add_argument("--position-coverage")
    parser.add_argument("--claimed-settings")
    parser.add_argument("--provenance-note")
    parser.add_argument("--update-cadence")
    parser.add_argument("--week-designated")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    section = build_section(
        args.input,
        args.comparison,
        section_key=args.section_key,
        meta={
            "name": args.name,
            "kind": args.kind,
            "url": args.url,
            "native_unit": args.native_unit,
            "position_coverage": args.position_coverage,
            "claimed_settings": args.claimed_settings,
            "provenance_note": args.provenance_note,
            "update_cadence": args.update_cadence,
            "week_designated": args.week_designated,
        },
    )
    output = args.output or default_output_path(section, args.output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(section, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = section["summary"]
    print(
        f"Built candidate section '{section['section_key']}' with {summary['placed_count']} values "
        f"across {summary['combo_count']} combos; {summary['review_row_count']} review rows. "
        f"reindex_status=pending. Wrote {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
