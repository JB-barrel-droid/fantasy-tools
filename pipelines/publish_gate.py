#!/usr/bin/env python3
"""JEG-362 (JEG-327 Phase C) — atomic publish gate orchestrator.

The bake pipeline runs this module to commit one coherent snapshot
atomically. Every gate must pass; if any fails, the entire transaction
rolls back, the candidate snapshot row stays at
``publishable=FALSE, is_active=FALSE``, and the prior known-good row
stays untouched. The FE reads ``api.product_snapshot`` (which filters
to ``is_active=TRUE AND publishable=TRUE``) and never sees the
failed row.

Gates (all run inside one transaction; JEG-376 bake-scoped gates —
see ``lanes/work/jeg376-gates/gates-bake-scoped.sql``, the authoritative
source; ``sql/contract/api_publish_gate.sql`` is a stale draft). The
orchestrator fans the bake-scoped gates out once per bake UUID in
``bake_ids.values_bake_uuids``:

  Bake-scoped (one run per bake UUID):
  1. values_reconciliation      — the bake has >=1 row in
                                  ``public.consolidated_values``
  2. player_joins               — every distinct player_key resolves
                                  in ``public.players``
  4. options_coverage           — selector/options coverage for the bake
  6. view_coverage              — the bake has >=1 combo_reindexed row

  Snapshot-scoped (run once):
  3. context_valid_fresh        — news/adjustments rows link to a
                                  snapshot (no orphans — orphans fail);
                                  empty context for the candidate is a
                                  WARNING (Jeremy 2026-10-04), not a
                                  failure
  5. source_freshness           — freshness computed from
                                  ``public.bakes`` + ``source_config``;
                                  stale does not fail — FE degrades
                                  per-source (Jeremy 2026-10-04)

  Synthetic (emitted ONLY on failure):
     bake_set_coverage          — every declared row-bearing source key
                                  is represented by a bake in the
                                  candidate set (pure-VORP keys excluded;
                                  ``cbs_adjusted`` may ride on ``cbs``)

PIPELINE CONTRACT (JEG-376): ``bake_ids`` MUST include
``values_bake_uuids`` — a JSON array of the per-source bake UUID
strings just loaded (``public.bakes.bake_id``). The orchestrator
validates every entry as a UUID and fails closed when the key is
missing, empty, or malformed. ``PublishGate.run()`` fills it in
automatically when you pass ``source_keys`` (it resolves the latest
``bake_id`` per source from ``public.bakes``); pass
``values_bake_uuids`` explicitly to pin exact UUIDs.

Usage (production, psycopg2 connection):

    from pipelines.publish_gate import PublishGate, PublishGateError

    gate = PublishGate(conn, contract_version="1.0.0")
    verdict = gate.run(candidate_snapshot_id, bake_ids={
        "primary": "2026-w04-bake-001",
        "values_bakes": ["2026-w04-bake-001"],  # legacy text ids (informational)
        "values_bake_uuids": ["<uuid>", ...],   # JEG-376: required; auto-resolved
        "per_source": {...},                     #   when source_keys is passed
    }, source_keys=["cbs", "cbsros", "espn", ...])
    if not verdict.passed:
        gate.abort()  # explicit rollback (defensive; conn.rollback())
        raise PublishGateError(verdict)
    # JEG-377: transactional activation. The DB function re-runs the
    # gates in-transaction and flips is_active/publishable atomically.
    # verdict.bake_ids (with JEG-376 values_bake_uuids) is merged onto
    # the candidate row so the in-function gate sees the same scope.
    gate.commit_active_flip(candidate_snapshot_id, verdict.bake_ids)

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
        -- gate runs all six gates (+ bake_set_coverage on failure)
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
    transactional activation ``SELECT api.activate_snapshot(...)``
    (JEG-377), but the caller wraps them in a transaction.
    ``PublishGate.publish(...)`` is the convenience wrapper that does
    BEGIN + gate + flip + COMMIT.

    The class is connection-agnostic: anything with a DB-API 2.0
    ``cursor()`` and ``commit()`` / ``rollback()`` works (psycopg2,
    psycopg, the Supabase sbclient cursor wrapper, or a test fake).
    """

    # SQL constants. The gate functions live in
    # lanes/work/jeg376-gates/gates-bake-scoped.sql (JEG-376; Roman
    # applies them; this module does not CREATE FUNCTION — the SQL
    # file is the authoritative source).
    _SQL_RUN_GATE = (
        "SELECT api.run_publish_gate(%s, %s::jsonb, %s::uuid)"
    )
    _SQL_LATEST_BAKE_UUIDS = (
        # Live public.bakes columns: bake_id (uuid PK), source,
        # source_generated_at, ingested_at, contract_version, context.
        # There is no bake_uuid/created_at column (JEG-389 bake-identity
        # cleanup 2026-10-04). The "bake_uuid" alias is kept so callers
        # and consolidated_values.bake_uuid stay stable.
        "SELECT DISTINCT ON (source) source, bake_id::text AS bake_uuid "
        "FROM public.bakes "
        "WHERE source = ANY(%s) "
        "ORDER BY source, ingested_at DESC"
    )
    # JEG-377: the flip is a single transactional DB call now.
    # _SQL_MERGE_BAKE_IDS persists the effective bake_ids (the ones
    # run() actually gated on, including JEG-376 values_bake_uuids)
    # onto the candidate row so api.activate_snapshot's in-transaction
    # gate re-check sees exactly the same scope.
    # JEG-389: the same statement ALSO sets product_snapshot.sources,
    # derived by derive_snapshot_sources() from the MERGED bake_ids
    # per_source keys — so the writer populates sources automatically
    # instead of relying on a one-time backfill. The shape matches the
    # backfilled convention: a JSONB object {<source>: {}, ...}.
    _SQL_GET_BAKE_IDS = (
        "SELECT bake_ids FROM public.product_snapshot WHERE snapshot_id = %s"
    )
    _SQL_MERGE_BAKE_IDS = (
        "UPDATE public.product_snapshot "
        "   SET bake_ids = %s::jsonb, "
        "       sources = %s::jsonb "
        " WHERE snapshot_id = %s"
    )
    _SQL_ACTIVATE_SNAPSHOT = "SELECT api.activate_snapshot(%s, %s::uuid, %s)"

    # Advisory-lock namespace for api.activate_snapshot. The live
    # product_snapshot has no product column; the value only scopes
    # the lock key (product:contract_version). "default" matches the
    # product_options product_key convention.
    DEFAULT_PRODUCT = "default"

    def __init__(self, conn: Any, contract_version: str):
        self.conn = conn
        self.contract_version = contract_version

    # -- bake UUID resolution -------------------------------------

    @staticmethod
    def derive_snapshot_sources(bake_ids: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Derive ``product_snapshot.sources`` from ``bake_ids.per_source``.

        JEG-389: the snapshot writer populates ``sources`` automatically
        from the per-source bake map instead of relying on a one-time
        backfill. Shape matches the backfilled convention: a JSONB object
        ``{<source>: {}, ...}`` with sorted keys. An empty/missing
        ``per_source`` map yields ``{}`` (fail-closed: no phantom sources).
        """
        per_source = (bake_ids or {}).get("per_source") or {}
        if not isinstance(per_source, dict):
            return {}
        return {k: {} for k in sorted(per_source)}

    def resolve_values_bake_uuids(
        self, source_keys: Sequence[str]
    ) -> List[str]:
        """Resolve the latest bake UUID per source from ``public.bakes``.

        Satisfies the JEG-376 pipeline contract (``values_bake_uuids``
        in ``bake_ids``) when the caller does not pin the UUIDs
        explicitly. One UUID per source key; the newest
        ``ingested_at`` row wins. (The UUIDs are ``bakes.bake_id``;
        "bake_uuid" is the stable alias used by ``bake_ids`` and
        ``consolidated_values.bake_uuid``.)

        Fail-closed: raises :class:`PublishGateError` when any source
        key has no bake record — the bake must be created/loaded
        before the publish can be gated.
        """
        keys = list(source_keys)
        with self.conn.cursor() as cur:
            cur.execute(self._SQL_LATEST_BAKE_UUIDS, (keys,))
            rows = cur.fetchall()
        found: Dict[str, str] = {}
        for r in rows:
            if isinstance(r, dict):
                found[str(r["source"])] = str(r["bake_uuid"])
            else:
                found[str(r[0])] = str(r[1])
        missing = [k for k in keys if k not in found]
        if missing:
            raise PublishGateError(
                PublishVerdict(
                    contract_version=self.contract_version,
                    bake_ids={},
                    gates=[],
                    raw={
                        "passed": False,
                        "gates": [
                            {
                                "gate": "values_bake_uuids_resolution",
                                "passed": False,
                                "reason": "no bake record in public.bakes",
                                "missing_sources": missing,
                            }
                        ],
                    },
                )
            )
        # Preserve the caller's key order (the SQL returns source order).
        return [found[k] for k in keys]

    # -- public API ------------------------------------------------

    def run(
        self,
        candidate_snapshot_id: Optional[str] = None,
        bake_ids: Optional[Dict[str, Any]] = None,
        source_keys: Optional[Sequence[str]] = None,
    ) -> PublishVerdict:
        """Run every gate inside the caller's open transaction.

        Does NOT flip ``is_active``; the caller calls
        ``commit_active_flip(...)`` after this returns a passed
        verdict.

        ``candidate_snapshot_id`` is passed through to
        ``api.run_publish_gate`` so gates 3-5 read the candidate row
        directly instead of guessing it via generated_at ordering
        (W3 review S2). It also correlates the gate run with the
        candidate row in the audit log.

        JEG-376: ``bake_ids`` must carry ``values_bake_uuids`` (the
        per-source bake UUIDs). When it is absent and ``source_keys``
        is given, this method resolves the latest UUID per source
        from ``public.bakes`` automatically. When both are absent it
        leaves ``bake_ids`` untouched (the orchestrator then fails
        closed server-side with a clear reason) — this keeps the
        pre-JEG-376 call signature backward compatible.
        """
        bake_ids = dict(bake_ids or {})
        if "values_bake_uuids" not in bake_ids:
            if source_keys is None:
                LOG.warning(
                    "publish gate: no values_bake_uuids and no source_keys; "
                    "the JEG-376 orchestrator will fail closed server-side"
                )
            else:
                bake_ids["values_bake_uuids"] = self.resolve_values_bake_uuids(
                    source_keys
                )
        with self.conn.cursor() as cur:
            cur.execute(
                self._SQL_RUN_GATE,
                (self.contract_version, json.dumps(bake_ids, sort_keys=True),
                 candidate_snapshot_id),
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

    def commit_active_flip(
        self,
        candidate_snapshot_id: str,
        bake_ids: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Atomically re-gate and flip the active snapshot (JEG-377).

        Calls ``SELECT api.activate_snapshot(product, candidate,
        contract_version)``, which advisory-locks, re-runs
        ``api.run_publish_gate`` against the candidate row's
        ``bake_ids`` IN-TRANSACTION, then flips ``is_active`` /
        ``publishable``. The gate re-check inside the same database
        transaction closes the TOCTOU race the old manual two-UPDATE
        version had between the Python gate check and the flip.

        When ``bake_ids`` is given (the effective bake_ids from
        ``run()``, including JEG-376 ``values_bake_uuids``), it is
        merged onto the candidate row first so the in-function gate
        sees exactly the scope the Python pre-check used.

        Must be called inside the same transaction as ``run(...)``
        and only when the verdict passed.

        Any database error — gate failure inside the function, a
        unique-violation on the flip, a missing candidate — becomes
        :class:`PublishGateError` with a synthetic ``active_flip``
        gate failure, so the caller rolls back cleanly. The partial
        unique index ``product_snapshot_active_uidx`` (one active row
        per contract_version) remains the last line of defense inside
        the function.
        """
        try:
            with self.conn.cursor() as cur:
                if bake_ids:
                    # JEG-389: read the candidate's current bake_ids, merge
                    # the effective scope over them in Python, and derive
                    # product_snapshot.sources from the MERGED per_source
                    # keys — so sources is populated automatically from the
                    # same scope the gates ran on. Single UPDATE writes both
                    # columns atomically.
                    cur.execute(self._SQL_GET_BAKE_IDS, (candidate_snapshot_id,))
                    row = cur.fetchone()
                    current = GateResult.from_jsonb(row[0]) if row and row[0] else {}
                    merged = {**current, **dict(bake_ids)}
                    sources = self.derive_snapshot_sources(merged)
                    cur.execute(
                        self._SQL_MERGE_BAKE_IDS,
                        (
                            json.dumps(merged, sort_keys=True),
                            json.dumps(sources, sort_keys=True),
                            candidate_snapshot_id,
                        ),
                    )
                cur.execute(
                    self._SQL_ACTIVATE_SNAPSHOT,
                    (
                        self.DEFAULT_PRODUCT,
                        candidate_snapshot_id,
                        self.contract_version,
                    ),
                )
        except PublishGateError:
            raise
        except Exception as exc:  # RaiseException, UniqueViolation, driver-specific
            raise PublishGateError(
                PublishVerdict(
                    contract_version=self.contract_version,
                    bake_ids=dict(bake_ids or {}),
                    gates=[],
                    raw={
                        "passed": False,
                        "gates": [
                            {
                                "gate": "active_flip",
                                "passed": False,
                                "reason": f"api.activate_snapshot failed: {exc}",
                            },
                        ],
                    },
                )
            ) from exc

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
        source_keys: Optional[Sequence[str]] = None,
    ) -> PublishVerdict:
        """Convenience: ``BEGIN`` + ``run(...)`` + ``commit_active_flip(...)`` + ``COMMIT``.

        Raises ``PublishGateError`` (and rolls back) if any gate
        fails or the active flip violates the partial unique index.
        On success, returns the passed verdict. Caller pattern::

            gate = PublishGate(conn, contract_version="1.0.0")
            verdict = gate.publish(candidate_id, bake_ids={...},
                                   source_keys=[...])
            # verdict.passed = True; commit is done

        ``source_keys`` is passed through to ``run(...)`` so
        ``values_bake_uuids`` is auto-resolved when the caller does
        not pin the UUIDs explicitly (JEG-376).
        """
        # psycopg2 / psycopg implicitly BEGIN on first execute
        # when the connection is in autocommit=False mode (the
        # default). For drivers that do not, the caller must BEGIN
        # before calling. We document this in the docstring.
        try:
            verdict = self.run(candidate_snapshot_id, bake_ids, source_keys)
        except PublishGateError:
            self.conn.rollback()
            raise
        if not verdict.passed:
            self.conn.rollback()
            raise PublishGateError(verdict)
        try:
            self.commit_active_flip(candidate_snapshot_id, verdict.bake_ids)
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
    """Gate names in the order the JEG-376 orchestrator emits them.

    The four bake-scoped gates (values_reconciliation, player_joins,
    options_coverage, view_coverage) are fanned out once per bake
    UUID in the candidate's ``values_bake_uuids`` set; the two
    snapshot-scoped gates (context_valid_fresh, source_freshness)
    run once. The synthetic ``bake_set_coverage`` entry is emitted
    ONLY when it fails (a declared row-bearing source has no bake
    in the candidate set).

    Useful for tests and for the audit log: "the gate failed at gate
    #3" reads better as "context_valid_fresh" than as a SQL index.
    """
    return (
        "values_reconciliation",
        "player_joins",
        "options_coverage",
        "view_coverage",
        "context_valid_fresh",
        "source_freshness",
        "bake_set_coverage",  # failure-only synthetic gate
    )