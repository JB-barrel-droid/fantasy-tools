"""Offline fixture, source, units and filter regressions for JEG-1481 / JEG-1195."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
from build_versus_vegas import build_view, render_html  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "weekly_inputs" / "valid"
SCRIPT = ROOT / "app" / "versus-vegas" / "view.js"


def weekly_fixture():
    """Synthetic sources reuse the committed, validator-owned complete fixture.

    Four comparisons: Vegas +3, ECR +2, equal points, real zero on both sides.
    ESPN is deliberately present and different: it must never fill ECR.
    """
    doc = json.loads((FIXTURES / "complete.json").read_text())
    meta = doc["legs"]["experts.espn_weekly"]
    for leg_id, source, kind in (("experts.ecr_weekly", "fantasypros", "expert"),
                                 ("vegas", "propline", "vegas")):
        doc["legs"][leg_id] = {**copy.deepcopy(meta), "source": source, "kind": kind}
    for index, row in enumerate(doc["players"]):
        ecr = (10, 15, 8, 0)[index]
        vegas = (13, 13, 8, 0)[index]
        for leg_id, value in (("experts.ecr_weekly", ecr), ("vegas", vegas)):
            row["legs"][leg_id] = {"provenance": "complete",
                "values": {scoring: value for scoring in ("standard", "half_ppr", "ppr")}}
    return doc


def partial_fixture():
    doc = weekly_fixture()
    doc["legs"]["vegas"]["availability"] = "partial"
    cell = doc["players"][0]["legs"]["vegas"]
    cell["values"]["ppr"] = None
    cell["missing_reason"] = {"ppr": "Reception market missing"}
    cell["provenance"] = "partial"
    return doc


class VersusVegas(unittest.TestCase):
    def test_imports_as_package_with_isolated_python_path(self):
        command = [sys.executable, "-I", "-c",
                   "import sys; sys.path.insert(0, sys.argv[1]); import pipelines.build_versus_vegas",
                   str(ROOT)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_weekly_points_direction_and_real_zero(self):
        doc = weekly_fixture()
        original = copy.deepcopy(doc)
        with mock.patch.object(socket, "create_connection", side_effect=AssertionError("network")):
            view = build_view(doc)
        cells = [row["scoring"]["half_ppr"] for row in view["players"]]
        self.assertEqual([c["difference"] for c in cells], [3, -2, 0, 0])
        self.assertEqual([c["direction"] for c in cells], ["Vegas higher", "ECR higher", "Equal", "Equal"])
        self.assertEqual(doc, original)
        self.assertEqual(view["plays"], [])

    def test_partial_rows_visible_and_unflagged_in_every_scoring(self):
        view = build_view(partial_fixture())
        self.assertEqual(len(view["players"]), 4)
        row = view["players"][0]
        for cell in row["scoring"].values():
            self.assertIsNone(cell["direction"])
            self.assertIsNone(cell["difference"])
        self.assertEqual(row["scoring"]["half_ppr"]["coverage"], "both")
        self.assertEqual(row["scoring"]["ppr"]["coverage"], "partial")
        self.assertIsNone(row["scoring"]["ppr"]["vegas"]["value"])
        self.assertEqual(row["scoring"]["ppr"]["vegas"]["reason"], "Reception market missing")

    def test_absent_ecr_does_not_fall_back_to_espn(self):
        view = build_view(json.loads((FIXTURES / "complete.json").read_text()))
        for row in view["players"]:
            for cell in row["scoring"].values():
                self.assertIsNone(cell["ecr"]["value"])
                self.assertIsNone(cell["vegas"]["value"])
                self.assertEqual(cell["coverage"], "missing")
                self.assertIsNone(cell["direction"])

    def test_declared_unavailable_preserves_producer_reason(self):
        view = build_view(json.loads((FIXTURES / "unavailable.json").read_text()))
        reason = view["legs"]["vegas"]["missing_reason"]
        self.assertTrue(reason)
        for row in view["players"]:
            self.assertEqual(row["scoring"]["half_ppr"]["vegas"]["reason"], reason)

    def test_ranks_never_subtracted_from_points(self):
        doc = weekly_fixture()
        doc["legs"]["experts.ecr_weekly"]["units"] = "rank"
        for row in doc["players"]:
            row["legs"]["experts.ecr_weekly"]["values"] = dict.fromkeys(("standard", "half_ppr", "ppr"), 3)
        view = build_view(doc)
        for row in view["players"]:
            cell = row["scoring"]["half_ppr"]
            self.assertEqual(cell["ecr"]["value"], 3)
            self.assertEqual(cell["ecr"]["units"], "rank")
            self.assertIsNone(cell["difference"])
            self.assertIn("no conversion", cell["reason"])

    def test_old_content_and_unresolved_identity_stay_unflagged(self):
        for freshness, week, label in (("one_week_behind", 7, "published"),
                                       ("stale", 6, "stale")):
            doc = weekly_fixture()
            doc["legs"]["vegas"].update(freshness=freshness, content_week=week, label=label)
            view = build_view(doc)
            self.assertTrue(all(r["scoring"]["half_ppr"]["difference"] is None for r in view["players"]))
            self.assertEqual(view["players"][0]["scoring"]["half_ppr"]["vegas"]["value"], 13)
        doc = weekly_fixture()
        row = doc["players"].pop(0)
        row.update(player_key=None, unresolved_reason="No canonical match")
        doc["players"].append(row)
        result = build_view(doc)["players"][-1]
        self.assertIsNone(result["player_key"])
        self.assertIn("Unresolved identity", result["scoring"]["half_ppr"]["reason"])
        self.assertIsNone(result["scoring"]["half_ppr"]["direction"])

    def test_contract_fails_closed_and_sources_are_pinned(self):
        for change in (lambda d: d.update(horizon="ros"),
                       lambda d: d.update(schema_version="999.0.0"),
                       lambda d: d["legs"]["vegas"].update(source="fds"),
                       lambda d: d["legs"]["experts.ecr_weekly"].update(source="espn"),
                       lambda d: d["players"][0]["legs"]["vegas"].update(missing_reason={"ppr": "missing"})):
            doc = weekly_fixture()
            change(doc)
            with self.assertRaises(ValueError):
                build_view(doc)

    def test_script_payload_is_escaped(self):
        doc = weekly_fixture()
        doc["players"][0]["name"] = '</script><img src=x onerror="alert(1)">'
        html = render_html(build_view(doc))
        self.assertNotIn('</script><img', html)
        self.assertIn('\\u003c/script>', html)

    def test_design_alternatives_preserve_the_exact_comparison_payload(self):
        view = build_view(partial_fixture())
        original = copy.deepcopy(view)
        for layout in ("compact", "analysis"):
            rendered = render_html(view, layout, '<img src=x>')
            payload = re.search(r'<script id="versus-data" type="application/json">(.*?)</script>',
                                rendered, flags=re.DOTALL)
            self.assertEqual(json.loads(payload.group(1)), view)
            self.assertIn(f'data-layout="{layout}"', rendered)
            self.assertIn('&lt;img src=x&gt;', rendered)
        self.assertEqual(view, original)
        with self.assertRaises(ValueError):
            render_html(view, 'unrecognized-layout')

    def test_standalone_design_reuses_the_shared_foundation_offline(self):
        rendered = render_html(build_view(weekly_fixture()))
        self.assertEqual(rendered.count('@font-face'), 1)
        self.assertIn('data:font/woff2;base64,', rendered)
        self.assertNotIn('url("fonts/fraunces.woff2")', rendered)
        self.assertIn('--ddf-content-max: 1184px', rendered)
        self.assertIn('SIL OPEN FONT LICENSE', rendered)
        self.assertIn('ddf-fn-disclosure', rendered)

    def test_player_identity_provenance_is_preserved(self):
        doc = weekly_fixture()
        result = build_view(doc)["players"][0]
        for key in ("player_key", "resolved_by", "source_ids"):
            self.assertEqual(result[key], doc["players"][0][key])

    def test_producer_cli_output_builds_preview_without_relabeling(self):
        fixtures = ROOT / "tests" / "fixtures" / "weekly_inputs_producer"
        with tempfile.TemporaryDirectory() as directory:
            inputs = Path(directory) / "inputs-wk8.json"
            preview = Path(directory) / "index.html"
            command = [sys.executable, "pipelines/build_weekly_inputs.py",
                       "--season", "2026", "--week", "8", "--as-of", "2026-10-29T02:00:00Z",
                       "--out", str(inputs)]
            for flag, filename in (("players", "players.json"), ("sleeper-base", "sleeper_base.json"),
                                   ("aliases", "player_aliases.json"), ("espn-weekly", "espn_weekly.csv"),
                                   ("status", "status.json"), ("byes", "byes.json")):
                command += ["--" + flag, str(fixtures / filename)]
            producer = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(producer.returncode, 0, producer.stderr)
            source = json.loads(inputs.read_text())
            self.assertEqual(source["legs"]["experts.ecr_weekly"]["source"], "fantasypros_ecr")
            consumer = subprocess.run([sys.executable, "pipelines/build_versus_vegas.py", str(inputs),
                                       "--out", str(preview)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            payload = re.search(r'<script id="versus-data" type="application/json">(.*?)</script>',
                                preview.read_text(), flags=re.DOTALL)
            self.assertIsNotNone(payload)
            result = json.loads(payload.group(1))
            self.assertEqual(result["legs"]["ecr"], source["legs"]["experts.ecr_weekly"])
            self.assertEqual(len(result["players"]), len(source["players"]))
            self.assertEqual([row["player_key"] for row in result["players"]],
                             [row["player_key"] for row in source["players"]])
            for actual, original in zip(result["players"], source["players"]):
                self.assertEqual(actual["resolved_by"], original.get("resolved_by"))
                self.assertEqual(actual["source_ids"], original.get("source_ids", {}))
                for cell in actual["scoring"].values():
                    self.assertEqual(cell["coverage"], "missing")
                    self.assertIsNone(cell["direction"])
                    self.assertIsNone(cell["difference"])
                    self.assertIsNone(cell["ecr"]["value"])
                    self.assertIn("no weekly ECR producer yet", cell["ecr"]["reason"])
            self.assertTrue(any(row["player_key"] is None for row in result["players"]))

    def test_producer_source_label_also_accepts_populated_weekly_points(self):
        doc = weekly_fixture()
        doc["legs"]["experts.ecr_weekly"]["source"] = "fantasypros_ecr"
        cells = [row["scoring"]["half_ppr"] for row in build_view(doc)["players"]]
        self.assertEqual([cell["difference"] for cell in cells], [3, -2, 0, 0])

    def test_empty_input_and_new_minor_warnings_remain_inspectable(self):
        doc = weekly_fixture()
        doc["schema_version"] = "1.1.0"
        doc["new_metadata"] = "future additive field"
        doc["players"] = []
        view = build_view(doc)
        self.assertEqual(view["players"], [])
        self.assertTrue(any(i["code"] == "field.unknown" for i in view["warnings"]))

    def test_cli_builds_offline_and_never_overwrites_invalid_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "inputs.json"
            target = Path(directory) / "preview.html"
            source.write_text(json.dumps(weekly_fixture()))
            command = [sys.executable, "pipelines/build_versus_vegas.py", str(source), "--out", str(target)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            original = target.read_text()
            self.assertIn('Input SHA-256', original)
            source.write_text('{"horizon":"ros"}')
            self.assertNotEqual(subprocess.run(command, cwd=ROOT, capture_output=True).returncode, 0)
            self.assertEqual(target.read_text(), original)
            source.write_text(json.dumps(weekly_fixture()))
            same_path = subprocess.run(command[:-1] + [str(source)], cwd=ROOT, capture_output=True)
            self.assertNotEqual(same_path.returncode, 0)
            self.assertEqual(json.loads(source.read_text()), weekly_fixture())

    def test_js_filters_coverage_and_sort(self):
        view = build_view(partial_fixture())
        code = """
