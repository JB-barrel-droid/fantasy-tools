"""JEG-610: the divergence report to Linear sub-issue builder (no network)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))

import open_divergence_issues as odi  # noqa: E402


def report() -> dict:
    row = lambda status, **kw: {"label": status.title(), "status": status, "week": 6,
                                "message": "msg", "reasons": ["why"], **kw}
    return {"week": 6, "checklist": ["Step one", "Step two"], "sources": {
        "a": row("warn"), "b": row("ok"), "c": row("reviewed"),
        "d": row("investigate"), "e": row("n/a")}}


class PendingIssues(unittest.TestCase):
    def test_only_unresolved_flagged_sources(self):
        keys = [i["key"] for i in odi.pending_issues(report())]
        self.assertEqual(keys, ["divergence:a:w6", "divergence:d:w6"])

    def test_body_has_checklist_reasons_and_key(self):
        item = odi.pending_issues(report())[0]
        self.assertIn("- [ ] Step one", item["description"])
        self.assertIn("- why", item["description"])
        self.assertIn(item["key"], item["title"])

    def test_week_falls_back_to_report_week(self):
        r = report()
        del r["sources"]["a"]["week"]
        self.assertEqual(odi.pending_issues(r)[0]["key"], "divergence:a:w6")


class Main(unittest.TestCase):
    def run_main(self, env):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.json"
            p.write_text(json.dumps(report()))
            buf = StringIO()
            with mock.patch.dict(os.environ, env, clear=True), redirect_stdout(buf):
                rc = odi.main(["--report", str(p)])
            return rc, buf.getvalue()

    def test_no_token_never_touches_network(self):
        with mock.patch.object(odi, "_graphql", side_effect=AssertionError("network")):
            rc, out = self.run_main({})
        self.assertEqual(rc, 0)
        self.assertIn("LINEAR_API_KEY not set", out)

    def test_existing_key_is_skipped_and_new_one_created(self):
        with mock.patch.object(odi, "existing_titles",
                               return_value=("P", "T", ["x [divergence:a:w6]"])), \
             mock.patch.object(odi, "create", return_value="JEG-1") as create:
            rc, out = self.run_main({"LINEAR_API_KEY": "k"})
        self.assertEqual(rc, 0)
        self.assertEqual(create.call_count, 1)
        self.assertIn("exists, skipped: divergence:a:w6", out)
        self.assertEqual(create.call_args.args[3]["key"], "divergence:d:w6")


if __name__ == "__main__":
    unittest.main()
