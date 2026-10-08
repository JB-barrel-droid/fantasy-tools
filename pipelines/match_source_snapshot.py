#!/usr/bin/env python3
"""Match a raw source snapshot to canonical player_key values."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from lib.canonical_players import norm_plain  # noqa: E402  -- identity-map key convention
from lib.layered_identity import resolve_sleeper  # noqa: E402  -- JEG-366 base layer
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import player_aliases  # noqa: E402  -- the one verified alias list

DEFAULT_PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"
DEFAULT_IDENTITY_MAP = ROOT / "data" / "inputs" / "player_identity_map.json"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "source-matches"
INPUT_SCHEMA = "trade-value-source-snapshot-v1"
OUTPUT_SCHEMA = "trade-value-source-matches-v1"


def normalize_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "snapshot"


# normalize_name is defined above (label-only, not for identity matching)


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
        # GAP-SOURCE-URL-WEEK2: the article these values were priced from;
        # promotion writes it to the fixture section's `url`.
        "source_url": snapshot.get("source_url"),
        "snapshot_manifest": str(manifest_path) if manifest_path.is_file() else None,
        "note": (
            "content_vintage is immutable source provenance. "
            "source_pulled_at, snapshot_fetched_at, and generated_at are processing/acquisition times."
        ),
    }


def load_identity_map(path: Path) -> dict[str, Any]:
    """Load the canonical player identity table.

    Jeremy 2026-10-04 ("Always yes"): player identification MUST come from
    the canonical identity table, never from ad-hoc name matching against
    the chart roster. Returns the raw map with 'canonical' and
    'alias_to_canonical' sections.
    """
    payload = load_json(path)
    if "canonical" not in payload or "alias_to_canonical" not in payload:
        raise SystemExit(f"{path} is not a player identity map")
    return payload


def resolve_identity(
    name: str, identity_map: dict[str, Any]
) -> dict[str, Any] | None:
    """Resolve a source name through the canonical identity table.

    Returns the canonical record (name, pos, team) or None if the table
    does not know this name. Fail-closed: unknown names are NOT guessed.

    The identity map is keyed by canonical_players.norm_plain (punctuation
    DELETED: "Ja'Marr" -> "jamarr", "A.J." -> "aj") plus some raw lowercase
    spellings. normalize_name() above REPLACES punctuation with a space
    ("ja marr"), so looking up with it alone missed every punctuated name
    (Chase, JSN, St. Brown, A.J. Brown, C.J. Stroud ...) and sent them to
    review as unknown_identity. Try the map's own key convention first.
    """
    alias_to_canonical = identity_map["alias_to_canonical"]
    canonical = identity_map["canonical"]
    # Verified aliases (data/inputs/player_aliases.json) first: the identity
    # map holds only mechanical spelling variants.
    raw = str(player_aliases.canonical_spelling(name) or "")
    for key in identity_keys(raw):
        canonical_key = alias_to_canonical.get(key)
        if canonical_key is None and key in canonical:
            canonical_key = key
        if canonical_key is not None:
            return canonical.get(canonical_key)
    return None


def identity_keys(name: str) -> list[str]:
    """Lookup keys for the identity map, most specific convention first."""
    keys = [norm_plain(name), name.lower().strip(), normalize_name(name)]
    return [k for k in dict.fromkeys(keys) if k]


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


def build_canonical_index(
    records: list[dict[str, Any]], identity_map: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    """Roster index keyed the same way source rows are: by canonical name.

    Each roster record is filed under its own normalized name AND under the
    normalized canonical name the identity table gives it, so a roster that
    says "Cam Ward" joins a source row the table resolves to "Cameron Ward".
    Both sides go through the identity table; nothing is fuzzy-matched.
    """
    index = build_name_index(records)
    for record in records:
        identity = resolve_identity(record["name"], identity_map)
        if not identity:
            continue
        key = normalize_name(identity["name"])
        bucket = index.setdefault(key, [])
        if all(r["player_key"] != record["player_key"] for r in bucket):
            bucket.append(record)
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


def match_snapshot(
    snapshot_path: Path,
    players_path: Path,
    identity_map_path: Path | None = None,
    use_sleeper: bool = True,
) -> dict[str, Any]:
    snapshot = load_json(snapshot_path)
    if snapshot.get("schema") != INPUT_SCHEMA:
        raise SystemExit(f"{snapshot_path} is not a {INPUT_SCHEMA} file")
    rows = snapshot.get("rows")
    if not isinstance(rows, list):
        raise SystemExit(f"{snapshot_path} must contain rows[]")

    # Jeremy 2026-10-04: identity resolves through the canonical table.
    # players.json supplies chart player_keys only, joined via canonical name.
    identity_map = load_identity_map(
        identity_map_path or DEFAULT_IDENTITY_MAP
    )
    records = player_records(players_path)
    index = build_canonical_index(records, identity_map)
    matched = []
    review = []
    for row in rows:
        normalized = normalize_name(row.get("player_name"))
        # Step 1: canonical identity MUST come from the identity table.
        # JEG-366: names the manual table does not know fall through to the
        # Sleeper base layer, which returns None on any ambiguity (never a
        # guess). identity_source records which layer resolved the row.
        identity = resolve_identity(row.get("player_name"), identity_map)
        identity_source = "manual"
        if identity is None and use_sleeper:
            identity = resolve_sleeper(row.get("player_name"), row.get("pos") or None)
            identity_source = identity["source"] if identity else None
        if identity is None:
            review.append(
                {
                    "reason": "unknown_identity",
                    "source_player_name": row.get("player_name"),
                    "normalized_name": normalized,
                    "source": snapshot.get("source"),
                    "native_value": row.get("native_value", row.get("value")),
                    "value": row.get("value"),
                    "scoring": row.get("scoring")
                    or snapshot.get("default_scoring"),
                    "teams": row.get("teams") or snapshot.get("default_teams"),
                    "pos": row.get("pos"),
                    "team": row.get("team"),
                    "source_player_id": row.get("source_player_id"),
                }
            )
            continue
        # Step 2: join canonical identity to the chart roster for player_key.
        # Use the identity table's canonical name (not the source's spelling).
        canonical_normalized = normalize_name(identity["name"])
        candidates = index.get(canonical_normalized, [])
        player, reason = resolve_candidate(row, candidates)
        if player:
            matched.append(
                {
                    "player_key": player["player_key"],
                    "canonical_name": player["name"],
                    "identity_source": identity_source,
                    "source_player_name": row.get("player_name"),
                    "source": snapshot.get("source"),
                    # Carry the source's raw published value. Downstream stages
                    # prefer native_value over value (which may already be
                    # reindexed/flattened); dropping it here silently corrupts
                    # the entire chain -- see 2026-09-30 FantasyCalc JSN defect.
                    "native_value": row.get("native_value", row.get("value")),
                    "value": row.get("value"),
                    "scoring": row.get("scoring") or snapshot.get("default_scoring"),
                    "teams": row.get("teams") or snapshot.get("default_teams"),
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
                "native_value": row.get("native_value", row.get("value")),
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
        # JEG-366: which identity layer resolved each matched row.
        "identity_layers": {
            layer: sum(1 for m in matched if m.get("identity_source") == layer)
            for layer in ("manual", "sleeper", "sleeper-rostered")
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
    parser.add_argument("--no-sleeper", action="store_true",
                        help="manual identity table only (disable the JEG-366 Sleeper layer)")
    args = parser.parse_args()

    payload = match_snapshot(args.input, args.players, use_sleeper=not args.no_sleeper)
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
