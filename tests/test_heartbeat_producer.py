#!/usr/bin/env python3
"""Tests for the heartbeat observation producer (JEG-339).

Hermetic: no network. The fetch path is patched by tests. Verification
happens outside this sandbox.

Covers:
    1. classify_result table-driven for all 7 approved verdicts.
    2. content_mismatch via the `force_verdict` escape hatch on a 200.
    3. Ambiguity bucket (status None + error None) is never fabricated green.
    4. run_once with a stub writer + monkey-patched fetch (no network).
    5. NDJSONWriter round-trip (write → read → equal).
    6. SupabaseWriter is credential-free and raises NotImplementedError.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from unittest import mock


_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from pipelines import heartbeat_producer as producer  # noqa: E402


UTC = timezone.utc


def _check(**overrides) -> dict:
    base = {
        "check_id": "c1",
        "url": "https://example.invalid/",
        "enabled": True,
        "timeout_seconds": 10,
        "latency_budget_ms": 3000,
        "check_type": "http_status",
    }
    base.update(overrides)
    return base


# ---- 1. classify_result table-driven verdict coverage -----------------------------


class TestClassifyResultVerdicts(unittest.TestCase):
    """All 7 approved verdicts via classify_result.

    The (status_code=None, error=None) row is the ambiguity bucket — it
    must NEVER produce 'ok' per JEG-339 standing rules.
    """

    CASES: List[Tuple[Optional[int], Optional[int], Optional[str], str]] = [
        # (status_code, elapsed_ms, error, expected_verdict)
        (200, 412, None, "ok"),
        (201, 100, None, "ok"),
        (204, 300, None, "ok"),
        (299, 50,  None, "ok"),
        (301, 100, None, "http_error"),
        (404, 80,  None, "http_error"),
        (500, 5,   None, "http_error"),
        (503, 88,  None, "http_error"),
        (None, 10000, "timeout", "timeout"),
        (None, 12000, "dns",     "dns_error"),
        (None, 50,    "dns",     "dns_error"),
        (None, 200,   "tls",     "tls_error"),
        (None, 250,   "connect", "connect_error"),
        (None, 0,     "connect", "connect_error"),
        # Ambiguity bucket: never green.
        (None, None, None, "connect_error"),
    ]

    def test_table(self):
        url = "https://example.invalid/"
        check = _check()
        for status_code, elapsed_ms, error, expected in self.CASES:
            with self.subTest(
                status_code=status_code,
                elapsed_ms=elapsed_ms,
                error=error,
                expected=expected,
            ):
                row = producer.classify_result(
                    url, status_code, elapsed_ms, error, check
                )
                self.assertEqual(
                    set(row.keys()),
                    {"checked_at", "url", "status_code", "response_ms", "verdict"},
                )
                self.assertEqual(row["url"], url)
                self.assertEqual(row["status_code"], status_code)
                self.assertEqual(row["response_ms"], elapsed_ms)
                self.assertEqual(row["verdict"], expected)
                # checked_at must be a UTC ISO-8601 'Z' string.
                self.assertTrue(row["checked_at"].endswith("Z"))
                parsed = datetime.strptime(
                    row["checked_at"], "%Y-%m-%dT%H:%M:%S.%fZ"
                ).replace(tzinfo=UTC)
                self.assertIsNotNone(parsed)

    def test_brief_sample_ok(self):
        # Brief sample:
        #   classify_result('https://x/', 200, 412, None, {}) → ok
        row = producer.classify_result("https://x/", 200, 412, None, {})
        self.assertEqual(row["url"], "https://x/")
        self.assertEqual(row["status_code"], 200)
        self.assertEqual(row["response_ms"], 412)
        self.assertEqual(row["verdict"], "ok")

    def test_status_none_without_error_is_not_ok(self):
        row = producer.classify_result("u", None, None, None, _check())
        self.assertNotEqual(row["verdict"], "ok")
        self.assertEqual(row["verdict"], "connect_error")


# ---- 2. content_mismatch via force_verdict escape hatch -----------------------


class TestForceVerdictEscapeHatch(unittest.TestCase):
    """A future content-checking phase sets `force_verdict` to override the
    network-based mapping. Without that flag, a 200 is always 'ok'.
    """

    def test_content_mismatch_on_200(self):
        row = producer.classify_result(
            "https://x/", 200, 412, None,
            _check(force_verdict="content_mismatch"),
        )
        self.assertEqual(row["verdict"], "content_mismatch")
        self.assertEqual(row["status_code"], 200)
        self.assertEqual(row["response_ms"], 412)

    def test_force_verdict_overrides_timeout(self):
        # If a content verdict wins even when the fetch timed out, it wins.
        row = producer.classify_result(
            "https://x/", None, 10000, "timeout",
            _check(force_verdict="content_mismatch"),
        )
        self.assertEqual(row["verdict"], "content_mismatch")

    def test_force_verdict_must_be_in_approved_set(self):
        # An unknown forced value is ignored; normal mapping runs.
        row = producer.classify_result(
            "https://x/", 200, 412, None,
            _check(force_verdict="made_up_verdict"),
        )
        self.assertEqual(row["verdict"], "ok")


# ---- 3. run_once with a stub writer (no network) ------------------------------


class _RecordingWriter(producer.ObservationWriter):
    def __init__(self) -> None:
        self.rows: List[dict] = []

    def write(self, row: dict) -> None:
        self.rows.append(row)


class TestRunOnce(unittest.TestCase):
    CHECKS = [
        {"check_id": "ok-check",     "url": "https://ok.invalid/",
         "enabled": True,  "timeout_seconds": 5, "latency_budget_ms": 1000,
         "check_type": "http_status"},
        {"check_id": "broken-check", "url": "https://broken.invalid/",
         "enabled": True,  "timeout_seconds": 5, "latency_budget_ms": 1000,
         "check_type": "http_status"},
        {"check_id": "skip-check",   "url": "https://skip.invalid/",
         "enabled": False, "timeout_seconds": 5, "latency_budget_ms": 1000,
         "check_type": "http_status"},
    ]

    def test_run_once_ok_and_failure(self):
        fetch_table = {
            "https://ok.invalid/":     (200, 80, None),
            "https://broken.invalid/": (None, 10000, "timeout"),
        }
        writer = _RecordingWriter()
        with mock.patch.object(
            producer, "_fetch", side_effect=lambda u, t: fetch_table[u]
        ):
            summary = producer.run_once(self.CHECKS, writer)
        self.assertEqual(summary["ran"], 2)            # enabled only
        self.assertEqual(summary["ok_count"], 1)
        self.assertEqual(sorted(summary["failed"]), ["broken-check"])
        self.assertGreaterEqual(summary["elapsed_ms"], 0)

        by_url = {r["url"]: r for r in writer.rows}
        self.assertEqual(by_url["https://ok.invalid/"]["verdict"], "ok")
        self.assertEqual(by_url["https://broken.invalid/"]["verdict"], "timeout")
        # Disabled check produced no row.
        self.assertNotIn("https://skip.invalid/", by_url)

    def test_run_once_disabled_check_does_not_call_fetch(self):
        writer = _RecordingWriter()
        only_disabled = [self.CHECKS[2]]
        with mock.patch.object(producer, "_fetch") as fake_fetch:
            summary = producer.run_once(only_disabled, writer)
        self.assertEqual(summary["ran"], 0)
        self.assertEqual(summary["ok_count"], 0)
        self.assertEqual(summary["failed"], [])
        fake_fetch.assert_not_called()

    def test_run_once_writer_failure_marks_check_failed_but_continues(self):
        class _FlakyWriter(producer.ObservationWriter):
            def __init__(self, fail_url: str) -> None:
                self.fail_for = fail_url
                self.written: List[dict] = []

            def write(self, row: dict) -> None:
                if row["url"] == self.fail_for:
                    raise IOError("simulated write failure")
                self.written.append(row)

        fetches = iter([
            (200, 10, None),
            (200, 10, None),
        ])
        writer = _FlakyWriter(fail_url="https://plain.invalid/")
        checks = [
            {"check_id": "good", "url": "https://good.invalid/",
             "enabled": True, "timeout_seconds": 5, "latency_budget_ms": 1000,
             "check_type": "http_status"},
            {"check_id": "broken-write", "url": "https://plain.invalid/",
             "enabled": True, "timeout_seconds": 5, "latency_budget_ms": 1000,
             "check_type": "http_status"},
        ]
        with mock.patch.object(
            producer, "_fetch", side_effect=lambda u, t: next(fetches)
        ):
            summary = producer.run_once(checks, writer)
        self.assertEqual(summary["ran"], 2)
        self.assertEqual(summary["ok_count"], 1)
        self.assertIn("broken-write", summary["failed"])
        self.assertEqual(len(writer.written), 1)

    def test_run_once_supabase_writer_raises(self):
        checks = [
            {"check_id": "x", "url": "https://x.invalid/",
             "enabled": True, "timeout_seconds": 5, "latency_budget_ms": 1000,
             "check_type": "http_status"},
        ]
        writer = producer.SupabaseWriter()
        with mock.patch.object(
            producer, "_fetch", return_value=(200, 5, None)
        ):
            with self.assertRaises(NotImplementedError):
                producer.run_once(checks, writer)


# ---- 4. NDJSONWriter round-trip ----------------------------------------------


class TestNDJSONWriterRoundTrip(unittest.TestCase):
    def test_round_trip_three_rows(self):
        rows = [
            {"checked_at": "2026-10-04T12:00:00.000000Z",
             "url": "https://a/", "status_code": 200, "response_ms": 80,
             "verdict": "ok"},
            {"checked_at": "2026-10-04T12:00:01.000000Z",
             "url": "https://b/", "status_code": None, "response_ms": 10000,
             "verdict": "timeout"},
            {"checked_at": "2026-10-04T12:00:02.000000Z",
             "url": "https://c/", "status_code": 503, "response_ms": 88,
             "verdict": "http_error"},
        ]
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "obs.ndjson")
            w = producer.NDJSONWriter(path)
            for row in rows:
                w.write(row)
            with open(path, encoding="utf-8") as fh:
                lines = [ln for ln in fh.read().splitlines() if ln]
            self.assertEqual(len(lines), len(rows))
            parsed = [json.loads(ln) for ln in lines]
            self.assertEqual(parsed, rows)

    def test_appends_across_instances(self):
        # Two NDJSONWriter instances against the same path must append, not
        # clobber — important for the 60s timer ticks.
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "obs.ndjson")
            producer.NDJSONWriter(path).write(
                {"checked_at": "2026-10-04T12:00:00.000000Z",
                 "url": "https://a/", "status_code": 200, "response_ms": 80,
                 "verdict": "ok"}
            )
            producer.NDJSONWriter(path).write(
                {"checked_at": "2026-10-04T12:00:01.000000Z",
                 "url": "https://b/", "status_code": None, "response_ms": 10000,
                 "verdict": "timeout"}
            )
            with open(path, encoding="utf-8") as fh:
                lines = [ln for ln in fh.read().splitlines() if ln]
            self.assertEqual(len(lines), 2)


# ---- 5. SupabaseWriter is credential-free ------------------------------------


class TestSupabaseWriterIsCredentialFree(unittest.TestCase):
    def test_raises_on_write(self):
        w = producer.SupabaseWriter()
        with self.assertRaises(NotImplementedError):
            w.write({"checked_at": "x", "url": "u",
                     "status_code": 1, "response_ms": 1, "verdict": "ok"})

    def test_constructor_ignores_args(self):
        w = producer.SupabaseWriter("anything", ["goes"], {"here": "too"},
                                    named="too")
        self.assertFalse(hasattr(w, "url"))
        self.assertFalse(hasattr(w, "options"))


if __name__ == "__main__":
    unittest.main()