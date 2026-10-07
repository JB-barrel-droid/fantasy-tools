"""JEG-432 R5 (freshness flag) and R1 (source x method pair registry).

Guards, each negative-tested in this file against a simulated broken
implementation (a text mutation of the shipped JS, applied by
tests/source_freshness_harness.js before it evaluates the file):

- FRESH-CAL: product-data.js's content calendar matches
  pipelines/nfl_week.py (Tuesday flip) on every day of the season. A
  Thursday-flip calendar (the watchdog's) must fail it.
- FRESH-HONEST: with every weekly chart on Week 4 and the content week at 5,
  every source is flagged "older" -- but the first load is not emptied.
  A build that excludes by calendar week alone must fail it.
- FRESH-MIXED: with FantasyCalc on Week 5 and the rest on Week 4, the Week 4
  weekly charts are excluded from the first load (still selectable), and the
  ESPN anchor / rest-of-season curves are not. A build that never excludes,
  or that excludes rest-of-season curves, must fail it.
- FRESH-DEFAULTS: curve-widget's first-load default set and its
  defaultGroupedSources guard both honour the exclusion; a widget that drops
  the exclusion from the guard must fail it.
- REG-PAIRS / REG-DERIVED / REG-COPY: one row per (source, method), the
  design's allowed pairs, availability derived from the data (not counts in
  code), and reason text that obeys the copy rules.
"""

import copy
import datetime
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "source_freshness_harness.js"
FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
INDEX = ROOT / "app" / "trade-value-chart" / "index.html"
INPUTS = ROOT / "app" / "trade-value-chart" / "assets" / "adjustment-inputs.json"

sys.path.insert(0, str(ROOT / "pipelines"))
from nfl_week import current_nfl_week  # noqa: E402

WEEKLY_CHART_KEYS = ["usatoday", "fantasycalc", "fantasypros", "cbs",
                     "fantasycalc_adjusted", "usatoday_adjusted",
                     "fantasypros_adjusted", "cbs_adjusted"]
ROS_KEYS = ["espn", "cbsros", "razzball", "espn_vorp", "cbsros_vorp", "razzball_vorp"]

# Simulated broken implementations (text mutations of the shipped JS).
THURSDAY_FLIP = [("Date.UTC(2026, 8, 8); // Tue 2026-09-08", "Date.UTC(2026, 8, 10); // Thu")]
EXCLUDE_BY_CALENDAR = [("Math.min(Math.max(...weeklyWeeks), currentWeek)", "currentWeek")]
NEVER_EXCLUDE = [("row.vintage_week !== null && row.vintage_week < referenceWeek", "false")]
EXCLUDE_ROS_TOO = [('row.excluded_on_first_load = row.cadence === "weekly" && referenceWeek !== null &&',
                    "row.excluded_on_first_load = referenceWeek !== null &&"),
                   ('.filter(row => row.cadence === "weekly" && row.vintage_week !== null)',
                    ".filter(row => row.vintage_week !== null)")]
GUARD_IGNORES_EXCLUSION = [("return defaultIndexedSourceKeys(inputs, excluded).every(",
                            "return defaultIndexedSourceKeys(inputs).every(")]
HARDCODED_AVAILABLE = [("if (coverage.count === null) {", "if (false) {")]


def run(payload):
    proc = subprocess.run(["node", str(HARNESS)], input=json.dumps(payload).encode(),
                          capture_output=True, timeout=120)
    if proc.returncode != 0:
        raise AssertionError(f"harness failed ({proc.returncode}): {proc.stderr.decode()[:800]}")
    return json.loads(proc.stdout.decode())


def fixture_sources():
    return json.loads(FIXTURE.read_text())["sources"]


def all_week(sources, week):
    out = copy.deepcopy(sources)
    for key in WEEKLY_CHART_KEYS:
        out[key]["week_designated"] = f"Week {week}"
        out[key]["content_vintage"] = f"Week {week}"
    return out


