#!/usr/bin/env python3
"""Weekly-input contract (JEG-1227, S1 of JEG-1195).

Pins pipelines/lib/weekly_inputs_contract.py to its fixtures and its doc:

* every committed fixture is exactly what tests/fixtures/weekly_inputs/
  build_fixtures.py writes (deterministic, no hand edits);
* every valid case has no errors and every invalid case reports exactly the
  error codes in expected.json (zero vs missing, duplicate and unresolved keys,
  wrong week and season, incompatible units, rest-of-season contamination);
* version and additive-compatibility rules;
* every validation code is documented in docs/weekly-inputs-contract.md and
  exercised by at least one case.

Offline: no network, no credentials, no Supabase.
Run: python3 -m unittest tests.test_weekly_inputs_contract
"""
from __future__ import annotations

import ast
import copy
import io
import json
import re
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "weekly_inputs"
MODULE = ROOT / "pipelines" / "lib" / "weekly_inputs_contract.py"
DOC = ROOT / "docs" / "weekly-inputs-contract.md"
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(FIXTURES))

from lib import weekly_inputs_contract as wic  # noqa: E402
from lib.scoring import SCORING  # noqa: E402
import build_fixtures  # noqa: E402


def codes(issues, severity="error"):
    return [i.code for i in issues if i.severity == severity]


def expected():
    return json.loads((FIXTURES / "expected.json").read_text())


KICKOFFS = {9000101: "2026-11-01T17:00:00Z", 9000102: "2026-11-01T18:00:00Z",
            9000103: "2026-11-01T21:25:00Z", 9000104: "2026-11-03T01:15:00Z"}


def with_1_1_legs(doc):
    """The base artifact at schema 1.1.0 with the roster and slate legs added (JEG-1416)."""
    doc["schema_version"] = "1.1.0"
    doc["legs"]["roster"] = {
        "kind": "roster", "source": "espn", "horizon": "week", "units": "roster",
        "scoring": None, "content_season": 2026, "content_week": 8,
        "content_vintage": "2026-10-28", "captured_at": "2026-10-28T12:00:00Z",
        "availability": "complete", "freshness": "current", "label": "published",
    }
    doc["legs"]["slate"] = {
        "kind": "slate", "source": "nfl_schedule", "horizon": "week", "units": "kickoff",
        "scoring": None, "content_season": 2026, "content_week": 8, "game_week": 8,
        "content_vintage": "2026-10-28", "captured_at": "2026-10-28T09:00:00Z",
        "availability": "complete", "freshness": "current", "label": "published",
    }
    for row, pct, trend in zip(doc["players"], (84.2, 0.0, 45.5, 98.0), (6.4, 0.0, -1.5, 2.0)):
        row["legs"]["roster"] = {"provenance": "complete",
                                 "values": {"rostered_pct": pct, "adds_trend": trend}}
        row["legs"]["slate"] = {"provenance": "complete",
                                "values": {"kickoff_at": KICKOFFS[row["player_key"]]}}
    return doc


def unavailable_1_1_leg(doc, leg_id, kind, source, units, reason, keys):
    doc["legs"][leg_id] = {
        "kind": kind, "source": source, "horizon": "week", "units": units, "scoring": None,
        "content_season": None, "content_week": None, "content_vintage": None,
        "captured_at": None, "availability": "unavailable", "freshness": None,
        "label": "unavailable", "missing_reason": reason,
    }
    for row in doc["players"]:
        row["legs"][leg_id] = {"provenance": "missing", "values": {k: None for k in keys}}
    return doc


