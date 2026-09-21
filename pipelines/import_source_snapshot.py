#!/usr/bin/env python3
"""Import a scraped trade-value source snapshot into a standard raw format."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "raw" / "sources"
SCHEMA = "trade-value-source-snapshot-v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "snapshot"


def first_value(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    lower = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        if name in lower and lower[name] not in (None, ""):
            return lower[name]
    return None


def parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "")
    if text in {"--", "-", "n/a", "N/A"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def normalize_scoring(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    aliases = {
        "ppr": "ppr",
        "full": "ppr",
        "full_ppr": "ppr",
        "half": "half_ppr",
        "half_ppr": "half_ppr",
        "0_5_ppr": "half_ppr",
        "standard": "standard",
        "std": "standard",
        "non_ppr": "standard",
    }
    return aliases.get(text, text)


def load_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle)), {}

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)], {}
    if isinstance(payload, dict):
        rows = (
            payload.get("rows")
            or payload.get("items")
            or payload.get("players")
            or payload.get("values")
            or []
        )
        if isinstance(rows, dict):
            rows = [
                {"player_name": key, "value": value}
                for key, value in rows.items()
            ]
        return [item for item in rows if isinstance(item, dict)], payload
    raise SystemExit(f"Unsupported snapshot payload in {path}")


def normalize_rows(
    rows: list[dict[str, Any]],
    *,
    default_scoring: str | None,
    default_teams: int | None,
) -> list[dict[str, Any]]:
    normalized = []
    skipped = 0
    for row in rows:
        player_name = first_value(row, ("player_name", "player", "name", "full_name"))
        value = parse_float(first_value(row, ("value", "trade_value", "ros_value", "score")))
        if not player_name or value is None:
            skipped += 1
            continue
        scoring = normalize_scoring(first_value(row, ("scoring", "format"))) or default_scoring
        teams = parse_int(first_value(row, ("teams", "league_size", "team_count"))) or default_teams
        normalized.append(
            {
                "player_name": str(player_name).strip(),
                "value": value,
                "pos": str(first_value(row, ("pos", "position")) or "").strip() or None,
                "team": str(first_value(row, ("team", "nfl_team")) or "").strip() or None,
                "scoring": scoring,
                "teams": teams,
                "source_player_id": first_value(row, ("source_player_id", "player_id", "id")),
            }
        )
    if not normalized:
        raise SystemExit(f"No usable rows found; skipped {skipped} rows")
    return normalized


def build_snapshot(
    path: Path,
    *,
    source: str | None,
    scoring: str | None,
    teams: int | None,
    fetched_at: str | None,
    source_url: str | None,
) -> dict[str, Any]:
    rows, metadata = load_rows(path)
    resolved_source = source or metadata.get("source")
    if not resolved_source:
        raise SystemExit("--source is required when the input file has no source field")

    resolved_scoring = normalize_scoring(scoring or metadata.get("scoring") or metadata.get("format"))
    resolved_teams = teams or parse_int(metadata.get("teams") or metadata.get("league_size"))
    normalized = normalize_rows(rows, default_scoring=resolved_scoring, default_teams=resolved_teams)

    return {
        "schema": SCHEMA,
        "source": str(resolved_source),
        "fetched_at": fetched_at or metadata.get("fetched_at") or utc_now(),
        "source_url": source_url or metadata.get("source_url") or metadata.get("url"),
        "default_scoring": resolved_scoring,
        "default_teams": resolved_teams,
        "row_count": len(normalized),
        "rows": normalized,
    }


def default_output_path(snapshot: dict[str, Any], output_dir: Path) -> Path:
    fetched = str(snapshot["fetched_at"])[:10]
    name = "-".join(
        part for part in (
            slug(snapshot["source"]),
            slug(str(snapshot.get("default_scoring") or "mixed")),
            str(snapshot.get("default_teams") or "mixed"),
            str(snapshot["fetched_at"]).replace(":", "").replace("+", "p").replace("Z", "z"),
        )
        if part
    )
    return output_dir / slug(snapshot["source"]) / fetched / f"{name}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--source")
    parser.add_argument("--scoring")
    parser.add_argument("--teams", type=int)
    parser.add_argument("--fetched-at")
    parser.add_argument("--source-url")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    snapshot = build_snapshot(
        args.input,
        source=args.source,
        scoring=args.scoring,
        teams=args.teams,
        fetched_at=args.fetched_at,
        source_url=args.source_url,
    )
    output = args.output or default_output_path(snapshot, args.output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Imported {snapshot['row_count']} {snapshot['source']} rows to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