def mixed_sources():
    """FantasyCalc (raw + adjusted) on Week 5, every other weekly chart on Week 4."""
    out = all_week(fixture_sources(), 4)
    for key in ("fantasycalc", "fantasycalc_adjusted"):
        out[key]["week_designated"] = "Week 5"
        out[key]["content_vintage"] = "Week 5"
    return out


# ---------------------------------------------------------------- R5 checks

def calendar_mismatches(mutations=()):
    start = datetime.date(2026, 8, 25)
    days = [(start + datetime.timedelta(days=i)).isoformat() for i in range(200)]
    weeks = run({"cmd": "weeks", "days": days, "mutations": list(mutations)})["weeks"]
    return [d for d in days if weeks[d] != current_nfl_week(datetime.date.fromisoformat(d))]


def honest_violations(mutations=()):
    f = run({"cmd": "freshness", "sources": all_week(fixture_sources(), 4),
             "today": "2026-10-06", "mutations": list(mutations)})
    problems = []
    if f["current_content_week"] != 5:
        problems.append(f"content week {f['current_content_week']} != 5 on Tue 2026-10-06")
    for key in WEEKLY_CHART_KEYS:
        if f["series"][key]["status"] != "older":
            problems.append(f"{key} not flagged older")
    if f["first_load_excluded"]:
        problems.append(f"first load emptied by the calendar: {f['first_load_excluded']}")
    return problems


def mixed_violations(mutations=()):
    f = run({"cmd": "freshness", "sources": mixed_sources(), "today": "2026-10-06",
             "mutations": list(mutations)})
    expected = {"usatoday", "fantasypros", "cbs", "usatoday_adjusted",
                "fantasypros_adjusted", "cbs_adjusted"}
    problems = []
    if set(f["first_load_excluded"]) != expected:
        problems.append(f"excluded {sorted(f['first_load_excluded'])} != {sorted(expected)}")
    for key in ROS_KEYS:
        if f["series"][key]["excluded_on_first_load"]:
            problems.append(f"rest-of-season {key} excluded")
    if f["series"]["fantasycalc"]["status"] != "current":
        problems.append("fantasycalc week 5 not current")
    return problems


class FreshnessCalendarTest(unittest.TestCase):
    def test_calendar_matches_nfl_week_py(self):
        self.assertEqual(calendar_mismatches(), [])

    def test_calendar_tuesday_flip_points(self):
        weeks = run({"cmd": "weeks", "days": ["2026-10-05", "2026-10-06", "2026-09-07"]})["weeks"]
        self.assertEqual(weeks, {"2026-10-05": 4, "2026-10-06": 5, "2026-09-07": 1})

    def test_negative_thursday_flip_calendar_is_caught(self):
        self.assertTrue(calendar_mismatches(THURSDAY_FLIP),
                        "a Thursday-flip (watchdog) calendar must not pass FRESH-CAL")


class FreshnessFlagTest(unittest.TestCase):
    def test_all_older_flagged_but_first_load_kept(self):
        self.assertEqual(honest_violations(), [])

    def test_negative_calendar_only_exclusion_is_caught(self):
        self.assertTrue(honest_violations(EXCLUDE_BY_CALENDAR))

    def test_mixed_week_excludes_older_weekly_charts(self):
        self.assertEqual(mixed_violations(), [])

    def test_negative_never_exclude_is_caught(self):
        self.assertTrue(mixed_violations(NEVER_EXCLUDE))

    def test_negative_excluding_rest_of_season_is_caught(self):
        self.assertTrue(mixed_violations(EXCLUDE_ROS_TOO))

    def test_shipped_fixture_vintages_resolve(self):
        """Every source in the shipped fixture gets a week from its own metadata."""
        f = run({"cmd": "freshness", "sources": fixture_sources(), "today": "2026-10-06"})
        unknown = [k for k, row in f["series"].items() if row["vintage_week"] is None]
        self.assertEqual(unknown, [])
        self.assertEqual(f["calendar_source"], "pipelines/nfl_week.py")


