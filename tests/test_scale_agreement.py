"""Regression: the scale-agreement builder must flag simulated broken states.

These tests prove the verdict logic distinguishes genuine inter-source
disagreement from indexation artifacts introduced by our own reindexing --
using synthetic inputs, not just asserting the current fixture's verdicts.
A guard that only asserts current behavior is worse than no guard.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipelines"))
from build_scale_agreement import verdict_for, in_band, BAND_LOW, BAND_HIGH


class VerdictLogicTest(unittest.TestCase):
    def test_agreement_when_both_in_band(self):
        verdict, _ = verdict_for(1.0, 1.0)
        self.assertEqual(verdict, "agreement")

    def test_agreement_at_band_edges(self):
        # Exactly on the band edges counts as agreement (inclusive band,
        # matching the chart's peakAgreement which uses < low / > high).
        verdict, _ = verdict_for(BAND_LOW, BAND_HIGH)
        self.assertEqual(verdict, "agreement")

    def test_genuine_disagreement_when_native_shape_differs(self):
        # Simulated broken state 1: the source's PUBLISHED shape already
        # differs from the anchor (e.g. FantasyPros QB at 0.74x shape).
        # The reindex did not cause this.
        verdict, reason = verdict_for(0.74, 0.47)
        self.assertEqual(verdict, "genuine disagreement")
        self.assertIn("before any indexation", reason)

    def test_genuine_disagreement_when_shape_high(self):
        verdict, _ = verdict_for(1.50, 0.77)
        self.assertEqual(verdict, "genuine disagreement")

    def test_indexation_artifact_when_shape_tracks_but_reindexed_diverges(self):
        # Simulated broken state 2: the source's published shape TRACKS the
        # anchor (1.03x) but the reindexed output is 0.53x -- our reindexing
        # broke it (e.g. USA Today QB). This is the defect class the section
        # exists to catch.
        verdict, reason = verdict_for(1.03, 0.53)
        self.assertEqual(verdict, "indexation artifact")
        self.assertIn("reindex", reason)

    def test_indexation_artifact_when_reindexed_high(self):
        verdict, _ = verdict_for(1.0, 1.50)
        self.assertEqual(verdict, "indexation artifact")

    def test_native_disagreement_wins_over_artifact(self):
        # If the native shape already differs, the verdict is genuine
        # disagreement even when the reindexed also diverges -- the reindex
        # did not introduce a disagreement that was already there.
        verdict, _ = verdict_for(0.50, 0.50)
        self.assertEqual(verdict, "genuine disagreement")

    def test_band_matches_chart_health(self):
        # The builder must judge by the same band the chart judges by.
        # value-model.js: PEAK_AGREEMENT_LOW = 0.80, PEAK_AGREEMENT_HIGH = 1.25.
        self.assertEqual(BAND_LOW, 0.80)
        self.assertEqual(BAND_HIGH, 1.25)
        chart_vm = (
            Path(__file__).resolve().parent.parent
            / "app" / "trade-value-chart" / "assets" / "value-model.js"
        )
        text = chart_vm.read_text(encoding="utf-8")
        self.assertIn("PEAK_AGREEMENT_LOW = 0.80", text)
        self.assertIn("PEAK_AGREEMENT_HIGH = 1.25", text)

    def test_in_band_helper(self):
        self.assertTrue(in_band(1.0))
        self.assertTrue(in_band(0.80))
        self.assertTrue(in_band(1.25))
        self.assertFalse(in_band(0.79))
        self.assertFalse(in_band(1.26))


class BuilderOutputTest(unittest.TestCase):
    def test_builder_produces_required_fields(self):
        # The builder must run against the real fixture and emit every field
        # the spec requires per cell.
        import json
        import subprocess

        repo = Path(__file__).resolve().parent.parent
        subprocess.run(
            [sys.executable, "pipelines/build_scale_agreement.py"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        data = json.loads((repo / "dist" / "modules" / "scale-agreement.json").read_text(encoding="utf-8"))
        self.assertEqual(data["anchor"], "espn")
        self.assertEqual(data["band"], [0.80, 1.25])
        self.assertIn(data["status"], ("ok", "warn", "bad"))
        required = {
            "anchor_scale",
            "native_scale",
            "reindexed_scale",
            "native_vs_anchor",
            "reindexed_vs_native",
            "reindexed_vs_anchor",
            "verdict",
        }
        for src, sdata in data["sources"].items():
            for pos in ("QB", "RB", "WR", "TE"):
                cell = sdata["cells"][pos]
                self.assertTrue(
                    required <= set(cell.keys()),
                    f"{src}/{pos} missing fields: {required - set(cell.keys())}",
                )
                self.assertIn(
                    cell["verdict"],
                    ("agreement", "genuine disagreement", "indexation artifact", "insufficient data"),
                )


if __name__ == "__main__":
    unittest.main()
