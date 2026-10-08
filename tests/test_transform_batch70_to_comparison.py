"""JEG-242: transform_batch70_to_comparison.py bridges candidates to a real view.

The 08:20 CDT review caught the transformer writing consumer-less
`_jeg242_batch70` keys that no view reads -- "not real view integration yet".
The rewritten transformer writes `sources[<src>].vorp_views` in the exact
contract the chart's JEG-210 view toggle consumes (display-name-keyed views
resolved through the payload's own player_keys table, with the producing
scoring/teams carried so the widget can gate rendering on a match).

This module pins the bridge:
  Positive (must pass):
    - a batch70 candidate transforms into vorp_views blocks with values
      verbatim (full pipeline precision; no rounding) keyed by display name,
      and usat maps to usatoday.
    - scoring/teams from the candidate manifest are carried on the block.
    - the Makefile names this transform (transform-vorp-views target).
  Negative regressions (each must FAIL the old/unwired state):
    - wrong batch70 schema aborts; a candidate without a manifest aborts
      (never transform an unreviewed artifact).
    - a canonical key with no player_keys display name aborts and names the
      key (no silent drops, no invented names).
    - a batch70 source with no comparison mapping is skipped with an explicit
      reason (never silently admitted).
    - the output contains no `_jeg242_batch70` consumer-less keys.
"""
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(REPO / "pipelines"))

from transform_batch70_to_comparison import main as transform_main  # noqa: E402

CHECKER = REPO / "preview" / "check_vorp_views_parity.js"

PLAYER_KEYS = {"Alice A": 1, "Bob B": 2, "Cara C": 3}


def _comparison():
    return {
        "player_keys": dict(PLAYER_KEYS),
        "sources": {
            "fantasycalc": {"name": "FantasyCalc"},
            "usatoday": {"name": "USA Today"},
            "fantasypros": {"name": "FantasyPros"},
            "cbs": {"name": "CBS"},
        },
    }


def _candidate(sources=("fantasycalc", "usat")):
    views = {}
    for i, src in enumerate(sources):
        base = 100.0 - i * 7.0
        views[src] = {
            "indexed": {"1": base, "2": base / 2, "3": base / 4},
            "vorp": {"1": 12.345678, "2": 6.0, "3": 0.0},
            "adj_values": {"1": 70.0, "2": 35.123456, "3": 0.0},
        }
    return {
        "schema": "shared-batch70-views-v1",
        "artifact_status": "candidate",
        "manifest": {
            "configuration": {"scoring": "half_ppr", "teams": 12},
        },
        "sources": views,
    }


def _run(tmp: Path, candidate: dict, comparison: dict):
    cand_path = tmp / "candidate.json"
    comp_path = tmp / "comparison.json"
    out_path = tmp / "out.json"
    cand_path.write_text(json.dumps(candidate))
    comp_path.write_text(json.dumps(comparison))
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = transform_main(["--batch70", str(cand_path),
                                   "--comparison", str(comp_path),
                                   "--out", str(out_path)])
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    payload = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else None
    return code, out.getvalue() + err.getvalue(), payload


