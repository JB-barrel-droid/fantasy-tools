#!/usr/bin/env python3
"""JEG-362 (JEG-327 Phase C) — atomic publish gate orchestrator.

The bake pipeline runs this module to commit one coherent snapshot
atomically. Every gate must pass; if any fails, the entire transaction
rolls back, the candidate snapshot row stays at
``publishable=FALSE, is_active=FALSE``, and the prior known-good row
stays untouched. The FE reads ``api.product_snapshot`` (which filters
to ``is_active=TRUE AND publishable=TRUE``) and never sees the
failed row.

Gates (all run inside one transaction, see
``sql/contract/api_publish_gate.sql``):

  1. values reconciliation      — single-bake coherence OR every
                                  distinct bake declared in
                                  ``bake_ids.values_bakes[]``
  2. player joins               — every distinct player_key resolves
                                  in ``public.players``
  3. context valid + fresh      — news/adjustments rows link to a
                                  snapshot (no orphans); active snap
                                  has at least one context row
  4. selector / options coverage — every ``source_keys[]`` key has
                                  value rows and per-source meta
  5. source freshness rules     — tier_price_vintage == bake_id;
                                  every source's ``source_validation``
                                  equals ``'live'``

Usage (production, psycopg2 connection):

    from pipelines.publish_gate import PublishGate, PublishGateError

    gate = PublishGate(conn, contract_version="1.0.0")
    verdict = gate.run(candidate_snapshot_id, bake_ids={
        "primary": "2026-w04-bake-001",
        "values_bakes": ["2026-w04-bake-001"],
        "per_source": {...},
    })
    if not verdict.passed:
        gate.abort()  # explicit rollback (defensive; conn.rollback())
        raise PublishGateError(verdict)
    gate.commit_active_flip(candidate_snapshot_id)

Or, the convenience wrapper that does gate + flip + commit in one
transaction::

    gate.publish(candidate_snapshot_id, bake_ids)

The candidate row is inserted by the caller BEFORE
``gate.publish(...)`` is called; ``gate.publish`` is the atomic
commit step. Caller pattern::

    BEGIN;
        INSERT INTO public.product_snapshot
            (contract_version, generated_at, is_active, publishable,
             bake_ids, value_weeks, sources, source_validation,
             espn_zeroed, methodology_combos, reference_freshness,
             health, pie_vintage_per_source, players_snapshot_at,
             context_meta)
        VALUES (...) RETURNING snapshot_id;
        -- pass that snapshot_id into gate.publish(...)
        -- gate runs all five gates
        -- gate flips is_active on the candidate + sets publishable=TRUE
        -- gate flips is_active=FALSE on the prior active row
    COMMIT;  -- or ROLLBACK on gate failure

Non-goal: this module does NOT insert the candidate row (the bake
pipeline owns row assembly); it only validates and flips.

Testing: the module is connection-agnostic. Tests pass a fake
DB-API connection that records calls (see
``tests/test_publish_gate.py``). Live runs use psycopg2 against
Supabase.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


LOG = logging.getLogger("publish_gate")


class PublishGateError(Exception):
    """Raised when the publish gate refuses to flip the snapshot.

    The transaction is rolled back before this is raised; the prior
    known-good snapshot stays active. The exception's ``verdict``
    attribute carries the full gate result for the audit log.
    """

    def __init__(self, verdict: "PublishVerdict"):
        self.verdict = verdict
        first_fail = verdict.first_failure()
        msg = (
            f"publish gate refused: "
            f"{first_fail['gate']}: {first_fail.get('reason', '(no reason)')}"
            if first_fail
            else "publish gate refused (no detail)"
        )
        super().__init__(msg)


@dataclass
class GateResult:
    """One gate's verdict. Mirrors the JSONB shape returned by the SQL functions."""

    gate: str
    passed: bool
    details: Dict[str, Any] = field(default_factory=dict)

    def to_jsonb(self) -> str:
        return json.dumps(
            {"gate": self.gate, "passed": self.passed, **self.details},
            sort_keys=True,
        )

    @classmethod
    def from_jsonb(cls, payload: Any) -> Dict[str, Any]:
        """Coerce whatever the driver returned into a JSONB-shaped dict."""
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8")
        if isinstance(payload, str):
            return json.loads(payload)
        if isinstance(payload, dict):
            return payload
        raise TypeError(f"unexpected gate payload type: {type(payload).__name__}")


