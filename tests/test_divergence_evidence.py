"""JEG-1277: offline eligibility audit for the four dated divergence reports
that JEG-952 (threshold tuning) needs before any threshold review.

The synthetic fixture proves the audit's rules. It never satisfies the real
evidence prerequisite. The committed-receipts fixture is copied from git
history by tools/research/divergence-evidence-audit/extract_receipts.py and
pins today's real verdict: three qualifying weeks per source, not four.

    python3 -m unittest -v tests.test_divergence_evidence
"""
from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools" / "research" / "divergence-evidence-audit"
FIXTURES = REPO / "tests" / "fixtures" / "divergence-evidence-audit"
DOCS = REPO / "docs" / "research" / "divergence-evidence-audit"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"divergence_evidence_{name}", TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit_mod = _load("audit")
extract_mod = _load("extract_receipts")
SYNTHETIC = json.loads((FIXTURES / "synthetic-four-weeks.json").read_text(encoding="utf-8"))
REAL = json.loads((FIXTURES / "committed-receipts.json").read_text(encoding="utf-8"))


def synthetic(weeks=(1, 2, 3, 4)) -> dict:
    doc = copy.deepcopy(SYNTHETIC)
    doc["receipts"] = [r for r in doc["receipts"] if r["report"]["week"] in weeks]
    return doc


def as_if_real(doc: dict) -> dict:
    """Strip the synthetic flags so the rules alone decide (contract tests only)."""
    doc = copy.deepcopy(doc)
    doc["synthetic"] = False
    for r in doc["receipts"]:
        r["synthetic"] = False
    return doc


def receipt(doc: dict, week: int) -> dict:
    return next(r for r in doc["receipts"] if r["report"]["week"] == week)


def counted(result: dict, source: str = "usatoday") -> list[int]:
    return result["sources"][source]["counted_weeks"]


def week_row(result: dict, week: int, source: str = "usatoday") -> dict:
    return next(row for row in result["sources"][source]["weeks"] if row["week"] == week)


class SyntheticNeverRealEvidence(unittest.TestCase):
    def test_four_synthetic_weeks_meet_the_contract_but_are_not_real_evidence(self):
        result = audit_mod.audit(synthetic())
        self.assertEqual(sorted(result["four_weeks_met"]), ["cbsros", "usatoday"])
        self.assertEqual(result["real_evidence_sufficient"], [])
        self.assertFalse(result["all_sources_sufficient"])
        self.assertFalse(result["threshold_review_allowed"])
        self.assertIsNone(result["threshold_recommendation"])
        for v in result["sources"].values():
            self.assertTrue(v["synthetic"])
            self.assertEqual(v["counted_weeks"], [1, 2, 3, 4])

    def test_one_synthetic_receipt_taints_a_real_looking_document(self):
        doc = as_if_real(synthetic())
        receipt(doc, 2)["synthetic"] = True
        result = audit_mod.audit(doc)
        self.assertEqual(result["four_weeks_met"], ["usatoday", "cbsros"])
        self.assertEqual(result["real_evidence_sufficient"], [])

    def test_rules_alone_accept_four_clean_weeks(self):
        # Contract positive path: with the flags removed the same data passes, so the
        # synthetic flag (not some other rule) is what keeps it out of real evidence.
        result = audit_mod.audit(as_if_real(synthetic()))
        self.assertEqual(result["real_evidence_sufficient"], ["usatoday", "cbsros"])
        self.assertTrue(result["threshold_review_allowed"])
        self.assertIsNone(result["threshold_recommendation"])


class WeekCounts(unittest.TestCase):
    def test_zero_reports(self):
        result = audit_mod.audit(as_if_real(synthetic(weeks=())))
        self.assertEqual(result["sources"], {})
        self.assertEqual(result["real_evidence_sufficient"], [])
        self.assertFalse(result["threshold_review_allowed"])

    def test_zero_qualifying_weeks_when_every_report_week_is_missing(self):
        doc = as_if_real(synthetic())
        for r in doc["receipts"]:
            r["report"]["week"] = None
        v = audit_mod.audit(doc)["sources"]["usatoday"]
        self.assertEqual(v["counted"], 0)
        self.assertEqual(v["captures_without_week"], 4)
        self.assertFalse(v["four_weeks_met"])

    def test_one_week(self):
        v = audit_mod.audit(as_if_real(synthetic(weeks=(2,))))["sources"]["usatoday"]
        self.assertEqual((v["counted"], v["four_weeks_met"]), (1, False))

    def test_three_weeks(self):
        result = audit_mod.audit(as_if_real(synthetic(weeks=(1, 2, 3))))
        self.assertEqual(counted(result), [1, 2, 3])
        self.assertEqual(result["real_evidence_sufficient"], [])
        self.assertFalse(result["threshold_review_allowed"])

    def test_four_weeks(self):
        self.assertEqual(counted(audit_mod.audit(as_if_real(synthetic()))), [1, 2, 3, 4])