class FixtureFilesTest(unittest.TestCase):
    def test_committed_fixtures_match_the_builder(self):
        built = build_fixtures.build()
        on_disk = {p.relative_to(FIXTURES).as_posix(): p.read_text()
                   for p in FIXTURES.rglob("*.json")}
        self.assertEqual(sorted(on_disk), sorted(built), "fixture file set differs from the builder")
        for rel, text in built.items():
            self.assertEqual(on_disk[rel], text, f"{rel} differs from build_fixtures.py output")

    def test_builder_is_deterministic(self):
        self.assertEqual(build_fixtures.build(), build_fixtures.build())

    def test_case_coverage_named_in_the_ticket(self):
        names = set(expected())
        for rel in ("valid/complete.json", "valid/partial.json", "valid/stale.json",
                    "valid/unknown.json", "valid/unavailable.json", "valid/zero_value.json",
                    "invalid/zero_filled.json", "invalid/null_no_reason.json",
                    "invalid/duplicate_key.json", "invalid/unresolved_no_reason.json",
                    "invalid/wrong_week_current.json", "invalid/future_season.json",
                    "invalid/last_season_as_current.json", "invalid/rank_as_points.json",
                    "valid/roster_slate_complete.json", "valid/roster_slate_partial.json",
                    "valid/roster_slate_stale.json", "valid/roster_slate_unavailable.json",
                    "invalid/points_units_on_status.json", "invalid/ros_horizon.json",
                    "invalid/ros_leg_id.json", "invalid/ros_field.json",
                    "valid/unknown_no_provenance.json", "invalid/current_null_provenance.json",
                    "invalid/unknown_labelled_published.json", "invalid/scoring_object_entry.json"):
            self.assertIn(rel, names)


class FixtureCasesTest(unittest.TestCase):
    def test_every_case_reports_exactly_its_expected_codes(self):
        for rel, want in expected().items():
            with self.subTest(case=rel):
                issues = wic.validate_file(FIXTURES / rel)
                self.assertEqual(codes(issues), want["errors"], "\n".join(map(str, issues)))
                self.assertEqual(codes(issues, "warning"), want["warnings"], "\n".join(map(str, issues)))

    def test_valid_cases_are_valid_and_invalid_cases_are_not(self):
        for rel in expected():
            issues = wic.validate_file(FIXTURES / rel)
            self.assertEqual(wic.is_valid(issues), rel.startswith("valid/"), rel)

    def test_validation_is_stable_and_does_not_mutate(self):
        doc = json.loads((FIXTURES / "invalid/last_season_as_current.json").read_text())
        before = copy.deepcopy(doc)
        self.assertEqual(wic.validate(doc), wic.validate(doc))
        self.assertEqual(doc, before)


class MissingVersusZeroTest(unittest.TestCase):
    def setUp(self):
        self.doc = build_fixtures.base()
        self.cell = self.doc["players"][0]["legs"]["experts.espn_weekly"]

    def test_real_zero_without_reason_is_valid(self):
        self.cell["values"]["standard"] = 0
        self.assertEqual(codes(wic.validate(self.doc)), [])

    def test_null_needs_a_reason(self):
        self.cell["values"]["standard"] = None
        self.cell["provenance"] = "partial"
        self.doc["legs"]["experts.espn_weekly"]["availability"] = "partial"
        self.assertEqual(codes(wic.validate(self.doc)), ["missing.no_reason"])
        self.cell["missing_reason"] = {"standard": "not projected"}
        self.assertEqual(codes(wic.validate(self.doc)), [])

    def test_zero_with_reason_is_a_fill(self):
        self.cell["values"]["standard"] = 0
        self.cell["missing_reason"] = {"standard": "not projected"}
        self.assertEqual(codes(wic.validate(self.doc)), ["missing.zero_filled"])

    def test_booleans_are_not_points(self):
        self.cell["values"]["standard"] = False
        self.assertEqual(codes(wic.validate(self.doc)), ["value.type"])


