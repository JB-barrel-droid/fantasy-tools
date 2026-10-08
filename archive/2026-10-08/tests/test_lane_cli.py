"""Regression: lanes/bin/lane mechanical CLI (JEG-94).

Hermetic: every test builds its own tmp lanes/ tree (with a minimal
ROUTING.md fixture) so the real repo's lanes/outbox and lanes/inbox are
never touched. The repo's hermetic test-unit list runs without data/raw,
snapshots, or network, and this module is wired into that contract.

Acceptance coverage (per JEG-94 ticket):
- send copies the brief into outbox/<lane>/ and prints the wake-up line.
- send refuses a brief that requires a capability the target lane lacks.
- poll flags a result newer than its matching brief.
- list shows outbox briefs with no matching inbox result (= awaiting).

Plus guards that prove each check is non-vacuous: a positive control case
for every negative-control case below.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "lanes" / "bin" / "lane"


# A minimal ROUTING.md with the same shape as the real one. The column
# order matches lanes/ROUTING.md (minimax first after the Task class and
# Examples columns) so the lane-key extraction is exercised, not assumed.
MINI_ROUTING = textwrap.dedent("""\
    # Lane Routing & Capability Guard (test fixture for JEG-94 tests)
    Not every task may go to every lane. This is a minimal copy of the
    real lanes/ROUTING.md used by the lane CLI tests so they can run in
    a tmp dir without touching the repo.

    | Task class | Examples | minimax | claude | chatgpt |
    |---|---|---|---|---|
    | repo code change | pipeline Python/JS, tests, guards | YES | YES | YES |
    | wiring verification | run verify scripts | YES | YES | YES |
    | needs vision / OCR | read text from screenshots/images | NO | MAYBE | MAYBE |
    | needs live browser | rendered-page checks | NO | NO | NO |
    | needs credentials | Supabase DDL via SQL editor, OAuth | NO | NO | NO |
    | needs Mac-only files | Razzball snapshot on Jeremy's machine | NO | NO | NO |
    | methodology decision | indexation, VORP math | NO | advise | advise |
    | values / copy calls | what the chart shows | NO | NO | NO |
    | merge / push / deploy | anything touching main | NO | NO | NO |
    """)


def run(args, root: Path | None = None, stdin: str | None = None):
    """Invoke the lane CLI as a subprocess. Uses sys.executable so the
    script's executable bit is not required for the test to pass."""
    cmd = [sys.executable, str(SCRIPT)]
    if root is not None:
        cmd.extend(["--root", str(root)])
    cmd.extend(args)
    return subprocess.run(
        cmd, capture_output=True, text=True, input=stdin
    )


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class LaneCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.lanes = self.tmpdir / "lanes"
        self.lanes.mkdir()
        write(self.lanes / "ROUTING.md", MINI_ROUTING)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # ---------------------------------------------------------------------
    # --help / top-level wiring
    # ---------------------------------------------------------------------
    def test_help_exits_zero_and_lists_subcommands(self) -> None:
        r = run(["--help"])
        self.assertEqual(
            r.returncode, 0, msg=f"--help failed:\nstderr={r.stderr}"
        )
        self.assertIn("send", r.stdout)
        self.assertIn("poll", r.stdout)
        self.assertIn("list", r.stdout)
        self.assertIn("JEG-94", r.stdout, msg="--help should mention the ticket")

    def test_subcommand_help_exits_zero(self) -> None:
        for sub in ("send", "poll", "list"):
            with self.subTest(sub=sub):
                r = run([sub, "--help"])
                self.assertEqual(
                    r.returncode, 0,
                    msg=f"{sub} --help failed:\nstderr={r.stderr}",
                )

    def test_missing_subcommand_errors(self) -> None:
        r = run([])
        self.assertNotEqual(r.returncode, 0)

    # ---------------------------------------------------------------------
    # send: happy path
    # ---------------------------------------------------------------------
    def test_send_copies_brief_and_prints_wakeup_line(self) -> None:
        brief = self.tmpdir / "JEG-94-brief.md"
        write(
            brief,
            "Issue: JEG-94\n"
            "Required capabilities: repo code change\n\n"
            "Task: implement the lane CLI\n",
        )
        r = run(
            ["send", "--lane", "minimax", "--issue", "JEG-94",
             "--brief", str(brief)],
            root=self.lanes,
        )
        self.assertEqual(
            r.returncode, 0,
            msg=f"send failed:\nstdout={r.stdout}\nstderr={r.stderr}",
        )
        # Wake-up line is EXACT (per JEG-94 acceptance).
        self.assertEqual(
            r.stdout.strip(),
            "Brief ready: lanes/outbox/minimax/JEG-94-brief.md",
        )
        # File copied verbatim into outbox.
        dest = self.lanes / "outbox" / "minimax" / "JEG-94-brief.md"
        self.assertTrue(dest.exists(), f"expected {dest} to exist")
        self.assertEqual(dest.read_text(encoding="utf-8"), brief.read_text())

    def test_send_no_required_capabilities_is_trivially_ok(self) -> None:
        """A brief without a 'Required capabilities:' line is always
        acceptable -- the guard only refuses explicitly-required work."""
        brief = self.tmpdir / "JEG-y.md"
        write(brief, "Issue: JEG-y\nTask: hello\n")
        r = run(
            ["send", "--lane", "minimax", "--issue", "JEG-y",
             "--brief", str(brief)],
            root=self.lanes,
        )
        self.assertEqual(
            r.returncode, 0,
            msg=f"send failed:\nstderr={r.stderr}",
        )
        self.assertIn("lanes/outbox/minimax/JEG-y-brief.md", r.stdout)

    def test_send_normalizes_capability_matching(self) -> None:
        """Brief writers may write 'vision', 'vision/OCR', or
        'needs vision / OCR' -- all should match the ROUTING.md row."""
        for token in ("vision", "vision/OCR", "needs vision / OCR", "VISION"):
            with self.subTest(token=token):
                # Fresh tmp so the outbox state from other subtests doesn't
                # leak.
                sub_tmp = tempfile.TemporaryDirectory()
                try:
                    sub_root = Path(sub_tmp.name) / "lanes"
                    sub_root.mkdir()
                    write(sub_root / "ROUTING.md", MINI_ROUTING)
                    brief = Path(sub_tmp.name) / "JEG.md"
                    write(
                        brief,
                        f"Issue: JEG\nRequired capabilities: {token}\n",
                    )
                    r = run(
                        ["send", "--lane", "minimax", "--issue", "JEG",
                         "--brief", str(brief)],
                        root=sub_root,
                    )
                    self.assertNotEqual(
                        r.returncode, 0,
                        msg=f"token {token!r} should have been refused:\n"
                            f"stdout={r.stdout}\nstderr={r.stderr}",
                    )
                    self.assertIn("cannot do", r.stderr)
                finally:
                    sub_tmp.cleanup()

    # ---------------------------------------------------------------------
    # send: capability guard (the lane-lacks case from JEG-94 acceptance)
    # ---------------------------------------------------------------------
    def test_send_refuses_brief_needing_vision(self) -> None:
        """minimax cannot do 'needs vision / OCR' (matrix answer NO).
        The guard must refuse before any file is copied."""
        brief = self.tmpdir / "JEG-vision.md"
        write(
            brief,
            "Issue: JEG-vision\nRequired capabilities: needs vision / OCR\n",
        )
        r = run(
            ["send", "--lane", "minimax", "--issue", "JEG-vision",
             "--brief", str(brief)],
            root=self.lanes,
        )
        self.assertNotEqual(
            r.returncode, 0,
            msg="expected refusal but send returned 0",
        )
        self.assertIn("cannot do", r.stderr)
        self.assertIn("needs vision", r.stderr)
        # Nothing copied.
        self.assertFalse(
            (self.lanes / "outbox" / "minimax").exists(),
            "outbox dir must not be created when send is refused",
        )

    def test_send_refuses_credentials_live_browser_methodology_values(self) -> None:
        """All five capabilities the LANES.md note says minimax must NOT
        take -- vision, live browser, credentials, Mac-only files,
        methodology/values/copy. Refuse each one."""
        forbidden = [
            "needs vision / OCR",
            "needs live browser",
            "needs credentials",
            "needs Mac-only files",
            "methodology decision",
            "values / copy calls",
            "merge / push / deploy",
        ]
        for cap in forbidden:
            with self.subTest(cap=cap):
                sub_tmp = tempfile.TemporaryDirectory()
                try:
                    sub_root = Path(sub_tmp.name) / "lanes"
                    sub_root.mkdir()
                    write(sub_root / "ROUTING.md", MINI_ROUTING)
                    brief = Path(sub_tmp.name) / "JEG.md"
                    write(
                        brief,
                        f"Issue: JEG\nRequired capabilities: {cap}\n",
                    )
                    r = run(
                        ["send", "--lane", "minimax", "--issue", "JEG",
                         "--brief", str(brief)],
                        root=sub_root,
                    )
                    self.assertNotEqual(
                        r.returncode, 0,
                        msg=f"{cap!r} should be refused",
                    )
                    self.assertIn("cannot do", r.stderr)
                    # Nothing copied.
                    self.assertFalse(
                        (sub_root / "outbox" / "minimax").exists(),
                    )
                finally:
                    sub_tmp.cleanup()

    def test_send_refuses_unknown_capability(self) -> None:
        """Briefs that name a capability no row in the matrix matches
        are refused (fail closed rather than guessing)."""
        brief = self.tmpdir / "JEG-unknown.md"
        write(
            brief,
            "Issue: JEG-unknown\n"
            "Required capabilities: something-not-in-the-matrix\n",
        )
        r = run(
            ["send", "--lane", "minimax", "--issue", "JEG-unknown",
             "--brief", str(brief)],
            root=self.lanes,
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown capability", r.stderr)

    def test_send_reports_multiple_unsupported_capabilities(self) -> None:
        """If the brief lists several forbidden capabilities, the refusal
        names every one of them in the same error."""
        brief = self.tmpdir / "JEG-multi.md"
        write(
            brief,
            "Issue: JEG-multi\n"
            "Required capabilities: needs vision / OCR, needs credentials\n",
        )
        r = run(
            ["send", "--lane", "minimax", "--issue", "JEG-multi",
             "--brief", str(brief)],
            root=self.lanes,
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("needs vision", r.stderr)
        self.assertIn("credentials", r.stderr)

    def test_send_accepts_capability_lane_can_do(self) -> None:
        """Positive control: a brief that only requires 'repo code change'
        is accepted for every lane listed in the fixture."""
        brief = self.tmpdir / "JEG-ok.md"
        write(brief, "Issue: JEG-ok\nRequired capabilities: repo code change\n")
        for lane in ("minimax", "claude", "chatgpt"):
            with self.subTest(lane=lane):
                sub_tmp = tempfile.TemporaryDirectory()
                try:
                    sub_root = Path(sub_tmp.name) / "lanes"
                    sub_root.mkdir()
                    write(sub_root / "ROUTING.md", MINI_ROUTING)
                    r = run(
                        ["send", "--lane", lane, "--issue", "JEG-ok",
                         "--brief", str(brief)],
                        root=sub_root,
                    )
                    self.assertEqual(
                        r.returncode, 0,
                        msg=f"{lane} refused a capability it can do:\n"
                            f"stderr={r.stderr}",
                    )
                    self.assertIn(
                        f"lanes/outbox/{lane}/JEG-ok-brief.md", r.stdout
                    )
                finally:
                    sub_tmp.cleanup()

    # ---------------------------------------------------------------------
    # send: input validation
    # ---------------------------------------------------------------------
    def test_send_missing_brief_fails_closed(self) -> None:
        r = run(
            ["send", "--lane", "minimax", "--issue", "JEG-94",
             "--brief", str(self.tmpdir / "does-not-exist.md")],
            root=self.lanes,
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not found", r.stderr)

    def test_send_missing_root_fails_closed(self) -> None:
        """If --root points at a non-existent lanes/ tree, refuse before
        attempting to copy."""
        brief = self.tmpdir / "JEG.md"
        write(brief, "Issue: JEG\n")
        bogus = self.tmpdir / "no-such-lanes"
        r = run(
            ["send", "--lane", "minimax", "--issue", "JEG",
             "--brief", str(brief)],
            root=bogus,
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("routing file not found", r.stderr)

    # ---------------------------------------------------------------------
    # poll
    # ---------------------------------------------------------------------
    def test_poll_flags_newer_result(self) -> None:
        """When a result's mtime > its matching brief's mtime, the poll
        output marks it NEWER and the summary counts it."""
        outbox = self.lanes / "outbox" / "minimax"
        outbox.mkdir(parents=True)
        brief = outbox / "JEG-77-brief.md"
        brief.write_text("brief body", encoding="utf-8")
        # Backdate the brief.
        old = time.time() - 3600
        os.utime(brief, (old, old))

        inbox = self.lanes / "inbox" / "minimax"
        inbox.mkdir(parents=True)
        result = inbox / "JEG-77-result.md"
        result.write_text("result body", encoding="utf-8")
        new = time.time()
        os.utime(result, (new, new))

        r = run(["poll", "--lane", "minimax"], root=self.lanes)
        self.assertEqual(
            r.returncode, 0,
            msg=f"poll failed:\nstderr={r.stderr}",
        )
        self.assertIn("JEG-77-result.md", r.stdout)
        self.assertIn("NEWER", r.stdout)
        self.assertIn("1 result(s) newer than their matching brief(s).", r.stdout)

    def test_poll_does_not_flag_older_result(self) -> None:
        """Positive control: a result older than its matching brief is
        NOT flagged. The guard that catches 'newer' must not catch every
        relation."""
        outbox = self.lanes / "outbox" / "minimax"
        outbox.mkdir(parents=True)
        brief = outbox / "JEG-77-brief.md"
        brief.write_text("brief body", encoding="utf-8")
        new = time.time()
        os.utime(brief, (new, new))

        inbox = self.lanes / "inbox" / "minimax"
        inbox.mkdir(parents=True)
        result = inbox / "JEG-77-result.md"
        result.write_text("result body", encoding="utf-8")
        old = time.time() - 3600
        os.utime(result, (old, old))

        r = run(["poll", "--lane", "minimax"], root=self.lanes)
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertNotIn("NEWER", r.stdout)
        self.assertIn("0 result(s) newer than their matching brief(s).", r.stdout)

    def test_poll_lists_results_with_mtimes(self) -> None:
        """Even when no result is newer, poll still lists every result
        file alongside its mtime and its matching brief's mtime."""
        outbox = self.lanes / "outbox" / "minimax"
        outbox.mkdir(parents=True)
        brief = outbox / "JEG-77-brief.md"
        brief.write_text("b", encoding="utf-8")
        inbox = self.lanes / "inbox" / "minimax"
        inbox.mkdir(parents=True)
        result = inbox / "JEG-77-result.md"
        result.write_text("r", encoding="utf-8")

        r = run(["poll", "--lane", "minimax"], root=self.lanes)
        self.assertEqual(r.returncode, 0)
        self.assertIn("JEG-77-result.md", r.stdout)
        self.assertIn("result_mtime=", r.stdout)
        self.assertIn("brief_mtime=", r.stdout)

    def test_poll_no_results(self) -> None:
        """An empty inbox prints a clear 'no result files' line and exits 0."""
        r = run(["poll", "--lane", "minimax"], root=self.lanes)
        self.assertEqual(r.returncode, 0)
        self.assertIn("no result files", r.stdout)

    def test_poll_orphan_result_without_brief(self) -> None:
        """A result whose matching brief does not exist yet (e.g. the
        human wrote it manually) is listed without being flagged NEWER."""
        inbox = self.lanes / "inbox" / "minimax"
        inbox.mkdir(parents=True)
        orphan = inbox / "JEG-99-result.md"
        orphan.write_text("orphan", encoding="utf-8")
        r = run(["poll", "--lane", "minimax"], root=self.lanes)
        self.assertEqual(r.returncode, 0)
        self.assertIn("JEG-99-result.md", r.stdout)
        self.assertIn("missing", r.stdout)
        self.assertIn("0 result(s) newer", r.stdout)

    # ---------------------------------------------------------------------
    # list
    # ---------------------------------------------------------------------
    def test_list_shows_awaiting_briefs(self) -> None:
        """Briefs with no matching result appear as AWAITING and are
        counted in the summary."""
        outbox = self.lanes / "outbox" / "minimax"
        outbox.mkdir(parents=True)
        (outbox / "JEG-1-brief.md").write_text("a", encoding="utf-8")
        (outbox / "JEG-2-brief.md").write_text("b", encoding="utf-8")
        inbox = self.lanes / "inbox" / "minimax"
        inbox.mkdir(parents=True)
        (inbox / "JEG-1-result.md").write_text("r", encoding="utf-8")

        r = run(["list"], root=self.lanes)
        self.assertEqual(
            r.returncode, 0,
            msg=f"list failed:\nstderr={r.stderr}",
        )
        self.assertIn("[minimax]", r.stdout)
        self.assertIn("JEG-1-brief.md", r.stdout)
        self.assertIn("JEG-2-brief.md", r.stdout)
        # JEG-1 has a result -> DONE. JEG-2 has no result -> AWAITING.
        self.assertIn("DONE   ", r.stdout)
        self.assertIn("AWAITING", r.stdout)
        self.assertIn("1 brief(s) awaiting a lane result.", r.stdout)

    def test_list_no_briefs_anywhere(self) -> None:
        r = run(["list"], root=self.lanes)
        self.assertEqual(r.returncode, 0)
        self.assertIn("no briefs in any outbox", r.stdout)

    def test_list_across_all_three_lanes(self) -> None:
        """list scans every lane, not just --lane's."""
        for lane in ("claude", "chatgpt", "minimax"):
            outbox = self.lanes / "outbox" / lane
            outbox.mkdir(parents=True)
            (outbox / f"JEG-{lane}-brief.md").write_text("x", encoding="utf-8")
        r = run(["list"], root=self.lanes)
        self.assertEqual(r.returncode, 0)
        self.assertIn("[claude]", r.stdout)
        self.assertIn("[chatgpt]", r.stdout)
        self.assertIn("[minimax]", r.stdout)
        self.assertIn("3 brief(s) awaiting", r.stdout)

    def test_list_does_not_count_done_briefs(self) -> None:
        """Positive control: a brief whose matching result already exists
        is shown as DONE and is NOT counted in the awaiting total."""
        outbox = self.lanes / "outbox" / "minimax"
        outbox.mkdir(parents=True)
        (outbox / "JEG-done-brief.md").write_text("b", encoding="utf-8")
        inbox = self.lanes / "inbox" / "minimax"
        inbox.mkdir(parents=True)
        (inbox / "JEG-done-result.md").write_text("r", encoding="utf-8")

        r = run(["list"], root=self.lanes)
        self.assertEqual(r.returncode, 0)
        self.assertIn("DONE   ", r.stdout)
        self.assertNotIn("AWAITING", r.stdout)
        self.assertIn("0 brief(s) awaiting a lane result.", r.stdout)


if __name__ == "__main__":
    unittest.main()