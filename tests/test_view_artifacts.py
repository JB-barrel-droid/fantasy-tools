"""JEG-265: per-view addressable artifacts (vorp-view.json, adj-view.json).

The dashboard renders one card per view reading only that view's artifact.
Both must be non-empty, carry their view tag (vorp / adj), and survive a
sync run that has the lineage artifact available.

Discrimination: the test fails if either artifact is missing/empty in a
fixture run, or if its view tag is wrong.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_view_builder():
    """Import pipelines/build_view_artifacts.py without making it a package."""
    if str(REPO / "pipelines") not in sys.path:
        sys.path.insert(0, str(REPO / "pipelines"))
    sys.modules.pop("build_view_artifacts", None)
    return importlib.import_module("build_view_artifacts")


def _fixture_lineage():
    """A minimal but realistic source-value-lineage fixture."""
    rows = [
        {"player_key": "p1", "native": 100.0, "group": "QB|Starter",
         "alloc_factor": 0.5, "our_group_vorp": 50.0, "imputed_vorp": 50.0,
         "ddf_rebuilt": 100.0, "indexed": 70.0, "index_mult": 0.7,
         "reweight_mult": 1.0, "reweighted": 70.0, "chart_value": 70.0,
         "chart_matches_indexed": True},
        {"player_key": "p2", "native": 90.0, "group": "RB|Starter",
         "alloc_factor": 0.4, "our_group_vorp": 36.0, "imputed_vorp": 36.0,
         "ddf_rebuilt": 90.0, "indexed": 60.0, "index_mult": 0.67,
         "reweight_mult": 0.95, "reweighted": 57.0, "chart_value": 60.0,
         "chart_matches_indexed": False},
    ]
    return {
        "generated_at": "2026-10-03T00:00:00+00:00",
        "sources": {
            "fantasypros": {
                "label": "FantasyPros",
                "top25": rows,
                "vorp_round_trip": {"method": "published",
                                    "positions": {"QB": {"waiver_line_value": 5.0, "n_rostered": 12, "n_dedicated": 12, "n_flex": 0, "n_bench": 72, "waiver_method": "roster_determined"}},
                                    "error": None},
            },
        },
    }


class ViewArtifactsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)
        # Mirror the dist/modules layout the builder writes.
        (self.tmp_path / "modules").mkdir()
        self.lineage = _fixture_lineage()
        (self.tmp_path / "modules" / "source-value-lineage.json").write_text(
            json.dumps(self.lineage), encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_both_artifacts_present_and_non_empty(self):
        b = _load_view_builder()
        # Patch the builder's output paths to the temp dir.
        b.LINEAGE_PATH = str(self.tmp_path / "modules" / "source-value-lineage.json")
        b.VORP_OUT = str(self.tmp_path / "modules" / "vorp-view.json")
        b.ADJ_OUT = str(self.tmp_path / "modules" / "adj-view.json")

        rc = b.main()
        self.assertEqual(rc, 0)

        for name in ("vorp-view.json", "adj-view.json"):
            p = self.tmp_path / "modules" / name
            self.assertTrue(p.exists(), f"missing artifact: {name}")
            self.assertGreater(p.stat().st_size, 10,
                               f"artifact too small to be valid: {name}")

    def test_vorp_artifact_carries_vorp_view_tag(self):
        b = _load_view_builder()
        b.LINEAGE_PATH = str(self.tmp_path / "modules" / "source-value-lineage.json")
        b.VORP_OUT = str(self.tmp_path / "modules" / "vorp-view.json")
        b.ADJ_OUT = str(self.tmp_path / "modules" / "adj-view.json")
        b.main()

        j = json.loads((self.tmp_path / "modules" / "vorp-view.json").read_text())
        self.assertEqual(j["view"], "vorp",
                         "vorp-view.json must carry view='vorp'")
        self.assertIn("fantasypros", j["sources"])

    def test_adj_artifact_carries_adj_view_tag(self):
        b = _load_view_builder()
        b.LINEAGE_PATH = str(self.tmp_path / "modules" / "source-value-lineage.json")
        b.VORP_OUT = str(self.tmp_path / "modules" / "vorp-view.json")
        b.ADJ_OUT = str(self.tmp_path / "modules" / "adj-view.json")
        b.main()

        j = json.loads((self.tmp_path / "modules" / "adj-view.json").read_text())
        self.assertEqual(j["view"], "adj",
                         "adj-view.json must carry view='adj'")

    def test_missing_lineage_raises(self):
        """Fail-closed on no lineage: builder raises FileNotFoundError."""
        b = _load_view_builder()
        b.LINEAGE_PATH = str(self.tmp_path / "modules" / "does-not-exist.json")
        b.VORP_OUT = str(self.tmp_path / "modules" / "vorp-view.json")
        b.ADJ_OUT = str(self.tmp_path / "modules" / "adj-view.json")
        with self.assertRaises(FileNotFoundError):
            b.main()

    def test_view_status_reflects_per_row_failures(self):
        """A failing player row in a source must bubble up to view.status."""
        # Mutate one row: missing imputed_vorp but group assigned -> bad row.
        bad_lineage = json.loads(json.dumps(self.lineage))
        bad_lineage["sources"]["fantasypros"]["top25"][1]["imputed_vorp"] = None
        (self.tmp_path / "modules" / "source-value-lineage.json").write_text(
            json.dumps(bad_lineage), encoding="utf-8"
        )
        b = _load_view_builder()
        b.LINEAGE_PATH = str(self.tmp_path / "modules" / "source-value-lineage.json")
        b.VORP_OUT = str(self.tmp_path / "modules" / "vorp-view.json")
        b.ADJ_OUT = str(self.tmp_path / "modules" / "adj-view.json")
        b.main()
        j = json.loads((self.tmp_path / "modules" / "vorp-view.json").read_text())
        self.assertEqual(j["status"], "bad",
                         "vorp view status must reflect bad row")
        self.assertEqual(j["sources"]["fantasypros"]["status"], "bad")

    def test_skill_position_null_group_is_bad_not_skipped(self):
        """JEG-266: a skill-position row with no group at all must fail the
        view (nulls where the Option C 8-group input was expected), not be
        silently skipped. Non-skill rows without groups stay skipped."""
        bad_lineage = json.loads(json.dumps(self.lineage))
        row = bad_lineage["sources"]["fantasypros"]["top25"][0]
        row["group"] = None
        row["alloc_factor"] = None
        row["our_group_vorp"] = None
        row["imputed_vorp"] = None
        row["vorp_inferred_position"] = "QB"
        (self.tmp_path / "modules" / "source-value-lineage.json").write_text(
            json.dumps(bad_lineage), encoding="utf-8"
        )
        b = _load_view_builder()
        b.LINEAGE_PATH = str(self.tmp_path / "modules" / "source-value-lineage.json")
        b.VORP_OUT = str(self.tmp_path / "modules" / "vorp-view.json")
        b.ADJ_OUT = str(self.tmp_path / "modules" / "adj-view.json")
        b.main()
        j = json.loads((self.tmp_path / "modules" / "vorp-view.json").read_text())
        self.assertEqual(j["sources"]["fantasypros"]["status"], "bad",
                         "skill-position null group must be bad, not skipped")
        self.assertEqual(j["status"], "bad")


if __name__ == "__main__":
    unittest.main()