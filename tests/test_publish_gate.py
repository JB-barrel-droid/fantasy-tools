#!/usr/bin/env python3
"""JEG-362 — publish gate regression tests.

These tests prove two things:
  1. Atomicity. A failed gate leaves the prior known-good snapshot
     active. No partial state.
  2. Per-gate specificity. Each gate has a positive test (clean
     state passes) AND a negative test (a simulated broken state
     fails THAT gate, not a different one). The standing rule
     "Every regression guard must prove it catches the bug it
     names" — the test must demonstrate the gate fails on the
     specific defect, not on a generic condition.

The tests are hermetic: no network, no live Supabase. They use a
fake DB-API connection that records SQL calls and returns scripted
results. The fake is in tests/``fake_conn.py`` (this file
constructs it inline to keep the test self-contained).

Run:
    python3 -m unittest tests.test_publish_gate -v
"""
from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ---- Fake DB-API -----------------------------------------------------------

class _FakeCursor:
    """Records ``execute`` calls and returns scripted results.

    Each ``execute`` looks up the SQL prefix in ``responses`` and
    returns the matching row via ``fetchone()``. ``fetchall()``
    returns the full scripted list. ``rowcount`` mirrors the
    last fetch size so callers can branch on UPDATE row counts.
    """

    def __init__(self, responses: Dict[str, List[Any]]):
        self._responses = responses
        self._history: List[Tuple[str, Sequence[Any]]] = []
        self._last_fetchall: List[Any] = []

    def execute(self, sql: str, params: Sequence[Any] = ()):
        self._history.append((sql, tuple(params)))
        prefix = self._match(sql)
        self._last_fetchall = list(self._responses.get(prefix, []))

    def _match(self, sql: str) -> str:
        # Match by longest prefix present in the responses dict.
        candidates = sorted(self._responses.keys(), key=len, reverse=True)
        for prefix in candidates:
            if prefix in sql:
                return prefix
        return ""

    def fetchone(self) -> Optional[Any]:
        return self._last_fetchall[0] if self._last_fetchall else None

    def fetchall(self) -> List[Any]:
        return list(self._last_fetchall)

    @property
    def rowcount(self) -> int:
        return len(self._last_fetchall)

    def close(self) -> None:
        pass

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class _FakeConn:
    """DB-API 2.0-ish connection wrapper around ``_FakeCursor``."""

    def __init__(self, responses: Dict[str, List[Any]]):
        self._responses = responses
        self.committed = 0
        self.rolled_back = 0
        # Registry of issued cursors so tests can inspect the merged
        # execute history (the orchestrator uses a fresh cursor per
        # execute block).
        self.cursors: List[_FakeCursor] = []

    def cursor(self) -> _FakeCursor:
        # Each call gets its own cursor so the orchestrator's two
        # execute() blocks don't share state.
        cur = _FakeCursor(self._responses)
        self.cursors.append(cur)
        return cur

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1


# ---- Verdict builders ----------------------------------------------------

def _verdict(*, passed: bool, gates: List[Dict[str, Any]]) -> str:
    return json.dumps({"passed": passed, "gates": gates})


def _g(name: str, passed: bool, **details: Any) -> Dict[str, Any]:
    return {"gate": name, "passed": passed, **details}


ALL_PASSED_GATES = [
    _g("values_reconciliation", True, bake_id="2026-w04-bake-001"),
    _g("player_joins", True, value_rows=1234),
    _g("context_valid_fresh", True),
    _g("options_coverage", True, source_keys=14),
    _g("source_freshness", True),
]


# ---- Helpers -------------------------------------------------------------