class NullProvenanceTest(unittest.TestCase):
    """Unknown provenance never passes as current or published data (JEG-1267)."""

    def setUp(self):
        self.doc = build_fixtures.base()
        self.leg = self.doc["legs"]["experts.espn_weekly"]

    def test_each_null_field_fails_a_current_published_leg(self):
        for name in wic.PROVENANCE_FIELDS:
            with self.subTest(field=name):
                doc = copy.deepcopy(self.doc)
                doc["legs"]["experts.espn_weekly"][name] = None
                issues = [i for i in wic.validate(doc) if i.code == "leg.provenance_unknown"]
                self.assertEqual([i.path for i in issues], [f"$.legs.experts.espn_weekly.{name}"])

    def test_every_aged_freshness_and_published_label_needs_provenance(self):
        for freshness, label in (("current", "modeled"), ("one_week_behind", "modeled"),
                                 ("stale", "stale"), ("unknown", "published")):
            with self.subTest(freshness=freshness, label=label):
                self.leg.update(freshness=freshness, label=label, content_vintage=None)
                self.assertIn("leg.provenance_unknown", codes(wic.validate(self.doc)))

    def test_same_nulls_pass_as_unknown_and_unpublished(self):
        # The control: only freshness and label change, so the rule turns on exactly those.
        self.leg.update(content_season=None, content_week=None, content_vintage=None, captured_at=None)
        self.assertEqual(codes(wic.validate(self.doc)), ["leg.provenance_unknown"] * 4)
        self.leg.update(freshness="unknown", label="modeled")
        self.assertEqual(codes(wic.validate(self.doc)), [])

    def test_unavailable_partial_and_zero_semantics_unchanged(self):
        for rel in ("valid/unavailable.json", "valid/partial.json", "valid/zero_value.json",
                    "valid/unknown.json", "valid/unknown_no_provenance.json"):
            with self.subTest(case=rel):
                self.assertEqual(codes(wic.validate_file(FIXTURES / rel)), [])


class MalformedShapeTest(unittest.TestCase):
    """Malformed JSON shapes come back as issues, never as exceptions (JEG-1267)."""

    SHAPES = ([{}], [[]], [None], {}, [], None, "x", 1.5, True, {"a": {}})

    def test_malformed_scoring_entries_are_reported(self):
        for scoring in ([{}], [[]], [None], ["half_ppr", {}], [1]):
            with self.subTest(scoring=scoring):
                doc = build_fixtures.base()
                doc["legs"]["experts.espn_weekly"]["scoring"] = scoring
                issues = wic.validate(doc)
                self.assertIn("field.type", codes(issues))
                self.assertTrue(any(i.path.startswith("$.legs.experts.espn_weekly.scoring[") for i in issues))

    def test_no_value_anywhere_raises(self):
        base = json.loads((FIXTURES / "valid/complete.json").read_text())

        def paths(obj, at=()):
            yield at
            items = obj.items() if isinstance(obj, dict) else enumerate(obj) if isinstance(obj, list) else ()
            for k, v in items:
                yield from paths(v, at + (k,))

        for at in list(paths(base))[1:]:
            for shape in self.SHAPES:
                doc = copy.deepcopy(base)
                target = doc
                for k in at[:-1]:
                    target = target[k]
                target[at[-1]] = copy.deepcopy(shape)
                try:
                    wic.validate(doc)
                except Exception as exc:  # noqa: BLE001 - the point is that nothing escapes
                    self.fail(f"{at} = {shape!r} raised {type(exc).__name__}: {exc}")


