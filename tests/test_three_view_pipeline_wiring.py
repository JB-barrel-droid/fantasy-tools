"""JEG-242: the three-view pipeline is wired through a versioned refresh path.

The parent defect: build_imputed_vorps / build_reweighted_values existed as
modules but NOTHING invoked them -- no Makefile target, no refresh path, no
required test. The old refresh (pipelines/refresh_vorp_translation.py) still
runs the legacy unified.translate_source method.

This module pins the wiring:
  Positive (must pass):
    - pipelines/refresh_vorp_views.py runs the real producers end-to-end on
      fixtures, gates the candidate with review_batch70_views, and writes a
      versioned run manifest pinning every input hash. No Supabase, no
      promotion, candidate only.
    - the Makefile names this wiring: the refresh target exists and this
      module is registered in the required test-unit list.
  Negative regressions against the exact parent defect (each must FAIL the
  old/unwired state):
    - the refresh orchestrator never imports the legacy unified.translate_source
      path; a grep of its source finds no legacy reference.
    - invoking the refresh without --controls/--reference exits nonzero
      (no invented weights; the weighting decision stays with Jeremy).
    - a tampered publisher values file mid-refresh aborts nonzero and the
      run manifest is never written (no partial refresh looks complete).
    - an unknown source file in the values dir is ignored, not silently
      admitted (only SOURCE_KINDS members are eligible).
"""
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(REPO / "pipelines"))

from refresh_vorp_views import main as refresh_main  # noqa: E402
from build_reweighted_values import SOURCE_KINDS  # noqa: E402

ROSTER = {
    "schema": "option-c-publisher-roster-v1",
    "teams": 12,
    "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1},
    "flex_count": 1,
    "flex_eligible": ["RB", "WR", "TE"],
    "bench_total": 72,
    "scoring": "half_ppr",
}

GROUP_TARGETS = {
    ("QB", "starter"): 148.84, ("QB", "bench"): 26.27,
    ("RB", "starter"): 995.91, ("RB", "bench"): 175.75,
    ("WR", "starter"): 975.04, ("WR", "bench"): 172.07,
    ("TE", "starter"): 145.73, ("TE", "bench"): 23.38,
}

CONTROLS = {
    "QB/starter": 100.0, "QB/bench": 20.0,
    "RB/starter": 800.0, "RB/bench": 150.0,
    "WR/starter": 800.0, "WR/bench": 150.0,
    "TE/starter": 120.0, "TE/bench": 25.0,
}


def _synthetic_values(seed_offset=0.0):
    counts = {"QB": 20, "RB": 70, "WR": 90, "TE": 40}
    queues = {pos: [f"{pos}-{i}" for i in range(n)] for pos, n in counts.items()}
    order = []
    while any(queues.values()):
        for pos in ("QB", "RB", "WR", "TE"):
            if queues[pos]:
                order.append((pos, queues[pos].pop(0)))
    values, key = {}, 90001
    for rank, (pos, _tag) in enumerate(order):
        values[str(key)] = [pos, 1000.0 - rank * 0.5 + seed_offset]
        key += 1
    return values


def _group_vorps_artifact():
    return {
        "teams": 12, "scoring": "half_ppr", "units": "raw_surplus_ppg",
        "roster": {
            "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1},
            "flex_count": 1, "flex_eligible": ["RB", "WR", "TE"],
            "bench_mix": {"QB": 12, "RB": 24, "WR": 24, "TE": 12},
        },
        "groups": [
            {"position": p, "role": r, "total_vorp": GROUP_TARGETS[(p, r)]}
            for p, r in [("QB", "starter"), ("QB", "bench"), ("RB", "starter"),
                         ("RB", "bench"), ("WR", "starter"), ("WR", "bench"),
                         ("TE", "starter"), ("TE", "bench")]
        ],
    }


def _fixture(tmp: Path):
    values_dir = tmp / "values"
    values_dir.mkdir()
    (values_dir / "fantasycalc.json").write_text(json.dumps(_synthetic_values()))
    (values_dir / "usat.json").write_text(json.dumps(_synthetic_values(37.0)))
    (tmp / "group_vorps.json").write_text(json.dumps(_group_vorps_artifact()))
    (tmp / "roster.json").write_text(json.dumps(ROSTER))
    (tmp / "controls.json").write_text(json.dumps(CONTROLS))
    return {
        "--values-dir": str(values_dir),
        "--group-vorps": str(tmp / "group_vorps.json"),
        "--roster-config": str(tmp / "roster.json"),
        "--controls": str(tmp / "controls.json"),
        "--out-dir": str(tmp / "out"),
    }


def _run_refresh(argdict):
    argv = []
    for k, v in argdict.items():
        argv += [k, v]
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = refresh_main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue() + err.getvalue()