class TestTransformBatch70ToComparison(unittest.TestCase):
    def test_transforms_to_vorp_views(self):
        with tempfile.TemporaryDirectory() as td:
            code, log, payload = _run(Path(td), _candidate(), _comparison())
            self.assertEqual(code, 0, log)
            fc = payload["sources"]["fantasycalc"]["vorp_views"]
            self.assertEqual(fc["schema"], "vorp-views-v1")
            self.assertEqual(fc["scoring"], "half_ppr")
            self.assertEqual(fc["teams"], 12)
            self.assertEqual(fc["views"]["indexed"], {"Alice A": 100.0, "Bob B": 50.0, "Cara C": 25.0})
            # usat maps to usatoday
            usa = payload["sources"]["usatoday"]["vorp_views"]
            self.assertEqual(usa["views"]["indexed"]["Alice A"], 93.0)
            self.assertEqual(usa["source"], "usatoday")

    def test_values_verbatim_full_precision(self):
        with tempfile.TemporaryDirectory() as td:
            code, log, payload = _run(Path(td), _candidate(), _comparison())
            self.assertEqual(code, 0, log)
            fc = payload["sources"]["fantasycalc"]["vorp_views"]["views"]
            self.assertEqual(fc["vorp"]["Alice A"], 12.345678)
            self.assertEqual(fc["adj_values"]["Bob B"], 35.123456)
            self.assertEqual(fc["vorp"]["Cara C"], 0.0)  # genuine zeros kept

    def test_wrong_schema_aborts(self):
        with tempfile.TemporaryDirectory() as td:
            cand = _candidate()
            cand["schema"] = "something-else-v1"
            code, log, payload = _run(Path(td), cand, _comparison())
            self.assertNotEqual(code, 0)
            self.assertIsNone(payload)

    def test_missing_manifest_aborts(self):
        with tempfile.TemporaryDirectory() as td:
            cand = _candidate()
            del cand["manifest"]
            code, log, payload = _run(Path(td), cand, _comparison())
            self.assertNotEqual(code, 0)
            self.assertIn("manifest", log)

    def test_unmapped_key_aborts_naming_key(self):
        with tempfile.TemporaryDirectory() as td:
            cand = _candidate()
            cand["sources"]["fantasycalc"]["indexed"]["999"] = 1.0
            cand["sources"]["fantasycalc"]["vorp"]["999"] = 1.0
            cand["sources"]["fantasycalc"]["adj_values"]["999"] = 1.0
            code, log, payload = _run(Path(td), cand, _comparison())
            self.assertNotEqual(code, 0)
            self.assertIn("999", log)

    def test_unknown_source_skipped_with_reason(self):
        with tempfile.TemporaryDirectory() as td:
            cand = _candidate(sources=("fantasycalc", "espn"))
            code, log, payload = _run(Path(td), cand, _comparison())
            self.assertEqual(code, 0, log)
            manifest = payload["_jeg242_transform"]["sources"]
            self.assertEqual(manifest["espn"]["status"], "skipped")
            self.assertIn("reason", manifest["espn"])
            self.assertEqual(manifest["fantasycalc"]["status"], "updated")

    def test_no_consumerless_batch70_keys(self):
        with tempfile.TemporaryDirectory() as td:
            code, log, payload = _run(Path(td), _candidate(), _comparison())
            self.assertEqual(code, 0, log)
            text = json.dumps(payload)
            self.assertNotIn("_jeg242_batch70", text)

    def test_makefile_names_transform(self):
        text = (REPO / "Makefile").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^transform-vorp-views:")

    def test_preview_chain_runs_transform_and_parity(self):
        """The preview target must bridge the candidate into the copied
        dashboard AND verify it second-language -- otherwise the transformer
        output is never consumed."""
        text = (REPO / "Makefile").read_text(encoding="utf-8")
        self.assertIn("transform_batch70_to_comparison.py", text)
        self.assertIn("check_vorp_views_parity.js", text)

    def _node_check(self, candidate_path: Path, comparison_path: Path):
        proc = subprocess.run(
            ["node", str(CHECKER), str(candidate_path), str(comparison_path)],
            capture_output=True, timeout=60,
        )
        return proc.returncode, proc.stdout.decode() + proc.stderr.decode()

    def test_node_checker_passes_on_transformer_output(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            code, log, payload = _run(tmp, _candidate(), _comparison())
            self.assertEqual(code, 0, log)
            cand_path = tmp / "candidate.json"
            out_path = tmp / "out.json"
            cand_path.write_text(json.dumps(_candidate()))
            # _run already wrote out.json; re-derive paths explicitly
            rc, out = self._node_check(cand_path, out_path)
            self.assertEqual(rc, 0, f"node checker failed:\n{out}")
            self.assertIn("VORP-VIEWS PARITY OK", out)

    def test_node_checker_catches_tampered_value(self):
        """The second-language check must discriminate a tampered view value."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            code, log, payload = _run(tmp, _candidate(), _comparison())
            self.assertEqual(code, 0, log)
            cand_path = tmp / "candidate.json"
            out_path = tmp / "out.json"
            cand_path.write_text(json.dumps(_candidate()))
            tampered = json.loads(out_path.read_text(encoding="utf-8"))
            vv = tampered["sources"]["fantasycalc"]["vorp_views"]["views"]["vorp"]
            vv["Alice A"] = vv["Alice A"] + 0.5
            out_path.write_text(json.dumps(tampered))
            rc, out = self._node_check(cand_path, out_path)
            self.assertNotEqual(rc, 0, "tampered value must fail the parity check")
            self.assertIn("PARITY FAILED", out)


if __name__ == "__main__":
    unittest.main()