class VersionTest(unittest.TestCase):
    def doc(self, version, **extra):
        d = build_fixtures.base()
        d["schema_version"] = version
        d.update(extra)
        return d

    def test_any_1x_is_read(self):
        for v in ("1.0.0", "1.0.7", "1.1.0", "1.9.3"):
            self.assertTrue(wic.is_valid(wic.validate(self.doc(v))), v)

    def test_unknown_field_is_an_error_at_a_known_minor_and_a_warning_at_a_newer_one(self):
        known = wic.validate(self.doc("1.0.4", extra_field=1))
        newer = wic.validate(self.doc("1.2.0", extra_field=1))
        self.assertEqual(codes(known), ["field.unknown"])
        self.assertEqual(codes(newer), [])
        self.assertEqual(codes(newer, "warning"), ["field.unknown"])

    def test_newer_minor_does_not_relax_required_fields_or_rules(self):
        d = self.doc("1.3.0")
        del d["built_at"]
        d["horizon"] = "ros"
        self.assertEqual(codes(wic.validate(d)), ["field.missing", "ros.horizon"])

    def test_other_majors_and_malformed_versions_are_refused(self):
        self.assertEqual(codes(wic.validate(self.doc("2.0.0"))), ["version.unsupported_major"])
        self.assertEqual(codes(wic.validate(self.doc("0.9.0"))), ["version.unsupported_major"])
        for bad in ("1.0", "v1.0.0", "01.0.0", 1, None):
            self.assertEqual(codes(wic.validate(self.doc(bad))), ["version.malformed"], repr(bad))

    def test_a_new_expert_source_needs_no_version_bump(self):
        valid = wic.validate_file(FIXTURES / "valid/unknown.json")
        self.assertEqual(json.loads((FIXTURES / "valid/unknown.json").read_text())["schema_version"], "1.0.0")
        self.assertEqual(codes(valid) + codes(valid, "warning"), [])

    def test_current_version_constant(self):
        self.assertEqual(wic.SCHEMA_VERSION, "1.1.0")
        self.assertEqual(wic.parse_version(wic.SCHEMA_VERSION)[:2], (wic.READER_MAJOR, wic.READER_MINOR))


