import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def reference_artifact(rows, review_rows=None, source="fantasycalc"):
    return {
        "schema": "trade-value-source-reference-v1",
        "generated_at": "2026-09-21T12:00:00Z",
        "input_match": "output/source-matches/fantasycalc/matched.json",
        "source": source,
        "fetched_at": "2026-09-21T12:00:00Z",
        "scoring": "ppr",
        "teams": 12,
        "combo_key": "ppr_12",
        "summary": {"matched_input_count": len(rows), "reference_row_count": len(rows),
                    "inherited_review_count": len(review_rows or []), "duplicate_review_count": 0},
        "rows": rows,
        "values_by_player_key": {str(r["player_key"]): r["value"] for r in rows
                                 if isinstance(r.get("value"), (int, float))},
        "player_key_by_source_name": {},
        "review_rows": review_rows or [],
    }


def comparison_fixture():
    return {
        "built_at": "2026-09-19T15:48:29Z",
        "display": {"josh allen": "Josh Allen", "bijan robinson": "Bijan Robinson"},
        "player_keys": {"josh allen": 869, "bijan robinson": 101},
        "teams": {"josh allen": "BUF", "bijan robinson": "ATL"},
        "value_weeks": {"monday": 2},
        "source_validation": {"fantasycalc": "live"},
        "sources": {
            "fantasycalc": {
                "name": "FantasyCalc",
                "value_provenance": "published",
                "fetched_at": "2026-09-19T15:48:29Z",
                "combos": {
                    "full_12": {
                        "native": {"josh allen": 20.0, "bijan robinson": 60.0},
                        "reindexed": {"josh allen": 29.0, "bijan robinson": 74.0},
                        "n": 2,
                    }
                },
            }
        },
    }


def ref_row(key, name, value, scoring="ppr", teams=12, qb=None):
    row = {"player_key": key, "canonical_name": name, "source_player_name": name,
           "source": "fantasycalc", "value": value, "scoring": scoring, "teams": teams,
           "pos": "QB", "team": "BUF", "source_player_id": None}
    if qb is not None:
        row["qb"] = qb
    return row