@dataclass
class PublishVerdict:
    """Aggregate verdict across all gates. One per ``PublishGate.run()`` call."""

    contract_version: str
    bake_ids: Dict[str, Any]
    gates: List[GateResult]
    raw: Dict[str, Any]

    @property
    def passed(self) -> bool:
        return bool(self.raw.get("passed"))

    def first_failure(self) -> Optional[Dict[str, Any]]:
        for g in self.raw.get("gates", []):
            if not g.get("passed"):
                return g
        return None

    def failed_gates(self) -> List[Dict[str, Any]]:
        return [g for g in self.raw.get("gates", []) if not g.get("passed")]

    def gate_log(self) -> Dict[str, Any]:
        """Compact log payload (suitable for ``context_meta.gate_log``)."""
        return {
            "passed": self.passed,
            "gates": [
                {"gate": g.gate, "passed": g.passed, **g.details}
                for g in self.gates
            ],
        }


class PublishGate:
    """Atomic snapshot/publish gate orchestrator.

    All SQL is run on the caller's ``conn``. The caller owns
    transaction boundaries (``BEGIN`` / ``COMMIT`` / ``ROLLBACK``) — this
    class issues ``SELECT api.run_publish_gate(...)`` and the
    active-flip ``UPDATE`` statements, but the caller wraps them in
    a transaction. ``PublishGate.publish(...)`` is the convenience
    wrapper that does BEGIN + gate + flip + COMMIT.

    The class is connection-agnostic: anything with a DB-API 2.0
    ``cursor()`` and ``commit()`` / ``rollback()`` works (psycopg2,
    psycopg, the Supabase sbclient cursor wrapper, or a test fake).
    """

    # SQL constants. The gate functions live in
    # sql/contract/api_publish_gate.sql (Roman applies them; this
    # module does not CREATE FUNCTION — the SQL file is the
    # authoritative source).
    _SQL_RUN_GATE = (
        "SELECT api.run_publish_gate(%s, %s::jsonb)"
    )
    _SQL_DEACTIVATE_PRIOR_ACTIVE = (
        "UPDATE public.product_snapshot "
        "   SET is_active = FALSE "
        " WHERE contract_version = %s "
        "   AND is_active = TRUE "
        "   AND publishable = TRUE "
        "   AND snapshot_id <> %s"
    )
    _SQL_ACTIVATE_CANDIDATE = (
        "UPDATE public.product_snapshot "
        "   SET is_active = TRUE, "
        "       publishable = TRUE, "
        "       built_at = COALESCE(built_at, NOW()) "
        " WHERE snapshot_id = %s "
        "   AND contract_version = %s"
    )

    def __init__(self, conn: Any, contract_version: str):
        self.conn = conn
        self.contract_version = contract_version

    # -- public API ------------------------------------------------

    def run(
        self,
        candidate_snapshot_id: Optional[str] = None,
        bake_ids: Optional[Dict[str, Any]] = None,
    ) -> PublishVerdict:
        """Run every gate inside the caller's open transaction.

        Does NOT flip ``is_active``; the caller calls
        ``commit_active_flip(...)`` after this returns a passed
        verdict.

        ``candidate_snapshot_id`` is currently informational only —
        the gate functions operate on the contract_version / per-source
        data, not the candidate row. The field exists so the audit
        log can correlate the gate run with the candidate row.
        """
        bake_ids = bake_ids or {}
        with self.conn.cursor() as cur:
            cur.execute(
                self._SQL_RUN_GATE,
                (self.contract_version, json.dumps(bake_ids, sort_keys=True)),
            )
            row = cur.fetchone()
        if row is None or row[0] is None:
            raise PublishGateError(
                PublishVerdict(
                    contract_version=self.contract_version,
                    bake_ids=bake_ids,
                    gates=[],
                    raw={"passed": False, "gates": [], "reason": "no gate row returned"},
                )
            )

        raw = GateResult.from_jsonb(row[0])
        gates = [
            GateResult(
                gate=str(g.get("gate", "?")),
                passed=bool(g.get("passed")),
                details={
                    k: v
                    for k, v in g.items()
                    if k not in ("gate", "passed")
                },
            )
            for g in raw.get("gates", [])
        ]
        verdict = PublishVerdict(
            contract_version=self.contract_version,
            bake_ids=bake_ids,
            gates=gates,
            raw=raw,
        )
        if not verdict.passed:
            LOG.warning(
                "publish gate FAILED contract=%s failed=%s",
                self.contract_version,
                [g["gate"] for g in verdict.failed_gates()],
            )
        else:
            LOG.info(
                "publish gate PASSED contract=%s gates=%d",
                self.contract_version,
                len(gates),
            )
        return verdict

    def commit_active_flip(self, candidate_snapshot_id: str) -> None:
        """Flip the prior active row to is_active=FALSE and the
        candidate to is_active=TRUE, publishable=TRUE. Must be
        called inside the same transaction as ``run(...)`` and only
        when the verdict passed.

        The partial unique index ``product_snapshot_active_uidx``
        (one active row per contract_version) makes the second
        UPDATE fail with ``UniqueViolation`` if the first UPDATE
        somehow misses the prior active row. The class catches and
        re-raises as ``PublishGateError`` so the caller can roll back
        cleanly.
        """
        try:
            with self.conn.cursor() as cur:
                # Order matters: deactivate, then activate. If activate
                # fails the unique constraint, the deactivate stays
                # in place inside this transaction and the caller
                # rolls back.
                cur.execute(
                    self._SQL_DEACTIVATE_PRIOR_ACTIVE,
                    (self.contract_version, candidate_snapshot_id),
                )
                cur.execute(
                    self._SQL_ACTIVATE_CANDIDATE,
                    (candidate_snapshot_id, self.contract_version),
                )
        except Exception as exc:  # UniqueViolation or driver-specific
            type_name = type(exc).__name__
            if "UniqueViolation" in type_name or "unique constraint" in str(exc).lower():
                raise PublishGateError(
                    PublishVerdict(
                        contract_version=self.contract_version,
                        bake_ids={},
                        gates=[],
                        raw={
                            "passed": False,
                            "gates": [
                                {
                                    "gate": "active_flip",
                                    "passed": False,
                                    "reason": "partial unique index violation",
                                },
                            ],
                        },
                    )
                ) from exc
            raise

    def abort(self) -> None:
        """Roll back the caller's transaction. Defensive: callers
        should ``conn.rollback()`` directly; this is a convenience for
        symmetry with ``publish(...)`` below.
        """
        self.conn.rollback()

    def publish(
        self,
        candidate_snapshot_id: str,
        bake_ids: Optional[Dict[str, Any]] = None,
    ) -> PublishVerdict:
        """Convenience: ``BEGIN`` + ``run(...)`` + ``commit_active_flip(...)`` + ``COMMIT``.

        Raises ``PublishGateError`` (and rolls back) if any gate
        fails or the active flip violates the partial unique index.
        On success, returns the passed verdict. Caller pattern::

            gate = PublishGate(conn, contract_version="1.0.0")
            verdict = gate.publish(candidate_id, bake_ids={...})
            # verdict.passed = True; commit is done
        """
        # psycopg2 / psycopg implicitly BEGIN on first execute
        # when the connection is in autocommit=False mode (the
        # default). For drivers that do not, the caller must BEGIN
        # before calling. We document this in the docstring.
        try:
            verdict = self.run(candidate_snapshot_id, bake_ids)
        except PublishGateError:
            self.conn.rollback()
            raise
        if not verdict.passed:
            self.conn.rollback()
            raise PublishGateError(verdict)
        try:
            self.commit_active_flip(candidate_snapshot_id)
        except PublishGateError:
            self.conn.rollback()
            raise
        self.conn.commit()
        return verdict


# ---------------------------------------------------------------------------
# Module-level helpers used by the bake pipeline
# ---------------------------------------------------------------------------


def gate_log_for_context_meta(verdict: PublishVerdict) -> Dict[str, Any]:
    """Format the gate log for inclusion in ``product_snapshot.context_meta.gate_log``.

    The bake writes this into the candidate row's context_meta so the
    JEG-322 health surface and the audit log can read the gate verdict
    without re-running. Shape::

        {
            "passed": bool,
            "ran_at": iso8601 timestamp,
            "gates": [
                {"gate": "values_reconciliation", "passed": bool, ...},
                ...
            ]
        }
    """
    import datetime as _dt
    return {
        "ran_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        **verdict.gate_log(),
    }


def expected_gate_names() -> Sequence[str]:
    """The five gate names in the order the orchestrator runs them.

    Useful for tests and for the audit log: "the gate failed at gate
    #3" reads better as "context_valid_fresh" than as a SQL index.
    """
    return (
        "values_reconciliation",
        "player_joins",
        "context_valid_fresh",
        "options_coverage",
        "source_freshness",
    )