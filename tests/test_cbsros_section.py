"""Regression tests for the cbsros fixture section metadata.

The monitor's C10 rendered-output check went bad on 2026-10-01 because the
cbsros section carried no week_designated label (expected 'Week 4' or, for
rest-of-season sources, 'rest of season'). CBS ROS is rest-of-season
projections, so the section builder must stamp week_designated accordingly.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_cbsros_section_from_ddf_leg as cbsros_builder


def _fake_leg(tmp: Path, scoring: str, teams: int) -> None:
    leg_dir = tmp / f"leg-{scoring}-{teams}t"
    leg_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "bake_id": f"test-cbsros-{scoring}-{teams}t",
        "generated_at": "2026-09-30T00:00:00Z",
        "inputs": {
            "scoring": scoring,
            "teams": teams,
            "cbsros_snapshot_date": "2026-09-30",
        },
        "values": [
            {"player_norm": "jahmyr gibbs", "value": 60.0, "ppg": 20.0},
        ],
    }
    (leg_dir / "ddf_leg_cbsros.json").write_text(json.dumps(doc))


class CbsrosWeekDesignatedTest(unittest.TestCase):
    def test_section_from_leg_stamps_rest_of_season(self):
        """The builder must label the section 'rest of season' (fails on the
        pre-fix builder, which emitted no week_designated at all)."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for scoring in ("ppr", "half_ppr", "standard"):
                for teams in (8, 10, 12, 14):
                    _fake_leg(tmp_path, scoring, teams)
            old_leg_dir = cbsros_builder.LEG_DIR
            cbsros_builder.LEG_DIR = tmp_path
            try:
                fixture = {"player_keys": {"jahmyr gibbs": 1}}
                section = cbsros_builder.section_from_leg(
                    fixture, "https://example.invalid/cbsros", ["full_12"]
                )
            finally:
                cbsros_builder.LEG_DIR = old_leg_dir
        self.assertEqual(section.get("week_designated"), "rest of season")

    def test_fixture_cbsros_section_carries_label(self):
        """The live fixture's cbsros section must carry the label the C10
        monitor check requires."""
        fixture = json.loads(
            (ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json")
            .read_text()
        )
        self.assertEqual(
            fixture["sources"]["cbsros"].get("week_designated"), "rest of season"
        )


if __name__ == "__main__":
    unittest.main()
