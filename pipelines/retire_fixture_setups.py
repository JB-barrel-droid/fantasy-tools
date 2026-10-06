#!/usr/bin/env python3
"""Retire league setups a source no longer saves (decision league-settings-001).

The backend saves one league setup (12 teams, 1 QB) per scoring format; other
team counts and rosters are derived in the browser. This removes a source's
other setups from the comparison fixture so the fixture never carries blocks
nothing refreshes any more (promotion merges per setup and stamps one week on
the whole source, so a stale 8-team block would otherwise be labelled with the
new week -- risk register GAP-PROMOTE-MIXED-VINTAGE).

It only deletes whole setup blocks. It never edits a value inside a kept
block. A rollback record (the removed blocks, before/after hashes) is written
to output/comparison-promotions/ like a promotion record.

Fail closed: refuses if a kept setup (e.g. full_12_qb1) is missing for a
source, so a typo can never empty a source.

Usage:
  python3 pipelines/retire_fixture_setups.py --source fantasycalc --source fantasycalc_adjusted \
      --keep-teams 12 --keep-qb 1 [--fixture PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
RECORD_DIR = REPO / "output" / "comparison-promotions"
SCORINGS = ("full", "half", "standard")
SETUP_RE = re.compile(r"^(full|half|standard)_(\d+)(?:_qb(\d))?$")


def sha256_canonical(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def keep(setup: str, teams: int, qb: int) -> bool:
    m = SETUP_RE.match(setup)
    if not m:
        return True  # unknown shape: never delete what we don't understand
    t, q = int(m.group(2)), m.group(3)
    return t == teams and (q is None or int(q) == qb)


def retire(fixture: dict, sources: list[str], teams: int, qb: int) -> dict:
    """Mutates fixture; returns {source: {removed_setup: block}}."""
    removed: dict[str, dict] = {}
    for src in sources:
        sec = fixture["sources"].get(src)
        if sec is None:
            raise SystemExit(f"refused: source {src!r} not in fixture")
        combos = sec.get("combos", {})
        kept = {k: v for k, v in combos.items() if keep(k, teams, qb)}
        missing = [s for s in SCORINGS
                   if not any(SETUP_RE.match(k) and SETUP_RE.match(k).group(1) == s for k in kept)]
        if missing:
            raise SystemExit(f"refused: {src} would keep no {teams}-team setup for {missing}")
        removed[src] = {k: v for k, v in combos.items() if k not in kept}
        sec["combos"] = kept
        sec["retired_setups"] = {
            "decision": "league-settings-001",
            "kept": f"{teams} teams, {qb} QB",
            "removed": sorted(removed[src]),
            "note": "Other team counts and rosters are derived in the browser; "
                    "these setups are no longer saved or refreshed.",
        }
    return removed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", action="append", required=True)
    ap.add_argument("--keep-teams", type=int, default=12)
    ap.add_argument("--keep-qb", type=int, default=1)
    ap.add_argument("--fixture", type=Path, default=FIXTURE)
    ap.add_argument("--record-dir", type=Path, default=RECORD_DIR)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    raw = args.fixture.read_text(encoding="utf-8")
    fixture = json.loads(raw)
    before = sha256_canonical(fixture)
    removed = retire(fixture, args.source, args.keep_teams, args.keep_qb)
    after = sha256_canonical(fixture)
    for src, blocks in removed.items():
        print(f"{src}: removing {len(blocks)} setups, keeping {sorted(fixture['sources'][src]['combos'])}")
    if args.dry_run:
        print("dry run: fixture not written")
        return 0
    # Preserve the file's own serialization (indent=2, trailing newline or not)
    # so the diff is only the removed blocks.
    tail = "\n" if raw.endswith("\n") else ""
    args.fixture.write_text(json.dumps(fixture, indent=2) + tail, encoding="utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    args.record_dir.mkdir(parents=True, exist_ok=True)
    record = args.record_dir / f"retire-setups-{'-'.join(args.source)}-{stamp}.json"
    record.write_text(json.dumps({
        "kind": "retire_setups", "decision": "league-settings-001", "at": stamp,
        "fixture": str(args.fixture.relative_to(REPO)) if args.fixture.is_relative_to(REPO) else str(args.fixture),
        "fixture_sha256_before": before, "fixture_sha256_after": after,
        "removed": removed,
    }, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {args.fixture}; rollback record {record}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