class Duplicates(unittest.TestCase):
    def test_repeated_captures_of_one_week_count_once(self):
        doc = as_if_real(synthetic(weeks=(1, 2, 3)))
        again = copy.deepcopy(receipt(doc, 3))
        again["commit"], again["report"]["generated_at"] = "recapture-week-3", "2099-01-03T18:00:00Z"
        doc["receipts"].append(again)
        result = audit_mod.audit(doc)
        self.assertEqual(counted(result), [1, 2, 3])
        row = week_row(result, 3)
        self.assertEqual((row["captures"], row["qualifying_captures"]), (2, 2))
        self.assertEqual(row["representative"]["commit"], "recapture-week-3")  # newest capture represents it

    def test_a_week_that_serves_the_previous_weeks_data_is_not_new(self):
        doc = as_if_real(synthetic())
        fp = receipt(doc, 3)["served"]["sources"]["usatoday"]["fingerprint"]
        receipt(doc, 4)["served"]["sources"]["usatoday"]["fingerprint"] = fp
        result = audit_mod.audit(doc)
        self.assertEqual(counted(result), [1, 2, 3])
        self.assertEqual(week_row(result, 4)["why_not"], "served data repeats week 3")
        self.assertEqual(counted(result, "cbsros"), [1, 2, 3, 4])

    def test_report_labelled_a_new_week_but_served_last_weeks_charts(self):
        # The week 8 case (JEG-1172): content week 4, every chart still served as week 3.
        doc = as_if_real(synthetic())
        receipt(doc, 4)["served"]["sources"]["usatoday"]["week"] = 3
        result = audit_mod.audit(doc)
        self.assertEqual(counted(result), [1, 2, 3])
        self.assertEqual(week_row(result, 4)["rejections"], {"served_week_mismatch": 1})


class MissingDatesAndCounts(unittest.TestCase):
    def _rejected(self, mutate, reason, source="usatoday"):
        doc = as_if_real(synthetic())
        mutate(receipt(doc, 2))
        result = audit_mod.audit(doc)
        self.assertEqual(counted(result, source), [1, 3, 4], reason)
        self.assertIn(reason, week_row(result, 2, source)["rejections"])
        # A report-wide problem rejects week 2 for every source; a source's own problem only for it.
        expected = [] if _receipt_wide(reason) else ["cbsros"]
        self.assertEqual(result["real_evidence_sufficient"], expected, reason)

    def test_missing_report_date(self):
        self._rejected(lambda r: r["report"].pop("generated_at"), "missing_report_date")

    def test_missing_build_date(self):
        self._rejected(lambda r: r["report"].update(fixture_built_at=None), "missing_build_date")

    def test_missing_source_date(self):
        self._rejected(lambda r: r["source_meta"]["sources"]["usatoday"].update(source_date=None),
                       "source_date_missing")

    def test_missing_served_provenance(self):
        self._rejected(lambda r: r["served"]["sources"].pop("usatoday"), "served_provenance_missing")

    def test_served_index_from_another_content_week(self):
        self._rejected(lambda r: r["served"].update(content_week=1), "served_provenance_conflict")

    def test_unknown_served_week(self):
        self._rejected(lambda r: r["served"]["sources"]["usatoday"].update(week=None), "served_week_unknown")

    def test_missing_denominator(self):
        self._rejected(lambda r: r["sources"]["usatoday"]["combos"]["half_12"].pop("n"), "missing_counts")

    def test_missing_outlier_count(self):
        self._rejected(lambda r: r["sources"]["usatoday"]["combos"]["full_12"].update(outliers=None),
                       "missing_counts")

    def test_zero_denominator(self):
        self._rejected(lambda r: r["sources"]["usatoday"]["combos"]["full_12"].update(n=0), "zero_denominator")

    def test_rate_that_disagrees_with_its_counts(self):
        self._rejected(lambda r: r["sources"]["usatoday"]["combos"]["full_12"].update(outlier_rate=0.9),
                       "rate_count_mismatch")

    def test_missing_warning_list(self):
        self._rejected(lambda r: r["report"].update(flagged=None), "missing_warning_counts")

    def test_warning_count_that_disagrees_with_statuses(self):
        self._rejected(lambda r: r["report"].update(flagged=["USA Today"]), "warning_count_mismatch")

    def test_not_a_committed_receipt(self):
        # e.g. the historical 48%/52% figures quoted in Linear: a number without a report blob.
        self._rejected(lambda r: r.update(commit=None, report_blob=None), "not_committed_receipt")

    def test_reporter_rounding_is_not_a_count_mismatch(self):
        # 77 / 176 = 0.4375, which the reporter rounds (half to even) to 0.438.
        doc = as_if_real(synthetic())
        receipt(doc, 2)["sources"]["usatoday"]["combos"]["full_12"].update(n=176, outliers=77, outlier_rate=0.438)
        self.assertEqual(counted(audit_mod.audit(doc)), [1, 2, 3, 4])


