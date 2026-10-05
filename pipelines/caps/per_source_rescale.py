"""Per-source 70-cap rescale pipeline stage.

Adapts the design doc (lanes/outbox/minimax/rescale-pipeline-integration.md)
from DataFrame-based signatures to row-dict signatures (the loader is
stdlib-only -- NO pandas). The contracts are preserved:

    compute_rescale_factors(rows)                       -> {source: {"pre_max", "scale_factor"}}
    apply_per_source_cap(rows, factors, cap=CAP)        -> NEW row list (input untouched)
    preflight_validate_cap(rows, cap=CAP, eps=EPS)       -> raises RescaleError on violation
    build_rescale_audit(factors, rows_before, rows_after, run_context)
                                                        -> list[dict] (per scaled source + SUMMARY)
    emit_artifact_rescale_audit(entries, path)          -> writes JSON artifact; raises on failure
    insert_rescale_audit(sb, entries)                   -> inserts into per_source_cap_audit

Each combo row looks like::

    {"source": <source>, "view": "combo_reindexed", "value": <float>, ...}

Only rows with ``view == "combo_reindexed"`` participate. Rows with other
views (e.g. ``vorp_indexed``) are passed through untouched. NaNs are
excluded from the per-source max and are never introduced by scaling; if
any non-finite value is present after rescale, preflight fails closed.

Edge cases (per design doc §6):
- ``pre_max <= 0``  -> factor = 1.0 (no rescale, no division by zero)
- NaN values       -> excluded from max; never introduced by scaling
- Float residue    -> ALWAYS clamp via ``min(cap, v * factor)`` so a
  scaled value of 70.0000000003 becomes exactly 70.0
- factor           ->  min(1.0, cap / pre_max)

The cap default is 70 (matches the ``ck_combo_reindexed_cap`` DB CHECK
constraint and the ``scale_70_over_max`` invariant baked into every
properly indexed DDF leg).
"""

from __future__ import annotations

import json
import math
import os
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

# Cap value column (the loader views combo_reindexed under this column name).
# Mirrors consolidated_values.value when view = "combo_reindexed".
CAP = 70.0

# Validation tolerance for the post-rescale max check.
EPS = 1e-9

# What makes a brief overshoot trigger the audit. We treat any factor strictly
# less than 1.0 - SCALE_AUDIT_EPS as a real rescale (small underflow from
# 1.0/1.0 should not spam the audit table).
SCALE_AUDIT_EPS = 1e-12


class RescaleError(Exception):
    """Raised by the per-source rescale pipeline stage.

    The loader maps this to its own ``LoadError`` so the failure surface is
    uniform with the rest of the load path.
    """