class ComparisonCandidateBuildTest(unittest.TestCase):
    def run_script(self, script, *args):
        result = subprocess.run(
            ["python3", f"pipelines/{script}", *args],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(0, result.returncode, msg=f"{script} failed:\n{result.stderr}")
        return result

    def build_section(self, tmp: Path, rows, review_rows=None, extra_args=()):
        ref = tmp / "reference.json"
        fixture = tmp / "comparison.json"
        section = tmp / "section.json"
        write_json(ref, reference_artifact(rows, review_rows))
        write_json(fixture, comparison_fixture())
        self.run_script("build_comparison_source_section.py",
                        "--input", str(ref), "--comparison", str(fixture),
                        "--output", str(section), *extra_args)
        return json.loads(section.read_text(encoding="utf-8")), fixture

    def test_builds_candidate_section_with_native_values_only(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [ref_row(869, "Josh Allen", 24.0), ref_row(101, "Bijan Robinson", 67.5),
                    ref_row(999999, "Ghost Player", 5.0)]
            section, _ = self.build_section(tmp, rows)

            self.assertEqual("trade-value-comparison-section-candidate-v1", section["schema"])
            self.assertEqual("fantasycalc", section["section_key"])
            self.assertEqual("pending", section["reindex_status"])
            self.assertEqual("published", section["value_provenance"])

            combos = section["combos"]
            self.assertEqual(["full_12"], sorted(combos))
            native = combos["full_12"]["native"]
            self.assertEqual({"josh allen": 24.0, "bijan robinson": 67.5}, native)
            self.assertNotIn("reindexed", combos["full_12"])
            self.assertNotIn("fit", combos["full_12"])
            self.assertNotIn("index_total", combos["full_12"])

            reasons = [row["reason"] for row in section["review_rows"]]
            self.assertIn("no_canonical_slug", reasons)
            ghost = next(row for row in section["review_rows"] if row["reason"] == "no_canonical_slug")
            self.assertEqual(999999, ghost["player_key"])

            summary = section["summary"]
            self.assertEqual(3, summary["reference_row_count"])
            self.assertEqual(2, summary["placed_count"])
            self.assertEqual(1, summary["review_row_count"])

    def test_missing_values_stay_missing_never_zero(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [ref_row(869, "Josh Allen", 24.0), ref_row(101, "Bijan Robinson", None)]
            section, _ = self.build_section(tmp, rows)

            native = section["combos"]["full_12"]["native"]
            self.assertEqual({"josh allen": 24.0}, native)
            self.assertNotIn(0.0, list(native.values()))
            reasons = [row["reason"] for row in section["review_rows"]]
            self.assertIn("non_numeric_value", reasons)

    def test_duplicate_player_key_goes_to_review_never_merged(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [ref_row(869, "Josh Allen", 24.0), ref_row(869, "Josh Allen", 25.0)]
            section, _ = self.build_section(tmp, rows)

            native = section["combos"]["full_12"]["native"]
            self.assertEqual({"josh allen": 24.0}, native)
            reasons = [row["reason"] for row in section["review_rows"]]
            self.assertIn("duplicate_player_key", reasons)

    def test_inherited_review_rows_are_carried_forward(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [ref_row(869, "Josh Allen", 24.0)]
            review = [{"reason": "no_match", "source_player_name": "Unknown Player", "value": 1.0}]
            section, _ = self.build_section(tmp, rows, review_rows=review)

            reasons = [row["reason"] for row in section["review_rows"]]
            self.assertIn("no_match", reasons)
            self.assertEqual(1, section["summary"]["inherited_review_count"])

    def test_merge_writes_candidate_artifact_and_report_without_touching_fixture(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [ref_row(869, "Josh Allen", 24.0), ref_row(101, "Bijan Robinson", 67.5)]
            section_payload, fixture = self.build_section(tmp, rows)
            section_path = tmp / "section.json"

            before = fixture.read_bytes()
            candidate_out = tmp / "candidate.json"
            report_out = tmp / "report.json"
            self.run_script("merge_comparison_candidate.py",
                            "--candidate", str(section_path), "--comparison", str(fixture),
                            "--output", str(candidate_out), "--report", str(report_out))

            # Live fixture untouched.
            self.assertEqual(before, fixture.read_bytes())

            candidate = json.loads(candidate_out.read_text(encoding="utf-8"))
            self.assertIn("fantasycalc", candidate["sources"])
            installed = candidate["sources"]["fantasycalc"]
            self.assertEqual("trade-value-comparison-section-candidate-v1", installed["schema"])
            self.assertEqual("candidate", candidate["source_validation"]["fantasycalc"])
            self.assertEqual("fantasycalc", candidate["candidate"]["section_key"])
            self.assertEqual("pending", candidate["candidate"]["reindex_status"])
            # The pre-existing baseline section was replaced, not duplicated.
            self.assertEqual(1, len(candidate["sources"]))

            report = json.loads(report_out.read_text(encoding="utf-8"))
            self.assertEqual("trade-value-comparison-candidate-report-v1", report["schema"])
            self.assertEqual("pass", report["zero_fill_check"]["status"])
            compared = report["combo_comparison"]
            self.assertEqual("current fixture section", compared["baseline"])
            full_12 = compared["combos"]["full_12"]
            self.assertEqual(2, full_12["n_overlap"])
            self.assertEqual(0, full_12["n_candidate_only"])
            # Candidate native (24.0/67.5) vs current native (20.0/60.0): deltas 4.0, 7.5.
            self.assertAlmostEqual(5.75, full_12["mean_abs_delta"])
            self.assertAlmostEqual(7.5, full_12["max_abs_delta"])
            self.assertEqual(2, len(full_12["largest_deltas"]))

    def test_merge_with_new_section_key_reports_no_baseline(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [ref_row(869, "Josh Allen", 24.0)]
            ref = tmp / "reference.json"
            fixture = tmp / "comparison.json"
            section_path = tmp / "section.json"
            payload = reference_artifact(rows, source="razzball")
            write_json(ref, payload)
            write_json(fixture, comparison_fixture())
            self.run_script("build_comparison_source_section.py",
                            "--input", str(ref), "--comparison", str(fixture),
                            "--output", str(section_path))

            candidate_out = tmp / "candidate.json"
            report_out = tmp / "report.json"
            self.run_script("merge_comparison_candidate.py",
                            "--candidate", str(section_path), "--comparison", str(fixture),
                            "--output", str(candidate_out), "--report", str(report_out))

            candidate = json.loads(candidate_out.read_text(encoding="utf-8"))
            self.assertIn("razzball", candidate["sources"])
            self.assertIn("fantasycalc", candidate["sources"])
            report = json.loads(report_out.read_text(encoding="utf-8"))
            self.assertEqual("none (new section key)", report["combo_comparison"]["baseline"])


    def test_qb_dimension_carried_in_combo_key_never_collapsed(self):
        # qb2 = leagues starting 2 QBs. The QB dimension must survive as its
        # own combo (full_12_qb2), never collapsed into full_12 or silently
        # mapped. Regression: the builder ignored the qb field entirely.
        with TemporaryDirectory() as td:
            tmp = Path(td)
            rows = [ref_row(869, "Josh Allen", 20.0, qb=1),
                    ref_row(101, "Bijan Robinson", 60.0, qb=1),
                    ref_row(869, "Josh Allen", 40.0, qb=2),
                    ref_row(101, "Bijan Robinson", 55.0, qb=2)]
            # duplicate player_keys across qb splits must not collapse: build
            # one section per qb split (the pipeline's per-combo reference rule)
            for qb in (1, 2):
                qrows = [r for r in rows if r["qb"] == qb]
                section, _ = self.build_section(tmp, qrows)
                combo = f"full_12_qb{qb}"
                self.assertEqual(sorted(section["combos"].keys()), [combo],
                                 f"qb={qb} rows must land in {combo} only")
                self.assertIn("player_keys", section["combos"][combo])

    def test_rows_without_qb_keep_unsuffixed_combo(self):
        with TemporaryDirectory() as td:
            tmp = Path(td)
            rows = [ref_row(869, "Josh Allen", 20.0), ref_row(101, "Bijan Robinson", 60.0)]
            section, _ = self.build_section(tmp, rows)
            self.assertEqual(sorted(section["combos"].keys()), ["full_12"])

    def test_merge_refuses_to_write_inside_data(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [ref_row(869, "Josh Allen", 24.0)]
            section_payload, fixture = self.build_section(tmp, rows)
            section_path = tmp / "section.json"

            evil = ROOT / "data" / "fixtures" / "current" / "evil-candidate.json"
            result = subprocess.run(
                ["python3", "pipelines/merge_comparison_candidate.py",
                 "--candidate", str(section_path), "--comparison", str(fixture),
                 "--output", str(evil)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("Refusing to write inside data/", result.stderr)
            self.assertFalse(evil.exists())

    def test_multiple_reference_inputs_union_into_single_candidate(self):
        # The reference stage emits one artifact per (scoring, teams, qb)
        # group; the section builder must consume all of a source's artifacts
        # into ONE candidate section (union of combos), not one section per
        # artifact.
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows_ppr = [ref_row(869, "Josh Allen", 24.0, scoring="ppr"),
                        ref_row(101, "Bijan Robinson", 67.5, scoring="ppr")]
            rows_half = [ref_row(869, "Josh Allen", 20.0, scoring="half_ppr"),
                         ref_row(101, "Bijan Robinson", 60.0, scoring="half_ppr")]
            review = [{"reason": "no_match", "source_player_name": "Unknown Player",
                       "value": 1.0}]
            ref1 = tmp / "ref-ppr.json"
            ref2 = tmp / "ref-half.json"
            # Both artifacts replicate the same input-level review rows, as
            # the reference builder does per group.
            write_json(ref1, reference_artifact(rows_ppr, review, source="usatoday"))
            write_json(ref2, reference_artifact(rows_half, review, source="usatoday"))
            fixture = tmp / "comparison.json"
            write_json(fixture, comparison_fixture())
            section_path = tmp / "section.json"
            self.run_script("build_comparison_source_section.py",
                            "--input", str(ref1), str(ref2),
                            "--comparison", str(fixture),
                            "--section-key", "usatoday",
                            "--output", str(section_path))
            section = json.loads(section_path.read_text(encoding="utf-8"))

            self.assertEqual(["full_12", "half_12"], sorted(section["combos"]))
            self.assertEqual({"josh allen": 24.0, "bijan robinson": 67.5},
                             section["combos"]["full_12"]["native"])
            self.assertEqual({"josh allen": 20.0, "bijan robinson": 60.0},
                             section["combos"]["half_12"]["native"])
            # Identical inherited review rows are deduped, not doubled.
            no_match = [r for r in section["review_rows"] if r["reason"] == "no_match"]
            self.assertEqual(1, len(no_match))
            self.assertEqual(1, section["summary"]["inherited_review_count"])
            self.assertEqual(4, section["summary"]["reference_row_count"])
            self.assertEqual(4, section["summary"]["placed_count"])
            # Both inputs are recorded for provenance.
            self.assertEqual([str(ref1), str(ref2)], section["input_reference"])

    def test_duplicate_within_one_combo_still_flagged_across_inputs(self):
        # The dedupe key widened to (player_key, combo) so one player can
        # appear once per combo; a repeat WITHIN one combo (even across two
        # reference inputs) is still a genuine duplicate.
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            ref1 = tmp / "r1.json"
            ref2 = tmp / "r2.json"
            write_json(ref1, reference_artifact(
                [ref_row(869, "Josh Allen", 24.0, scoring="ppr")], source="usatoday"))
            write_json(ref2, reference_artifact(
                [ref_row(869, "Josh Allen", 25.0, scoring="ppr")], source="usatoday"))
            fixture = tmp / "comparison.json"
            write_json(fixture, comparison_fixture())
            section_path = tmp / "section.json"
            self.run_script("build_comparison_source_section.py",
                            "--input", str(ref1), str(ref2),
                            "--comparison", str(fixture),
                            "--output", str(section_path))
            section = json.loads(section_path.read_text(encoding="utf-8"))
            self.assertEqual(["full_12"], sorted(section["combos"]))
            self.assertEqual({"josh allen": 24.0},
                             section["combos"]["full_12"]["native"])
            dupes = [r for r in section["review_rows"]
                     if r["reason"] == "duplicate_player_key"]
            self.assertEqual(1, len(dupes))
            self.assertEqual("full_12", dupes[0]["combo"])

    def test_single_reference_input_keeps_string_input_reference(self):
        # One input behaves exactly as before: input_reference stays a plain
        # string path.
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [ref_row(869, "Josh Allen", 24.0)]
            section, _ = self.build_section(tmp, rows)
            self.assertIsInstance(section["input_reference"], str)
            self.assertTrue(section["input_reference"].endswith("reference.json"))

    def test_multiple_reference_inputs_must_agree_on_source_and_vintage(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fixture = tmp / "comparison.json"
            write_json(fixture, comparison_fixture())

            ref_a = tmp / "a.json"
            write_json(ref_a, reference_artifact(
                [ref_row(869, "Josh Allen", 24.0)], source="usatoday"))
            ref_b = tmp / "b.json"
            payload_b = reference_artifact(
                [ref_row(869, "Josh Allen", 24.0)], source="fantasycalc")
            write_json(ref_b, payload_b)
            out = tmp / "section.json"
            result = subprocess.run(
                ["python3", "pipelines/build_comparison_source_section.py",
                 "--input", str(ref_a), str(ref_b),
                 "--comparison", str(fixture), "--output", str(out)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("refusing to mix sources", result.stderr)

            ref_c = tmp / "c.json"
            payload_c = reference_artifact(
                [ref_row(869, "Josh Allen", 24.0)], source="usatoday")
            payload_c["fetched_at"] = "2026-09-20T12:00:00Z"
            write_json(ref_c, payload_c)
            result = subprocess.run(
                ["python3", "pipelines/build_comparison_source_section.py",
                 "--input", str(ref_a), str(ref_c),
                 "--comparison", str(fixture), "--output", str(out)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("refusing to mix vintages", result.stderr)


if __name__ == "__main__":
    unittest.main()