def _receipt_wide(reason: str) -> bool:
    """Problems with the whole report, which reject the week for every source."""
    return reason in ("missing_report_date", "missing_build_date", "missing_warning_counts",
                      "warning_count_mismatch", "not_committed_receipt", "served_provenance_conflict")


class MixedScoring(unittest.TestCase):
    def test_changed_combo_set_is_incompatible(self):
        doc = as_if_real(synthetic())
        combos = receipt(doc, 4)["sources"]["usatoday"]["combos"]
        combos["full_12_qb1"] = combos.pop("full_12")
        v = audit_mod.audit(doc)["sources"]["usatoday"]
        self.assertTrue(v["mixed_identity"])
        self.assertEqual(v["counted_weeks"], [1, 2, 3])
        self.assertFalse(v["four_weeks_met"])

    def test_changed_scoring_basis_is_incompatible(self):
        doc = as_if_real(synthetic())
        receipt(doc, 1)["source_meta"]["sources"]["cbsros"]["scoring_basis"] = "SYNTHETIC projections: ppr page"
        result = audit_mod.audit(doc)
        v = result["sources"]["cbsros"]
        self.assertTrue(v["mixed_identity"])
        self.assertEqual(v["counted_weeks"], [2, 3, 4])
        self.assertIn("scoring basis", week_row(result, 1, "cbsros")["why_not"])
        self.assertEqual(result["real_evidence_sufficient"], ["usatoday"])

    def test_changed_thresholds_are_incompatible(self):
        doc = as_if_real(synthetic())
        receipt(doc, 4)["report"]["thresholds"] = {**receipt(doc, 4)["report"]["thresholds"], "warn_outlier_rate": 0.55}
        result = audit_mod.audit(doc)
        self.assertEqual(counted(result), [1, 2, 3])
        self.assertEqual(result["real_evidence_sufficient"], [])


class RealCommittedReceipts(unittest.TestCase):
    """Today's real verdict, from the frozen copy of git history."""

    @classmethod
    def setUpClass(cls):
        cls.result = audit_mod.audit(REAL)

    def test_inventory_is_every_committed_report(self):
        self.assertFalse(REAL["synthetic"])
        self.assertEqual(len(REAL["receipts"]), 55)
        self.assertEqual(self.result["report_weeks_seen"], [5, 6, 7, 8])
        self.assertTrue(all(r["commit"] and r["report_blob"] for r in REAL["receipts"]))

    def test_three_qualifying_weeks_per_source_and_no_threshold_review(self):
        self.assertEqual(sorted(self.result["sources"]), sorted(audit_mod.SOURCES))
        for s, v in self.result["sources"].items():
            self.assertEqual(v["counted_weeks"], [5, 6, 7], s)
            self.assertFalse(v["four_weeks_met"], s)
            self.assertFalse(v["mixed_identity"], s)
        self.assertEqual(self.result["four_weeks_met"], [])
        self.assertEqual(self.result["real_evidence_sufficient"], [])
        self.assertFalse(self.result["threshold_review_allowed"])
        self.assertIsNone(self.result["threshold_recommendation"])

    def test_week_8_report_served_week_7_for_every_source(self):
        for s in audit_mod.SOURCES:
            row = week_row(self.result, 8, s)
            self.assertEqual((row["captures"], row["qualifying_captures"]), (1, 0), s)
            self.assertEqual(row["rejections"], {"served_week_mismatch": 1}, s)
            self.assertEqual(row["served_weeks_seen"], [7], s)

    def test_historical_48_52_rates_are_an_early_superseded_capture_of_week_5(self):
        first = REAL["receipts"][0]
        self.assertEqual(first["commit"][:8], "f29e6e29")
        rates = {s: first["sources"][s]["combos"]["full_12"]["outlier_rate"] for s in ("cbsros", "razzball")}
        self.assertEqual(rates, {"cbsros": 0.483, "razzball": 0.517})
        for s in ("cbsros", "razzball"):
            row = week_row(self.result, 5, s)
            self.assertEqual(row["captures"], 20)
            self.assertNotEqual(row["representative"]["commit"], first["commit"])  # counted once, newest capture

    def test_value_impact_is_summary_only(self):
        for v in self.result["sources"].values():
            self.assertEqual(v["value_impact"], "summary")

    def test_frozen_receipts_carry_the_summaries_they_are_credited_with(self):
        # Codex P2 on #1140: the receipts themselves, not the original blobs, hold the
        # per-position statistics and the five largest deviations with their values.
        for r in REAL["receipts"]:
            for s, v in r["sources"].items():
                for key, c in v["combos"].items():
                    self.assertTrue(audit_mod.has_value_summary(c), (r["commit"][:8], s, key))
                    self.assertEqual(len(c["examples"]), 5, (r["commit"][:8], s, key))


