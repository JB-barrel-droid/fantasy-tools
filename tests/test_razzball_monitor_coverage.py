import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_index_math  # noqa: E402
import build_pipeline_checkpoints  # noqa: E402
import build_source_fidelity  # noqa: E402
import build_source_value_lineage  # noqa: E402


DASHBOARD_HTML = ROOT / "modules" / "dashboard.html"


class RazzballMonitorCoverageTest(unittest.TestCase):
    def test_razzball_is_in_checkpoint_source_registry(self):
        self.assertIn("razzball", build_pipeline_checkpoints.SOURCES)
        self.assertEqual(build_pipeline_checkpoints.SRC_LABEL["razzball"], "Razzball")
        health = build_pipeline_checkpoints.razzball_health_from_fixture(
            {
                "built_at": "2026-10-01T00:00:00+00:00",
                "source_validation": {"razzball": "live"},
                "sources": {"razzball": {"vintage": "2026-10-01", "combos": {"full_12": {}}}},
            }
        )
        self.assertEqual(health["status"], "ok")
        self.assertFalse(health["supabase_landing"])

    def test_razzball_is_in_dashboard_source_orders(self):
        text = DASHBOARD_HTML.read_text()
        source_order = re.search(r"const SOURCE_ORDER = \[([^\]]+)\];", text)
        self.assertIsNotNone(source_order)
        self.assertIn('"razzball"', source_order.group(1))
        self.assertNotIn("10 checkpoints × 5 sources", text)
        self.assertIn('razzball:"Razzball"', text)

    def test_razzball_fidelity_loads_ddf_leg_natives(self):
        self.assertIn("razzball", build_source_fidelity.SOURCES)
        natives, vintage = build_source_fidelity.load_snapshot_natives("razzball")
        self.assertEqual(vintage, "2026-10-01")
        self.assertGreater(len(natives), 400)
        self.assertAlmostEqual(natives[("jahmyr gibbs", "ppr")], 24.4)

    def test_razzball_index_math_verifies_ddf_leg(self):
        result = build_index_math.verify_ddf_leg(
            "razzball",
            "Razzball",
            "-razzball-{scoring}-",
            "ddf_leg_razzball.json",
        )
        self.assertEqual(result["status"], "ok", result.get("mismatches"))
        self.assertIn("full_12", result["combos"])
        self.assertGreater(result["combos"]["full_12"]["checked"], 0)

    def test_razzball_lineage_is_projection_calculated(self):
        self.assertEqual(build_source_value_lineage.COMBO_KEYS["razzball"], "half_12")
        self.assertIsNone(build_source_value_lineage.ADJUSTED_SOURCES["razzball"])
        self.assertEqual(
            build_source_value_lineage.SOURCE_TYPES["razzball"],
            "calculated_from_projections",
        )
        self.assertIn("football.razzball.com", build_source_value_lineage.SOURCE_URLS["razzball"]["url"])


if __name__ == "__main__":
    unittest.main()
