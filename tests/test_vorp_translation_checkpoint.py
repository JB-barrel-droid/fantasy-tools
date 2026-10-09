"""Monitor checkpoints that replaced the JEG-70 translation-freshness check.

JEG-482 (Jeremy, 2026-10-08) removed the value-above-waivers translation from
the saved Indexed values, so build_pipeline_checkpoints reports the rank guard
instead (build_rank_guard_summary): every published chart's Indexed order must
equal its native order. ok on a clean fixture, bad on a reordered one, unk
when unreadable; read from the COMMITTED fixture, never the working tree.

The chain's VORP refresh stage (JEG-70) still runs, demand-driven and
fail-safe; its grains are a record only.
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_pipeline_checkpoints as bpc


def _doc(reordered=False):
    native = {"a": 10.0, "b": 8.0, "c": 5.0, "d": 1.0}
    doc = {"built_at": "2026-10-08T00:00:00+00:00", "sources": {}}
    for source in ("usatoday", "fantasypros", "cbs", "fantasycalc"):
        doc["sources"][source] = {"combos": {
            f"{sc}_12": {"native": dict(native), "reindexed": {k: v * 0.7 for k, v in native.items()}}
            for sc in ("full", "half", "standard")}}
    if reordered:
        r = doc["sources"]["cbs"]["combos"]["half_12"]["reindexed"]
        r["a"], r["b"] = r["b"], r["a"]
    return doc


class RankGuardSummaryTest(unittest.TestCase):
    def _run(self, doc):
        with patch.object(bpc, "committed_fixture_json", return_value=(doc, "origin/main")):
            return bpc.build_rank_guard_summary()

    def test_ok_when_every_chart_keeps_its_order(self):
        s = self._run(_doc())
        self.assertEqual(s["status"], "ok", s["reason"])
        self.assertEqual(s["n_checks"], 12)
        self.assertEqual(s["inversions"], 0)

    def test_bad_when_a_chart_is_reordered(self):
        s = self._run(_doc(reordered=True))
        self.assertEqual(s["status"], "bad")
        self.assertIn("cbs/half_12", s["reason"])
        self.assertEqual(s["inversions"], 1)

    def test_unk_when_fixture_unreadable(self):
        with patch.object(bpc, "committed_fixture_json", return_value=(None, "unreadable")):
            self.assertEqual(bpc.build_rank_guard_summary()["status"], "unk")

    def test_checkpoints_carry_rank_guard_not_translation(self):
        src = Path(bpc.__file__).read_text(encoding="utf-8")
        self.assertIn('result["rank_guard"] = build_rank_guard_summary()', src)
        self.assertNotIn("def build_vorp_translation_summary", src)


class VorpRefreshStageTest(unittest.TestCase):
    """JEG-70: the chain's VORP refresh stage is demand-driven and fail-safe."""

    def _fake(self, check_ok=True, refresh_ok=True):
        calls = []

        def run_fn(cmd, **kwargs):
            calls.append(cmd)
            if "--check-only" in cmd:
                return check_ok, "check"
            return refresh_ok, "refreshed"

        return run_fn, calls

    def test_skips_refresh_when_grains_fresh(self):
        import rebuild_comparison_chain as chain

        run_fn, calls = self._fake(check_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            result = chain.run_vorp_refresh(5, Path(tmp), run_fn)
        self.assertEqual(result["status"], "ok")
        # Only the check ran; no full refresh.
        self.assertEqual(len(calls), 1)
        self.assertIn("--check-only", calls[0])

    def test_refreshes_when_grains_stale(self):
        import rebuild_comparison_chain as chain

        run_fn, calls = self._fake(check_ok=False, refresh_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            result = chain.run_vorp_refresh(5, Path(tmp), run_fn)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(calls), 2)
        self.assertNotIn("--check-only", calls[1])
        self.assertIn("--week", calls[1])

    def test_refresh_failure_never_raises(self):
        import rebuild_comparison_chain as chain

        run_fn, _ = self._fake(check_ok=False, refresh_ok=False)
        with tempfile.TemporaryDirectory() as tmp:
            result = chain.run_vorp_refresh(5, Path(tmp), run_fn)
        # Fail-safe: failure is reported, not raised (the grains are a
        # record since JEG-482; no chart value reads them).
        self.assertEqual(result["status"], "failed")

    def test_unexpected_error_never_raises(self):
        import rebuild_comparison_chain as chain

        def boom(cmd, **kwargs):
            raise RuntimeError("transport down")

        with tempfile.TemporaryDirectory() as tmp:
            result = chain.run_vorp_refresh(5, Path(tmp), boom)
        self.assertEqual(result["status"], "failed")
        self.assertIn("transport down", result["detail"])


class CommittedFixtureReadTest(unittest.TestCase):
    """2026-10-04 regression, kept for the rank guard: the checkpoint reads the
    fixture as COMMITTED (what Pages serves), never the working tree, which is
    routinely dirty with other lanes' experiments."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_repo = bpc.REPO
        self.addCleanup(setattr, bpc, "REPO", self._orig_repo)

    def _write_tree(self, repo, doc):
        p = (Path(repo) / "data" / "fixtures" / "current"
             / "comparison-sources-data.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc))
        return p

    def _init_git_repo(self, repo, committed_doc):
        import shutil
        import subprocess

        if shutil.which("git") is None:
            self.skipTest("git not available")
        self._write_tree(repo, committed_doc)
        run = lambda *a: subprocess.run(a, check=True, capture_output=True,
                                        cwd=str(repo))
        run("git", "init", "-q", "-b", "main", ".")
        run("git", "add", ".")
        run("git", "-c", "user.email=t@t.test", "-c", "user.name=t",
            "commit", "-qm", "committed fixture")
        # origin/main ref without a network remote: git show works offline.
        run("git", "update-ref", "refs/remotes/origin/main", "main")

    def test_committed_blob_wins_over_dirty_tree(self):
        # origin/main holds the clean fixture (ok); the working tree holds a
        # reordered one (bad). The summary must report ok.
        repo = Path(self.tmp) / "repo"
        self._init_git_repo(repo, _doc())
        self._write_tree(repo, _doc(reordered=True))
        bpc.REPO = Path(repo)
        s = bpc.build_rank_guard_summary()
        self.assertEqual(s["status"], "ok", s["reason"])

    def test_helper_prefers_committed_over_head_and_tree(self):
        # Precedence: origin/main > HEAD > working tree.
        repo = Path(self.tmp) / "repo2"
        committed = _doc()
        self._init_git_repo(repo, committed)
        self._write_tree(repo, _doc(reordered=True))
        bpc.REPO = Path(repo)
        data, label = bpc.committed_fixture_json(
            "data/fixtures/current/comparison-sources-data.json")
        self.assertEqual(label, "origin/main")
        self.assertEqual(data, committed)


if __name__ == "__main__":
    unittest.main()