const V = require(process.argv[1]);
const view = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const state = V.filters('?scoring=ppr&position=QB&coverage=partial&sort=difference');
const rows = V.selectRows(view, state);
console.log(JSON.stringify({state, names: rows.map(r => r.name),
  counts: V.counts(view.players, 'ppr'),
  comparable: V.selectRows(view, V.filters('?coverage=comparable&sort=difference')).map(r => r.scoring.half_ppr.difference),
  defaults: V.filters('?scoring=ros&position=HACK&sort=nope&coverage=unknown'),
  zero: V.cellText({value: 0, units:'fantasy_points'}),
  missing: V.cellText({value: null}), rank: V.cellText({value:3, units:'rank'})}));
"""
        proc = subprocess.run(["node", "-e", code, str(SCRIPT)], input=json.dumps(view), capture_output=True, text=True, check=True)
        result = json.loads(proc.stdout)
        self.assertEqual(result["state"], {"scoring": "ppr", "position": "QB", "coverage": "partial", "sort": "difference"})
        self.assertEqual(result["names"], ["Fixture Quarterback"])
        self.assertEqual(result["counts"], {"total": 4, "both": 3, "partial": 1, "missing": 0, "comparable": 3})
        self.assertEqual(result["comparable"], [-2, 0, 0])
        self.assertEqual(result["defaults"], {"scoring": "half_ppr", "position": "all", "coverage": "all", "sort": "name"})
        self.assertEqual([result[k] for k in ("zero", "missing", "rank")], ["0 pts", "—", "#3"])


if __name__ == "__main__":
    unittest.main()