# ---------------------------------------------------------------------------
# Small numeric helpers
# ---------------------------------------------------------------------------
def _is_finite(v: Any) -> bool:
    """True iff v is a finite real number (not NaN / +/-Inf / non-numeric)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f)


def _finite_combo_indices_and_values(
    rows: Sequence[Mapping[str, Any]],
) -> List[tuple]:
    """Yield (index_in_rows, source, float_value) for combo_reindexed rows
    whose value is finite. NaN / Inf / non-numeric are excluded from the
    pre_max calculation but stay in the row list (preflight catches them)."""
    out = []
    for i, r in enumerate(rows):
        if r.get("view") != "combo_reindexed":
            continue
        v = r.get("value")
        if _is_finite(v):
            out.append((i, r.get("source"), float(v)))
    return out


def _per_source_max(rows: Sequence[Mapping[str, Any]]) -> Dict[str, float]:
    """Per-source max of combo_reindexed values, NaNs excluded."""
    pre_max: Dict[str, float] = {}
    for _i, src, fv in _finite_combo_indices_and_values(rows):
        if src is None:
            continue
        prev = pre_max.get(src, -math.inf)
        if fv > prev:
            pre_max[src] = fv
    return pre_max


def _per_source_row_count(rows: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    """Per-source count of combo_reindexed rows (including NaN rows; we count
    rows, not just finite values)."""
    counts: Dict[str, int] = {}
    for r in rows:
        if r.get("view") == "combo_reindexed":
            src = r.get("source")
            if src is not None:
                counts[src] = counts.get(src, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# compute_rescale_factors
# ---------------------------------------------------------------------------
def compute_rescale_factors(
    rows: Sequence[Mapping[str, Any]],
    cap: float = CAP,
) -> Dict[str, Dict[str, float]]:
    """Compute per-source rescale factors.

    Returns ``{source: {"pre_max": float, "scale_factor": float}}``.

    Rules:
    - ``pre_max <= 0``  -> factor = 1.0 (no rescale; do not divide by zero;
      do not amplify a negative series).
    - ``pre_max > 0``   -> factor = ``min(1.0, cap / pre_max)``.
    - NaNs in source values are excluded from the max.
    - Sources with no finite combo_reindexed rows are absent from the result.

    The cap default is module-level CAP (=70); ``cap`` is exposed so tests
    can exercise the same function with smaller caps without monkeypatching.
    The brief lists the signature as ``compute_rescale_factors(rows)``;
    ``cap`` is a kwarg and defaults to CAP so the contract is preserved.
    """
    pre_max = _per_source_max(rows)
    factors: Dict[str, Dict[str, float]] = {}
    for src, pm in pre_max.items():
        if pm <= 0:
            factor = 1.0
        else:
            factor = min(1.0, cap / pm)
        factors[src] = {"pre_max": pm, "scale_factor": factor}
    return factors


# ---------------------------------------------------------------------------
# apply_per_source_cap
# ---------------------------------------------------------------------------
def apply_per_source_cap(
    rows: Sequence[Mapping[str, Any]],
    factors: Mapping[str, Mapping[str, float]],
    cap: float = CAP,
) -> List[Dict[str, Any]]:
    """Return a NEW list of rows with combo_reindexed values rescaled per source.

    - Does NOT mutate the input rows.
    - Only rows with ``view == "combo_reindexed"`` are rescaled.
    - ``new_v = min(cap, v * factor)`` per source -- the clamp is mandatory to
      defeat float residue so a scaled value of 70.0000000003 becomes 70.0.
    - Non-finite values (NaN / Inf) are passed through unchanged; preflight
      will reject them rather than silently coercing.
    - Rows whose source is not in ``factors`` are passed through unchanged
      (a row with view != combo_reindexed, or a combo row from a source with
      no finite values to factor from -- extremely unusual but defined).
    - Non-combo rows are passed through unchanged.
    """
    out: List[Dict[str, Any]] = []
    for r in rows:
        if r.get("view") == "combo_reindexed":
            src = r.get("source")
            v = r.get("value")
            factor_info = factors.get(src) if src is not None else None
            if factor_info is not None and _is_finite(v):
                scaled = float(v) * float(factor_info["scale_factor"])
                new_v = min(cap, scaled)
                new_row = dict(r)
                new_row["value"] = new_v
                out.append(new_row)
            else:
                # No factor for this source, or non-finite value: pass through.
                # preflight will reject non-finite values; rows without a
                # factor simply have nothing to scale against (treated as
                # out-of-band; the rescale is a no-op for them).
                out.append(dict(r))
        else:
            out.append(dict(r))
    return out


# ---------------------------------------------------------------------------
# preflight_validate_cap
# ---------------------------------------------------------------------------
def preflight_validate_cap(
    rows: Sequence[Mapping[str, Any]],
    cap: float = CAP,
    eps: float = EPS,
) -> None:
    """Fail closed if any combo_reindexed value violates the post-rescale contract.

    Checks per combo_reindexed row:
    - value must be finite (NaN/Inf rejected).
    - value must be >= 0 (negative combo_reindexed rejected -- the leg is
      malformed or upstream rescale was skipped).
    - value must be <= ``cap + eps`` (over-cap rejected; should be impossible
      after apply_per_source_cap with clamp, but the DB CHECK is not the
      only thing standing between us and a corrupt load).

    On any violation, raises ``RescaleError`` whose message lists the first
    10 offenders (row index, source, kind, value). The caller should map
    this to ``LoadError`` so the load exits cleanly.
    """
    violations = []
    for i, r in enumerate(rows):
        if r.get("view") != "combo_reindexed":
            continue
        v = r.get("value")
        if not _is_finite(v):
            violations.append((i, r.get("source"), "non_finite", v))
            continue
        fv = float(v)
        if fv < 0:
            violations.append((i, r.get("source"), "negative", fv))
            continue
        if fv > cap + eps:
            violations.append((i, r.get("source"), "above_cap", fv))
    if violations:
        msgs = []
        for idx, src, kind, val in violations[:10]:
            try:
                val_repr = f"{float(val):.6f}"
            except (TypeError, ValueError):
                val_repr = repr(val)
            msgs.append(f"row={idx} source={src} kind={kind} value={val_repr}")
        raise RescaleError(
            f"preflight failed: {len(violations)} violation(s); "
            f"cap={cap} eps={eps}; first {len(msgs)}: {msgs}"
        )


# ---------------------------------------------------------------------------
# build_rescale_audit
# ---------------------------------------------------------------------------
def _scaled_sources(
    factors: Mapping[str, Mapping[str, float]],
    eps: float = SCALE_AUDIT_EPS,
) -> List[tuple]:
    """List ``(source, factor_info)`` for sources whose factor < 1.0 - eps."""
    out = []
    for src, info in factors.items():
        sf = float(info.get("scale_factor", 1.0))
        if sf < 1.0 - eps:
            out.append((src, info))
    return out


def _post_max(rows: Sequence[Mapping[str, Any]]) -> Dict[str, float]:
    """Per-source max of combo_reindexed values, NaNs excluded.

    Used by build_rescale_audit so the post_max reported is the value the
    audit entry actually corresponds to, not a re-computed approximation.
    """
    return _per_source_max(rows)


def _git_commit_sha(repo_root: Optional[Path] = None) -> Optional[str]:
    """Best-effort git commit SHA. Returns None on any failure (not in a git
    repo, git missing, network issues) -- the audit is informational, not
    a gate, so we never fail-closed here."""
    candidates = []
    if repo_root is not None:
        candidates.append(repo_root)
    candidates.append(Path(__file__).resolve().parents[2])  # repo root from pipelines/caps/
    for root in candidates:
        try:
            out = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            continue
    return None


def _loader_host() -> Optional[str]:
    try:
        return socket.gethostname()
    except OSError:
        return None


def build_rescale_audit(
    factors: Mapping[str, Mapping[str, float]],
    rows_before: Sequence[Mapping[str, Any]],
    rows_after: Sequence[Mapping[str, Any]],
    run_context: Optional[Mapping[str, Any]] = None,
    cap: float = CAP,
) -> List[Dict[str, Any]]:
    """Build audit entries: one dict per scaled source + one SUMMARY dict.

    ``run_context`` is optional but recommended. Recognized keys:
    ``run_id``, ``ddf_leg_version``, ``git_commit_sha``, ``loader_host``,
    ``built_at``. Missing keys become None in the audit entries; the SUMMARY
    entry is always emitted (even when there are no scaled sources -- the
    presence of the SUMMARY is the versioned evidence that the loader ran
    the rescale stage at all).

    Per-source entries are emitted only when ``scale_factor < 1.0 - eps``;
    the SUMMARY tracks ``sources_scaled`` and ``sources_total`` so an empty
    run is still auditable.
    """
    ctx = dict(run_context or {})
    pre_max_map = _per_source_max(rows_before)
    post_max_map = _post_max(rows_after)
    row_counts = _per_source_row_count(rows_after)

    scaled = _scaled_sources(factors)
    sources_total = len({
        r.get("source") for r in rows_after
        if r.get("view") == "combo_reindexed" and r.get("source") is not None
    })

    entries: List[Dict[str, Any]] = []
    for src, info in scaled:
        entries.append({
            "kind": "per_source",
            "source": src,
            "value_column": "combo_reindexed",
            "cap": float(cap),
            "pre_max": float(info["pre_max"]),
            "post_max": float(post_max_map.get(src, info["pre_max"])),
            "scale_factor": float(info["scale_factor"]),
            "source_row_count": int(row_counts.get(src, 0)),
            "run_id": ctx.get("run_id"),
            "ddf_leg_version": ctx.get("ddf_leg_version"),
            "git_commit_sha": ctx.get("git_commit_sha"),
            "loader_host": ctx.get("loader_host"),
            "built_at": ctx.get("built_at"),
        })

    summary = {
        "kind": "summary",
        "source": "__SUMMARY__",
        "value_column": "combo_reindexed",
        "cap": float(cap),
        "sources_scaled": len(scaled),
        "sources_total": sources_total,
        "run_id": ctx.get("run_id"),
        "ddf_leg_version": ctx.get("ddf_leg_version"),
        "git_commit_sha": ctx.get("git_commit_sha"),
        "loader_host": ctx.get("loader_host"),
        "built_at": ctx.get("built_at"),
    }
    entries.append(summary)
    return entries


# ---------------------------------------------------------------------------
# emit_artifact_rescale_audit
# ---------------------------------------------------------------------------
def emit_artifact_rescale_audit(
    entries: Sequence[Mapping[str, Any]],
    path: os.PathLike,
) -> Path:
    """Write the rescale audit entries to a versioned JSON artifact.

    The write is fail-closed: any I/O failure (parent dir creation, write,
    rename) raises ``RescaleError``. The loader aborts before any DB I/O
    when this raises, so a run is never published without its audit
    artifact in place.

    The artifact schema is ``rescale-audit-v1``; the file shape is::

        {
          "schema": "rescale-audit-v1",
          "entries": [ ... per_source + summary ... ]
        }

    Atomic write: write to a temp file in the same directory then rename,
    so a partial artifact cannot be observed by a subsequent read.
    """
    p = Path(path)
    payload = {
        "schema": "rescale-audit-v1",
        "entries": [dict(e) for e in entries],
    }
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise RescaleError(
            f"failed to create artifact directory {p.parent}: {e}"
        ) from e
    try:
        # Use a temp file in the same directory so os.replace is atomic.
        fd, tmp_name = tempfile.mkstemp(
            prefix=p.name + ".", suffix=".tmp", dir=str(p.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
                fh.write("\n")
            os.replace(tmp_name, p)
        except Exception:
            # Best-effort cleanup of the orphan temp file.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except RescaleError:
        raise
    except Exception as e:
        raise RescaleError(
            f"failed to write rescale audit artifact at {p}: {e}"
        ) from e
    return p


# ---------------------------------------------------------------------------
# insert_rescale_audit (DB write, gated behind PER_SOURCE_CAP_DB_AUDIT)
# ---------------------------------------------------------------------------
def insert_rescale_audit(
    sb: Any,
    entries: Sequence[Mapping[str, Any]],
    table: str = "per_source_cap_audit",
) -> int:
    """Insert per-source audit rows into the Supabase ``per_source_cap_audit``
    table. The single SUMMARY entry is also inserted -- the DB row count
    is expected to equal ``len(entries)`` (one row per entry, including
    SUMMARY).

    The caller is responsible for the ``PER_SOURCE_CAP_DB_AUDIT`` flag --
    this function does not consult it. When the flag is on, the caller
    must also verify the inserted row count matches ``len(entries)`` and
    abort the load on mismatch.

    Raises ``RescaleError`` if the underlying PostgREST call fails.
    """
    body = [dict(e) for e in entries]
    try:
        result = sb.post(table, body, prefer="return=representation")
    except Exception as e:
        raise RescaleError(
            f"per_source_cap_audit insert failed: {e}"
        ) from e
    if isinstance(result, list):
        return len(result)
    # Some clients return a single dict for single-row inserts; map to 1.
    if isinstance(result, dict):
        return 1
    return 0


# ---------------------------------------------------------------------------
# register_loader_run (DB write, gated behind PER_SOURCE_CAP_DB_AUDIT)
# ---------------------------------------------------------------------------
def register_loader_run(
    sb: Any,
    run_context: Mapping[str, Any],
    table: str = "loader_runs",
) -> str:
    """Register this loader execution in ``public.loader_runs``.

    JEG-389: ``loader_runs`` is the canonical owner of
    ``per_source_cap_audit.run_id`` (NOT fidelity_runs — the JEG-375
    fidelity suite's dimension is semantically unrelated). The FK
    ``fk_per_source_cap_audit_run_id`` requires the run row to exist
    before any audit row is inserted, so the loader must call this
    BEFORE :func:`insert_rescale_audit`.

    The insert is idempotent on ``run_id`` (merge-duplicates) so a
    retried registration with an explicit run_id does not fail.

    Returns the registered run_id. Raises :class:`RescaleError` on
    failure — the caller must abort the load (fail closed).
    """
    run_id = run_context.get("run_id")
    if not run_id:
        raise RescaleError("register_loader_run: run_context has no run_id")
    body = {
        "run_id": run_id,
        "ddf_leg_version": run_context.get("ddf_leg_version"),
        "git_commit_sha": run_context.get("git_commit_sha"),
        "loader_host": run_context.get("loader_host"),
    }
    try:
        sb.post(
            table,
            body,
            params="?on_conflict=run_id",
            prefer="resolution=merge-duplicates",
        )
    except Exception as e:
        raise RescaleError(f"loader_runs registration failed: {e}") from e
    return run_id


# ---------------------------------------------------------------------------
# Convenience: build a run_context dict for the loader.
# ---------------------------------------------------------------------------
def build_run_context(
    run_id: Optional[str] = None,
    ddf_leg_version: Optional[str] = None,
    git_commit_sha: Optional[str] = None,
    loader_host: Optional[str] = None,
    built_at: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build the run_context mapping consumed by ``build_rescale_audit``.

    Any field left None is filled by best-effort defaults (uuid4 for run_id,
    ``socket.gethostname()`` for loader_host, ISO 8601 UTC for built_at, and
    ``git rev-parse HEAD`` for git_commit_sha). Callers can pass explicit
    values to override.
    """
    import datetime as _dt
    import uuid as _uuid

    return {
        "run_id": run_id or str(_uuid.uuid4()),
        "ddf_leg_version": ddf_leg_version,
        "git_commit_sha": git_commit_sha if git_commit_sha is not None else _git_commit_sha(repo_root),
        "loader_host": loader_host if loader_host is not None else _loader_host(),
        "built_at": built_at or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }