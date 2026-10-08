#!/usr/bin/env python3
"""cbsros-supabase-sync.yml scrape step vs the puller's real snapshot shape.

The 2026-10-07 weekly run scraped 369 rows and then failed: the step-summary
line in the workflow read snapshot['row_count'], a key the puller never
writes (KeyError, exit 1), so the save step never ran. These tests produce a
snapshot with the real puller (CBS fetch stubbed with synthetic pages) and run
the workflow's own `python3 -c` readers against it, so a workflow/puller
schema mismatch fails here instead of on Wednesday's cron.

Also covers the puller's fetch retry and its per-page fail-closed guard.
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "cbsros-supabase-sync.yml"
PULLER = ROOT / "pipelines" / "pull_cbs_ros_projections.py"
CI_SNAPSHOT = "/tmp/cbsros_snapshot/snapshot.json"


def _load_puller():
    spec = importlib.util.spec_from_file_location("pull_cbs_ros_projections", PULLER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


puller = _load_puller()


def _row_html(name: str, pos: str, team: str, layout: list[str], idx: int) -> str:
    stats = {k: 1.0 for k in layout}
    stats.update({"gp": 12.0, "rec": 2.0 * idx})
    stats["fpts"] = 120.0 + idx
    stats["fppg"] = round(stats["fpts"] / stats["gp"], 1)
    player = (
        '<span class="CellPlayerName--long"><a href="/p">' + name + "</a>"
        '<span class="CellPlayerName-position"> ' + pos + " </span>"
        '<span class="CellPlayerName-team"> ' + team + " </span></span>"
    )
    tds = "".join(f"<td>{stats[k]}</td>" for k in layout)
    return f'<tr class="TableBase-bodyTr"><td>{player}</td>{tds}</tr>'


def _page(pos: str, n: int) -> str:
    layout = puller.LAYOUTS[pos]
    rows = "".join(_row_html(f"Player {pos}{i}", pos, "BUF", layout, i) for i in range(n))
    return f"<table>{rows}</table>"


def _scrape_step_body() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    m = re.search(r"- name: Scrape CBS ROS projections\n(.*?)(?=\n      - name:)", text, re.S)
    if not m:
        raise AssertionError("Scrape step not found in cbsros-supabase-sync.yml")
    return m.group(1)


def _run_puller(out_dir: Path, pages: dict[str, str]) -> Path:
    def fake_fetch(url: str) -> str:
        for pos, html in pages.items():
            if f"/{pos}/" in url:
                return html
        raise AssertionError(f"unexpected url {url}")

    argv = ["pull_cbs_ros_projections.py", "--date", "2026-10-07", "--out-dir", str(out_dir)]
    with mock.patch.object(puller, "fetch", fake_fetch), mock.patch.object(sys, "argv", argv), \
            redirect_stdout(io.StringIO()):
        rc = puller.main()
    assert rc == 0
    return out_dir / "snapshot.json"


class WorkflowReadsRealSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        pages = {p: _page(p, 5) for p in puller.POSITIONS}
        self.snapshot = _run_puller(Path(self.tmp.name), pages)
        self.n_rows = len(json.loads(self.snapshot.read_text(encoding="utf-8"))["rows"])

    def test_scrape_step_python_readers_succeed_on_puller_output(self):
        body = _scrape_step_body()
        readers = re.findall(r'python3 -c "(.*?)"\)', body)
        self.assertTrue(readers, "expected the step-summary row reader in the scrape step")
        for code in readers:
            self.assertIn(CI_SNAPSHOT, code)
            res = subprocess.run(
                [sys.executable, "-c", code.replace(CI_SNAPSHOT, str(self.snapshot))],
                capture_output=True, text=True,
            )
            self.assertEqual(res.returncode, 0, f"workflow reader failed: {code}\n{res.stderr}")
            self.assertEqual(res.stdout.strip(), str(self.n_rows))

    def test_scrape_step_is_fail_closed_bash(self):
        # The run step uses GitHub's default `bash -e`; a reader failure must
        # stop the job before the save step (it did, which is how 10-07 failed
        # loudly). Guard against someone adding `|| true` to paper over it.
        body = _scrape_step_body()
        self.assertNotRegex(body, r"\|\|\s*(true|echo)\b")
        self.assertNotIn("continue-on-error", body)


class FetchRetry(unittest.TestCase):
    def _http_error(self, code):
        return urllib.error.HTTPError("https://x", code, "err", {}, None)

    def test_transient_errors_retry_then_succeed(self):
        calls = iter([urllib.error.URLError("reset"), self._http_error(503), "<html>ok</html>"])

        def once(url):
            item = next(calls)
            if isinstance(item, Exception):
                raise item
            return item

        sleeps = []
        with mock.patch.object(puller, "_fetch_once", once), redirect_stdout(io.StringIO()):
            self.assertEqual(puller.fetch("https://x", sleep=sleeps.append), "<html>ok</html>")
        self.assertEqual(len(sleeps), 2)

    def test_block_status_fails_without_retry(self):
        count = {"n": 0}

        def once(url):
            count["n"] += 1
            raise self._http_error(403)

        with mock.patch.object(puller, "_fetch_once", once), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                puller.fetch("https://x", sleep=lambda s: None)
        self.assertEqual(count["n"], 1)
        self.assertIn("403", str(ctx.exception))

    def test_exhausted_retries_fail_closed(self):
        def once(url):
            raise urllib.error.URLError("timed out")

        with mock.patch.object(puller, "_fetch_once", once), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                puller.fetch("https://x", attempts=3, sleep=lambda s: None)
        self.assertIn("after 3 attempts", str(ctx.exception))


class EmptyPageFailsClosed(unittest.TestCase):
    def test_one_empty_position_page_fails(self):
        pages = {p: _page(p, 5) for p in puller.POSITIONS}
        pages["TE"] = "<html>layout changed</html>"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                _run_puller(Path(tmp), pages)
            self.assertIn("TE", str(ctx.exception))
            self.assertFalse((Path(tmp) / "snapshot.json").exists())


if __name__ == "__main__":
    unittest.main()
