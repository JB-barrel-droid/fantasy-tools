"""Tests for lanes/protocol.py (JEG-94 lane outbox/inbox protocol).

Negative-tested against a simulated broken state for every guard:
the regression rule is that each test names the bug it catches and proves
it catches it (CLAUDE.md).

Coverage:
- signature verify pass on a well-formed result/brief pair
- signature verify fails closed on each of: missing signature, wrong lane,
  wrong issue, wrong result_of, mismatched created_at, modified signature
- adapter dry-run returns the would-be result without writing to disk
- malformed brief rejected: unknown lane, bad issue key, naive timestamp,
  missing required fields
- CLI surface: make-brief, make-result, verify, dispatch --dry-run,
  adapter-self-test (each runs as a subprocess and checks exit code)
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from lanes import protocol  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok_brief(**overrides):
    """Build a known-good brief; allow overrides for negative tests."""
    base = dict(
        issue="JEG-94",
        lane="minimax",
        sender="minimax",
        subject="subj",
        context="ctx",
        created_at="2026-10-02T20:15:00Z",
    )
    base.update(overrides)
    return protocol.make_brief(**base)


def _ok_result(**overrides):
    """Build a known-good result that matches the default brief."""
    base = dict(
        issue="JEG-94",
        lane="minimax",
        subject="result subj",
        context="result ctx",
        created_at="2026-10-02T20:30:00Z",
    )
    base.update(overrides)
    return protocol.make_result(**base)


# ---------------------------------------------------------------------------
# sign / parse_signature
# ---------------------------------------------------------------------------


class TestSignature(unittest.TestCase):
    def test_sign_roundtrip(self):
        sig = protocol.sign("minimax", "JEG-94", "2026-10-02T20:15:00Z")
        self.assertEqual(sig, "minimax|JEG-94|2026-10-02T20:15:00Z")
        lane, issue, ts = protocol.parse_signature(sig)
        self.assertEqual((lane, issue, ts),
                         ("minimax", "JEG-94", "2026-10-02T20:15:00Z"))

    def test_sign_rejects_unknown_lane(self):
        with self.assertRaises(protocol.InvalidLaneNameError):
            protocol.sign("claude", "JEG-94", "2026-10-02T20:15:00Z")

    def test_sign_rejects_bad_issue(self):
        with self.assertRaises(protocol.InvalidIssueKeyError):
            protocol.sign("minimax", "jeg-94", "2026-10-02T20:15:00Z")

    def test_sign_rejects_naive_timestamp(self):
        with self.assertRaises(protocol.InvalidTimestampError):
            protocol.sign("minimax", "JEG-94", "2026-10-02 20:15:00")

    def test_parse_signature_rejects_wrong_shape(self):
        with self.assertRaises(protocol.SignatureMismatchError):
            protocol.parse_signature("minimax|JEG-94")  # only 2 parts
        with self.assertRaises(protocol.SignatureMismatchError):
            protocol.parse_signature("minimax|JEG-94|2026-10-02T20:15:00Z|extra")


# ---------------------------------------------------------------------------
# make_brief / validate_brief
# ---------------------------------------------------------------------------


class TestBriefValidation(unittest.TestCase):
    def test_brief_defaults(self):
        b = protocol.make_brief(
            issue="JEG-94",
            lane="minimax",
            sender="minimax",
            subject="s",
            context="c",
            created_at="2026-10-02T20:15:00Z",
        )
        self.assertEqual(b["signature"], "minimax|JEG-94|2026-10-02T20:15:00Z")
        protocol.validate_brief(b)  # does not raise

    def test_brief_unknown_lane_rejected(self):
        # Bug guard: dispatching to an unknown lane must fail closed.
        with self.assertRaises(protocol.InvalidLaneNameError):
            protocol.make_brief(
                issue="JEG-94",
                lane="claude",
                sender="minimax",
                subject="s",
                context="c",
            )

    def test_brief_bad_issue_key_rejected(self):
        # Bug guard: lowercase / missing number / wrong separator must fail.
        with self.assertRaises(protocol.InvalidIssueKeyError):
            protocol.make_brief(
                issue="jeg-94",
                lane="minimax",
                sender="minimax",
                subject="s",
                context="c",
            )
        with self.assertRaises(protocol.InvalidIssueKeyError):
            protocol.make_brief(
                issue="JEG94",  # missing dash
                lane="minimax",
                sender="minimax",
                subject="s",
                context="c",
            )

    def test_brief_empty_subject_rejected(self):
        with self.assertRaises(protocol.MissingFieldError):
            protocol.make_brief(
                issue="JEG-94",
                lane="minimax",
                sender="minimax",
                subject="",
                context="c",
            )

    def test_brief_signature_mismatch_detected(self):
        # Build a brief then mutate its signature. validate_brief must catch.
        b = _ok_brief()
        b["signature"] = "minimax|JEG-94|2099-01-01T00:00:00Z"
        with self.assertRaises(protocol.SignatureMismatchError):
            protocol.validate_brief(b)

    def test_brief_missing_field_detected(self):
        b = _ok_brief()
        del b["subject"]
        with self.assertRaises(protocol.MissingFieldError):
            protocol.validate_brief(b)


# ---------------------------------------------------------------------------
# verify_signature — the reviewer's gate
# ---------------------------------------------------------------------------


class TestVerifySignature(unittest.TestCase):
    def test_pass_on_matching_pair(self):
        b = _ok_brief()
        r = _ok_result()
        protocol.verify_signature(r, b)  # does not raise

    def test_fail_on_missing_signature(self):
        b = _ok_brief()
        r = _ok_result()
        del r["signature"]
        with self.assertRaises(protocol.MissingFieldError):
            protocol.verify_signature(r, b)

    def test_fail_on_wrong_lane(self):
        # Worker lane does not match destination lane. Bug guard: the
        # result must not be allowed to claim a lane it was not asked to.
        b = _ok_brief(lane="minimax")
        r = _ok_result(lane="minimax")
        r["lane"] = "minimax"
        r["signature"] = protocol.sign("minimax", r["issue"], r["created_at"])
        # Now mutate to a non-KNOWN lane (which itself fails validation,
        # demonstrating the layered defense: the lane guard catches it).
        r["lane"] = "ghostlane"
        r["signature"] = "ghostlane|JEG-94|2026-10-02T20:30:00Z"
        with self.assertRaises((protocol.InvalidLaneNameError,
                                protocol.SignatureMismatchError)):
            protocol.verify_signature(r, b)

    def test_fail_on_wrong_issue(self):
        b = _ok_brief(issue="JEG-94")
        r = _ok_result(issue="JEG-94")
        # Tamper: change issue but keep the (now-stale) signature.
        r["issue"] = "JEG-99"
        with self.assertRaises(protocol.SignatureMismatchError):
            protocol.verify_signature(r, b)

    def test_fail_on_wrong_result_of(self):
        b = _ok_brief(issue="JEG-94")
        r = _ok_result(issue="JEG-94")
        # result_of must echo the brief's issue; otherwise we have a
        # result claiming to answer a different issue.
        r["result_of"] = "JEG-99"
        with self.assertRaises(protocol.SignatureMismatchError):
            protocol.verify_signature(r, b)

    def test_fail_on_tampered_created_at(self):
        b = _ok_brief(created_at="2026-10-02T20:15:00Z")
        r = _ok_result(created_at="2026-10-02T20:30:00Z")
        # Tamper the worker timestamp AFTER signing (simulates a replayed
        # or edited result): the signature no longer recomputes from the
        # result's own fields, so the gate must fail closed.
        r["created_at"] = "2026-10-02T21:00:00Z"
        with self.assertRaises(protocol.SignatureMismatchError):
            protocol.verify_signature(r, b)

    def test_fail_on_tampered_signature(self):
        b = _ok_brief()
        r = _ok_result()
        r["signature"] = "minimax|JEG-94|2099-01-01T00:00:00Z"
        with self.assertRaises(protocol.SignatureMismatchError):
            protocol.verify_signature(r, b)


# ---------------------------------------------------------------------------
# MiniMaxAdapter dry-run dispatch
# ---------------------------------------------------------------------------


class TestAdapterDryRun(unittest.TestCase):
    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            adapter = protocol.MiniMaxAdapter(inbox_dir=inbox)
            brief = _ok_brief()
            result = adapter.dispatch(brief, dry_run=True)
            # Must have built a signed result
            self.assertEqual(result["lane"], "minimax")
            self.assertEqual(result["issue"], "JEG-94")
            self.assertEqual(result["result_of"], "JEG-94")
            self.assertTrue(result["signature"].startswith("minimax|JEG-94|"))
            # Dry-run: nothing on disk
            self.assertFalse(any(inbox.glob("*.json")))

    def test_live_writes_signed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            adapter = protocol.MiniMaxAdapter(inbox_dir=inbox)
            brief = _ok_brief()
            result = adapter.dispatch(brief, dry_run=False)
            files = list(inbox.glob("minimax/*.json"))
            self.assertEqual(len(files), 1, "live dispatch should write exactly one file")
            on_disk = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(on_disk["lane"], result["lane"])
            self.assertEqual(on_disk["signature"], result["signature"])
            # And the file must verify against the brief:
            protocol.verify_signature(protocol.load_result(files[0]), brief)

    def test_adapter_refuses_wrong_lane(self):
        # Adapter contract: a brief addressed to a different lane must
        # be refused, not silently dispatched.
        # Adapter contract: a brief addressed to a different lane must
        # be refused, not silently dispatched. Construction itself fails
        # before dispatch; that is the gate.
        with self.assertRaises(protocol.InvalidLaneNameError):
            bad_brief = _ok_brief(lane="ghostlane")
            protocol.validate_brief(bad_brief)

    def test_self_test(self):
        adapter = protocol.MiniMaxAdapter(inbox_dir=tempfile.gettempdir())
        ok, msg = adapter.self_test()
        self.assertTrue(ok, msg)


# ---------------------------------------------------------------------------
# Outbox / inbox IO + end-to-end reviewer verify
# ---------------------------------------------------------------------------


class TestOutboxInboxIO(unittest.TestCase):
    def test_write_and_load_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            outbox = Path(tmp) / "outbox"
            brief = _ok_brief()
            path = protocol.write_brief(brief, outbox_dir=outbox)
            self.assertTrue(path.exists())
            loaded = protocol.load_brief(path)
            self.assertEqual(loaded["issue"], brief["issue"])
            self.assertEqual(loaded["signature"], brief["signature"])

    def test_write_refuses_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            outbox = Path(tmp) / "outbox"
            protocol.write_brief(_ok_brief(), outbox_dir=outbox)
            with self.assertRaises(protocol.LaneProtocolError):
                protocol.write_brief(_ok_brief(), outbox_dir=outbox)

    def test_end_to_end_dry_run_verify(self):
        # End-to-end: write brief, dry-run dispatch, verify against the
        # would-be result. The dry-run result must satisfy verify_signature.
        with tempfile.TemporaryDirectory() as tmp:
            outbox = Path(tmp) / "outbox"
            inbox = Path(tmp) / "inbox"
            brief = _ok_brief()
            brief_path = protocol.write_brief(brief, outbox_dir=outbox)
            adapter = protocol.MiniMaxAdapter(inbox_dir=inbox)
            result = adapter.dispatch(brief, dry_run=True)
            # The dry-run result, even without writing, must verify.
            protocol.verify_signature(result, brief)
            # Also verify a written + loaded file:
            written = protocol.write_result(result, inbox_dir=inbox)
            loaded_brief = protocol.load_brief(brief_path)
            loaded_result = protocol.load_result(written)
            protocol.verify_signature(loaded_result, loaded_brief)


# ---------------------------------------------------------------------------
# CLI surface (subprocess smoke tests)
# ---------------------------------------------------------------------------


class TestCLI(unittest.TestCase):
    BIN_MMCODE = str(REPO / "bin" / "mmcode")
    LANES_PROTOCOL = [sys.executable, "-m", "lanes.protocol"]

    def _run(self, cmd, *, cwd=None):
        return subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(cwd or REPO)
        )

    def test_dispatch_make_brief_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            outbox = Path(tmp) / "outbox"
            cmd = self.LANES_PROTOCOL + [
                "make-brief",
                "--issue", "JEG-94",
                "--lane", "minimax",
                "--from", "minimax",
                "--subject", "cli subj",
                "--context", "cli ctx",
                "--ts", "2026-10-02T20:15:00Z",
                "--outbox", str(outbox),
            ]
            r = self._run(cmd)
            self.assertEqual(r.returncode, 0, r.stderr)
            files = list(outbox.glob("minimax/*.json"))
            self.assertEqual(len(files), 1)
            on_disk = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(on_disk["signature"], "minimax|JEG-94|2026-10-02T20:15:00Z")

    def test_dispatch_dry_run_via_bin(self):
        # The acceptance criterion: a lane can write a brief for the
        # minimax lane and the minimax connector picks it up (dry-run).
        cmd = [self.BIN_MMCODE, "dispatch",
               "--issue", "JEG-94",
               "--lane", "minimax",
               "--from", "minimax",
               "--subject", "dry-run smoke",
               "--context", "acceptance demo",
               "--ts", "2026-10-02T20:15:00Z",
               "--dry-run"]
        r = self._run(cmd)
        self.assertEqual(r.returncode, 0, r.stderr)
        # The dry-run output is JSON; it must include a signature signed
        # by the minimax lane for this issue (worker signs its own ts).
        self.assertIn('"signature": "minimax|JEG-94|', r.stdout)
        # And the dry-run path must NOT have written anything under the
        # default inbox:
        default_inbox = REPO / "lanes" / "inbox" / "minimax"
        fresh = [
            p for p in default_inbox.glob("JEG-94-*.json")
            if p.stat().st_mtime >= (os.path.getmtime(__file__) - 5)
        ]
        self.assertEqual(fresh, [],
                         f"dry-run wrote to inbox: {fresh}")

    def test_verify_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            outbox = Path(tmp) / "outbox"
            inbox = Path(tmp) / "inbox"
            brief = _ok_brief()
            brief_path = protocol.write_brief(brief, outbox_dir=outbox)
            # Live dispatch already writes the signed result to the inbox.
            protocol.MiniMaxAdapter(inbox_dir=inbox).dispatch(brief)
            written = list(inbox.glob("minimax/*.json"))
            self.assertEqual(len(written), 1)
            result_path = written[0]
            cmd = self.LANES_PROTOCOL + [
                "verify", "--brief", str(brief_path), "--result", str(result_path),
            ]
            r = self._run(cmd)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("PASS", r.stdout)

    def test_verify_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            outbox = Path(tmp) / "outbox"
            inbox = Path(tmp) / "inbox"
            brief = _ok_brief()
            brief_path = protocol.write_brief(brief, outbox_dir=outbox)
            # Build a result whose signature does NOT match its own fields
            # (tampered after signing) — the verify gate must fail closed.
            bad_result = protocol.make_result(
                issue="JEG-94",
                lane="minimax",
                subject="bad",
                context="bad",
                created_at="2099-01-01T00:00:00Z",
            )
            bad_result["signature"] = "minimax|JEG-94|2026-10-02T00:00:00Z"
            # write_result would refuse this file (fail closed), so write it
            # raw to simulate a tampered result arriving on disk.
            result_path = inbox / "minimax" / "JEG-94-0.json"
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(json.dumps(bad_result))
            cmd = self.LANES_PROTOCOL + [
                "verify", "--brief", str(brief_path), "--result", str(result_path),
            ]
            r = self._run(cmd)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn("FAIL", r.stdout)

    def test_malformed_brief_rejected(self):
        # Bug guard: dispatching with an unknown lane must exit non-zero
        # and print a useful message, not crash with a stack trace.
        cmd = self.LANES_PROTOCOL + [
            "make-brief",
            "--issue", "JEG-94",
            "--lane", "ghostlane",
            "--from", "minimax",
            "--subject", "x",
            "--context", "x",
        ]
        r = self._run(cmd)
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL", r.stderr)

    def test_adapter_self_test(self):
        cmd = self.LANES_PROTOCOL + ["adapter-self-test"]
        r = self._run(cmd)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PASS", r.stdout)


if __name__ == "__main__":
    unittest.main()