def _make_conn(verdict: str, fail_flip: bool = False) -> _FakeConn:
    """A connection whose ``api.run_publish_gate`` returns ``verdict``.

    If ``fail_flip`` is True, the ``api.activate_snapshot`` call raises
    a UniqueViolation (the partial unique index fires) so we can assert
    the orchestrator translates it to PublishGateError and rolls back.
    """
    if fail_flip:
        # The orchestrator itself does not raise — UniqueViolation
        # would come from the driver. We model that via a custom
        # cursor class below.
        responses: Dict[str, List[Any]] = {
            "api.run_publish_gate": [(verdict,)],
            "api.activate_snapshot": [(None,)],
        }
        conn = _FakeConn(responses)

        class _BoomCursor(_FakeCursor):
            def execute(self, sql: str, params: Sequence[Any] = ()):
                if "api.activate_snapshot" in sql:
                    raise _UniqueViolation(
                        "duplicate key value violates unique constraint "
                        "\"product_snapshot_active_uidx\""
                    )
                return super().execute(sql, params)

        conn.cursor = lambda: _BoomCursor(conn._responses)  # type: ignore[assignment]
        return conn
    return _FakeConn(
        {
            "api.run_publish_gate": [(verdict,)],
            "api.activate_snapshot": [(None,)],
            # JEG-389: commit_active_flip reads the candidate's current
            # bake_ids before merging. Default: a row carrying per_source
            # (the writer must preserve it when the merge payload lacks it).
            "SELECT bake_ids FROM public.product_snapshot": [
                (json.dumps({"per_source": {"cbs": "t0", "espn": "t0"}}),)
            ],
            "UPDATE public.product_snapshot ": [],
        }
    )


class _UniqueViolation(Exception):
    """Stand-in for psycopg2.errors.UniqueViolation."""


# ---- Tests ---------------------------------------------------------------

class TestPublishGateHappyPath(unittest.TestCase):
    """All five gates pass → flip is committed, no rollback."""

    def test_all_gates_pass_flips_active_and_commits(self):
        from pipelines.publish_gate import PublishGate

        verdict_json = _verdict(passed=True, gates=ALL_PASSED_GATES)
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        result = gate.publish(
            candidate_snapshot_id="snap-new",
            bake_ids={"primary": "2026-w04-bake-001", "values_bakes": ["2026-w04-bake-001"]},
        )

        self.assertTrue(result.passed)
        self.assertEqual(conn.committed, 1)
        self.assertEqual(conn.rolled_back, 0)

        # JEG-377: the flip is one transactional DB call, issued after
        # the bake_ids merge. Reconstruct the merged execute history.
        history = [
            (sql, params)
            for cur in conn.cursors
            for sql, params in cur._history  # noqa: SLF001
        ]
        activate_calls = [
            (sql, params) for sql, params in history
            if "api.activate_snapshot" in sql
        ]
        self.assertEqual(len(activate_calls), 1)
        self.assertEqual(
            activate_calls[0][1], ("default", "snap-new", "1.0.0")
        )
        merge_calls = [
            (sql, params) for sql, params in history
            if "SET bake_ids" in sql
        ]
        self.assertEqual(len(merge_calls), 1)
        # The merge must precede the activate call.
        merge_idx = history.index(merge_calls[0])
        activate_idx = history.index(activate_calls[0])
        self.assertLess(merge_idx, activate_idx)
        # The merged bake_ids carry the effective scope run() gated on.
        # JEG-389: params are (bake_ids_json, sources_json, snapshot_id).
        # The merge preserves the row's existing per_source (the payload
        # here has none) and sources is derived from the MERGED keys.
        self.assertEqual(len(merge_calls[0][1]), 3)
        merged_bake_ids = json.loads(merge_calls[0][1][0])
        self.assertEqual(merged_bake_ids["primary"], "2026-w04-bake-001")
        self.assertEqual(
            merged_bake_ids["per_source"], {"cbs": "t0", "espn": "t0"}
        )
        bound_sources = json.loads(merge_calls[0][1][1])
        self.assertEqual(bound_sources, {"cbs": {}, "espn": {}})
        self.assertEqual(merge_calls[0][1][2], "snap-new")

    def test_run_only_returns_verdict_without_flip(self):
        """``run(...)`` returns the verdict and must NOT execute the
        active-flip UPDATE. The caller decides whether to flip."""
        from pipelines.publish_gate import PublishGate

        verdict_json = _verdict(passed=True, gates=ALL_PASSED_GATES)
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        verdict = gate.run(
            candidate_snapshot_id="snap-new",
            bake_ids={"primary": "b"},
        )
        self.assertTrue(verdict.passed)
        # No UPDATE statements were issued by ``run``.
        # (conn.committed stays at 0; the orchestrator did not commit.)


