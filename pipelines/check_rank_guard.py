#!/usr/bin/env python3
"""Rank guard (JEG-482): every published chart's Indexed order is its own order.

Indexed (methodology.md, The Three Views #3) is a published chart's native
values times one factor, so for every published chart x saved combo the
Indexed order must equal the native order: for every pair of players the
chart ranks strictly apart (native_a > native_b), Indexed must keep
indexed_a > indexed_b. An Indexed tie between two players the chart ranks
apart counts as an inversion too (a collapse loses the publisher's order).
Native ties have no order to keep and are skipped.

Writes a machine-readable result (schema rank-guard-v1) for the JEG-480
fidelity pulse and exits 1 on any inversion:

    python3 pipelines/check_rank_guard.py [--fixture PATH] [--out PATH] [--copy PATH ...]

Default --out output/rank-guard.json. `make sync` runs it on the fixture it
publishes and copies the result to dist/modules/rank-guard.json; the
comparison chain runs it after re-indexing the promoted fixture.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
OUT = REPO / "output" / "rank-guard.json"
SCHEMA = "rank-guard-v1"
PUBLISHED_SOURCES = ("fantasycalc", "usatoday", "fantasypros", "cbs")
MAX_EXAMPLES = 5


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def native_ranks(native: dict) -> dict:
    """{player: 1-based rank by native value, descending}; ties share the best
    rank (competition ranking), so two players the chart prices equally show
    the same number."""
    values = {k: v for k, v in ((k, _finite(v)) for k, v in native.items()) if v is not None}
    ordered = sorted(values, key=lambda k: (-values[k], str(k)))
    ranks, previous, rank = {}, None, 0
    for i, key in enumerate(ordered, start=1):
        if values[key] != previous:
            rank, previous = i, values[key]
        ranks[key] = rank
    return ranks


def count_inversions(native: dict, indexed: dict) -> dict:
    """Pairs the chart orders strictly whose Indexed order is not the same.

    Over the players both maps price with finite values. Returns {n, pairs,
    inversions, examples} where pairs counts the strictly ordered native pairs
    checked and examples lists the first few inversions by native rank."""
    keys = [k for k in indexed if k in native
            and _finite(native[k]) is not None and _finite(indexed[k]) is not None]
    nat = {k: _finite(native[k]) for k in keys}
    idx = {k: _finite(indexed[k]) for k in keys}
    ordered = sorted(keys, key=lambda k: (-nat[k], str(k)))
    ranks = native_ranks({k: nat[k] for k in keys})
    pairs = inversions = 0
    examples = []
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if nat[a] == nat[b]:
                continue
            pairs += 1
            if idx[a] > idx[b]:
                continue
            inversions += 1
            if len(examples) < MAX_EXAMPLES:
                examples.append({"higher": a, "native_rank": ranks[a], "native": nat[a], "indexed": idx[a],
                                 "lower": b, "lower_native_rank": ranks[b], "lower_native": nat[b],
                                 "lower_indexed": idx[b]})
    return {"n": len(keys), "pairs": pairs, "inversions": inversions, "examples": examples}


def check_fixture(doc: dict) -> dict:
    """The rank-guard-v1 result for every published chart x combo in doc."""
    checks = []
    for source in PUBLISHED_SOURCES:
        sdata = (doc.get("sources") or {}).get(source)
        if not isinstance(sdata, dict):
            continue
        for combo_name, combo in sorted((sdata.get("combos") or {}).items()):
            native = combo.get("native") or {}
            indexed = combo.get("reindexed") or {}
            if not native or not indexed:
                checks.append({"source": source, "combo": combo_name, "ok": True,
                               "skipped": "no native or Indexed values saved"})
                continue
            result = count_inversions(native, indexed)
            checks.append({"source": source, "combo": combo_name,
                           "ok": result["inversions"] == 0, **result})
    failed = [c for c in checks if not c["ok"]]
    return {
        "schema": SCHEMA,
        "rule": ("Indexed order equals native order for every published chart x combo "
                 "(zero inversions beyond exact native ties); JEG-482"),
        "status": "fail" if failed else "pass",
        "fixture_built_at": doc.get("built_at"),
        "totals": {"checks": len(checks), "failed": len(failed),
                   "inversions": sum(c.get("inversions", 0) for c in checks)},
        "checks": checks,
    }


def run(fixture: Path, out: Path | None, copies=()) -> dict:
    doc = json.loads(Path(fixture).read_text(encoding="utf-8"))
    result = check_fixture(doc)
    result["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result["fixture"] = str(Path(fixture).resolve().relative_to(REPO)) \
        if Path(fixture).resolve().is_relative_to(REPO) else str(fixture)
    text = json.dumps(result, indent=1) + "\n"
    for path in ([out] if out else []) + list(copies):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Published-chart rank guard (JEG-482).")
    ap.add_argument("--fixture", default=str(FIXTURE))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--copy", action="append", default=[], help="also write the result here")
    args = ap.parse_args(argv)
    result = run(Path(args.fixture), Path(args.out), args.copy)
    t = result["totals"]
    print(f"rank guard: {result['status']} -- {t['checks']} chart x combo checks, "
          f"{t['failed']} failed, {t['inversions']} inversions -> {args.out}")
    for check in result["checks"]:
        if not check["ok"]:
            print(f"  FAIL {check['source']}/{check['combo']}: {check['inversions']} inversions "
                  f"of {check['pairs']} pairs; first: {check['examples'][:1]}")
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
