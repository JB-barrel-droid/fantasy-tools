import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_index_math  # noqa: E402
import build_pipeline_checkpoints  # noqa: E402
import build_source_fidelity  # noqa: E402


DASHBOARD_HTML = ROOT / "modules" / "dashboard.html"


def _newest_razzball_leg_natives(leg_dir):
    """Independent read of the newest 12-team Razzball legs' per-game values."""
    legs = []
    for path in leg_dir.glob("*/ddf_leg_razzball.json"):
        leg = json.loads(path.read_text())
        inputs = leg.get("inputs", {})
        if inputs.get("teams") == 12 and inputs.get("scoring") in ("ppr", "half_ppr", "standard"):
            legs.append(leg)
    newest = max(leg["inputs"]["razzball_snapshot_date"] for leg in legs)
    return ({(row["player_norm"].strip(), leg["inputs"]["scoring"]): float(row["ppg"])
             for leg in legs if leg["inputs"]["razzball_snapshot_date"] == newest
             for row in leg["values"]
             if row.get("player_norm") and isinstance(row.get("ppg"), (int, float))},
            newest)


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
        # The razzball:"Razzball" label lived in the source-value lineage
        # card's label map, retired 2026-10-08 (chore/retire-extras).

    def test_razzball_fidelity_loads_ddf_leg_natives(self):
        # Recompute-based (2026-10-08): this pinned vintage 2026-10-01 and
        # Gibbs 24.4 from the first committed legs; the 2026-10-06 legs made
        # it red. The natives must be exactly the newest legs' per-game values.
        self.assertIn("razzball", build_source_fidelity.SOURCES)
        natives, vintage = build_source_fidelity.load_snapshot_natives("razzball")
        expected, expected_vintage = _newest_razzball_leg_natives(ROOT / "data" / "ddf-two-tier")
        self.assertEqual(vintage, expected_vintage)
        self.assertGreater(len(natives), 400)
        self.assertEqual(natives, expected)

    def test_razzball_natives_ignore_older_legs(self):
        # Two snapshot dates side by side, the older one listed last: only the
        # newer leg's values may load, and a player only the older leg has
        # must not leak in.
        def leg(date, rows):
            return {"inputs": {"teams": 12, "scoring": "ppr", "razzball_snapshot_date": date},
                    "values": [{"player_norm": n, "ppg": v} for n, v in rows]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, payload in (
                ("ddf-20261006-razzball-ppr-12t-0p15", leg("2026-10-06", [("a", 20.0)])),
                ("zz-ddf-20261001-razzball-ppr-12t-0p15", leg("2026-10-01", [("a", 99.0), ("old only", 5.0)])),
            ):
                (root / "data" / "ddf-two-tier" / name).mkdir(parents=True)
                (root / "data" / "ddf-two-tier" / name / "ddf_leg_razzball.json").write_text(json.dumps(payload))
            with mock.patch.object(build_source_fidelity, "REPO", root):
                natives, vintage = build_source_fidelity.load_razzball_leg_natives()
        self.assertEqual(vintage, "2026-10-06")
        self.assertEqual(natives, {("a", "ppr"): 20.0})

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


if __name__ == "__main__":
    unittest.main()
