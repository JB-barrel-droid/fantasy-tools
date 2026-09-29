#!/usr/bin/env python3
"""Match a raw source snapshot to canonical player_key values."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "source-matches"
INPUT_SCHEMA = "trade-value-source-snapshot-v1"
OUTPUT_SCHEMA = "trade-value-source-matches-v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "snapshot"


def normalize_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return payload


def infer_vintage_kind(manifest: dict[str, Any], snapshot: dict[str, Any]) -> str:
    if manifest.get("week_designated") is not None:
        return "week_designated"
    vintage = manifest.get("content_vintage")
    if isinstance(vintage, str) and re.fullmatch(r"\s*week\s+\d+\s*", vintage, re.I):
        return "week_designated"
    if isinstance(vintage, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", vintage.strip()):
        return "file_meta" if str(snapshot.get("source") or "").lower() == "espn" else "source_content_date"
    return "unknown"


def source_provenance(snapshot_path: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Immutable source-vintage facts plus separate processing/acquisition times."""
    manifest_path = snapshot_path.parent / "snapshot-manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        manifest = load_json(manifest_path)
    return {
        "source": snapshot.get("source"),
        "content_vintage": manifest.get("content_vintage"),
        "content_vintage_derived_from": manifest.get("content_vintage_derived_from"),
        "vintage_kind": infer_vintage_kind(manifest, snapshot),
        "week_designated": manifest.get("week_designated"),
        "source_pulled_at": manifest.get("pulled_at"),
        "snapshot_fetched_at": snapshot.get("fetched_at"),
        "snapshot_manifest": str(manifest_path) if manifest_path.is_file() else None,
        "note": (
            "content_vintage is immutable source provenance. "
            "source_pulled_at, snapshot_fetched_at, and generated_at are processing/acquisition times."
        ),
    }


def player_records(players_path: Path) -> list[dict[str, Any]]:
    payload = load_json(players_path)
    rows = payload.get("players")
    if not isinstance(rows, list):
        raise SystemExit(f"{players_path} must contain players[]")
    records = []
    for row in rows:
        key = row.get("player_key")
        name = str(row.get("name") or row.get("full_name") or "").strip()
        if not isinstance(key, int) or not name:
            continue
        records.append(
            {
                "player_key": key,
                "name": name,
                "normalized_name": normalize_name(name),
                "team": str(row.get("team") or "").strip().upper() or None,
                "pos": str(row.get("pos") or "").strip().upper() or None,
            }
        )
    return records


def build_name_index(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        index.setdefault(record["normalized_name"], []).append(record)
    return index


def resolve_candidate(row: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    if not candidates:
        return None, "no_match"
    if len(candidates) == 1:
        return candidates[0], None

    pos = str(row.get("pos") or "").strip().upper()
    team = str(row.get("team") or "").strip().upper()
    filtered = candidates
    if pos:
        filtered = [candidate for candidate in filtered if candidate.get("pos") == pos]
    if team and len(filtered) > 1:
        filtered = [candidate for candidate in filtered if candidate.get("team") == team]
    if len(filtered) == 1:
        return filtered[0], None
    return None, "ambiguous"


def default_output_path(snapshot: dict[str, Any], output_dir: Path) -> Path:
    fetched = str(snapshot.get("fetched_at") or utc_now())[:10]
    source = slug(str(snapshot.get("source") or "source"))
    scoring = slug(str(snapshot.get("default_scoring") or "mixed"))
    teams = str(snapshot.get("default_teams") or "mixed")
    return output_dir / source / fetched / f"{source}-{scoring}-{teams}-matched.json"


def match_snapshot(snapshot_path: Path, players_path: Path) -> dict[str, Any]:
    snapshot = load_json(snapshot_path)
    if snapshot.get("schema") != INPUT_SCHEMA:
        raise SystemExit(f"{snapshot_path} is not a {INPUT_SCHEMA} file")
    rows = snapshot.get("rows")
    if not isinstance(rows, list):
        raise SystemExit(f"{snapshot_path} must contain rows[]")

    records = player_records(players_path)
    index = build_name_index(records)
    matched = []
    review = []
    for row in rows:
        normalized = normalize_name(row.get("player_name"))
        candidates = index.get(normalized, [])
        player, reason = resolve_candidate(row, candidates)
        if player:
            # Carry the qb dimension through. Snapshot rows may use either
            # "qb" (section-stage vocabulary) or "qb_slots" (Supabase grain
            # key). Without this, combo_key_for(qb=None) produces bare keys
            # like "full_12" that never match fixture combo names ("full_12_qb1").
            _qb = row.get("qb") if row.get("qb") is not None else row.get("qb_slots")
            matched.append(
                {
                    "player_key": player["player_key"],
                    "canonical_name": player["name"],
                    "source_player_name": row.get("player_name"),
                    "source": snapshot.get("source"),
                    "value": row.get("value"),
                    "native_value": row.get("native_value"),
                    "scoring": row.get("scoring") or snapshot.get("default_scoring"),
                    "teams": row.get("teams") or snapshot.get("default_teams"),
                    "qb": _qb,
                    "pos": row.get("pos"),
                    "team": row.get("team"),
                    "source_player_id": row.get("source_player_id"),
                }
            )
            continue
        review.append(
            {
                "reason": reason,
                "source_player_name": row.get("player_name"),
                "normalized_name": normalized,
                "source": snapshot.get("source"),
                "value": row.get("value"),
                "scoring": row.get("scoring") or snapshot.get("default_scoring"),
                "teams": row.get("teams") or snapshot.get("default_teams"),
                "pos": row.get("pos"),
                "team": row.get("team"),
                "candidate_player_keys": [candidate["player_key"] for candidate in candidates],
                "candidate_names": [candidate["name"] for candidate in candidates],
            }
        )

    return {
        "schema": OUTPUT_SCHEMA,
        "generated_at": utc_now(),
        "input_snapshot": str(snapshot_path),
        "source": snapshot.get("source"),
        "fetched_at": snapshot.get("fetched_at"),
        "source_provenance": source_provenance(snapshot_path, snapshot),
        "default_scoring": snapshot.get("default_scoring"),
        "default_teams": snapshot.get("default_teams"),
        "summary": {
            "input_row_count": len(rows),
            "matched_count": len(matched),
            "review_count": len(review),
        },
        "matched_rows": matched,
        "review_rows": review,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--players", type=Path, default=DEFAULT_PLAYERS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    payload = match_snapshot(args.input, args.players)
    output = args.output or default_output_path(payload, args.output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = payload["summary"]
    print(
        f"Matched {summary['matched_count']} of {summary['input_row_count']} rows; "
        f"{summary['review_count']} need review. Wrote {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
