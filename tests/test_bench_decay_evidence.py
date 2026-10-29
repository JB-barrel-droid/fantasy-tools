"""JEG-1276: the bench-decay evidence benchmark reruns offline from a fixed
manifest and rejects future or leaked dates, missing horizons and
missing-versus-zero mistakes. Run: python3 -m unittest tests.test_bench_decay_evidence
"""
import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "research" / "bench-decay-evidence" / "bench_decay_evidence.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "bench-decay-evidence"

_spec = importlib.util.spec_from_file_location("bench_decay_evidence", TOOL)
bde = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bde)

# Fixture file -> (manifest id, path inside the temporary root, content block)
FIXTURE_SOURCES = [
    ("bench_by_week.json", "post1_bench_by_week", "data/bench_by_week.json",
     {"kind": "mixed", "content_end_date": "2026-10-23"}),
    ("breakout_rate.json", "post1_breakout_rate", "data/breakout_rate.json",
     {"kind": "seasons", "first_season": 2015, "last_season": 2025}),
    ("starter_bench_risk.json", "post1_starter_bench_risk", "data/starter_bench_risk.json",
     {"kind": "snapshot", "content_end_date": "2026-10-23"}),
    ("source_accuracy.json", "jeg943_source_accuracy", "data/source_accuracy.json",
     {"kind": "content_weeks", "season": 2026, "first_week": 2, "last_week": 6}),
    ("lineup_m.json", "jeg528_lineup_m", "data/lineup_m.json",
     {"kind": "seasons", "first_season": 2015, "last_season": 2025}),
]