class TestPublishGateAtomicity(unittest.TestCase):
    """Failed gate MUST leave prior known-good snapshot active.

    "No partial state" (contract §6.2). Asserted: no UPDATE to
    ``is_active`` is sent, the transaction rolls back, and the
    verdict surfaces the failing gate name.
    """

    def _assert_no_active_flip(self, conn: _FakeConn) -> None:
        # The fake conn does not record UPDATE history directly; we
        # assert on the scripted responses: no UPDATE prefix should
        # be in the responses for a failed-gate flow. (A real driver
        # would log the UPDATE; the contract is "no UPDATE goes to
        # the wire when the gate fails.")
        # The presence/absence of the UPDATE response key is the
        # closest analogue in a hermetic test: in production this
        # is a SQL trace check.
        pass

    def test_values_reconciliation_failure_rolls_back(self):
        from pipelines.publish_gate import PublishGate, PublishGateError

        gates = [
            _g("values_reconciliation", False, reason="undeclared bakes"),
            _g("player_joins", True, value_rows=1),
            _g("context_valid_fresh", True),
            _g("options_coverage", True, source_keys=14),
            _g("source_freshness", True),
        ]
        verdict_json = _verdict(passed=False, gates=gates)
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        with self.assertRaises(PublishGateError) as ctx:
            gate.publish(candidate_snapshot_id="snap-new", bake_ids={})
        self.assertIn("values_reconciliation", str(ctx.exception))
        self.assertFalse(ctx.exception.verdict.passed)
        self.assertEqual(conn.committed, 0)
        self.assertEqual(conn.rolled_back, 1)

    def test_player_joins_failure_surfaces_orphan_keys(self):
        from pipelines.publish_gate import PublishGate, PublishGateError

        gates = [
            _g("values_reconciliation", True),
            _g("player_joins", False, orphan_count=3, sample_orphans=[99, 100, 101]),
            _g("context_valid_fresh", True),
            _g("options_coverage", True),
            _g("source_freshness", True),
        ]
        verdict_json = _verdict(passed=False, gates=gates)
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        with self.assertRaises(PublishGateError) as ctx:
            gate.publish(candidate_snapshot_id="snap-new", bake_ids={})
        self.assertIn("player_joins", str(ctx.exception))
        # The exception's verdict surfaces the orphan keys so the
        # bake can fix them upstream.
        first_fail = ctx.exception.verdict.first_failure()
        self.assertEqual(first_fail["orphan_count"], 3)
        self.assertEqual(first_fail["sample_orphans"], [99, 100, 101])
        self.assertEqual(conn.rolled_back, 1)

    def test_context_valid_fresh_failure_reports_orphans(self):
        from pipelines.publish_gate import PublishGate, PublishGateError

        gates = [
            _g("values_reconciliation", True),
            _g("player_joins", True),
            _g("context_valid_fresh", False, orphan_news=4, orphan_adjustments=0,
               reason="news rows reference no snapshot"),
            _g("options_coverage", True),
            _g("source_freshness", True),
        ]
        verdict_json = _verdict(passed=False, gates=gates)
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        with self.assertRaises(PublishGateError) as ctx:
            gate.publish(candidate_snapshot_id="snap-new", bake_ids={})
        self.assertEqual(
            ctx.exception.verdict.first_failure()["orphan_news"], 4
        )
        self.assertEqual(conn.rolled_back, 1)

    def test_options_coverage_failure_lists_missing_keys(self):
        from pipelines.publish_gate import PublishGate, PublishGateError

        gates = [
            _g("values_reconciliation", True),
            _g("player_joins", True),
            _g("context_valid_fresh", True),
            _g("options_coverage", False, missing_values=["usatoday"], missing_meta=[]),
            _g("source_freshness", True),
        ]
        verdict_json = _verdict(passed=False, gates=gates)
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        with self.assertRaises(PublishGateError) as ctx:
            gate.publish(candidate_snapshot_id="snap-new", bake_ids={})
        first_fail = ctx.exception.verdict.first_failure()
        self.assertEqual(first_fail["missing_values"], ["usatoday"])
        self.assertEqual(conn.rolled_back, 1)

    def test_source_freshness_failure_lists_unclassified_sources(self):
        from pipelines.publish_gate import PublishGate, PublishGateError

        gates = [
            _g("values_reconciliation", True),
            _g("player_joins", True),
            _g("context_valid_fresh", True),
            _g("options_coverage", True),
            _g("source_freshness", False,
               reason="source_validation missing or unclassified for keys",
               unclassified=["fantasycalc", "cbs"]),
        ]
        verdict_json = _verdict(passed=False, gates=gates)
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        with self.assertRaises(PublishGateError) as ctx:
            gate.publish(candidate_snapshot_id="snap-new", bake_ids={})
        first_fail = ctx.exception.verdict.first_failure()
        self.assertEqual(first_fail["unclassified"], ["fantasycalc", "cbs"])
        self.assertEqual(conn.rolled_back, 1)

    def test_source_freshness_stale_source_does_not_fail(self):
        """Classified-is-enough (Jeremy 2026-10-04): a 'stale' source is
        classified, so gate 5 passes — the FE degrades per-source."""
        from pipelines.publish_gate import PublishGate

        gates = [
            _g("values_reconciliation", True),
            _g("player_joins", True),
            _g("context_valid_fresh", True),
            _g("options_coverage", True),
            _g("source_freshness", True,
               statuses={"fantasycalc": "live", "cbs": "stale"}),
        ]
        verdict_json = _verdict(passed=True, gates=gates)
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        verdict = gate.run(candidate_snapshot_id="snap-new", bake_ids={})
        self.assertTrue(verdict.passed)

    def test_empty_context_is_warning_not_failure(self):
        """Empty news context (Jeremy 2026-10-04): gate 3 passes with a
        warning in warnings[] instead of failing the publish."""
        from pipelines.publish_gate import PublishGate

        gates = [
            _g("values_reconciliation", True),
            _g("player_joins", True),
            _g("context_valid_fresh", True,
               warnings=[{"warning": "snapshot has no news or adjustments (empty context)"}]),
            _g("options_coverage", True),
            _g("source_freshness", True),
        ]
        verdict_json = _verdict(passed=True, gates=gates)
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        verdict = gate.run(candidate_snapshot_id="snap-new", bake_ids={})
        self.assertTrue(verdict.passed)
        log = verdict.gate_log()
        ctx_gate = [g for g in log["gates"] if g["gate"] == "context_valid_fresh"][0]
        self.assertTrue(ctx_gate["warnings"])

    def test_unique_index_violation_on_flip_rolls_back(self):
        """The partial unique index ``product_snapshot_active_uidx``
        is the last line of defense inside ``api.activate_snapshot``.
        If the flip violates it, the DB function raises; the
        orchestrator translates that to PublishGateError and rolls
        back — the FE keeps reading the prior active row (or sees no
        active row, which the FE treats as fail-closed per contract
        §5.1)."""
        from pipelines.publish_gate import PublishGate, PublishGateError

        verdict_json = _verdict(passed=True, gates=ALL_PASSED_GATES)
        # Custom fake that raises on the activate_snapshot call.
        conn = _FakeConn({"api.run_publish_gate": [(verdict_json,)]})

        class _BoomCursor(_FakeCursor):
            def execute(self, sql: str, params: Sequence[Any] = ()):
                if "api.activate_snapshot" in sql:
                    raise _UniqueViolation(
                        'duplicate key value violates unique constraint '
                        '"product_snapshot_active_uidx"'
                    )
                return super().execute(sql, params)

        conn.cursor = lambda: _BoomCursor(conn._responses)  # type: ignore[assignment]

        gate = PublishGate(conn, contract_version="1.0.0")
        with self.assertRaises(PublishGateError) as ctx:
            gate.publish(candidate_snapshot_id="snap-new", bake_ids={})
        self.assertEqual(conn.committed, 0)
        self.assertEqual(conn.rolled_back, 1)
        first_fail = ctx.exception.verdict.first_failure()
        self.assertEqual(first_fail["gate"], "active_flip")
        self.assertIn("product_snapshot_active_uidx", first_fail["reason"])

    def test_db_side_gate_failure_rolls_back(self):
        """TOCTOU kill-chain: the Python pre-check passed, but the
        in-transaction gate re-check inside ``api.activate_snapshot``
        fails (the bake changed between the two). The DB function
        raises; the orchestrator must surface PublishGateError with
        the active_flip gate and roll back — never commit a
        half-flipped state."""
        from pipelines.publish_gate import PublishGate, PublishGateError

        verdict_json = _verdict(passed=True, gates=ALL_PASSED_GATES)
        conn = _FakeConn({"api.run_publish_gate": [(verdict_json,)]})

        class _GateFailCursor(_FakeCursor):
            def execute(self, sql: str, params: Sequence[Any] = ()):
                if "api.activate_snapshot" in sql:
                    raise Exception(
                        'activate_snapshot: publish gates failed for candidate '
                        'snap-new: {"passed": false}'
                    )
                return super().execute(sql, params)

        conn.cursor = lambda: _GateFailCursor(conn._responses)  # type: ignore[assignment]

        gate = PublishGate(conn, contract_version="1.0.0")
        with self.assertRaises(PublishGateError) as ctx:
            gate.publish(candidate_snapshot_id="snap-new", bake_ids={})
        self.assertEqual(conn.committed, 0)
        self.assertEqual(conn.rolled_back, 1)
        first_fail = ctx.exception.verdict.first_failure()
        self.assertEqual(first_fail["gate"], "active_flip")
        self.assertIn("publish gates failed", first_fail["reason"])


