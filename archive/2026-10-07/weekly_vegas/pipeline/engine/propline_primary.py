"""PropLine-primary Vegas leg merge (2026-09-18).

Priority: ("propline", "odds_api", "fds").

- PropLine is the PRIMARY raw-price leg: every player with PropLine
  prop coverage gets Vegas fantasy points translated LOCALLY from the
  PropLine cache via engine.vegas (never a vendor's blended number).
- FDS is the FALLBACK: players without PropLine coverage (props not
  posted yet) get the FDS-primary treatment — fantasy points recomputed
  locally from vegas-attributed translated stats only, labeled
  'fds-derived'/'fds-partial', Sunday-only, with per-stat provenance.
- The Odds API is the AUDIT leg: where the selective Odds-API pull has
  publishable raw-book coverage that disagrees materially with the
  PropLine number, the disagreement is recorded as a QA finding
  (PropLine wins; the audit is disclosure, not an override).

Returns (vegas_by_pos, extra, propline_keys, fds_keys, local_keys, audit).
"""
from collections import defaultdict

from .fds_fallback import (
    merge_fds_primary,
    apply_local_audit,
    FDS_PROVENANCE,
    FDS_PARTIAL,
)
from .source_priority import check_priority, VEGAS_SOURCE_PRIORITY


def check_propline_primary(priority):
    """Fail-closed: the PropLine-primary merge only runs under the
    ("propline", "odds_api", "fds") priority."""
    tup = check_priority(priority)
    if tup != ("propline", "odds_api", "fds"):
        raise NotImplementedError(
            f"PropLine-primary merge requires "
            f"('propline', 'odds_api', 'fds'), got {tup!r}.")
    return tup


def build_propline_primary(propline_by_pos, propline_extra, fds_index,
                           local_by_pos, local_extra, pos_of,
                           priority=VEGAS_SOURCE_PRIORITY,
                           sunday_only=True, now=None):
    """PropLine-primary entry point.

    propline_by_pos: {pos: {key: {"std","half","ppr"}}} from PropLine.
    propline_extra: {key: {..., "vegas_leg": "propline", ...}}.
    fds_index: FDS payload index (fallback for PropLine gaps).
    local_by_pos/local_extra: Odds-API audit leg.
    pos_of: key -> pos lookup.

    FDS fills ONLY keys PropLine missed (never overrides a PropLine
    number). The Odds-API audit runs over the merged build and records
    material disagreements as QA findings.
    """
    check_propline_primary(priority)
    vegas_by_pos = defaultdict(dict)
    extra = {}
    # 1. PropLine primary: copy the translated numbers in.
    for pos, d in (propline_by_pos or {}).items():
        for k, pts in d.items():
            vegas_by_pos[pos][k] = dict(pts)
    for k, e in (propline_extra or {}).items():
        extra[k] = dict(e)
        extra[k]["vegas_leg"] = "propline"
    propline_keys = {k for d in vegas_by_pos.values() for k in d}

    # 2. FDS fallback: only keys PropLine missed. Filter the index
    # BEFORE the merge — merge_fds_primary overwrites unconditionally,
    # so PropLine keys must never reach it.
    fds_fallback_index = {
        k: rec for k, rec in (fds_index or {}).items()
        if k not in propline_keys}
    fds_counts, fds_keys = merge_fds_primary(
        vegas_by_pos, extra, fds_fallback_index, pos_of,
        priority=("fds", "local"), sunday_only=sunday_only, now=now)

    # 3. Odds-API audit leg: material disagreements recorded, PropLine
    # wins. apply_local_audit expects the FDS key set to distinguish
    # audit overrides; here the "primary" is PropLine, so pass the
    # propline keys as the protected set.
    disagreements, audit_counts = apply_local_audit(
        vegas_by_pos, extra, local_by_pos, local_extra,
        propline_keys, priority=("fds", "local"))
    local_keys = {k for d in (local_by_pos or {}).values() for k in d}
    audit = {"disagreements": disagreements,
             "counts": audit_counts,
             "fds_counts": fds_counts,
             "propline_keys": sorted(propline_keys)}
    return vegas_by_pos, extra, propline_keys, fds_keys, local_keys, audit
