"""Caps package: per-source cap enforcement for DDF leg loads.

The 2026-10-04 CBS ROS incident (combo_reindexed max hit 97.3, fixed ad-hoc
in Supabase rather than versioned) is the bug class this package prevents.
Every per-source cap that lands in ``consolidated_values.combo_reindexed``
must come from this pipeline stage or its successors; a future ingest cannot
write combo_reindexed > CAP into the table.

The rescale is deterministic, fail-closed, and idempotent:
- factor = min(1.0, CAP/pre_max) for every source with pre_max > 0
- factor = 1.0 for sources with pre_max <= 0 (no rescale, no div-by-zero)
- scaled = min(CAP, value * factor) to defeat float residue
- preflight refuses any post-rescale value > CAP + EPS or any non-finite value
- artifact write is mandatory and fail-closed; load aborts before any DB I/O
  if the JSON artifact cannot be written
"""

from .per_source_rescale import (  # noqa: F401
    CAP as DEFAULT_CAP,
    EPS as DEFAULT_EPS,
    RescaleError,
    compute_rescale_factors,
    apply_per_source_cap,
    preflight_validate_cap,
    build_rescale_audit,
    emit_artifact_rescale_audit,
    insert_rescale_audit,
)