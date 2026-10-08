"""JEG-70: VORP translation freshness checkpoint on the monitor.

build_pipeline_checkpoints.build_vorp_translation_summary() reads the
translation provenance stamped into the fixture's as-published combos and
reports ok/warn/bad/unk. These tests prove each state fires on the right
input -- including the discrimination case: a combo whose provenance grain
week is missing (pre-JEG-70 wiring) must warn, and an unexpected
reindex-fallback must go bad (fallback as steady state is the failure
JEG-70 exists to prevent).
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_pipeline_checkpoints as bpc


def _combo(method, week):
    return {
        "reindexed": {"a": 1.0},
        "translation": {
            "method": method,
            "grain": {"source": "usatoday", "scoring": "half_ppr",
                      "league_teams": 12, "week": week, "season": 2026},
        },
    }


def _fixture(combos_by_source, tmp):
    doc = {"built_at": "2026-10-02T00:00:00+00:00", "sources": {}}
    for source, combos in combos_by_source.items():
        doc["sources"][source] = {"combos": combos}
    p = Path(tmp) / "data" / "fixtures" / "current" / "comparison-sources-data.json"
    p.write_text(json.dumps(doc))
    return p


class VorpTranslationSummaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_repo = bpc.REPO
        bpc.REPO = Path(self.tmp)
        (Path(self.tmp) / "data" / "fixtures" / "current").mkdir(parents=True)

    def tearDown(self):
        bpc.REPO = self._orig_repo

    def _write(self, combos_by_source):
        return _fixture(combos_by_source, self.tmp)

    def _run(self):
        with patch.object(bpc, "expected_content_week", return_value=5):
            return bpc.build_vorp_translation_summary()

    def _full_ok_combos(self):
        combos = {}
        for source in ("usatoday", "fantasypros", "cbs"):
            combos[source] = {
                f"{sc}_12": _combo("vorp-supabase", 5)
                for sc in ("full", "half", "standard")
            }
        combos["fantasycalc"] = {
            f"{sc}_{t}_qb1": _combo("vorp-supabase", 5)
            for sc in ("full", "half", "standard") for t in (8, 10, 12, 14)
        }
        return combos

    def test_ok_when_all_grains_current(self):
        self._write(self._full_ok_combos())
        s = self._run()
        self.assertEqual(s["status"], "ok", s["reason"])
        self.assertEqual(s["n_ok"], s["n_expected"])
        self.assertGreater(s["n_expected"], 0)

    def test_warn_when_grain_week_stale(self):
        combos = self._full_ok_combos()
        combos["usatoday"]["half_12"] = _combo("vorp-supabase", 4)
        self._write(combos)
        s = self._run()
        self.assertEqual(s["status"], "warn", s["reason"])
        self.assertIn("half_12", s["reason"])
        self.assertIn("4 < 5", s["reason"])

    def test_lagging_source_grain_is_judged_by_its_content_week(self):
        # GAP-VORP-GRAIN-WEEK-LABEL: CBS on Week-4 natives while the chain is
        # in Week 5 is stamped grain week 4 -- correct, not stale.
        combos = self._full_ok_combos()
        combos["cbs"] = {f"{sc}_12": _combo("vorp-supabase", 4) for sc in ("full", "half", "standard")}
        path = self._write(combos)
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["sources"]["cbs"]["week_designated"] = "Week 4"
        path.write_text(json.dumps(doc))
        s = self._run()
        self.assertEqual(s["status"], "ok", s["reason"])
        # ...and a Week-4 grain on a Week-5 section is still stale.
        doc["sources"]["cbs"]["week_designated"] = "Week 5"
        path.write_text(json.dumps(doc))
        s = self._run()
        self.assertEqual(s["status"], "warn", s["reason"])
        self.assertIn("4 < 5", s["reason"])

    def test_warn_when_grain_week_unrecorded(self):
        # Discrimination: pre-JEG-70 provenance stamps week=null. The
        # checkpoint must not call that ok -- it must warn until the chain
        # rewires with the week-stamping fix.
        combos = self._full_ok_combos()
        combos["cbs"]["half_12"] = _combo("vorp-supabase", None)
        self._write(combos)
        s = self._run()
        self.assertEqual(s["status"], "warn", s["reason"])
        self.assertIn("not recorded", s["reason"])

    def test_bad_when_unexpected_fallback(self):
        # JEG-70 acceptance criterion 3: fallback must never be the steady
        # state. A combo the guard does NOT pin, sitting on reindex-fallback,
        # is bad -- not warn.
        combos = self._full_ok_combos()
        combos["fantasypros"]["half_12"] = _combo("reindex-fallback", 5)
        self._write(combos)
        s = self._run()
        self.assertEqual(s["status"], "bad", s["reason"])
        self.assertIn("reindex-fallback", s["reason"])

    def test_bad_when_no_provenance(self):
        combos = self._full_ok_combos()
        del combos["usatoday"]["half_12"]["translation"]
        self._write(combos)
        s = self._run()
        self.assertEqual(s["status"], "bad", s["reason"])

    def test_qb_divergent_siblings_excluded(self):
        # qb2 combos whose natives diverge are pinned to reindex-fallback by
        # design (data-driven guard); they must not trip the checkpoint.
        combos = self._full_ok_combos()
        combos["fantasycalc"]["half_12_qb2"] = {
            "native": {"x": 99.0},  # diverges from qb1 -> guarded
            "reindexed": {"x": 1.0},
            "translation": {
                "method": "reindex-fallback",
                "grain": {"source": "fantasycalc", "scoring": "half_ppr",
                          "league_teams": 12, "week": 5, "season": 2026},
            },
        }
        combos["fantasycalc"]["half_12_qb1"]["native"] = {"x": 1.0}
        self._write(combos)
        s = self._run()
        self.assertEqual(s["status"], "ok", s["reason"])

    def test_unk_when_fixture_missing(self):
        s = self._run()
        self.assertEqual(s["status"], "unk")


class ApplyComboWeekStampTest(unittest.TestCase):
    """Discrimination for the JEG-70 provenance fix: apply_combo must stamp
    week/season into the provenance grain. On the pre-fix code the grain
    recorded week=null/season=null and the checkpoint could never verify
    freshness from the fixture."""

    def test_apply_combo_stamps_week_and_season(self):
        import translate_via_vorp as tvv

        combo = {"reindexed": {"some-player": 42.0}, "player_keys": {}}
        report = tvv.apply_combo(
            "usatoday", "half_12", combo,
            {"12345": 55.0},  # translated keyed by player_key
            fixture_keys={"some-player": "12345"},
            name_keys={},
            week=5, season=2026,
        )
        self.assertEqual(report["method"], "vorp-supabase")
        grain = combo["translation"]["grain"]
        self.assertEqual(grain["week"], 5, "week must be stamped (was null pre-fix)")
        self.assertEqual(grain["season"], 2026, "season must be stamped (was null pre-fix)")


if __name__ == "__main__":
    unittest.main()


class ChainWeekThreadingTest(unittest.TestCase):
    """JEG-70: the chain must pass --week to the translate_via_vorp stage so
    the stage fetches the current week's Supabase grain (fetch_translated
    filters week=eq) instead of silently reusing the default week after
    rollover."""

    def test_process_section_passes_week_to_vorp_stage(self):
        import rebuild_comparison_chain as chain

        cmds = []

        def fake_run(cmd, **kwargs):
            cmds.append(cmd)
            return True, "ok"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            section = repo / "usatoday-half-12-section.json"
            section.write_text("{}")
            # Minimal reindex artifact so process_section reaches the vorp stage
            reindexed = repo / "output" / "reindexed"
            reindexed.mkdir(parents=True)
            # process_section runs reindex first via fake; emulate its output
            orig = fake_run

            def fake2(cmd, **kwargs):
                if Path(cmd[1]).name == "reindex_comparison_section.py":
                    out = Path(cmd[cmd.index("--out") + 1])
                    out.write_text(json.dumps({"combos": {}}))
                    return True, "reindexed"
                return orig(cmd, **kwargs)

            # review must write its artifact with a ready verdict
            def fake3(cmd, **kwargs):
                if Path(cmd[1]).name == "review_comparison_candidate.py":
                    out = Path(cmd[cmd.index("--out") + 1])
                    out.write_text(json.dumps({"verdict": "ready"}))
                    return True, "reviewed"
                if Path(cmd[1]).name == "promote_comparison_section.py":
                    return True, "promoted"
                return fake2(cmd, **kwargs)

            chain.process_section(section, repo, fake3, nfl_week=7)

        vorp_cmds = [c for c in cmds
                     if Path(c[1]).name == "translate_via_vorp.py"]
        self.assertEqual(len(vorp_cmds), 1)
        self.assertIn("--week", vorp_cmds[0])
        self.assertEqual(vorp_cmds[0][vorp_cmds[0].index("--week") + 1], "7")

    def test_process_section_omits_week_when_none(self):
        import rebuild_comparison_chain as chain

        cmds = []

        def fake3(cmd, **kwargs):
            cmds.append(cmd)
            if Path(cmd[1]).name == "reindex_comparison_section.py":
                out = Path(cmd[cmd.index("--out") + 1])
                out.write_text(json.dumps({"combos": {}}))
                return True, "reindexed"
            if Path(cmd[1]).name == "review_comparison_candidate.py":
                out = Path(cmd[cmd.index("--out") + 1])
                out.write_text(json.dumps({"verdict": "ready"}))
                return True, "reviewed"
            if Path(cmd[1]).name == "promote_comparison_section.py":
                return True, "promoted"
            return True, "ok"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            section = repo / "usatoday-half-12-section.json"
            section.write_text("{}")
            chain.process_section(section, repo, fake3)  # nfl_week=None

        vorp_cmds = [c for c in cmds
                     if Path(c[1]).name == "translate_via_vorp.py"]
        self.assertEqual(len(vorp_cmds), 1)
        self.assertNotIn("--week", vorp_cmds[0])


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
        # Fail-safe: failure is reported, not raised (the per-combo
        # vorp-translate stage falls back to reindex).
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
    """2026-10-04 regression: build_vorp_translation_summary must read the
    fixture as COMMITTED (what Pages serves), never the working tree.

    In the shared checkout the working tree is routinely dirty with other
    lanes' uncommitted experiments. A dirty comparison-sources-data.json
    unpinned the data-driven _qb_divergent_siblings guard, so expected
    combos sat on reindex-fallback and this check false-redded `bad` three
    times while production served the committed bytes (which genuinely
    compute to `warn`). committed_fixture_json() closes that hole; these
    tests prove the wiring against a simulated broken state.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_repo = bpc.REPO
        self.addCleanup(setattr, bpc, "REPO", self._orig_repo)

    def _doc(self, bad_combo=False):
        doc = {"built_at": "2026-10-04T00:00:00+00:00", "sources": {}}
        combos = {}
        for source in ("usatoday", "fantasypros", "cbs"):
            combos[source] = {
                f"{sc}_12": _combo("vorp-supabase", 5)
                for sc in ("full", "half", "standard")
            }
        if bad_combo:
            # Working-tree broken state: an unexpected reindex-fallback the
            # guard does not pin -> "bad" if the tree were consulted.
            combos["fantasypros"]["half_12"] = _combo("reindex-fallback", 5)
        else:
            # Committed (served) bytes: one combo with grain week unrecorded
            # (pre-JEG-70 provenance) -> "warn".
            combos["cbs"]["half_12"] = _combo("vorp-supabase", None)
        for source, c in combos.items():
            doc["sources"][source] = {"combos": c}
        return doc

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

    def _run_summary(self, repo):
        bpc.REPO = Path(repo)
        with patch.object(bpc, "expected_content_week", return_value=5):
            return bpc.build_vorp_translation_summary()

    def test_committed_blob_wins_over_dirty_tree(self):
        # End-to-end through the real helper: origin/main holds the clean
        # committed fixture (warn), the working tree holds the dirty fixture
        # that would report bad. The summary must report warn -- proving the
        # tree is not consulted. Fails on pre-fix code (reads tree -> bad).
        repo = Path(self.tmp) / "repo"
        self._init_git_repo(repo, self._doc(bad_combo=False))
        self._write_tree(repo, self._doc(bad_combo=True))  # dirty the tree
        s = self._run_summary(repo)
        self.assertEqual(s["status"], "warn", s["reason"])
        self.assertIn("not recorded", s["reason"])

    def test_helper_prefers_committed_over_head_and_tree(self):
        # Precedence: origin/main > HEAD > working tree.
        repo = Path(self.tmp) / "repo2"
        committed = self._doc(bad_combo=False)
        self._init_git_repo(repo, committed)
        self._write_tree(repo, self._doc(bad_combo=True))
        bpc.REPO = Path(repo)
        data, label = bpc.committed_fixture_json(
            "data/fixtures/current/comparison-sources-data.json")
        self.assertEqual(label, "origin/main")
        self.assertEqual(data, committed)

    def test_unk_when_committed_read_fails_everywhere(self):
        # No committed blob, no HEAD, no tree file -> unk (never a failure
        # claim). Pre-fix code had no committed_fixture_json helper, so this
        # patch raises AttributeError there: the wiring itself is asserted.
        with patch.object(bpc, "expected_content_week", return_value=5), \
             patch.object(bpc, "committed_fixture_json",
                          return_value=(None, "unreadable")):
            s = bpc.build_vorp_translation_summary()
        self.assertEqual(s["status"], "unk")