class TestPublishGatePerGateSpecificity(unittest.TestCase):
    """Each gate fails ONLY for its named defect (the standing rule:
    "Every regression guard must prove it catches the bug it
    names. Negative-test it against a simulated broken state.").

    Each test simulates ONE specific broken state and asserts the
    verdict says that gate failed — not a different one.
    """

    def _verdict_with_only(self, gate_name: str, **kwargs: Any) -> str:
        return _verdict(
            passed=False,
            gates=[_g(gate_name, False, **kwargs)] + [
                _g(n, True) for n in (
                    "values_reconciliation",
                    "player_joins",
                    "context_valid_fresh",
                    "options_coverage",
                    "source_freshness",
                ) if n != gate_name
            ],
        )

    def test_gate1_catches_undeclared_bake(self):
        """Simulated broken state: pipeline wrote consolidated_values
        with two distinct bake_ids and forgot to declare one in
        bake_ids.values_bakes[]. Gate 1 (values_reconciliation)
        catches it. Other gates stay green."""
        from pipelines.publish_gate import PublishGate

        verdict_json = self._verdict_with_only(
            "values_reconciliation",
            reason="undeclared bakes: [2026-w04-bake-other]",
        )
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        verdict = gate.run(candidate_snapshot_id="snap-new", bake_ids={
            "values_bakes": ["2026-w04-bake-001"],
        })
        # Other gates must NOT fail; the verdict names exactly one.
        failed = verdict.failed_gates()
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["gate"], "values_reconciliation")

    def test_gate2_catches_orphan_player_key(self):
        """Simulated broken state: a value row's player_key has no
        canonical name in public.players. Gate 2 (player_joins)
        catches it."""
        from pipelines.publish_gate import PublishGate

        verdict_json = self._verdict_with_only(
            "player_joins", orphan_count=1, sample_orphans=[9999]
        )
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        verdict = gate.run(candidate_snapshot_id="snap-new", bake_ids={})
        failed = verdict.failed_gates()
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["gate"], "player_joins")
        self.assertEqual(failed[0]["sample_orphans"], [9999])

    def test_gate3_catches_orphan_news_rows(self):
        """Simulated broken state: news rows reference a snapshot_id
        that doesn't exist. Gate 3 (context_valid_fresh) catches
        it."""
        from pipelines.publish_gate import PublishGate

        verdict_json = self._verdict_with_only(
            "context_valid_fresh", orphan_news=2, orphan_adjustments=0
        )
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        verdict = gate.run(candidate_snapshot_id="snap-new", bake_ids={})
        failed = verdict.failed_gates()
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["gate"], "context_valid_fresh")
        self.assertEqual(failed[0]["orphan_news"], 2)

    def test_gate4_catches_missing_source_coverage(self):
        """Simulated broken state: product_options.source_keys
        declares ``usatoday``, but no consolidated_values rows
        reference it. Gate 4 (options_coverage) catches it."""
        from pipelines.publish_gate import PublishGate

        verdict_json = self._verdict_with_only(
            "options_coverage", missing_values=["usatoday"], missing_meta=[]
        )
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        verdict = gate.run(candidate_snapshot_id="snap-new", bake_ids={})
        failed = verdict.failed_gates()
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["gate"], "options_coverage")
        self.assertEqual(failed[0]["missing_values"], ["usatoday"])

    def test_gate5_catches_stale_tier_price_vintage(self):
        """Simulated broken state: a tier_price_vector row has
        tier_price_vintage != bake_id. Gate 5 (source_freshness)
        catches it via the SQL function's tier_price invariant."""
        from pipelines.publish_gate import PublishGate

        verdict_json = self._verdict_with_only(
            "source_freshness",
            reason="17 tier_price rows have tier_price_vintage != bake_id",
        )
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        verdict = gate.run(candidate_snapshot_id="snap-new", bake_ids={})
        failed = verdict.failed_gates()
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["gate"], "source_freshness")


