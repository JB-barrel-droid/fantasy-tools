"""Compute and stamp immutable lineage blocks on derived sections.

JEG-132 R5a (writers): a derived section must record which raw input it was
built from so the sibling R5b checker can detect a derived section lagging
its input (live case 2026-10-02: CBS ROS table vintage 2026-10-02 vs
promoted CBS ROS section vintage 2026-09-30).

Schema (must remain stable for the sibling R5b checker; see
JEG-132-lineage-writers.md):

    lineage: {
        raw_vintage:         <content_vintage of the raw section, OR the
                              fallback vintage if content_vintage is absent>,
        raw_content_sha256:  <SHA-256 over the raw section's (player_key,
                              native, reindexed) triples, computed exactly
                              as `compute_raw_sha` below>,
        raw_built_at:        <built_at of the raw section>,
        vintage_source:      "content_vintage" | "legacy_fallback"
                              -- makes the fallback visible, never silent,
    }

Rules:
- Raw sections do NOT get a lineage block (they are inputs).
- The block is written at build time. Promote must preserve unknown keys
  (see promote_comparison_section.py; R4a does not drop lineage).
- The SHA-256 must be reproducible: any caller recomputing over the same
  triples must get the same hash byte-for-byte.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_raw_sha(
    triples: list[tuple[Any, Any, Any]],
) -> str:
    """SHA-256 over an ordered list of (player_key, native, reindexed) triples.

    Stable byte-for-byte: triples are sorted by player_key (int) before
    hashing, then serialized as compact JSON with sorted keys. Both the
    ordering and the JSON shape are part of the contract -- the writer and
    any future recomputer must use the same function.

    Args:
        triples: list of (player_key, native_value, reindexed_value) tuples.
            Values must be JSON-serializable (int / float / None / str).
            None is allowed (D2 gate may drop rows upstream).

    Returns:
        hex-encoded SHA-256 digest.
    """
    # Sort by player_key so insertion order doesn't change the hash.
    def sort_key(t):
        k = t[0]
        try:
            return (0, int(k))
        except (TypeError, ValueError):
            return (1, str(k))

    ordered = sorted(triples, key=sort_key)
    payload = json.dumps(
        [{"player_key": pk, "native": n, "reindexed": r}
         for (pk, n, r) in ordered],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def collect_fixture_section_triples(section: dict) -> list[tuple[Any, Any, Any]]:
    """Collect (player_key, native, reindexed) triples from a fixture section.

    Iterates every combo in the section, taking native and reindexed from
    that combo and the player_key from `combos[combo].player_keys` (numeric
    identity, not name strings -- matches build_*.py identity rules).

    Skips combos that lack player_keys (identity unknown) or native /
    reindexed. Skips entries where player_key is missing or non-numeric.
    """
    triples: list[tuple[Any, Any, Any]] = []
    combos = section.get("combos") or {}
    for combo in combos.values():
        if not isinstance(combo, dict):
            continue
        pkeys = combo.get("player_keys") or {}
        native = combo.get("native") or {}
        reindexed = combo.get("reindexed") or {}
        for slug, key in pkeys.items():
            try:
                kid = int(key)
            except (TypeError, ValueError):
                continue
            n = native.get(slug)
            r = reindexed.get(slug)
            triples.append((kid, n, r))
    return triples


def collect_leg_triples(leg: dict) -> list[tuple[Any, Any, Any]]:
    """Collect (player_key, native, reindexed) triples from a DDF leg.

    The leg has `values[]` rows with player_key, ppg (native), value
    (reindexed). Same triple contract as collect_fixture_section_triples.
    """
    triples: list[tuple[Any, Any, Any]] = []
    for row in (leg.get("values") or []):
        if not isinstance(row, dict):
            continue
        key = row.get("player_key")
        try:
            kid = int(key) if key is not None else None
        except (TypeError, ValueError):
            kid = None
        if kid is None:
            continue
        native = row.get("ppg")
        reindexed = row.get("value")
        triples.append((kid, native, reindexed))
    return triples


def collect_reference_triples(reference: dict) -> list[tuple[Any, Any, Any]]:
    """Collect (player_key, native, reindexed) triples from a source-reference.

    A reference artifact has `rows[]` with player_key, value (reindexed),
    native_value (native). Identity is numeric player_key.
    """
    triples: list[tuple[Any, Any, Any]] = []
    for row in (reference.get("rows") or []):
        if not isinstance(row, dict):
            continue
        key = row.get("player_key")
        try:
            kid = int(key) if key is not None else None
        except (TypeError, ValueError):
            kid = None
        if kid is None:
            continue
        # Prefer native_value (raw published); fall back to value.
        native = row.get("native_value", row.get("value"))
        reindexed = row.get("value")
        triples.append((kid, native, reindexed))
    return triples


def resolve_raw_vintage(
    *,
    content_vintage: Any = None,
    espn_snapshot: Any = None,
    vintage: Any = None,
    fetched_at: Any = None,
) -> tuple[Any, str]:
    """Resolve raw_vintage + vintage_source from the raw input's fields.

    R4a stamps `content_vintage` as the immutable source provenance.
    Older inputs may carry `espn_snapshot`, `vintage`, or `fetched_at` --
    those are flagged `legacy_fallback` so the dependence is visible.
    Returns (raw_vintage, vintage_source).
    """
    if content_vintage is not None:
        return content_vintage, "content_vintage"
    for field_value, field_name in (
        (espn_snapshot, "espn_snapshot"),
        (vintage, "vintage"),
        (fetched_at, "fetched_at"),
    ):
        if field_value is not None:
            return field_value, "legacy_fallback"
    # Last resort: no vintage available. Mark fallback so the checker can
    # see the gap rather than silently pass.
    return None, "legacy_fallback"


def build_lineage_block(
    *,
    triples: list[tuple[Any, Any, Any]],
    raw_vintage: Any,
    raw_built_at: Any,
    vintage_source: str,
) -> dict:
    """Assemble the immutable lineage dict from pre-resolved values.

    The caller resolves `raw_vintage` and `vintage_source` (via
    `resolve_raw_vintage`) and supplies the triples (via one of the
    collect_* helpers).
    """
    raw_content_sha256 = compute_raw_sha(triples)
    return {
        "raw_vintage": raw_vintage,
        "raw_content_sha256": raw_content_sha256,
        "raw_built_at": raw_built_at,
        "vintage_source": vintage_source,
    }