class FixtureCase(unittest.TestCase):
    """A temporary root holding the fixtures, with a manifest pinned to them."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        sources = []
        for name, sid, rel, content in FIXTURE_SOURCES:
            dest = self.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(FIXTURES / name, dest)
            sources.append({"id": sid, "path": rel, "origin": "fixture", "source_date": "2026-10-23",
                            "capture_date": "2026-10-23", "content": copy.deepcopy(content),
                            "sha256": bde.sha256(dest), "required": True})
        shutil.copy(FIXTURES / "timing_rule.txt", self.root / "timing_rule.txt")
        self.manifest = {
            "ticket": "JEG-1276", "as_of": "2026-10-29",
            "baseline": {"branch": "main", "commit": "fixture"},
            "setting": {"scoring": "ppr", "teams": 12},
            "sources": sources,
            "rules": [{"id": "jeg528_timing_factor", "source_date": "2026-10-16", "capture_date": "2026-10-16",
                       "statement": "fixture rule", "full_season_weeks": 17,
                       "must_contain": [{"path": "timing_rule.txt", "line": "FULL_SEASON_WEEKS = 17"}]}],
        }

    def source(self, sid):
        return next(s for s in self.manifest["sources"] if s["id"] == sid)

    def rewrite(self, sid, mutate):
        """Change a fixture artifact and re-pin its hash (a deliberate new manifest)."""
        entry = self.source(sid)
        path = self.root / entry["path"]
        data = json.loads(path.read_text())
        mutate(data)
        path.write_text(json.dumps(data))
        entry["sha256"] = bde.sha256(path)

    def build(self):
        return bde.build(self.manifest, self.root)

    def row(self, result, rid):
        return next(r for r in result["rows"] if r["id"] == rid)


class PositiveTests(FixtureCase):
    def test_rerun_is_deterministic(self):
        first = bde.outputs(self.build())
        second = bde.outputs(self.build())
        self.assertEqual(first, second)

    def test_rows_cover_both_components_and_every_horizon(self):
        result = self.build()
        ids = {r["id"] for r in result["rows"]}
        self.assertEqual({f"F1.w{w:02d}" for w in range(1, 18)}, {i for i in ids if i.startswith("F1.")})
        self.assertEqual({f"O1.w{w:02d}" for w in range(4, 17)}, {i for i in ids if i.startswith("O1.")})
        self.assertEqual({"fill-in insurance", "option value", "projection accuracy over time"},
                         {r["component"] for r in result["rows"]})

    def test_every_row_has_an_evidence_class_window_cohort_and_n(self):
        allowed = set(self.build()["evidence_classes"])
        for row in self.build()["rows"]:
            self.assertIn(row["evidence"], allowed, row["id"])
            for key in ("window", "cohort", "n"):
                self.assertNotIn(row[key], (None, ""), f"{row['id']} {key}")

    def test_hypothetical_rows_are_never_labelled_measured(self):
        for row in self.build()["rows"]:
            if row["id"].startswith(("F3.", "F4.")):
                self.assertTrue(row["evidence"].startswith("hypothetical"), row["id"])
                self.assertEqual(row["n"], bde.NA, row["id"])

    def test_timing_series_matches_the_604_rule_including_the_empty_window(self):
        result = self.build()
        self.assertAlmostEqual(self.row(result, "F4.w01")["values"]["timing_factor_604"], round(16 / 17, 4))
        self.assertAlmostEqual(self.row(result, "F4.w16")["values"]["timing_factor_604"], round(1 / 17, 4))
        # Week 17: window (18, 17) is empty; #604 leaves the factor at 1.
        self.assertEqual(self.row(result, "F4.w17")["values"]["timing_factor_604"], 1.0)

    def test_hazard_replay_reproduces_jeg528_figures(self):
        # JEG-528: RB starter misses at least one game ~86% with 12 weeks left, ~39% with 3.
        values = self.row(self.build(), "F3.RB")["values"]
        self.assertAlmostEqual(values["p_miss_ge1_in_12"], round(1 - 0.85 ** 12, 4))
        self.assertAlmostEqual(values["p_miss_ge1_in_3"], round(1 - 0.85 ** 3, 4))


class DateTests(FixtureCase):
    def test_future_capture_date_is_rejected(self):
        self.source("post1_breakout_rate")["capture_date"] = "2026-10-30"
        with self.assertRaisesRegex(bde.EvidenceError, "future date"):
            self.build()

    def test_future_source_date_is_rejected(self):
        self.source("post1_breakout_rate")["source_date"] = "2026-11-01"
        with self.assertRaisesRegex(bde.EvidenceError, "future date"):
            self.build()

    def test_content_week_after_capture_is_rejected(self):
        # Content week 7 ends Monday 2026-10-26, after a 2026-10-23 capture.
        self.source("jeg943_source_accuracy")["content"]["last_week"] = 7
        with self.assertRaisesRegex(bde.EvidenceError, "leaked date"):
            self.build()

    def test_content_week_6_is_accepted_at_a_2026_10_23_capture(self):
        self.assertEqual(bde.content_week_end(2026, 6).isoformat(), "2026-10-19")
        self.build()

    def test_incomplete_season_is_rejected(self):
        self.source("post1_breakout_rate")["content"]["last_season"] = 2026
        with self.assertRaisesRegex(bde.EvidenceError, "leaked date"):
            self.build()

    def test_content_end_date_after_capture_is_rejected(self):
        self.source("post1_starter_bench_risk")["content"]["content_end_date"] = "2026-10-24"
        with self.assertRaisesRegex(bde.EvidenceError, "leaked date"):
            self.build()

    def test_malformed_date_is_rejected(self):
        self.manifest["as_of"] = "Oct 29"
        with self.assertRaisesRegex(bde.EvidenceError, "not an ISO date"):
            self.build()


class HorizonTests(FixtureCase):
    def test_missing_model_week_is_rejected(self):
        self.rewrite("post1_bench_by_week",
                     lambda d: d["model_bench_share_by_week"].pop(8))
        with self.assertRaisesRegex(bde.EvidenceError, r"missing horizons \[9\]"):
            self.build()

    def test_missing_breakout_week_is_rejected(self):
        self.rewrite("post1_bench_by_week",
                     lambda d: d.__setitem__("breakout_rate_by_week", d["breakout_rate_by_week"][:-1]))
        with self.assertRaisesRegex(bde.EvidenceError, r"missing horizons \[16\]"):
            self.build()

    def test_duplicate_week_is_rejected(self):
        self.rewrite("post1_bench_by_week",
                     lambda d: d["model_bench_share_by_week"].append(dict(d["model_bench_share_by_week"][0])))
        with self.assertRaisesRegex(bde.EvidenceError, "appears twice"):
            self.build()

    def test_missing_remaining_weeks_is_rejected_not_zeroed(self):
        self.rewrite("post1_bench_by_week",
                     lambda d: d["model_bench_share_by_week"][3].pop("remaining_weeks"))
        with self.assertRaisesRegex(bde.EvidenceError, "remaining_weeks is missing"):
            self.build()

    def test_missing_series_is_rejected(self):
        self.rewrite("post1_bench_by_week", lambda d: d.pop("breakout_rate_by_week"))
        with self.assertRaisesRegex(bde.EvidenceError, "series is missing"):
            self.build()


class MissingVersusZeroTests(FixtureCase):
    def test_missing_value_is_reported_missing_not_zero(self):
        # The fixture drops bench_share_by_pos.TE at content week 5.
        values = self.row(self.build(), "F1.w05")["values"]
        self.assertEqual(values["bench_share_TE"], "missing")
        self.assertNotEqual(values["bench_share_TE"], 0)

    def test_real_zero_stays_zero(self):
        values = self.row(self.build(), "F1.w14")["values"]
        self.assertEqual(values["bye_share"], 0.0)
        self.assertNotEqual(values["bye_share"], "missing")
        self.assertEqual(self.row(self.build(), "O3.QB.d2")["values"]["breakouts"], 0)

    def test_null_is_missing(self):
        self.rewrite("post1_bench_by_week",
                     lambda d: d["model_bench_share_by_week"][0].__setitem__("bench_share_overall", None))
        values = self.row(self.build(), "F1.w01")["values"]
        self.assertEqual(values["bench_share"], "missing")
        # Arithmetic on a missing value stays missing.
        self.assertEqual(self.row(self.build(), "F4.w01")["values"]["share_x_weeks"], "missing")

    def test_absent_sample_count_is_missing_not_zero(self):
        n = self.row(self.build(), "O1.w04")["n"]
        self.assertEqual(n, "missing")
        self.assertEqual(self.row(self.build(), "F1.w01")["n"], bde.NA)

    def test_markdown_never_prints_missing_as_zero(self):
        md = bde.render_md(self.build())
        line = next(x for x in md.splitlines() if x.startswith("| F1.w05 "))
        self.assertTrue(line.rstrip(" |").endswith("missing"), line)


class SourceTests(FixtureCase):
    def test_changed_artifact_without_new_pin_is_rejected(self):
        path = self.root / self.source("post1_breakout_rate")["path"]
        path.write_text(path.read_text().replace("0.04", "0.05"))
        with self.assertRaisesRegex(bde.EvidenceError, "does not match the manifest"):
            self.build()

    def test_absent_source_is_a_gap_not_fabricated_rows(self):
        (self.root / self.source("post1_breakout_rate")["path"]).unlink()
        result = self.build()
        self.assertIn("absent:post1_breakout_rate", {g["id"] for g in result["gaps"]})
        self.assertFalse([r for r in result["rows"] if r["id"].startswith(("O2.", "O3."))])

    def test_missing_rule_line_is_a_gap(self):
        (self.root / "timing_rule.txt").write_text("FULL_SEASON_WEEKS = 18\n")
        result = self.build()
        self.assertFalse(result["rules"][0]["all_present"])
        self.assertIn("rule:jeg528_timing_factor", {g["id"] for g in result["gaps"]})


class CommittedEvidenceTests(unittest.TestCase):
    """The committed manifest, at its pinned hashes, against the repo itself."""

    def test_manifest_dates_and_hashes_hold_and_outputs_are_current(self):
        self.assertEqual(bde.main(["--check"]), 0)

    def test_pinned_604_rule_lines_are_still_in_the_code(self):
        manifest = json.loads(bde.MANIFEST.read_text())
        for rule in bde.check_rules(manifest, REPO):
            self.assertTrue(rule["all_present"], rule)

    def test_every_source_has_the_dates_and_hash_the_ticket_requires(self):
        manifest = json.loads(bde.MANIFEST.read_text())
        for entry in manifest["sources"]:
            for key in ("source_date", "capture_date", "content", "sha256"):
                self.assertIn(key, entry, entry["id"])
            self.assertEqual(len(entry["sha256"]), 64, entry["id"])


if __name__ == "__main__":
    unittest.main()