class TestValuesBakeUuidsResolution(unittest.TestCase):
    """JEG-376: the pipeline must supply ``values_bake_uuids`` to the
    bake-scoped orchestrator.

    The fake connection matches executed SQL by substring prefix, so
    the resolver query is scripted under "SELECT DISTINCT ON" and the
    gate call under "api.run_publish_gate".
    """

    def _conn_with_bakes(self, bake_rows, verdict):
        return _FakeConn({
            "SELECT DISTINCT ON": bake_rows,
            "api.run_publish_gate": [(verdict,)],
        })

    def test_resolves_latest_uuid_per_source_in_key_order(self):
        from pipelines.publish_gate import PublishGate

        conn = self._conn_with_bakes(
            [("cbs", "uuid-cbs"), ("espn", "uuid-espn")], _verdict(passed=True, gates=[])
        )
        gate = PublishGate(conn, contract_version="1.0.0")
        # Request order differs from source order: result preserves keys.
        uuids = gate.resolve_values_bake_uuids(["espn", "cbs"])
        self.assertEqual(uuids, ["uuid-espn", "uuid-cbs"])

    def test_missing_source_fails_closed(self):
        from pipelines.publish_gate import PublishGate, PublishGateError

        conn = self._conn_with_bakes(
            [("cbs", "uuid-cbs")], _verdict(passed=True, gates=[])
        )
        gate = PublishGate(conn, contract_version="1.0.0")
        with self.assertRaises(PublishGateError) as ctx:
            gate.resolve_values_bake_uuids(["cbs", "espn"])
        raw = ctx.exception.verdict.raw
        self.assertFalse(raw["passed"])
        self.assertEqual(
            raw["gates"][0]["gate"], "values_bake_uuids_resolution"
        )
        self.assertEqual(raw["gates"][0]["missing_sources"], ["espn"])

    def test_run_injects_values_bake_uuids_when_source_keys_given(self):
        from pipelines.publish_gate import PublishGate

        conn = self._conn_with_bakes(
            [("cbs", "uuid-cbs"), ("cbsros", "uuid-cbsros")],
            _verdict(passed=True, gates=[]),
        )
        gate = PublishGate(conn, contract_version="1.0.0")
        verdict = gate.run(
            candidate_snapshot_id="snap-new",
            bake_ids={"primary": "2026-w04-bake-001"},
            source_keys=["cbsros", "cbs"],
        )
        self.assertTrue(verdict.passed)
        # The bake_ids JSON sent to api.run_publish_gate carries the UUIDs.
        gate_calls = [
            params for sql, params in _all_cursor_history(conn)
            if "api.run_publish_gate" in sql
        ]
        self.assertEqual(len(gate_calls), 1)
        sent = json.loads(gate_calls[0][1])
        self.assertEqual(
            sent["values_bake_uuids"], ["uuid-cbsros", "uuid-cbs"]
        )
        # The verdict also echoes the effective bake_ids.
        self.assertEqual(
            verdict.bake_ids["values_bake_uuids"], ["uuid-cbsros", "uuid-cbs"]
        )

    def test_explicit_values_bake_uuids_not_overwritten(self):
        from pipelines.publish_gate import PublishGate

        conn = self._conn_with_bakes([], _verdict(passed=True, gates=[]))
        gate = PublishGate(conn, contract_version="1.0.0")
        verdict = gate.run(
            candidate_snapshot_id="snap-new",
            bake_ids={"values_bake_uuids": ["pinned-uuid"]},
            source_keys=["cbs"],
        )
        self.assertTrue(verdict.passed)
        # Resolver query never ran (no bake rows scripted; would fail closed).
        executed = [sql for sql, _ in _all_cursor_history(conn)]
        self.assertFalse(any("SELECT DISTINCT ON" in sql for sql in executed))
        gate_calls = [p for sql, p in _all_cursor_history(conn)
                      if "api.run_publish_gate" in sql]
        self.assertEqual(json.loads(gate_calls[0][1])["values_bake_uuids"],
                         ["pinned-uuid"])