class ThreeViewPipelineWiringTests(unittest.TestCase):
    def test_refresh_wires_producers_review_and_manifest(self):
        """End-to-end candidate refresh: impute -> reweight -> review gate ->
        versioned run manifest. Candidate only: no Supabase, no promotion."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            args = _fixture(tmp)
            code, log = _run_refresh(args)
            self.assertEqual(code, 0, f"refresh failed:\n{log}")
            out = tmp / "out"
            candidate = json.loads((out / "candidate.json").read_text())
            self.assertEqual(candidate["schema"], "shared-batch70-views-v1")
            self.assertEqual(candidate["artifact_status"], "candidate")
            manifest = json.loads((out / "refresh-run.manifest.json").read_text())
            self.assertEqual(manifest["schema"], "vorp-views-refresh-run-v1")
            self.assertEqual(manifest["weight_selection"], "controls")
            self.assertEqual(manifest["promotion"], "none: candidate only; promotion is a separate reviewed step")
            self.assertEqual(set(manifest["sources_included"]), {"fantasycalc", "usat", "avg"})
            self.assertEqual(manifest["steps"], ["impute", "avg_backstop", "reweight", "review"])
            self.assertEqual(manifest["avg_backstop"]["target_count"], 168)
            self.assertEqual(manifest["avg_backstop"]["method"], "cross-source-average-v1")
            self.assertIn("avg", candidate["sources"])
            self.assertEqual(candidate["sources"]["avg"]["indexed"], {})
            # Every known source is accounted for: included or explicitly excluded.
            self.assertEqual(set(manifest["sources_included"]) | set(manifest["excluded_sources"]),
                             set(SOURCE_KINDS))
            # Every input hash is pinned; the manifest pins the candidate bytes.
            self.assertIn("values/fantasycalc", manifest["input_sha256"])
            self.assertIn("pre_backstop_batch", manifest["input_sha256"])
            self.assertIn("backstopped_batch", manifest["input_sha256"])
            self.assertIn("controls", manifest["input_sha256"])
            self.assertEqual(len(manifest["candidate_sha256"]), 64)
            # The review report is embedded: all gates ran and passed.
            report = "\n".join(manifest["review_report"])
            self.assertIn("gate 8/8 batch admission: OK", report)
            self.assertIn("REVIEW PASSED", report)

    def test_refresh_rejects_missing_weight_selection(self):
        """No --controls/--reference: the refresh must not invent weights.
        The weighting/horizon decision stays with Jeremy."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            args = _fixture(tmp)
            del args["--controls"]
            code, _log = _run_refresh(args)
            self.assertNotEqual(code, 0)

    def test_tampered_values_aborts_before_manifest(self):
        """A corrupted publisher values file mid-refresh aborts nonzero and
        leaves no run manifest behind: a partial refresh never looks complete."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            args = _fixture(tmp)
            values_dir = Path(args["--values-dir"])
            (values_dir / "fantasycalc.json").write_text("{not valid json")
            code, log = _run_refresh(args)
            self.assertNotEqual(code, 0, f"tampered refresh unexpectedly passed:\n{log}")
            self.assertFalse((tmp / "out" / "refresh-run.manifest.json").exists())

    def test_unknown_source_file_not_admitted(self):
        """A values file for a source outside SOURCE_KINDS is ignored, never
        silently admitted into the batch."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            args = _fixture(tmp)
            (Path(args["--values-dir"]) / "mystery.json").write_text(json.dumps(_synthetic_values()))
            code, log = _run_refresh(args)
            self.assertEqual(code, 0, f"refresh failed:\n{log}")
            manifest = json.loads((tmp / "out" / "refresh-run.manifest.json").read_text())
            self.assertNotIn("mystery", manifest["sources_included"])
            self.assertNotIn("mystery", manifest["excluded_sources"])

    def test_refresh_really_invokes_avg_backstop_stage(self):
        """Regression for the 2026-10-03 integration trap: the AVG/backstop
        helper existed with tests but refresh_vorp_views never invoked it."""
        src = (REPO / "pipelines" / "refresh_vorp_views.py").read_text()
        self.assertIn("backstop_main", src)
        self.assertIn("avg_backstop", src)
        self.assertIn("vorp-source-batch-augmented-v1.json", src)

    def test_orchestrator_does_not_touch_legacy_path(self):
        """The parent defect's signature: the old refresh runs
        unified.translate_source. The new orchestrator must not import or
        reference it -- wiring the old method back in would reintroduce the
        defect this ticket fixes."""
        src = (REPO / "pipelines" / "refresh_vorp_views.py").read_text()
        self.assertNotRegex(src, r"\btranslate_source\b")
        self.assertNotRegex(src, r"from unified import|import unified\b")
        self.assertNotRegex(src, r"refresh_vorp_translation")

    def test_makefile_names_the_wiring(self):
        """The wiring is only real if the Makefile names it: the refresh
        target exists and this module is in the required test-unit list."""
        makefile = (REPO / "Makefile").read_text()
        self.assertRegex(makefile, r"(?m)^refresh-vorp-views:")
        self.assertIn("tests.test_three_view_pipeline_wiring", makefile)
        unit_section = makefile.split("test-unit:")[1].split("test-integration:")[0]
        self.assertIn("tests.test_three_view_pipeline_wiring", unit_section)


if __name__ == "__main__":
    unittest.main()
