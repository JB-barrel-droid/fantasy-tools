#!/usr/bin/env python3
"""Fail closed when players.json identity fields diverge from the naming manifest.

The Supabase ``players`` table is the naming authority: one table, one numeric
key, one full_name. players.json fixtures are pinned exports of that table.
The manifest (data/fixtures/current/players.naming-manifest.json) records the
export's identity projection plus a hash; this check recomputes the projection
from players.json and fails closed on any divergence.

Refresh contract (see docs/pipeline-rules.md): every rebuild of players.json
from the naming table must re-pin the manifest atomically with the same
exported_at. A players.json whose identity projection does not match the
manifest blocks `make validate`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"
DEFAULT_MANIFEST = ROOT / "data" / "fixtures" / "current" / "players.naming-manifest.json"
MANIFEST_SCHEMA = "trade-value-naming-manifest-v1"


def identity_projection(players_path: Path) -> list[list[Any]]:
    payload = json.loads(players_path.read_text(encoding="utf-8"))
    rows = payload.get("players")
    if not isinstance(rows, list):
        raise SystemExit(f"{players_path} must contain players[]")
    projection = []
    for row in rows:
        key = row.get("player_key")
        name = str(row.get("full_name") or row.get("name") or "").strip()
        if not isinstance(key, int) or not name:
            raise SystemExit(f"{players_path} has a row missing player_key/full_name")
        projection.append([
            key,
            name,
            str(row.get("pos") or "").strip().upper() or None,
            str(row.get("team") or "").strip().upper() or None,
        ])
    projection.sort(key=lambda item: item[0])
    return projection


def projection_hash(projection: list[list[Any]]) -> str:
    canonical = json.dumps(projection, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def check(players_path: Path, manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        raise SystemExit(
            f"Missing naming manifest: {manifest_path}. "
            "Pin it with pipelines/pin_naming_manifest.py before running this check."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise SystemExit(f"{manifest_path} is not a {MANIFEST_SCHEMA} file")

    projection = identity_projection(players_path)
    actual_hash = projection_hash(projection)
    expected_hash = manifest.get("identity_hash")
    expected_rows = manifest.get("row_count")

    problems = []
    if actual_hash != expected_hash:
        problems.append(
            f"identity_hash mismatch: players.json computes {actual_hash[:12]}..., "
            f"manifest pins {str(expected_hash)[:12]}..."
        )
    if len(projection) != expected_rows:
        problems.append(f"row_count mismatch: players.json has {len(projection)}, manifest pins {expected_rows}")
    manifest_rows = manifest.get("rows", [])
    if [list(row) for row in manifest_rows] != projection:
        problems.append("identity projection rows differ from the manifest pin")

    if problems:
        raise SystemExit(
            "NAMING DRIFT DETECTED -- players.json identity fields diverge from the "
            f"pinned naming manifest ({manifest.get('exported_at')}, "
            f"source: {manifest.get('source_label')}):\n- " + "\n- ".join(problems)
            + "\nRe-pin from the Supabase players table with pipelines/pin_naming_manifest.py."
        )
    return {
        "status": "ok",
        "row_count": len(projection),
        "identity_hash": actual_hash,
        "exported_at": manifest.get("exported_at"),
        "source_label": manifest.get("source_label"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--players", type=Path, default=DEFAULT_PLAYERS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    result = check(args.players, args.manifest)
    print(
        f"Naming manifest OK: {result['row_count']} identity rows match the "
        f"{result['exported_at']} pin ({result['source_label']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