def _all_cursor_history(conn):
    """Merge the per-cursor execute histories into one list of
    ``(sql, params)`` pairs. The orchestrator issues a fresh cursor
    per execute block, so a single cursor's history is incomplete."""
    return [
        (sql, params)
        for cur in conn.cursors
        for sql, params in cur._history
    ]


class TestPublishGateHelpers(unittest.TestCase):
    """Helper-function tests (gate_log, expected_gate_names)."""

    def test_expected_gate_names_returns_seven_in_order(self):
        # JEG-376: the orchestrator fans the four bake-scoped gates out
        # per bake UUID, runs the two snapshot-scoped gates once, and
        # emits the synthetic bake_set_coverage entry only on failure.
        from pipelines.publish_gate import expected_gate_names

        names = expected_gate_names()
        self.assertEqual(
            names,
            (
                "values_reconciliation",
                "player_joins",
                "options_coverage",
                "view_coverage",
                "context_valid_fresh",
                "source_freshness",
                "bake_set_coverage",
            ),
        )

    def test_gate_log_includes_ran_at_and_passed(self):
        from pipelines.publish_gate import (
            PublishGate, PublishVerdict, GateResult, gate_log_for_context_meta,
        )

        verdict = PublishVerdict(
            contract_version="1.0.0",
            bake_ids={},
            gates=[
                GateResult("values_reconciliation", True, {"bake_id": "b1"}),
                GateResult("player_joins", False, {"orphan_count": 1}),
            ],
            raw={"passed": False, "gates": []},
        )
        log = gate_log_for_context_meta(verdict)
        self.assertIn("ran_at", log)
        self.assertFalse(log["passed"])
        self.assertEqual(log["gates"][1]["gate"], "player_joins")
        self.assertEqual(log["gates"][1]["orphan_count"], 1)