def default_violations(mutations=()):
    excluded = ["usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"]
    res = run({"cmd": "defaults", "inputsPath": str(INPUTS), "excluded": excluded,
               "active": ["espn", "fantasycalc_adjusted"], "deselected": [],
               "mutations": list(mutations)})
    problems = []
    if set(res["defaults"]) & set(excluded):
        problems.append(f"excluded keys in default set: {res['defaults']}")
    if not res["satisfied"]:
        problems.append("guard throws on a first load that left older-week sources off")
    return problems


class FirstLoadDefaultsTest(unittest.TestCase):
    def test_defaults_and_guard_honour_exclusion(self):
        self.assertEqual(default_violations(), [])

    def test_negative_guard_ignoring_exclusion_is_caught(self):
        self.assertTrue(default_violations(GUARD_IGNORES_EXCLUSION))

    def test_widget_init_wires_freshness(self):
        text = (ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js").read_text()
        self.assertIn("getSourceFreshness", text)
        self.assertIn("defaultIndexedSourceKeys(adjustmentInputs, firstLoadExcluded)", text)
        self.assertIn("userDeselectedSources, firstLoadExcluded)", text)


# ---------------------------------------------------------------- R1 checks

ALLOWED = {
    "fantasycalc": {"adjusted", "indexed"}, "fantasypros": {"adjusted", "indexed"},
    "cbs": {"adjusted", "indexed"}, "usatoday": {"adjusted", "indexed"},
    "espn": {"adjusted", "vorp_vs_waivers"}, "cbsros": {"adjusted", "vorp_vs_waivers"},
    "razzball": {"adjusted", "vorp_vs_waivers"},
}
REASON_CODES = {None, "stale_vintage", "not_offered", "insufficient_overlap",
                "league_setting_unsupported", "adjustment_pending"}
VORP_RE = re.compile(r"vorp", re.IGNORECASE)
LOCKED = re.compile(r"\bVORP vs waivers\b")


def registry(**kw):
    payload = {"cmd": "registry", "fixturePath": str(FIXTURE), "indexPath": str(INDEX),
               "scoring": "ppr", "teams": 12, "today": "2026-10-06"}
    payload.update(kw)
    return run(payload)


def row(reg, source, method):
    return next(r for r in reg["rows"] if r["source"] == source and r["method"] == method)


def copy_violations(texts):
    bad = []
    for text in texts:
        if not text:
            continue
        if VORP_RE.search(LOCKED.sub("", text)):
            bad.append(text)
        if "the market" in text.lower() or "pure vorp" in text.lower():
            bad.append(text)
    return bad


class PairRegistryTest(unittest.TestCase):
    def test_one_row_per_pair_and_allowed_matrix(self):
        reg = registry()
        keys = [(r["source"], r["method"]) for r in reg["rows"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(keys), 7 * 3)
        for r in reg["rows"]:
            self.assertIn(r["reason_code"], REASON_CODES)
            offered = r["method"] in ALLOWED[r["source"]]
            self.assertEqual(r["series_key"] is not None, offered, r)
            if not offered:
                self.assertEqual(r["reason_code"], "not_offered")
                self.assertFalse(r["available"])
            if not r["available"]:
                self.assertTrue(r["reason_text"], r)
        # At 12 teams on the shipped fixture every offered pair is available.
        offered_rows = [r for r in reg["rows"] if r["series_key"]]
        self.assertTrue(all(r["available"] for r in offered_rows),
                        [r for r in offered_rows if not r["available"]])
        self.assertEqual(row(reg, "espn", "vorp_vs_waivers")["method_label"], "VORP vs waivers")
        self.assertEqual(row(reg, "cbs", "adjusted")["method_label"], "Our Data Driven Adjustments")

    def test_unsaved_team_count_is_derived_from_the_12_team_base(self):
        # JEG-332 (#378) derives published charts at 8/10/14 teams from the saved
        # 12-team setup, so those pairs are available there (pinned before the
        # engine shipped as league_setting_unsupported; premise changed).
        reg = registry(teams=10)
        for source in ("fantasycalc", "fantasypros", "cbs", "usatoday"):
            for method in ("adjusted", "indexed"):
                r = row(reg, source, method)
                self.assertTrue(r["available"], r)
                self.assertEqual(r["derived_from_teams"], 12)
        self.assertTrue(row(reg, "espn", "adjusted")["available"])

    def test_no_12_team_base_is_league_setting_unsupported(self):
        sources = fixture_sources()
        sources["cbs"]["combos"] = {k: v for k, v in sources["cbs"]["combos"].items()
                                    if not k.endswith("_12")}
        r = row(registry(sources=sources, teams=10), "cbs", "indexed")
        self.assertFalse(r["available"])
        self.assertEqual(r["reason_code"], "league_setting_unsupported")

    def derived_violations(self, mutations=()):
        """REG-DERIVED: drop CBS's 12-team combos -> CBS must go unavailable at 12."""
        sources = fixture_sources()
        sources["cbs"]["combos"] = {k: v for k, v in sources["cbs"]["combos"].items()
                                    if not k.endswith("_12")}
        reg = registry(sources=sources, mutations=list(mutations))
        r = row(reg, "cbs", "indexed")
        return [] if (not r["available"] and r["reason_code"] == "league_setting_unsupported") else [r]

    def test_availability_is_derived_from_data(self):
        self.assertEqual(self.derived_violations(), [])

    def test_negative_hardcoded_availability_is_caught(self):
        self.assertTrue(self.derived_violations(HARDCODED_AVAILABLE))

    def test_insufficient_overlap(self):
        sources = fixture_sources()
        combo = sources["usatoday"]["combos"]["full_12"]
        field = "values" if "values" in combo else "reindexed"
        combo[field] = dict(list(combo[field].items())[:30])
        r = row(registry(sources=sources), "usatoday", "indexed")
        self.assertFalse(r["available"])
        self.assertEqual(r["reason_code"], "insufficient_overlap")
        self.assertLess(r["shared_players"], 40)

    def test_stale_vintage_row_in_mixed_weeks(self):
        reg = registry(sources=mixed_sources())
        for method in ("adjusted", "indexed"):
            r = row(reg, "usatoday", method)
            self.assertTrue(r["available"], "older-week sources stay selectable")
            self.assertTrue(r["excluded_on_first_load"])
            self.assertEqual(r["reason_code"], "stale_vintage")
            self.assertEqual(r["vintage_week"], 4)
        fc = row(reg, "fantasycalc", "adjusted")
        self.assertIsNone(fc["reason_code"])
        self.assertEqual(fc["vintage_week"], 5)

    def test_adjustment_pending(self):
        r = row(registry(pausedSeries=["cbs_adjusted"]), "cbs", "adjusted")
        self.assertFalse(r["available"])
        self.assertEqual(r["reason_code"], "adjustment_pending")

    def test_copy_rules(self):
        texts = []
        for kw in ({}, {"teams": 10}, {"sources": mixed_sources()}, {"pausedSeries": ["cbs_adjusted"]}):
            reg = registry(**kw)
            texts += [r["reason_text"] for r in reg["rows"]]
            texts += [r["method_label"] for r in reg["rows"]] + [r["source_label"] for r in reg["rows"]]
        self.assertEqual(copy_violations(texts), [])

    def test_negative_copy_check_catches_design_wording(self):
        self.assertTrue(copy_violations(["Pure VORP"]))
        self.assertTrue(copy_violations(["Raw VORP"]))
        self.assertTrue(copy_violations(["matches the market"]))
        self.assertEqual(copy_violations(["VORP vs waivers"]), [])


if __name__ == "__main__":
    unittest.main()
