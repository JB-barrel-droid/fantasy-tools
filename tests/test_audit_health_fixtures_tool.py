"""Regression coverage for the frozen-fixture writer (JEG-1165)."""

import copy
import importlib.util
import io
import json
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


TOOL_PATH = Path(__file__).resolve().parents[1] / "tools" / "audit_health_fixtures.py"


def synthetic_dump(marker="week7"):
    return {
        "marker": marker,
        "liveMatch": {"volatile": True},
        "inspection": {
            "valuePipeline": {
                "sources": {"espn": {"label": "ESPN"}, "cbs": {"label": "CBS"}},
                "included": ["espn", "cbs"],
            },
            "players": {
                "espn": {
                    "a": {"role": "starter", "adjusted": 10, "raw": 9},
                    "b": {"role": "bench", "adjusted": 5, "raw": 4},
                    "c": {"role": "starter", "adjusted": 20, "raw": 18},
                },
                "cbs": {
                    "a": {"role": "starter", "adjusted": 12, "raw": 11},
                    "b": {"role": "bench", "adjusted": 6, "raw": 5},
                },
            },
            "rows": {
                "a": {"indexed": {"espn": 10, "cbs": 12}, "position": "RB"},
                "b": {"indexed": {"espn": 5, "cbs": 6}, "position": "WR"},
                "c": {"indexed": {"espn": 20}, "position": "TE"},
            },
        },
    }


class AuditHealthFixturesToolTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("audit_health_fixtures_tool", TOOL_PATH)
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.out = self.root / "fixtures" / "audit"
        self.enterContext(patch.object(self.tool, "ROOT", self.root))
        self.enterContext(patch.object(self.tool, "OUT", self.out))
        self.stderr = self.enterContext(redirect_stderr(io.StringIO()))

    def test_write_creates_absent_file_and_parent_directories(self):
        doc = {"example": [1, 2], "nested": {"value": True}}
        self.assertFalse(self.out.exists())

        self.tool.write("new.json", doc)

        self.assertEqual(json.loads((self.out / "new.json").read_text()), doc)

    def test_write_preserves_existing_bytes_and_reports_skip(self):
        self.out.mkdir(parents=True)
        path = self.out / "frozen.json"
        original = b'{ "frozen": true }\r\n'
        path.write_bytes(original)

        self.tool.write("frozen.json", {"replacement": True})

        self.assertEqual(path.read_bytes(), original)
        self.assertIn("skip frozen.json", self.stderr.getvalue())

    def test_perturb_starters_changes_only_named_source_starters(self):
        doc = synthetic_dump()
        before = copy.deepcopy(doc)
        expected = copy.deepcopy(doc)
        expected["inspection"]["players"]["espn"]["a"]["adjusted"] = 12
        expected["inspection"]["players"]["espn"]["c"]["adjusted"] = 24
        expected["perturbation"] = {"source": "espn", "starters_x": 1.2}

        result = self.tool.perturb_starters(doc, "espn", 1.2)

        self.assertEqual(result, expected)
        self.assertEqual(doc, before)

    def test_drop_source_removes_all_references_without_mutating_input(self):
        doc = synthetic_dump()
        before = copy.deepcopy(doc)
        expected = copy.deepcopy(doc)
        inspection = expected["inspection"]
        del inspection["valuePipeline"]["sources"]["cbs"]
        inspection["valuePipeline"]["included"] = ["espn"]
        del inspection["players"]["cbs"]
        del inspection["rows"]["a"]["indexed"]["cbs"]
        del inspection["rows"]["b"]["indexed"]["cbs"]
        expected["perturbation"] = {"removed": "cbs"}

        result = self.tool.drop_source(doc, "cbs")

        self.assertEqual(result, expected)
        self.assertEqual(doc, before)

    def test_main_writes_seven_stripped_fixtures_and_preserves_them_on_rerun(self):
        dump = self.root / "dump"
        dump.mkdir()
        inputs = (
            "w7_ppr_12", "w5_ppr_12", "w3_ppr_12",
            "w4_half_ppr_8", "w7_half_ppr_8",
        )
        for name in inputs:
            (dump / (name + ".json")).write_text(json.dumps(synthetic_dump(name)))
        expected_markers = {
            "healthy_week7.json": "w7_ppr_12",
            "perturbed_espn_starter.json": "w7_ppr_12",
            "missing_cbs.json": "w7_ppr_12",
            "history_week5.json": "w5_ppr_12",
            "held_week3_ppr12.json": "w3_ppr_12",
            "held_week4_halfppr8.json": "w4_half_ppr_8",
            "extreme_8team_halfppr.json": "w7_half_ppr_8",
        }

        self.tool.main(["--dump", str(dump)])

        self.assertEqual({path.name for path in self.out.iterdir()}, set(expected_markers))
        before = {path.name: path.read_bytes() for path in self.out.iterdir()}
        for name, marker in expected_markers.items():
            with self.subTest(fixture=name):
                doc = json.loads(before[name])
                self.assertNotIn("liveMatch", doc)
                self.assertEqual(doc["marker"], marker)
        perturbed = json.loads(before["perturbed_espn_starter.json"])
        self.assertEqual(perturbed["inspection"]["players"]["espn"]["a"]["adjusted"], 12)
        missing = json.loads(before["missing_cbs.json"])
        self.assertNotIn("cbs", missing["inspection"]["players"])

        self.tool.main(["--dump", str(dump)])

        self.assertEqual(
            {path.name: path.read_bytes() for path in self.out.iterdir()}, before
        )


if __name__ == "__main__":
    unittest.main()