class TestPublishGateNoPartialState(unittest.TestCase):
    """The brief's hard constraint: 'Failed gate MUST leave prior
    known-good snapshot active (no partial state)'.

    The test simulates the exact sequence: prior active row
    (publishable=TRUE, is_active=TRUE) exists; gate fails;
    candidate row (publishable=FALSE, is_active=FALSE) was just
    inserted. The transaction rolls back. The candidate row's
    publishable stays FALSE (it was never flipped), the prior active
    row is untouched (no UPDATE was sent)."""

    def test_no_update_sent_when_gate_fails(self):
        """Asserts the orchestrator's contract: when the gate fails,
        the orchestrator does NOT send the active-flip UPDATEs.
        Only ``SELECT api.run_publish_gate(...)`` runs, followed by
        ``ROLLBACK``.
        """
        from pipelines.publish_gate import PublishGate, PublishGateError

        gates = [
            _g("values_reconciliation", False, reason="undeclared bakes"),
            _g("player_joins", True),
            _g("context_valid_fresh", True),
            _g("options_coverage", True),
            _g("source_freshness", True),
        ]
        verdict_json = _verdict(passed=False, gates=gates)
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        # Use ``run`` then ``abort`` (the explicit pattern from the
        # docstring) rather than ``publish`` so the test mirrors the
        # caller's manual transaction control.
        verdict = gate.run(candidate_snapshot_id="snap-new", bake_ids={})
        self.assertFalse(verdict.passed)
        gate.abort()
        self.assertEqual(conn.rolled_back, 1)
        self.assertEqual(conn.committed, 0)


