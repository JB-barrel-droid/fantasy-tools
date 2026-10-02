"""Projection source classification survives fixture regeneration."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import build_cbsros_section_from_ddf_leg as cbsros
import build_razzball_section_from_ddf_leg as razzball


class ProjectionSourceKindTest(unittest.TestCase):
    def test_both_builders_classify_their_projection_sections(self):
        for builder in (cbsros, razzball):
            with self.subTest(source=builder.SOURCE_KEY):
                leg = Mock()
                leg.read_text.return_value = json.dumps({
                    "inputs": {f"{builder.SOURCE_KEY}_snapshot_date": "2026-10-01"},
                    "values": [{"player_norm": "test player", "value": 5.0, "ppg": 12.0}],
                })
                with patch.object(builder, "find_fresh_leg", return_value=leg), \
                     patch.object(builder, "load_slug_to_pos", return_value={"test player": "RB"}):
                    section = builder.section_from_leg({}, "https://example.invalid", ["full_12"])
                self.assertEqual(section["kind"], "model projections, valued by our model")
                self.assertEqual(section["vintage"], "2026-10-01")
                self.assertEqual(section["combos"]["full_12"]["native"], {"test player": 12.0})


if __name__ == "__main__":
    unittest.main()
