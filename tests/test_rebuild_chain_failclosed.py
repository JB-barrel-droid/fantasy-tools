"""Fail-closed regression tests for pipelines/rebuild_comparison_chain.py.

These tests pin the validation-bypass repair (2026-09-29): the chain used
to rewrite review 'hold' verdicts to 'ready' (with a fabricated
auto_promotion_justification) and unconditionally force 'ready' on retry,
then treat partial/zero promotion as success. Every bypass below is
negative-tested against a simulated broken state — a guard that only
asserts current behavior without checking which state is right is worse
than no guard.

All stage scripts are faked (no subprocess); all filesystem writes go to
tmp dirs; the real repo is never touched.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINES = Path(__file__).resolve().parent.parent / "pipelines"
sys.path.insert(0, str(PIPELINES))
import rebuild_comparison_chain as chain  # noqa: E402


class WireFake:
    """Simulates the stage scripts with deterministic on-disk artifacts.

    verdicts maps section stem -> review verdict ("ready", "hold", ...).
    The special verdict "__no_file__" simulates a reviewer that crashes
    without writing its artifact.
    """

    def __init__(self, repo, verdicts=None):
        self.repo = Path(repo)
        self.verdicts = verdicts or {}
        self.calls = []  # stage script names, in call order
        self._tick = 0

    def _touch(self, path, content="{}"):
        # Distinct increasing mtimes so newest_file() picks deterministically.
        self._tick += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        os.utime(path, (self._tick, self._tick))
        return path

    def __call__(self, cmd, **kwargs):
        script = Path(cmd[1]).name
        self.calls.append(script)
        repo = self.repo

        if script == "match_source_snapshot.py":
            snap = Path(cmd[cmd.index("--input") + 1])
            source = snap.relative_to(repo / "data" / "raw" / "sources").parts[0]
            self._touch(repo / "output" / "matched" / source / "x-matched.json",
                        json.dumps({"matched": True}))
            return True, ""

        if script == "build_source_reference.py":
            matched = Path(cmd[cmd.index("--input") + 1])
            source = matched.relative_to(repo / "output" / "matched").parts[0]
            # Two refs per source -> two sections, for partial-promotion tests.
            for ref_name in ("x-a-reference.json", "x-b-reference.json"):
                self._touch(
                    repo / "output" / "references" / source / "2026-09-29" / ref_name,
                    json.dumps({"reference": ref_name}))
            return True, ""

        if script == "build_comparison_source_section.py":
            ref = Path(cmd[cmd.index("--input") + 1])
            rel = ref.relative_to(repo / "output" / "references")
            source, vintage = rel.parts[0], rel.parts[1]
            self._touch(
                repo / "output" / "comparison-candidates" / source / vintage
                / f"{ref.stem}-section.json",
                json.dumps({"section": ref.stem}))
            return True, ""

        if script == "reindex_comparison_section.py":
            out = Path(cmd[cmd.index("--out") + 1])
            self._touch(out, json.dumps({"reindexed": True}))
            return True, ""

        if script == "review_comparison_candidate.py":
            inp = Path(cmd[2])
            out = Path(cmd[cmd.index("--out") + 1])
            stem = inp.name.replace("-reindexed.json", "")
            verdict = self.verdicts.get(stem, self.verdicts.get("*", "ready"))
            if verdict == "__no_file__":
                return False, "review crashed"
            self._touch(out, json.dumps({
                "verdict": verdict,
                "checks": [{"name": "coverage:x",
                            "status": "fail" if verdict != "ready" else "pass"}],
            }))
            # Mirror the real reviewer: exit 2 on hold, 0 on ready.
            return verdict == "ready", ""

        if script == "promote_comparison_section.py":
            review_path = Path(cmd[2])
            data = json.loads(review_path.read_text())
            # Faithful to the real promoter: refuse non-ready verdicts.
            if data.get("verdict") != "ready":
                return False, "promotion refused: review verdict is not 'ready'"
            return True, ""

        if script == "build_cbsros_ddf_leg.py":
            return True, ""

        if script == "build_cbsros_section_from_ddf_leg.py":
            combos = {}
            for s in ("full", "half", "standard"):
                for t in (8, 10, 12, 14):
                    combos[f"{s}_{t}"] = {
                        # aaron rodgers 0.0: waiver-tier legitimately scores
                        # zero under DDF two-tier (must NOT fail review).
                        "values": {"jahmyr gibbs": 70.0, "bijan robinson": 54.7,
                                   "aaron rodgers": 0.0},
                        "native": {"jahmyr gibbs": 20.5, "bijan robinson": 18.2,
                                   "aaron rodgers": 13.9},
                    }
            fixture = {"sources": {"cbsros": {
                "combos": combos,
                "vintage": "2026-09-29",
            }}}
            fpath = repo / "data" / "fixtures" / "current" / "comparison-sources-data.json"
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(json.dumps(fixture))
            return True, ""

        if script == "build_adjustment_inputs.py":
            live = (repo / "app" / "trade-value-chart" / "assets"
                    / "adjustment-inputs.json")
            self._touch(live, json.dumps({"cells": []}))
            return True, ""

        if script == "build_adjusted_fixture_sections.py":
            return True, ""

        if script == "build_ddf_two_tier_leg.py":
            # Fake a DDF leg bake: write a leg dir with the snapshot vintage
            # so the ESPN review gate's newest-leg check passes.
            scoring = cmd[cmd.index("--scoring") + 1]
            teams = cmd[cmd.index("--teams") + 1]
            leg_dir = (repo / "data" / "ddf-two-tier"
                       / f"ddf-20260929-espn-{scoring}-{teams}t-0p15")
            self._touch(
                leg_dir / "ddf_leg.json",
                json.dumps({
                    "generated_at": "2026-09-30T00:00:00Z",
                    "inputs": {"espn_snapshot_date": "2026-09-29"},
                }))
            return True, ""

        if script == "build_espn_section_from_ddf_leg.py":
            combos = {}
            for s in ("full", "half", "standard"):
                for t in (8, 10, 12, 14):
                    combos[f"{s}_{t}"] = {
                        "values": {"jahmyr gibbs": 70.0, "bijan robinson": 54.7},
                        "native": {"jahmyr gibbs": 20.5, "bijan robinson": 18.2},
                    }
            fixture = {"sources": {"espn": {
                "combos": combos,
                "espn_snapshot": "2026-09-29",
                "value_provenance": "modeled",
            }}}
            fpath = repo / "data" / "fixtures" / "current" / "comparison-sources-data.json"
            fpath.parent.mkdir(parents=True, exist_ok=True)
            # Merge with any existing fixture (cbsros may have written first).
            existing = {}
            if fpath.is_file():
                existing = json.loads(fpath.read_text())
            existing.setdefault("sources", {}).update(fixture["sources"])
            fpath.write_text(json.dumps(existing))
            return True, ""

        raise AssertionError(f"unexpected stage script: {script}")


def make_repo(tmp, sources):
    """Fake repo tree with one snapshot per source."""
    repo = Path(tmp)
    for source in sources:
        snap_dir = repo / "data" / "raw" / "sources" / source / "2026-09-29"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "snapshot.json").write_text(json.dumps({"tables": []}))
    return repo


class FailClosedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="chain-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = make_repo(self.tmp, ("usatoday",))

    def _run_source(self, verdicts, source="usatoday", repo=None):
        fake = WireFake(repo or self.repo, verdicts=verdicts)
        result = chain.run_source(source, repo=repo or self.repo, run_fn=fake)
        return result, fake

    # --- the bypass repair -------------------------------------------------
    def test_hold_verdict_is_never_rewritten(self):
        """A hold stays a hold on disk: no verdict edit, no justification."""
        result, fake = self._run_source({"*": "hold"})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stage"], "review")
        review_files = list((self.repo / "output" / "reviewed").rglob("*-review.json"))
        self.assertTrue(review_files, "expected review artifacts on disk")
        for rf in review_files:
            data = json.loads(rf.read_text())
            self.assertEqual(data["verdict"], "hold")
            self.assertNotIn("auto_promotion_justification", data)
            self.assertNotIn("promoted_by", data)

    def test_hold_never_promotes(self):
        """Promote is not invoked for a held section."""
        result, fake = self._run_source({"*": "hold"})
        self.assertNotIn("promote_comparison_section.py", fake.calls)
        self.assertEqual(result["promoted"], 0)

    def test_no_verdict_rewrite_code_paths_remain(self):
        """Static guard: the bypass mechanisms must not reappear."""
        src = Path(chain.__file__).read_text()
        self.assertNotIn("auto_promotion_justification", src)
        self.assertNotIn('["verdict"] = "ready"', src)
        self.assertNotIn("['verdict'] = 'ready'", src)

    # --- halt semantics ----------------------------------------------------
    def test_first_hold_stops_later_sections(self):
        """Deterministic order: a-section (ready) promotes, b-section (hold)
        halts, c-section is never processed."""
        fake = WireFake(self.repo, verdicts={
            "a-section": "ready", "b-section": "hold", "c-section": "ready"})
        promoted, halted = [], None
        for name in ("a-section", "b-section", "c-section"):
            sec = self.repo / f"{name}.json"
            sec.write_text("{}")
            try:
                chain.process_section(sec, self.repo, fake)
                promoted.append(name)
            except chain.ChainHalt as h:
                halted = (name, h.stage)
                break
        self.assertEqual(promoted, ["a-section"])
        self.assertEqual(halted, ("b-section", "review"))
        reindexed = {p.name for p in (self.repo / "output" / "reindexed").glob("*")}
        self.assertNotIn("c-section-reindexed.json", reindexed)

    def test_partial_promotion_is_failure(self):
        """First section promotes, second holds -> source failed, and the
        promoted/section counts expose the partial run."""
        fake = WireFake(self.repo, verdicts={"*": "ready"})
        orig = fake.__call__

        def flipping(cmd, **kwargs):
            if (Path(cmd[1]).name == "review_comparison_candidate.py"
                    and "promote_comparison_section.py" in fake.calls):
                fake.verdicts["*"] = "hold"
            return orig(cmd, **kwargs)

        result = chain.run_source("usatoday", repo=self.repo, run_fn=flipping)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stage"], "review")
        self.assertEqual(result["sections"], 2)
        self.assertEqual(result["promoted"], 1)

    def test_zero_promotion_is_failure(self):
        result, _ = self._run_source({"*": "hold"})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["promoted"], 0)
        self.assertGreater(result["sections"], 0)

    def test_match_failure_halts_before_later_stages(self):
        fake = WireFake(self.repo)
        orig = fake.__call__

        def boom(cmd, **kwargs):
            if Path(cmd[1]).name == "match_source_snapshot.py":
                fake.calls.append("match_source_snapshot.py")
                return False, "matcher exploded"
            return orig(cmd, **kwargs)

        result = chain.run_source("usatoday", repo=self.repo, run_fn=boom)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stage"], "match")
        for s in ("build_source_reference.py",
                  "build_comparison_source_section.py",
                  "reindex_comparison_section.py",
                  "review_comparison_candidate.py",
                  "promote_comparison_section.py"):
            self.assertNotIn(s, fake.calls)

    def test_missing_review_artifact_halts(self):
        result, fake = self._run_source({"*": "__no_file__"})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stage"], "review")
        self.assertNotIn("promote_comparison_section.py", fake.calls)

    def test_garbage_verdict_halts(self):
        result, fake = self._run_source({"*": "banana"})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stage"], "review")
        self.assertNotIn("promote_comparison_section.py", fake.calls)

    # --- fit gating --------------------------------------------------------
    def test_fit_skipped_when_any_source_fails(self):
        """Only usatoday has a snapshot; the other four sources fail at the
        snapshot stage, so the fit must not run."""
        fake = WireFake(self.repo, verdicts={"*": "ready"})
        status = chain.execute_chain(nfl_week=4, repo=self.repo, run_fn=fake)
        self.assertNotIn("build_adjustment_inputs.py", fake.calls)
        self.assertFalse(status["success"])
        self.assertEqual(status["fit"]["status"], "skipped")

    def test_fit_runs_when_all_sources_succeed(self):
        repo = make_repo(self.tmp / "all", tuple(chain.SOURCES))
        fake = WireFake(repo, verdicts={"*": "ready"})
        status = chain.execute_chain(nfl_week=4, repo=repo, run_fn=fake)
        self.assertIn("build_adjustment_inputs.py", fake.calls)
        self.assertTrue(status["success"])
        self.assertEqual(status["fit"]["status"], "ok")

    # --- status durability -------------------------------------------------
    def test_status_written_on_unexpected_exception(self):
        """The finally path records partial runs even when a stage blows up
        outside ChainHalt."""
        fake = WireFake(self.repo)

        def boom(cmd, **kwargs):
            raise RuntimeError("unexpected stage crash")

        status = chain.execute_chain(nfl_week=4, repo=self.repo, run_fn=boom)
        status_path = self.repo / "output" / "comparison-chain-status.json"
        self.assertTrue(status_path.is_file())
        on_disk = json.loads(status_path.read_text())
        self.assertFalse(on_disk["success"])
        self.assertFalse(status["success"])
        self.assertEqual(on_disk["detail"]["usatoday"]["stage"], "error")
        # dist copy for the dashboard too
        self.assertTrue((self.repo / "dist" / "modules"
                         / "comparison-chain-status.json").is_file())

    def test_status_shape_kept_for_dashboard(self):
        """The checkpoints builder consumes run_at/runner/success/sources."""
        repo = make_repo(self.tmp / "shape", tuple(chain.SOURCES))
        fake = WireFake(repo, verdicts={"*": "ready"})
        status = chain.execute_chain(nfl_week=4, repo=repo, run_fn=fake)
        for key in ("run_at", "nfl_week", "sources", "failed", "success", "runner"):
            self.assertIn(key, status)
        # Honest runner label; the old "muse-cron" mislabel is gone.
        self.assertIn(status["runner"], ("github-actions", "local"))
        self.assertNotEqual(status["runner"], "muse-cron")

    def test_all_ready_end_to_end(self):
        result, fake = self._run_source({"*": "ready"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["stage"], "complete")
        self.assertEqual(result["promoted"], result["sections"])
        self.assertGreater(result["sections"], 0)

    # --- stage 8 (adjusted sections) gating --------------------------------
    def test_adjusted_sections_skipped_when_fit_fails(self):
        """Stage 8 runs only after a successful fit; a failed fit skips it
        and the chain reports failure."""
        repo = make_repo(self.tmp / "adj", tuple(chain.SOURCES))
        fake = WireFake(repo, verdicts={"*": "ready"})
        orig = fake.__call__

        def no_fit(cmd, **kwargs):
            if Path(cmd[1]).name == "build_adjustment_inputs.py":
                fake.calls.append("build_adjustment_inputs.py")
                return False, "fit exploded"
            return orig(cmd, **kwargs)

        status = chain.execute_chain(nfl_week=4, repo=repo, run_fn=no_fit)
        self.assertNotIn("build_adjusted_fixture_sections.py", fake.calls)
        self.assertFalse(status["success"])
        self.assertEqual(status["fit"]["status"], "failed")

    def test_adjusted_sections_failure_fails_chain(self):
        """A Stage 8 failure is terminal: chain success is False."""
        repo = make_repo(self.tmp / "adj2", tuple(chain.SOURCES))
        fake = WireFake(repo, verdicts={"*": "ready"})
        orig = fake.__call__

        def bad_adjusted(cmd, **kwargs):
            if Path(cmd[1]).name == "build_adjusted_fixture_sections.py":
                fake.calls.append("build_adjusted_fixture_sections.py")
                return False, "adjusted build exploded"
            return orig(cmd, **kwargs)

        status = chain.execute_chain(nfl_week=4, repo=repo, run_fn=bad_adjusted)
        self.assertFalse(status["success"])
        self.assertIn("adjusted_sections", status["failed"])

    # --- cbsros chain: DDF-leg path, never the quantile-reindex path ---------
    def _run_cbsros(self, repo=None, run_fn=None):
        repo = repo or make_repo(self.tmp / "cbsros", ("cbsros",))
        fake = run_fn or WireFake(repo)
        return chain.run_cbsros_source("cbsros", nfl_week=4, repo=repo, run_fn=fake), fake

    def test_cbsros_chain_ok_end_to_end(self):
        """cbsros rebuilds snapshot -> 12 legs -> section and passes review."""
        result, fake = self._run_cbsros()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["stage"], "complete")
        self.assertEqual(result["promoted"], 1)
        self.assertEqual(result["sections"], 1)
        leg_calls = [c for c in fake.calls if c == "build_cbsros_ddf_leg.py"]
        self.assertEqual(len(leg_calls), 12, "one leg build per scoring x teams")
        self.assertIn("build_cbsros_section_from_ddf_leg.py", fake.calls)

    def test_cbsros_chain_never_quantile_reindexes(self):
        """Defect guard: cbsros must not go through the ESPN-anchor
        quantile-reindex path (it would transform the DDF-direct values)."""
        result, fake = self._run_cbsros()
        self.assertEqual(result["status"], "ok")
        for banned in ("match_source_snapshot.py",
                       "build_source_reference.py",
                       "build_comparison_source_section.py",
                       "reindex_comparison_section.py",
                       "review_comparison_candidate.py",
                       "promote_comparison_section.py"):
            self.assertNotIn(banned, fake.calls, banned)

    def test_cbsros_review_halts_on_malformed_section(self):
        """The cbsros review is a real gate: a malformed section halts the
        chain fail-closed at the review stage (not a silent pass)."""
        repo = make_repo(self.tmp / "cbsros-bad", ("cbsros",))
        fake = WireFake(repo)
        orig = fake.__call__

        def bad_section(cmd, **kwargs):
            if Path(cmd[1]).name == "build_cbsros_section_from_ddf_leg.py":
                fake.calls.append("build_cbsros_section_from_ddf_leg.py")
                # Write a section missing combos -> review must halt.
                fpath = (repo / "data" / "fixtures" / "current"
                         / "comparison-sources-data.json")
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(json.dumps({"sources": {"cbsros": {"combos": {}}}}))
                return True, ""
            return orig(cmd, **kwargs)

        result = chain.run_cbsros_source("cbsros", nfl_week=4, repo=repo, run_fn=bad_section)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stage"], "review")
        self.assertIn("missing combos", result["detail"])

    def test_cbsros_leg_failure_halts(self):
        """A DDF leg build failure halts the cbsros chain at the leg stage."""
        repo = make_repo(self.tmp / "cbsros-legfail", ("cbsros",))
        fake = WireFake(repo)
        orig = fake.__call__

        def bad_leg(cmd, **kwargs):
            if Path(cmd[1]).name == "build_cbsros_ddf_leg.py":
                fake.calls.append("build_cbsros_ddf_leg.py")
                return False, "leg exploded"
            return orig(cmd, **kwargs)

        result = chain.run_cbsros_source("cbsros", nfl_week=4, repo=repo, run_fn=bad_leg)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stage"], "leg")
        self.assertNotIn("build_cbsros_section_from_ddf_leg.py", fake.calls)


if __name__ == "__main__":
    unittest.main()
