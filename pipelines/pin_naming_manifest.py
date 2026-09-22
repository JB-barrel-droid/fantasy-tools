#!/usr/bin/env python3
"""Pin the naming manifest from a players.json export.

The manifest records the identity projection (player_key, full_name, pos,
team) of a players.json that was exported from the Supabase ``players`` naming
table, plus a hash and the export timestamp. check_naming_drift.py fails
closed when a later players.json diverges from this pin.

Contract: run this atomically with every players.json rebuild, passing
--source-label "supabase:players" (or the exact export job id). The bootstrap
label is only for the first pin taken from an existing fixture; the next real
export must re-pin from the naming table.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from check_naming_drift import (
    DEFAULT_MANIFEST,
    DEFAULT_PLAYERS,
    MANIFEST_SCHEMA,
    identity_projection,
    projection_hash,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--players", type=Path, default=DEFAULT_PLAYERS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-label", required=True,
                        help='e.g. "supabase:players" or "bootstrap:players.json"')
    parser.add_argument("--exported-at", help="export timestamp; defaults to now (UTC)")
    args = parser.parse_args()

    projection = identity_projection(args.players)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "exported_at": args.exported_at or utc_now(),
        "source_label": args.source_label,
        "row_count": len(projection),
        "identity_hash": projection_hash(projection),
        "note": (
            "Pin of the Supabase players-table identity projection backing players.json. "
            "Re-pin atomically with every players.json rebuild (see docs/pipeline-rules.md)."
        ),
        "rows": projection,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"Pinned {manifest['row_count']} identity rows "
        f"(hash {manifest['identity_hash'][:12]}...) to {args.manifest}"
    )
    if args.source_label.startswith("bootstrap"):
        print("WARNING: bootstrap pin -- the next players.json rebuild must re-pin from supabase:players.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