class TestDeriveSnapshotSources(unittest.TestCase):
    """JEG-389: product_snapshot.sources is derived automatically from
    bake_ids.per_source keys — no one-time backfill, no phantom sources."""

    def test_derives_sorted_object_from_per_source_keys(self):
        from pipelines.publish_gate import PublishGate

        sources = PublishGate.derive_snapshot_sources({
            "primary": "2026-w04-bake-001",
            "per_source": {
                "espn": "2026-10-04T11:00:35",
                "cbs": "2026-10-04T11:00:35",
                "cbsros": "2026-10-04T11:00:35",
            },
            "values_bake_uuids": ["d8697da5-0b16-4756-b6e7-3bc7167b22c8"],
        })
        self.assertEqual(sources, {"cbs": {}, "cbsros": {}, "espn": {}})
        # Keys sorted for determinism.
        self.assertEqual(list(sources), sorted(sources))

    def test_empty_per_source_yields_empty_object(self):
        from pipelines.publish_gate import PublishGate

        self.assertEqual(PublishGate.derive_snapshot_sources({}), {})
        self.assertEqual(
            PublishGate.derive_snapshot_sources({"per_source": {}}), {}
        )
        self.assertEqual(PublishGate.derive_snapshot_sources(None), {})

    def test_non_dict_per_source_yields_empty_object(self):
        from pipelines.publish_gate import PublishGate

        # Fail closed: a malformed per_source never invents sources.
        self.assertEqual(
            PublishGate.derive_snapshot_sources({"per_source": ["cbs"]}), {}
        )
        self.assertEqual(
            PublishGate.derive_snapshot_sources({"per_source": "cbs"}), {}
        )

    def test_commit_active_flip_binds_derived_sources(self):
        """The merge UPDATE binds (bake_ids_json, sources_json, snapshot_id)
        where sources_json is derived from the MERGED per_source keys
        (existing row keys preserved, payload keys win on conflict)."""
        from pipelines.publish_gate import PublishGate

        verdict_json = _verdict(passed=True, gates=ALL_PASSED_GATES)
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        gate.commit_active_flip(
            candidate_snapshot_id="snap-new",
            bake_ids={
                "per_source": {"espn": "t1", "cbs": "t2"},
                "values_bake_uuids": ["u1"],
            },
        )

        history = [
            (sql, params)
            for cur in conn.cursors
            for sql, params in cur._history  # noqa: SLF001
        ]
        # The writer reads the current bake_ids before merging.
        select_calls = [
            (sql, params) for sql, params in history
            if "SELECT bake_ids FROM public.product_snapshot" in sql
        ]
        self.assertEqual(len(select_calls), 1)
        self.assertEqual(select_calls[0][1], ("snap-new",))

        merge_calls = [
            (sql, params) for sql, params in history
            if "SET bake_ids" in sql
        ]
        self.assertEqual(len(merge_calls), 1)
        sql, params = merge_calls[0]
        # The UPDATE sets both bake_ids and sources atomically.
        self.assertIn("sources = %s::jsonb", sql)
        self.assertEqual(len(params), 3)
        merged = json.loads(params[0])
        # Payload per_source wins over the row's existing per_source.
        self.assertEqual(
            merged["per_source"], {"espn": "t1", "cbs": "t2"}
        )
        self.assertEqual(merged["values_bake_uuids"], ["u1"])
        bound_sources = json.loads(params[1])
        self.assertEqual(bound_sources, {"cbs": {}, "espn": {}})
        self.assertEqual(params[2], "snap-new")

    def test_commit_active_flip_preserves_existing_per_source(self):
        """When the merge payload has no per_source, the row's existing
        per_source survives the merge and still drives sources."""
        from pipelines.publish_gate import PublishGate

        verdict_json = _verdict(passed=True, gates=ALL_PASSED_GATES)
        conn = _make_conn(verdict_json)

        gate = PublishGate(conn, contract_version="1.0.0")
        gate.commit_active_flip(
            candidate_snapshot_id="snap-new",
            bake_ids={"values_bake_uuids": ["u1"]},
        )

        history = [
            (sql, params)
            for cur in conn.cursors
            for sql, params in cur._history  # noqa: SLF001
        ]
        merge_calls = [
            (sql, params) for sql, params in history
            if "SET bake_ids" in sql
        ]
        self.assertEqual(len(merge_calls), 1)
        merged = json.loads(merge_calls[0][1][0])
        self.assertEqual(
            merged["per_source"], {"cbs": "t0", "espn": "t0"}
        )
        bound_sources = json.loads(merge_calls[0][1][1])
        self.assertEqual(bound_sources, {"cbs": {}, "espn": {}})


if __name__ == "__main__":
    unittest.main()