class ValueImpact(unittest.TestCase):
    def _impact(self, mutate):
        doc = as_if_real(synthetic())
        for r in doc["receipts"]:
            mutate(r["sources"]["usatoday"]["combos"]["full_12"])
        return audit_mod.audit(doc)["sources"]["usatoday"]["value_impact"]

    def test_full_summaries_count(self):
        self.assertEqual(self._impact(lambda c: None), "summary")

    def test_flags_without_content_are_missing(self):
        # The shape the first extractor wrote: a count and a boolean.
        self.assertEqual(self._impact(lambda c: c.update(examples=5, by_position=True)), "missing")

    def test_examples_without_values_are_missing(self):
        self.assertEqual(self._impact(lambda c: c.update(examples=[{"player_key": 1}])), "missing")

    def test_positions_without_statistics_are_missing(self):
        self.assertEqual(self._impact(lambda c: c.update(by_position={"QB": {"n": 3}})), "missing")

    def test_value_impact_never_gates_the_week_count(self):
        doc = as_if_real(synthetic())
        for r in doc["receipts"]:
            r["sources"]["usatoday"]["combos"]["full_12"].update(examples=[], by_position={})
        v = audit_mod.audit(doc)["sources"]["usatoday"]
        self.assertEqual((v["counted"], v["value_impact"]), (4, "missing"))


class CommittedOutputsMatch(unittest.TestCase):
    def test_matrix_and_summary_are_regenerated_not_hand_edited(self):
        result = audit_mod.audit(REAL)
        self.assertEqual((DOCS / "availability-matrix.md").read_text(encoding="utf-8"),
                         audit_mod.markdown(result, REAL))
        self.assertEqual(json.loads((DOCS / "availability.json").read_text(encoding="utf-8")),
                         json.loads(json.dumps(audit_mod.summary_json(result))))


class ExtractorMatching(unittest.TestCase):
    def test_same_commit_index_with_the_report_week_wins(self):
        later = ("abc", {"content_week": 6})
        same = ("abc", {"content_week": 5})
        kind, hit = extract_mod.match_build([later, same], "abc", week=5)
        self.assertEqual((kind, hit[1]["content_week"]), ("same_commit", 5))

    def test_receipt_copies_counts_and_keeps_missing_provenance_null(self):
        report = {"schema": "source-divergence-v1", "week": 7, "generated_at": "g", "fixture_built_at": "b",
                  "summary": {"flagged": []}, "sources": {"cbs": {"status": "ok", "combos": {
                      "full_12": {"n": 10, "outliers": 1, "outlier_rate": 0.1, "bias": 0, "mad": 1, "status": "ok",
                                  "examples": [{}], "by_position": {"QB": {}}}}}}}
        r = extract_mod.receipt("c", "t", "blob", report, None, None, None)
        self.assertIsNone(r["served"])
        self.assertIsNone(r["source_meta"])
        self.assertIn("served_provenance_missing", audit_mod.capture(r, "cbs")["problems"])

    def test_receipt_keeps_the_value_impact_content_not_just_flags(self):
        combo = {"n": 10, "outliers": 1, "outlier_rate": 0.1, "bias": 0.4, "mad": 1.5, "status": "ok",
                 "examples": [{"player_key": 7, "value": 30.1, "consensus": 18.2, "extra": "dropped"}],
                 "by_position": {"QB": {"n": 4, "outliers": 1, "outlier_rate": 0.25, "bias": 2.0, "mad": 3.0}}}
        report = {"sources": {"cbs": {"status": "ok", "combos": {"full_12": combo}}}}
        row = extract_mod.receipt("c", "t", "blob", report, None, None, None)["sources"]["cbs"]["combos"]["full_12"]
        self.assertEqual(row["examples"], [{"player_key": 7, "value": 30.1, "consensus": 18.2}])
        self.assertEqual(row["by_position"], {"QB": {"n": 4, "outliers": 1, "outlier_rate": 0.25,
                                                     "bias": 2.0, "mad": 3.0}})
        self.assertTrue(audit_mod.has_value_summary(row))


if __name__ == "__main__":
    unittest.main()
