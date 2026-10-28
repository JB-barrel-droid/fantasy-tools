"""Post-validation isolation accepts only a named changed source and a green retry."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from pipelines import isolate_post_validate as iso
from pipelines import rebuild_comparison_chain as chain
from pipelines import record_post_rebuild_validation


def fixture(cbs_value=1, espn_value=1):
    return {"sources": {
        "cbs": {"combos": {"full_12": {"values": {"x": cbs_value}}},
                "week_designated": "Week 8"},
        "espn": {"combos": {"full_12": {"values": {"x": espn_value}}},
                 "week_designated": "Week 8"}},
        "source_validation": {"cbs": {"ok": cbs_value == 1}, "espn": {"ok": True}}}


def fail(message):
    return ("FAIL: test_values (tests.test_source_integrity.TestSource)\n"
            "----------------------------------------------------------------------\n"
            f"AssertionError: {message}\n"
            "Ran 1 test in 0.1s\nFAILED (failures=1)\nmake: *** [test-core] Error 1\n")


class TestAttribution(unittest.TestCase):
    def test_long_alias_does_not_also_name_cbs(self):
        self.assertEqual(iso.failing_roots(fail("CBS rest of season malformed")), {"cbsros"})

    def test_unknown_multiple_or_traceback_only_declined(self):
        for message in ("invalid value", "CBS and ESPN invalid", "cbsros and cbs invalid"):
            with self.subTest(message=message), self.assertRaises(ValueError):
                iso.failing_roots(fail(message))
        log = ("ERROR: test_values (tests.test_source_integrity.TestSource)\n"
               "  File '/tmp/cbs.py', line 1\nValueError: malformed data\n")
        with self.assertRaises(ValueError):
            iso.failing_roots(log)

    def test_every_failure_must_name_same_source(self):
        with self.assertRaises(ValueError):
            iso.failing_roots(fail("cbs malformed") + fail("unknown output"))


class TestIsolation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.fixture_path = self.repo / chain.FIXTURE_REL
        self.fixture_path.parent.mkdir(parents=True)
        self.fixture_path.write_text(json.dumps(fixture()), encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.org",
                        "commit", "-qm", "baseline"], cwd=self.repo, check=True)
        status = {"success": True, "outcome": "green", "held": [], "held_detail": {},
                  "sources": {"cbs": "promoted", "espn": "promoted"},
                  "detail": {"cbs": {"status": "ok", "promoted": 1, "sections": 1},
                             "espn": {"status": "ok", "promoted": 1, "sections": 1}}}
        path = self.repo / iso.STATUS_RELS[0]
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(status), encoding="utf-8")

    def _change(self, cbs=2, espn=1):
        doc = fixture(cbs, espn)
        if cbs != 1:
            doc["sources"]["cbs"]["promoted_at"] = "2026-10-28T12:00:00Z"
            directory = self.repo / chain.PROMOTIONS_REL
            directory.mkdir(parents=True, exist_ok=True)
            record = directory / "cbs-2026-10-28-promotion.json"
            record.write_text(json.dumps({"source_key": "cbs", "promoted_at": "2026-10-28T12:00:00Z",
                                          "review_verdict": "ready",
                                          "section_after_sha256": chain._canonical_sha(doc["sources"]["cbs"])}))
        self.fixture_path.write_text(json.dumps(doc), encoding="utf-8")

    def _status(self):
        return json.loads((self.repo / iso.STATUS_RELS[0]).read_text(encoding="utf-8"))

    def test_bad_cbs_keeps_last_section_and_needs_retry_confirmation(self):
        self._change()
        self.assertEqual(iso.isolate(self.repo, fail("cbs invalid values"), 9), "cbs")
        result = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(result["sources"]["cbs"]["combos"]["full_12"]["values"]["x"], 1)
        self.assertEqual(result["sources"]["espn"], fixture()["sources"]["espn"])
        self.assertEqual(result["source_validation"]["cbs"], {"ok": True})
        self.assertEqual(result["sources"]["cbs"]["validationHold"]["root"], "cbs")
        self.assertFalse(self._status()["success"])
        self.assertEqual(iso.confirm(self.repo), "cbs")
        self.assertEqual(self._status()["outcome"], "published_with_holds")

    def test_unknown_or_unchanged_never_mutates(self):
        self._change()
        original = self.fixture_path.read_bytes()
        for log in (fail("invalid values"), fail("espn invalid values")):
            with self.subTest(log=log), self.assertRaises(ValueError):
                iso.isolate(self.repo, log, 9)
            self.assertEqual(self.fixture_path.read_bytes(), original)

    def test_espn_anchor_is_not_isolated(self):
        self._change(espn=2)
        with self.assertRaisesRegex(ValueError, "shared reindex anchor"):
            iso.isolate(self.repo, fail("espn invalid values"), 9)

    def test_confirm_requires_hold(self):
        self._change()
        iso.isolate(self.repo, fail("cbs invalid values"), 9)
        doc = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        del doc["sources"]["cbs"]["validationHold"]
        self.fixture_path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hold disappeared"):
            iso.confirm(self.repo)
        self.assertFalse(self._status()["success"])

    def test_failed_retry_stays_blocked(self):
        self._change()
        iso.isolate(self.repo, fail("cbs invalid values"), 9)
        record_post_rebuild_validation.record(self.repo, fail("unknown later failure"))
        with self.assertRaisesRegex(ValueError, "no pending"):
            iso.confirm(self.repo)
        self.assertEqual(self._status()["outcome"], "failed")

    def test_matching_promotion_record_is_retired(self):
        self._change()
        doc = json.loads(self.fixture_path.read_text())
        directory = self.repo / chain.PROMOTIONS_REL
        directory.mkdir(parents=True, exist_ok=True)
        record = directory / "cbs-2026-10-28-promotion.json"
        record.write_text(json.dumps({"source_key": "cbs", "promoted_at": "2026-10-28T12:00:00Z",
                                      "review_verdict": "ready",
                                      # The shared reindex changes the section hash later.
                                      "section_after_sha256": "0" * 64}))
        iso.isolate(self.repo, fail("cbs invalid values"), 9)
        self.assertFalse(record.exists())
        self.assertTrue(record.with_name("cbs-2026-10-28-promotion.rolled-back.json").exists())

    def test_unmatched_promotion_record_declines_without_changes(self):
        self._change()
        directory = self.repo / chain.PROMOTIONS_REL
        directory.mkdir(parents=True, exist_ok=True)
        record = directory / "cbs-2026-10-28-promotion.json"
        record.write_text(json.dumps({"source_key": "cbs", "promoted_at": "different",
                                      "section_after_sha256": "wrong"}))
        original = self.fixture_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "cannot be identified"):
            iso.isolate(self.repo, fail("cbs invalid values"), 9)
        self.assertEqual(self.fixture_path.read_bytes(), original)

    def test_corrected_save_releases_only_post_validate_hold(self):
        self._change()
        iso.isolate(self.repo, fail("cbs invalid values"), 9)
        self.assertTrue(chain.release_post_validate_hold(self.repo, "cbs"))
        doc = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        self.assertNotIn("validationHold", doc["sources"]["cbs"])
        doc["sources"]["espn"]["validationHold"] = {"reason": "fidelity: bad", "root": "espn"}
        self.fixture_path.write_text(json.dumps(doc), encoding="utf-8")
        self.assertFalse(chain.release_post_validate_hold(self.repo, "espn"))
        self.assertIn("validationHold", json.loads(self.fixture_path.read_text())["sources"]["espn"])


if __name__ == "__main__":
    unittest.main()