class RosterSlateContractTest(unittest.TestCase):
    """JEG-1416: the 1.1 roster and slate legs, and 1.0 artifacts under the 1.1 reader."""

    def test_1_0_artifacts_still_validate_under_the_1_1_reader(self):
        # The new legs are optional and additive: a 1.0.x artifact without them
        # is valid, never an error (a compatibility warning would be allowed).
        for version in ("1.0.0", "1.0.7"):
            with self.subTest(version=version):
                doc = build_fixtures.base()
                doc["schema_version"] = version
                self.assertEqual(codes(wic.validate(doc)), [])
                self.assertTrue(wic.is_valid(wic.validate(doc)))
        self.assertEqual(codes(wic.validate_file(FIXTURES / "valid/complete.json")), [])

    def test_1_1_artifact_with_both_legs_validates(self):
        issues = wic.validate(with_1_1_legs(build_fixtures.base()))
        self.assertEqual(codes(issues), [], "\n".join(map(str, issues)))
        self.assertEqual(codes(issues, "warning"), [])

    def test_partial_legs_validate(self):
        doc = with_1_1_legs(build_fixtures.base())
        roster = doc["players"][1]["legs"]["roster"]
        roster["values"]["adds_trend"] = None
        roster["provenance"] = "partial"
        roster["missing_reason"] = {"adds_trend": "not reported by the source"}
        doc["legs"]["roster"]["availability"] = "partial"
        slate = doc["players"][2]["legs"]["slate"]
        slate["values"]["kickoff_at"] = None
        slate["provenance"] = "missing"
        slate["missing_reason"] = {"kickoff_at": "team CCC not in the slate file"}
        doc["legs"]["slate"]["availability"] = "partial"
        self.assertEqual(codes(wic.validate(doc)), [])

    def test_stale_legs_validate(self):
        doc = with_1_1_legs(build_fixtures.base())
        for leg_id, captured in (("roster", "2026-10-13T12:00:00Z"), ("slate", "2026-10-13T09:00:00Z")):
            doc["legs"][leg_id].update(content_week=6, content_vintage="2026-10-13",
                                       captured_at=captured, freshness="stale", label="stale")
        self.assertEqual(codes(wic.validate(doc)), [])

    def test_unavailable_legs_validate_and_stay_missing(self):
        doc = with_1_1_legs(build_fixtures.base())
        unavailable_1_1_leg(doc, "roster", "roster", "espn", "roster",
                            "no ESPN roster file for this week", ["rostered_pct", "adds_trend"])
        unavailable_1_1_leg(doc, "slate", "slate", "nfl_schedule", "kickoff",
                            "no slate file for this week", ["kickoff_at"])
        self.assertEqual(codes(wic.validate(doc)), [])
        for row in doc["players"]:
            self.assertEqual(set(row["legs"]["roster"]["values"].values()), {None})
            self.assertIsNone(row["legs"]["slate"]["values"]["kickoff_at"])

    def test_complete_leg_with_a_null_is_inconsistent(self):
        doc = with_1_1_legs(build_fixtures.base())
        roster = doc["players"][0]["legs"]["roster"]
        roster["values"]["rostered_pct"] = None
        roster["provenance"] = "partial"
        roster["missing_reason"] = {"rostered_pct": "not reported by the source"}
        self.assertEqual(codes(wic.validate(doc)), ["availability.inconsistent"])

    def test_partial_leg_with_no_nulls_is_inconsistent(self):
        doc = with_1_1_legs(build_fixtures.base())
        doc["legs"]["slate"]["availability"] = "partial"
        self.assertEqual(codes(wic.validate(doc)), ["availability.inconsistent"])

    def test_roster_value_types_and_ranges(self):
        for field, value, code in (("rostered_pct", 100.1, "value.range"),
                                   ("rostered_pct", -0.1, "value.range"),
                                   ("adds_trend", 100.1, "value.range"),
                                   ("adds_trend", -100.1, "value.range"),
                                   ("rostered_pct", "high", "value.type"),
                                   ("rostered_pct", True, "value.type"),
                                   ("adds_trend", "up", "value.type")):
            with self.subTest(field=field, value=value):
                doc = with_1_1_legs(build_fixtures.base())
                doc["players"][0]["legs"]["roster"]["values"][field] = value
                self.assertEqual(codes(wic.validate(doc)), [code])

    def test_roster_bounds_and_zero_are_values(self):
        doc = with_1_1_legs(build_fixtures.base())
        doc["players"][0]["legs"]["roster"]["values"].update(rostered_pct=100, adds_trend=-100)
        doc["players"][1]["legs"]["roster"]["values"].update(rostered_pct=0, adds_trend=0)
        self.assertEqual(codes(wic.validate(doc)), [])

    def test_kickoff_must_be_a_timestamp_with_a_utc_offset(self):
        for bad in ("2026-11-01", "2026-11-01T17:00:00", "Sunday 1pm"):
            with self.subTest(kickoff_at=bad):
                doc = with_1_1_legs(build_fixtures.base())
                doc["players"][0]["legs"]["slate"]["values"]["kickoff_at"] = bad
                self.assertEqual(codes(wic.validate(doc)), ["timestamp.format"])

    def test_new_leg_kinds_must_match_their_ids(self):
        doc = with_1_1_legs(build_fixtures.base())
        doc["legs"]["roster"]["kind"] = "expert"
        self.assertEqual(codes(wic.validate(doc)), ["leg.kind_mismatch"])


class RemainingCodesTest(unittest.TestCase):
    """Codes no fixture file needs, each shown once on a small mutation."""

    CASES = {
        "season.range": lambda d: d.update(season=1999),
        "week.range": lambda d: d.update(content_week=19),
        "timestamp.format": lambda d: d.update(built_at="2026-10-28 13:30"),
        "leg.none": lambda d: (d.update(legs={}), [r.update(legs={}) for r in d["players"]]),
        "availability.value": lambda d: d["legs"]["bye"].update(availability="full"),
        "freshness.value": lambda d: d["legs"]["bye"].update(freshness="fresh"),
        "label.value": lambda d: d["legs"]["bye"].update(label="live"),
        "player.position": lambda d: d["players"][0].update(position="FB"),
        "value.range": lambda d: d["players"][0]["legs"]["bye"]["values"].update(bye_week=0),
        "missing.reason_unused": lambda d: d["players"][0]["legs"]["bye"].update(
            missing_reason={"bye_weak": "typo"}),
        "provenance.value": lambda d: d["players"][0]["legs"]["bye"].update(provenance="filled"),
        "field.type": lambda d: d.update(players={}),
    }

    def test_each_remaining_code(self):
        for code, mutate in self.CASES.items():
            with self.subTest(code=code):
                d = build_fixtures.base()
                mutate(d)
                self.assertEqual(codes(wic.validate(d)), [code])

    def test_optional_provenance_fields_are_checked(self):
        d = build_fixtures.base()
        d["legs"]["status"]["inputs"] = [{"name": "status.json", "sha256": "abc"}]
        d["players"][2]["legs"]["status"]["values"]["injury_start_date"] = "10/26/2026"
        self.assertEqual(codes(wic.validate(d)), ["field.type", "timestamp.format"])

    def test_unparseable_and_non_object_documents(self):
        self.assertEqual(codes(wic.validate_text("{not json")), ["json.invalid"])
        self.assertEqual(codes(wic.validate([])), ["type.document"])

    def test_every_code_is_exercised(self):
        seen = set(self.CASES) | {"json.invalid", "type.document"}
        for want in expected().values():
            seen.update(want["errors"])
            seen.update(want["warnings"])
        self.assertEqual(sorted(set(wic.CODES) - seen), [])


