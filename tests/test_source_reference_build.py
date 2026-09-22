import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


class SourceReferenceBuildTest(unittest.TestCase):
    def run_build(self, tmp: Path, match_payload: dict, extra_args=()):
        match_path = tmp / "matched.json"
        match_path.write_text(json.dumps(match_payload), encoding="utf-8")
        outdir = tmp / "out"
        result = subprocess.run(
            ["python3", "pipelines/build_source_reference.py",
             "--input", str(match_path), "--output-dir", str(outdir),
             *extra_args],
            cwd=ROOT, capture_output=True, text=True,
        )
        artifacts = sorted(outdir.rglob("*.json")) if outdir.exists() else []
        return result, artifacts

    def match_doc(self, rows, source="usatoday", default_scoring="ppr",
                  default_teams=12, default_qb=None, review_rows=()):
        doc = {
            "schema": "trade-value-source-matches-v1",
            "source": source,
            "fetched_at": "2026-09-21T12:00:00Z",
            "default_scoring": default_scoring,
            "default_teams": default_teams,
            "summary": {},
            "matched_rows": rows,
            "review_rows": list(review_rows),
        }
        if default_qb is not None:
            doc["default_qb"] = default_qb
        return doc

    def mrow(self, key, name, value, scoring="ppr", teams=12, qb=None, source="usatoday"):
        row = {"player_key": key, "canonical_name": name,
               "source_player_name": name, "source": source, "value": value,
               "scoring": scoring, "teams": teams,
               "pos": "QB", "team": "BUF", "source_player_id": None}
        if qb is not None:
            row["qb"] = qb
        return row

    def payloads_by_combo(self, artifacts):
        by_combo = {}
        for path in artifacts:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn(payload["combo_key"], by_combo,
                             "two artifacts share a combo_key -- output paths would collide")
            by_combo[payload["combo_key"]] = payload
        return by_combo

    def test_mixed_scoring_rows_split_per_group_no_spurious_duplicates(self):
        # Negative test for the named defect: grouping by player_key alone
        # turned one player_key's standard/half_ppr/ppr rows (distinct values)
        # into spurious "duplicate_player_key" review groups (USA Today
        # produced 230). Rows must split by (scoring, teams, qb): one
        # reference artifact per scoring group, zero duplicate review rows.
        rows = [
            self.mrow(869, "Josh Allen", 30.0, scoring="standard"),
            self.mrow(869, "Josh Allen", 35.0, scoring="half_ppr"),
            self.mrow(869, "Josh Allen", 40.0, scoring="ppr"),
            self.mrow(101, "Bijan Robinson", 60.0, scoring="standard"),
            self.mrow(101, "Bijan Robinson", 67.5, scoring="half_ppr"),
            self.mrow(101, "Bijan Robinson", 75.0, scoring="ppr"),
        ]
        result, artifacts = self.run_build(
            Path(self._tmpdir()), self.match_doc(rows))
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertEqual(3, len(artifacts))
        by_combo = self.payloads_by_combo(artifacts)
        self.assertEqual({"standard_12", "half_ppr_12", "ppr_12"}, set(by_combo))
        for combo, payload in by_combo.items():
            self.assertEqual(2, payload["summary"]["matched_input_count"], combo)
            self.assertEqual(2, payload["summary"]["reference_row_count"], combo)
            self.assertEqual(0, payload["summary"]["duplicate_review_count"], combo)
            dupes = [r for r in payload["review_rows"]
                     if r["reason"] == "duplicate_player_key"]
            self.assertEqual([], dupes, combo)
            self.assertEqual(combo, payload["combo_key"])
        # Combo slug is in the file name so per-group files never collide.
        for combo in by_combo:
            path = next(p for p in artifacts
                        if json.loads(p.read_text(encoding="utf-8"))["combo_key"] == combo)
            self.assertIn(combo.replace("_", "-"), path.name)

    def test_same_group_conflicting_values_still_flagged(self):
        # The duplicate guard is load-bearing: same player_key AND same
        # scoring/teams/qb with conflicting values must still become exactly
        # one duplicate review row.
        rows = [
            self.mrow(202, "Duplicate One", 10.0),
            self.mrow(202, "Duplicate One", 11.0),
            self.mrow(869, "Josh Allen", 24.0),
        ]
        result, artifacts = self.run_build(
            Path(self._tmpdir()), self.match_doc(rows))
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertEqual(1, len(artifacts))
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        self.assertEqual(1, payload["summary"]["duplicate_review_count"])
        dupes = [r for r in payload["review_rows"]
                 if r["reason"] == "duplicate_player_key"]
        self.assertEqual(1, len(dupes))
        self.assertEqual(202, dupes[0]["player_key"])
        self.assertEqual([11.0, 10.0], dupes[0]["values"])
        self.assertEqual(1, payload["summary"]["reference_row_count"])
        self.assertEqual([869], [r["player_key"] for r in payload["rows"]])

    def test_same_group_identical_values_single_reference_row(self):
        rows = [
            self.mrow(202, "Duplicate One", 10.0),
            self.mrow(202, "Duplicate One", 10.0),
        ]
        result, artifacts = self.run_build(
            Path(self._tmpdir()), self.match_doc(rows))
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertEqual(1, len(artifacts))
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        self.assertEqual(1, payload["summary"]["reference_row_count"])
        self.assertEqual([], payload["review_rows"])
        self.assertEqual(10.0, payload["rows"][0]["value"])

    def test_homogeneous_input_default_path_and_shape_unchanged(self):
        # A single homogeneous group must behave exactly as the pre-split
        # builder: same default output path, same artifact shape.
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            match = tmp / "matched.json"
            self.write_match(match)
            outdir = tmp / "out"
            result = subprocess.run(
                ["python3", "pipelines/build_source_reference.py",
                 "--input", str(match), "--output-dir", str(outdir)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(0, result.returncode, msg=result.stderr)
            expected = (outdir / "fantasycalc" / "2026-09-21"
                        / "fantasycalc-ppr-12-reference.json")
            self.assertTrue(expected.exists(), f"default path changed: {expected}")
            self.assertEqual([expected], sorted(outdir.rglob("*.json")))

            payload = json.loads(expected.read_text(encoding="utf-8"))
            self.assertEqual(
                {"schema", "generated_at", "input_match", "source", "fetched_at",
                 "scoring", "teams", "qb", "combo_key", "summary", "rows",
                 "values_by_player_key", "player_key_by_source_name",
                 "review_rows"},
                set(payload.keys()),
            )
            self.assertEqual("ppr_12", payload["combo_key"])
            self.assertEqual(
                {"matched_input_count": 4, "reference_row_count": 2,
                 "inherited_review_count": 1, "duplicate_review_count": 1},
                payload["summary"],
            )
            self.assertEqual(
                {"player_key", "canonical_name", "value", "scoring", "teams",
                 "qb", "pos", "team", "source_player_name", "source_player_id"},
                set(payload["rows"][0].keys()),
            )
            self.assertEqual([101, 869], [r["player_key"] for r in payload["rows"]])
            self.assertEqual(["no_match", "duplicate_player_key"],
                             [r["reason"] for r in payload["review_rows"]])

    def test_missing_scoring_rows_go_to_review_never_placed(self):
        # Fail-closed choice: a row whose scoring resolves nowhere is never
        # placed and never guessed into a group -- it becomes a
        # missing_scoring review row.
        rows = [
            self.mrow(869, "Josh Allen", 24.0, scoring=None),
            self.mrow(101, "Bijan Robinson", 67.5, scoring="ppr"),
        ]
        result, artifacts = self.run_build(
            Path(self._tmpdir()),
            self.match_doc(rows, default_scoring=None))
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertEqual(1, len(artifacts))
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        self.assertEqual("ppr_12", payload["combo_key"])
        self.assertEqual([101], [r["player_key"] for r in payload["rows"]])
        self.assertNotIn("869", payload["values_by_player_key"])
        missing = [r for r in payload["review_rows"]
                   if r["reason"] == "missing_scoring"]
        self.assertEqual(1, len(missing))
        self.assertEqual(869, missing[0]["player_key"])
        self.assertEqual(1, payload["summary"]["missing_scoring_review_count"])

    def test_all_rows_missing_scoring_fails_closed(self):
        rows = [self.mrow(869, "Josh Allen", 24.0, scoring=None)]
        result, artifacts = self.run_build(
            Path(self._tmpdir()),
            self.match_doc(rows, default_scoring=None))
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], artifacts)

    def test_explicit_output_with_multiple_groups_fails_closed(self):
        rows = [
            self.mrow(869, "Josh Allen", 30.0, scoring="standard"),
            self.mrow(869, "Josh Allen", 40.0, scoring="ppr"),
        ]
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            match = tmp / "matched.json"
            match.write_text(json.dumps(self.match_doc(rows)), encoding="utf-8")
            out = tmp / "reference.json"
            result = subprocess.run(
                ["python3", "pipelines/build_source_reference.py",
                 "--input", str(match), "--output", str(out)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("--output-dir", result.stderr)
            self.assertFalse(out.exists())

    def _tmpdir(self):
        # TemporaryDirectory as a context manager is awkward across the
        # run_build helper; tests that need explicit paths use their own.
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        return self._td.name

    def write_match(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "schema": "trade-value-source-matches-v1",
                    "source": "fantasycalc",
                    "fetched_at": "2026-09-21T12:00:00Z",
                    "default_scoring": "ppr",
                    "default_teams": 12,
                    "summary": {"input_row_count": 5, "matched_count": 4, "review_count": 1},
                    "matched_rows": [
                        {"player_key": 869, "canonical_name": "Josh Allen", "source_player_name": "Josh Allen", "source": "fantasycalc", "value": 24.0, "scoring": "ppr", "teams": 12, "pos": "QB", "team": "BUF", "source_player_id": None},
                        {"player_key": 101, "canonical_name": "Bijan Robinson", "source_player_name": "Bijan Robinson", "source": "fantasycalc", "value": 67.5, "scoring": "ppr", "teams": 12, "pos": "RB", "team": "ATL", "source_player_id": None},
                        {"player_key": 202, "canonical_name": "Duplicate One", "source_player_name": "Duplicate One A", "source": "fantasycalc", "value": 10.0, "scoring": "ppr", "teams": 12, "pos": "WR", "team": "NO", "source_player_id": None},
                        {"player_key": 202, "canonical_name": "Duplicate One", "source_player_name": "Duplicate One B", "source": "fantasycalc", "value": 11.0, "scoring": "ppr", "teams": 12, "pos": "WR", "team": "NO", "source_player_id": None},
                    ],
                    "review_rows": [
                        {"reason": "no_match", "source_player_name": "Unknown Player", "value": 1.0}
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_qb_dimension_survives_reference_row_rebuild(self):
        # Regression: unique_reference_rows rebuilt rows with an explicit
        # field list that dropped `qb`, so the candidate builder could not
        # see the QB dimension (full_10_qb1 collapsed to full_10). The qb
        # field must survive the rebuild.
        import tempfile, subprocess
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            mp = tmp / "match.json"
            match = {
                "schema": "trade-value-source-matches-v1",
                "source": "fantasycalc", "fetched_at": "2026-09-21T12:00:00Z",
                "default_scoring": "ppr", "default_teams": 12, "default_qb": 2,
                "summary": {}, "review_rows": [],
                "matched_rows": [
                    {"player_key": 869, "canonical_name": "Josh Allen",
                     "source_player_name": "Josh Allen", "source": "fantasycalc",
                     "value": 24.0, "scoring": "ppr", "teams": 12, "qb": 2,
                     "pos": "QB", "team": "BUF", "source_player_id": None},
                ],
            }
            mp.write_text(json.dumps(match), encoding="utf-8")
            out = tmp / "ref.json"
            r = subprocess.run(["python3", "pipelines/build_source_reference.py",
                                "--input", str(mp), "--output", str(out)],
                               cwd=Path(__file__).resolve().parents[1],
                               capture_output=True, text=True)
            self.assertEqual(0, r.returncode, msg=r.stderr)
            ref = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(ref["combo_key"], "ppr_12_qb2")
            self.assertEqual(ref["rows"][0].get("qb"), 2)

    def test_builds_reference_rows_and_keeps_duplicate_conflicts_for_review(self):
        with TemporaryDirectory() as tmp:
            match = Path(tmp) / "matched.json"
            output = Path(tmp) / "reference.json"
            self.write_match(match)

            subprocess.run(
                [
                    "python3",
                    "pipelines/build_source_reference.py",
                    "--input",
                    str(match),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("trade-value-source-reference-v1", payload["schema"])
            self.assertEqual("ppr_12", payload["combo_key"])
            self.assertEqual(
                {
                    "matched_input_count": 4,
                    "reference_row_count": 2,
                    "inherited_review_count": 1,
                    "duplicate_review_count": 1,
                },
                payload["summary"],
            )
            self.assertEqual([101, 869], [row["player_key"] for row in payload["rows"]])
            self.assertEqual({"101": 67.5, "869": 24.0}, payload["values_by_player_key"])
            self.assertEqual(["no_match", "duplicate_player_key"], [row["reason"] for row in payload["review_rows"]])


if __name__ == "__main__":
    unittest.main()