class RulesPinnedToRepoTest(unittest.TestCase):
    def test_scoring_keys_are_the_repo_scoring_keys(self):
        self.assertEqual(set(wic.SCORINGS), set(SCORING))

    def test_freshness_rule_matches_check_reference_freshness(self):
        # pipelines/check_reference_freshness.py make_source_week_item: 0 behind current,
        # 1 behind one_week_behind, 2+ stale, unknown week unknown.
        self.assertEqual(wic.freshness_for_weeks(8, 8), "current")
        self.assertEqual(wic.freshness_for_weeks(8, 7), "one_week_behind")
        self.assertEqual(wic.freshness_for_weeks(8, 6), "stale")
        self.assertEqual(wic.freshness_for_weeks(8, None), "unknown")
        src = (ROOT / "pipelines" / "check_reference_freshness.py").read_text()
        for word in wic.FRESHNESS:
            self.assertIn(f'"{word}"', src)

    def test_stdlib_and_repo_timestamps_only(self):
        tree = ast.parse(MODULE.read_text())
        mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        allowed = {"__future__", "argparse", "json", "math", "re", "sys", "dataclasses", "datetime",
                   "pathlib", "typing", "lib", "timestamps"}
        self.assertEqual(mods - allowed, set())


class DocTest(unittest.TestCase):
    def test_doc_lists_exactly_the_codes(self):
        text = DOC.read_text()
        table = set(re.findall(r"^\| `([a-z_]+\.[a-z_]+)` \|", text, re.M))
        self.assertEqual(sorted(table), sorted(wic.CODES))

    def test_doc_example_is_a_valid_fixture(self):
        text = DOC.read_text()
        self.assertIn("tests/fixtures/weekly_inputs/valid/complete.json", text)
        self.assertIn("python3 -m unittest tests.test_weekly_inputs_contract", text)


class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wic.main(list(args))
        return rc, buf.getvalue()

    def test_exit_status(self):
        ok = str(FIXTURES / "valid/additive_minor.json")
        bad = str(FIXTURES / "invalid/zero_filled.json")
        self.assertEqual(self.run_cli(ok)[0], 0)
        rc, out = self.run_cli(ok, bad)
        self.assertEqual(rc, 1)
        self.assertIn("missing.zero_filled", out)

    def test_json_output(self):
        rc, out = self.run_cli("--json", str(FIXTURES / "invalid/ros_horizon.json"))
        self.assertEqual(rc, 1)
        report = json.loads(out)
        self.assertEqual([i["code"] for i in next(iter(report.values()))], ["ros.horizon"])

    def test_malformed_scoring_fails_informatively(self):
        proc = subprocess.run([sys.executable, str(MODULE), str(FIXTURES / "invalid/scoring_object_entry.json")],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("field.type", proc.stdout)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)

    def test_script_runs_standalone(self):
        proc = subprocess.run([sys.executable, str(MODULE), str(FIXTURES / "valid/complete.json")],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
