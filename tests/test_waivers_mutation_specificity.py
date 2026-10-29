"""JEG-1279: a Waivers render mutant counts as killed only when its own check catches it.

tests/test_waivers_render.py::test_guard_fails_on_broken_builds serves eight broken copies of app/v2/waivers.js / waivers.css. At
430791c4 it counted a mutant as caught when run_checks returned any error or raised anything (`except Exception`), so a missing
browser (a SkipTest locally, a RuntimeError under RENDER_TESTS_REQUIRED=1), a navigation timeout, a stray page error or an
unrelated failed check all read as a kill. JEG-1282 (#1149) made the guard name each mutant's own check (CAUGHT_BY) and stop
catching exceptions; this module stays the stricter, independent evidence.

This module runs the same eight production-source mutants through the same run_checks (imported, unchanged) and counts a kill
only when:

  * the clean baseline returned no errors first;
  * the mutation anchor occurs exactly once in the production source (a stale or doubled anchor fails by name);
  * run_checks returned a list: an exception of any type, SkipTest included, is a harness failure;
  * the mutant's designated diagnostic (tests/fixtures/waivers-mutation-specificity.json) fired at every viewport it names, and
    every other line is a consequence the fixture lists for that mutant. A page error, an untagged line or any other diagnostic is
    a harness failure, even when the designated diagnostic also fired;
  * the original files served through the same override route pass afterwards (the restored control).

With JEG-1282 on main all eight are killed this way. At 430791c4 two were harness failures that the old guard counted: "no
aria-sort" left a dangling `if` that removed the header buttons, so the click timed out, and "no verdict text" made check() raise
ValueError after appending its diagnostic (each fixture entry's `note`). A mutant the suite cannot kill cleanly would be recorded
as `expect: harness` with its exact exception and defect ticket, and a fixture variant can show its check kills a well-formed
copy; none is needed now.

Offline (no browser): the classifier and the anchor rule on synthetic outcomes, the old rule's false greens, and the fixture
mirrors the suite's mutation table (read from its source with ast, so the two cannot drift). In Chromium: the baseline, the eight
mutants, the restored control, and four failures injected through the real harness (browser unavailable, navigation timeout,
unrelated page error, unrelated diagnostic), none of which may classify as killed.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

from tests import _render_env
from tests import test_waivers_render as suite

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "waivers-mutation-specificity.json"
SUITE = ROOT / "tests" / "test_waivers_render.py"
SOURCES = {"waivers.js": suite.WAIVERS_JS, "waivers.css": suite.WAIVERS_CSS}
KINDS = {"waivers.js": "text/javascript", "waivers.css": "text/css"}

KILLED, SURVIVED, UNSPECIFIC, HARNESS = "killed", "survived", "unspecific", "harness"
TAGGED = re.compile(r"\[(\d+)px\] (.*)", re.S)


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class StaleAnchor(AssertionError):
    pass


def mutate(source: str, find: str, replace: str, name: str) -> str:
    """The suite's `source.replace(find, replace, 1)`, refusing an anchor that is missing, doubled or a no-op."""
    count = source.count(find)
    if count != 1:
        raise StaleAnchor(f"mutation anchor for {name!r} occurs {count} times in the production source, want exactly 1: {find!r}")
    if find == replace:
        raise StaleAnchor(f"mutation {name!r} replaces its anchor with itself")
    return source.replace(find, replace, 1)


@dataclass(frozen=True)
class Outcome:
    errors: tuple = ()
    exception: BaseException | None = None


@dataclass(frozen=True)
class Verdict:
    kind: str
    detail: tuple = ()


def run(overrides=None, viewports=None) -> Outcome:
    viewports = viewports or tuple(tuple(v) for v in load_fixture()["viewports"])
    try:
        return Outcome(errors=tuple(suite.run_checks(overrides, viewports=viewports)))
    except Exception as exc:   # SkipTest is an Exception too: a run that could not happen is recorded, never counted
        return Outcome(exception=exc)


def legacy_caught(outcome: Outcome) -> bool:
    """The rule test_guard_fails_on_broken_builds applies: an exception becomes one error line, and any error is a kill."""
    errors = [str(outcome.exception)[:80]] if outcome.exception is not None else list(outcome.errors)
    return errors != []


def _in_order(reverse: bool, dashes: str):
    def check(values: list) -> bool:
        real = [v for v in values if v is not None]
        dash = [None] * (len(values) - len(real))
        ordered = sorted(real, reverse=reverse)
        return bool(real) and bool(dash) and values == (dash + ordered if dashes == "first" else ordered + dash)
    return check


# A sort diagnostic carries the column's values; the regex cannot say they are in order, so an entry with "values" names
# the order its `values` group must be in (Codex review on #1144: a broken numeric sort is a second failure, not a consequence).
ORDERS = {"ascending, dashes last": _in_order(False, "last"), "ascending, dashes first": _in_order(False, "first"),
          "descending, dashes first": _in_order(True, "first")}


def _rule(entry: dict):
    return frozenset(entry["widths"]), re.compile(entry["pattern"], re.S), ORDERS[entry["values"]] if "values" in entry else None


def _accepts(rule, width: int, message: str) -> bool:
    widths, pattern, order = rule
    match = pattern.fullmatch(message) if width in widths else None
    if not match or order is None:
        return bool(match)
    try:
        values = ast.literal_eval(match["values"])
    except (ValueError, SyntaxError):
        return False
    numbers = isinstance(values, list) and all(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool)) for v in values)
    return numbers and order(values)


def classify(outcome: Outcome, designation: dict) -> Verdict:
    """KILLED only for a completed run whose every line is the mutant's designated diagnostic or a listed consequence of it,
    with the designated diagnostic present at every width it names."""
    if outcome.exception is not None:
        return Verdict(HARNESS, (f"run raised {type(outcome.exception).__name__}: {str(outcome.exception)[:200]}",))
    if not outcome.errors:
        return Verdict(SURVIVED)
    designated = [_rule(d) for d in designation["designated"]]
    consequences = [_rule(c) for c in designation.get("consequences", [])]
    fired, stray = set(), []
    for line in outcome.errors:
        tagged = TAGGED.fullmatch(line)
        if not tagged:
            stray.append(f"untagged: {line}")
            continue
        width, message = int(tagged[1]), tagged[2]
        if message.startswith("page errors "):   # never a designated behaviour, whatever a pattern says
            stray.append(line)
            continue
        hits = {(i, width) for i, rule in enumerate(designated) if _accepts(rule, width, message)}
        fired |= hits
        if not hits and not any(_accepts(rule, width, message) for rule in consequences):
            stray.append(line)
    if stray:
        return Verdict(HARNESS, tuple(stray))
    missing = [f"[{w}px] {designation['designated'][i]['pattern']}" for i, (widths, _, _) in enumerate(designated) for w in sorted(widths)
               if (i, w) not in fired]
    if missing:
        return Verdict(UNSPECIFIC, tuple(f"designated diagnostic did not fire: {m}" for m in missing))
    return Verdict(KILLED, outcome.errors)


def suite_mutants(path: Path = SUITE) -> dict:
    """The `broken` table in test_guard_fails_on_broken_builds, read from the suite's source (not imported, not run)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    test = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "test_guard_fails_on_broken_builds"), None)
    table = next((n.value for n in ast.walk(test) if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "broken" for t in n.targets)), None) if test else None
    if not isinstance(table, ast.Dict):
        raise AssertionError(f"{path.name}: no `broken = {{...}}` table in test_guard_fails_on_broken_builds; this module must follow it")
    out = {}
    for key, value in zip(table.keys, table.values):
        try:
            file, call, kind = value.elts
            source_name = call.func.value.id
            find, replace, count = (ast.literal_eval(a) for a in call.args)
            entry = {"file": ast.literal_eval(file), "find": find, "replace": replace, "kind": ast.literal_eval(kind)}
        except (AttributeError, ValueError, TypeError) as exc:
            raise AssertionError(f"{path.name}: mutation {ast.dump(key)} is not `(file, js|css.replace(find, replace, 1), kind)`: {exc}") from exc
        if call.func.attr != "replace" or count != 1 or source_name != {"waivers.js": "js", "waivers.css": "css"}.get(entry["file"]):
            raise AssertionError(f"{path.name}: mutation {ast.literal_eval(key)!r} does not replace once in its own file")
        out[ast.literal_eval(key)] = entry
    return out


def entries(fixture: dict) -> dict:
    """The suite's mutants, then the fixture's own variants."""
    return {**fixture["mutants"], **fixture.get("variants", {})}


def expectation_problems(name: str, expect: dict, outcome: Outcome, verdict: Verdict) -> list[str]:
    """What differs from the verdict the fixture records. A known false green must fail in exactly its recorded way, so a fix to
    the suite (or a new way of failing) shows up here and the entry has to be changed to expect a kill."""
    if verdict.kind != expect["kind"]:
        return [f"{name}: {verdict.kind}, fixture expects {expect['kind']}: {list(verdict.detail)[:4]}"]
    if expect["kind"] != HARNESS:
        return []
    exc = outcome.exception
    if exc is None or type(exc).__name__ != expect["exception"] or not re.search(expect["message"], str(exc)):
        return [f"{name}: harness failure is not the recorded one ({expect['exception']} /{expect['message']}/): {exc!r}"[:400]]
    if not legacy_caught(outcome):
        return [f"{name}: the old rule no longer counts this as caught"]
    return []


def mutant_overrides(names, fixture=None, append: str = "") -> dict:
    """run_checks overrides for one or more fixture mutants applied together to the production source."""
    fixture = fixture or load_fixture()
    bodies = {}
    for name in names:
        m = entries(fixture)[name]
        bodies[m["file"]] = mutate(bodies.get(m["file"]) or SOURCES[m["file"]].read_text(encoding="utf-8"), m["find"], m["replace"], name)
    if append:
        bodies["waivers.js"] = (bodies.get("waivers.js") or SOURCES["waivers.js"].read_text(encoding="utf-8")) + "\n" + append + "\n"
    return {file: (body, KINDS[file]) for file, body in bodies.items()}


def only_designated(outcome: Outcome, designation: dict) -> Outcome:
    """The same run with every line the designation does not name removed: what is left is the designated evidence alone."""
    rules = [_rule(d) for d in designation["designated"]]
    keep = tuple(line for line in outcome.errors if (t := TAGGED.fullmatch(line)) and any(_accepts(r, int(t[1]), t[2]) for r in rules))
    return Outcome(errors=keep)


def digests() -> dict:
    """The files this module must only read."""
    paths = [*SOURCES.values(), SUITE, ROOT / "tests" / "_render_env.py", FIXTURE]
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def report(name: str, verdict: Verdict, outcome: Outcome) -> None:
    """One line per mutant in the test log (stderr), like the JEG-1056 GUARD CAUGHT lines."""
    print(f"MUTANT {verdict.kind.upper():10} legacy={'caught' if legacy_caught(outcome) else 'missed':6} {name}: "
          f"{'; '.join(verdict.detail)[:300]}", file=sys.stderr)


# ---------------------------------------------------------------------------------------------------------------------------
# Offline: no browser, no build.

SAMPLE = {"designated": [{"widths": [1366, 390], "pattern": "headline reads ''"}],
          "consequences": [{"widths": [390], "pattern": "the link opened a different result: .*", "why": "sample"}]}


class ClassifierOfflineTests(unittest.TestCase):
    """Harness failures never classify as killed; the old rule calls every one of them caught."""

    def harness_cases(self):
        designated = ("[1366px] headline reads ''", "[390px] headline reads ''")
        cases = {
            "browser unavailable, required": Outcome(exception=RuntimeError("render test cannot run (RENDER_TESTS_REQUIRED=1): Chromium is not available")),
            "browser unavailable, local skip": Outcome(exception=unittest.SkipTest("Chromium is not available")),
            "exception with no message": Outcome(exception=RuntimeError()),
            "unrelated page error with the designated diagnostic": Outcome(errors=designated + ("[1366px] page errors ['Error: boom']",)),
            "page error alone": Outcome(errors=("[390px] page errors ['TypeError: x is undefined']",)),
            "unrelated diagnostic with the designated diagnostic": Outcome(errors=designated + ("[1366px] table role None labelled by v2WaiversHeadline",)),
            "untagged line": Outcome(errors=designated + ("Timeout 30000ms exceeded",)),
        }
        try:
            from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout
        except Exception:   # the package is optional offline; the generic exceptions above already cover the rule
            pass
        else:
            cases["navigation timeout"] = Outcome(exception=PlaywrightTimeout("page.goto: Timeout 30000ms exceeded."))
            cases["browser launch error"] = Outcome(exception=PlaywrightError("BrowserType.launch: spawn EACCES"))
        return cases

    def test_harness_failures_are_never_killed(self):
        for name, outcome in self.harness_cases().items():
            with self.subTest(case=name):
                self.assertEqual(HARNESS, classify(outcome, SAMPLE).kind)
                self.assertTrue(legacy_caught(outcome), "the old rule counts this as a kill: the false green this module exists for")

    def test_a_page_error_cannot_be_designated(self):
        loose = {"designated": [{"widths": [1366], "pattern": ".*"}]}
        self.assertEqual(HARNESS, classify(Outcome(errors=("[1366px] page errors ['Error: boom']",)), loose).kind)

    def test_designated_alone_is_killed(self):
        outcome = Outcome(errors=("[1366px] headline reads ''", "[390px] headline reads ''"))
        self.assertEqual(KILLED, classify(outcome, SAMPLE).kind)

    def test_listed_consequences_do_not_spoil_a_kill(self):
        outcome = Outcome(errors=("[1366px] headline reads ''", "[390px] headline reads ''", "[390px] the link opened a different result: '' vs ''"))
        self.assertEqual(KILLED, classify(outcome, SAMPLE).kind)

    def test_designated_missing_at_one_width_is_unspecific(self):
        self.assertEqual(UNSPECIFIC, classify(Outcome(errors=("[1366px] headline reads ''",)), SAMPLE).kind)
        only_consequence = Outcome(errors=("[390px] the link opened a different result: 'a' vs 'b'",))
        self.assertEqual(UNSPECIFIC, classify(only_consequence, SAMPLE).kind)

    def test_designated_or_consequence_at_an_unlisted_width_is_stray(self):
        desktop_only = {"designated": [{"widths": [1366], "pattern": "aria-sort after one click: .*"}]}
        outcome = Outcome(errors=("[1366px] aria-sort after one click: []", "[390px] aria-sort after one click: []"))
        self.assertEqual(HARNESS, classify(outcome, desktop_only).kind)
        wrong_width = Outcome(errors=("[1366px] headline reads ''", "[390px] headline reads ''", "[1366px] the link opened a different result: 'a' vs 'b'"))
        self.assertEqual(HARNESS, classify(wrong_width, SAMPLE).kind)

    def test_a_known_false_green_must_fail_its_recorded_way(self):
        expect = {"kind": HARNESS, "exception": "ValueError", "message": "^'' is not in list$"}
        recorded = Outcome(exception=ValueError("'' is not in list"))
        self.assertEqual([], expectation_problems("x", expect, recorded, classify(recorded, SAMPLE)))
        other = Outcome(exception=RuntimeError("render test cannot run"))
        self.assertTrue(expectation_problems("x", expect, other, classify(other, SAMPLE)), "a different harness failure must not pass as the recorded one")
        fixed = Outcome(errors=("[1366px] headline reads ''", "[390px] headline reads ''"))
        self.assertTrue(expectation_problems("x", expect, fixed, classify(fixed, SAMPLE)), "a fixed suite must force the entry to expect a kill")

    def test_no_errors_survived(self):
        self.assertEqual(SURVIVED, classify(Outcome(), SAMPLE).kind)

    def test_patterns_match_whole_lines(self):
        self.assertEqual(HARNESS, classify(Outcome(errors=("[1366px] headline reads '' and more", "[390px] headline reads ''")), SAMPLE).kind)

    def test_only_designated_drops_contamination(self):
        outcome = Outcome(errors=("[1366px] headline reads ''", "[1366px] page errors ['Error: boom']", "[390px] headline reads ''"))
        self.assertEqual(("[1366px] headline reads ''", "[390px] headline reads ''"), only_designated(outcome, SAMPLE).errors)


class AnchorOfflineTests(unittest.TestCase):
    def test_stale_anchor_fails_by_name(self):
        with self.assertRaisesRegex(StaleAnchor, "'no grid role' occurs 0 times"):
            mutate("const t = {role: 'table'};", 'role: "grid", ', "", "no grid role")

    def test_doubled_anchor_fails(self):
        with self.assertRaisesRegex(StaleAnchor, "occurs 2 times"):
            mutate("a; a;", "a;", "", "doubled")

    def test_noop_mutation_fails(self):
        with self.assertRaisesRegex(StaleAnchor, "replaces its anchor with itself"):
            mutate("a;", "a;", "a;", "noop")

    def test_every_fixture_anchor_applies_once_to_the_production_source(self):
        for name, m in entries(load_fixture()).items():
            with self.subTest(mutation=name):
                source = SOURCES[m["file"]].read_text(encoding="utf-8")
                self.assertNotEqual(source, mutate(source, m["find"], m["replace"], name))


class FixtureOfflineTests(unittest.TestCase):
    def test_fixture_mirrors_the_suite_mutation_table(self):
        fixture = load_fixture()["mutants"]
        table = suite_mutants()
        self.assertEqual(sorted(table), sorted(fixture), "the suite's mutation names and the fixture's differ")
        for name, entry in table.items():
            with self.subTest(mutation=name):
                self.assertEqual({k: entry[k] for k in ("file", "find", "replace")}, {k: fixture[name][k] for k in ("file", "find", "replace")})
                self.assertEqual(KINDS[entry["file"]], entry["kind"])

    # Codex review on #1144: a consequence must not launder an unrelated failure that shares its diagnostic.
    HEADERS_390 = ("[390px] controls under 44 px on the Waivers tab (68 checked): [\"button#. 'Candidate' 73x32\", \"button#. 'DDF Value' 73x32\", "
                   "\"button#. 'Value above waivers' 134x32\", \"button#. 'Market value' 89x32\", \"button#. 'Starter change' 101x32\", "
                   "\"button#. 'Bench change' 97x32\"]")   # as observed in Chromium at 430791c4

    def test_card_layout_consequence_lists_only_the_header_sort_buttons(self):
        m = load_fixture()["mutants"]["no card layout"]
        layout = ("[390px] phone layout: table True cards True count 10", "[390px] sideways scroll 398px")
        self.assertEqual(KILLED, classify(Outcome(errors=layout + (self.HEADERS_390,)), m).kind)
        unrelated = {
            "a search-result button (no id or class either)": "[\"button#. 'Saquon Barkley · RB' 100x20\"]",
            "header buttons plus a search-result button": "[\"button#. 'Candidate' 73x32\", \"button#. 'Saquon Barkley · RB' 100x20\"]",
            "a header button that is not the 32 px header": "[\"button#. 'Candidate' 73x20\"]",
            "an unsortable column's label": "[\"button#. 'Reason' 73x32\"]",
            "items run together": "[\"button#. 'Candidate' 73x32\"\"button#. 'DDF Value' 73x32\"]",
        }
        for case, listed in unrelated.items():
            with self.subTest(case=case):
                line = f"[390px] controls under 44 px on the Waivers tab (68 checked): {listed}"
                self.assertEqual(HARNESS, classify(Outcome(errors=layout + (line,)), m).kind)

    def test_sort_consequence_and_designations_need_a_correctly_ordered_payload(self):
        fixture = load_fixture()
        aria = fixture["mutants"]["no aria-sort"]
        observed = ("[1366px] aria-sort after one click: []",
                    "[1366px] DDF Value ascending, dashes last: [] [0.0, 13.9, 16.1, 17.3, 26.5, 30.6, 30.6, 32.6, 34.1, None]")
        self.assertEqual(KILLED, classify(Outcome(errors=observed), aria).kind)
        for case, values in {"numbers out of order": "[3.0, 1.0, 2.0, None]", "dashes first": "[None, 1.0, 2.0]",
                             "no dash": "[1.0, 2.0]", "not a list of numbers": "[1.0, 'x', None]"}.items():
            with self.subTest(aria_sort=case):
                broken = observed[:1] + (f"[1366px] DDF Value ascending, dashes last: [] {values}",)
                self.assertEqual(HARNESS, classify(Outcome(errors=broken), aria).kind)
        dashes = fixture["mutants"]["dashes sorted first"]
        observed = ("[1366px] DDF Value descending, dashes last: [None, 34.1, 32.6, 30.6, 30.6, 26.5, 17.3, 16.1, 13.9, 0.0]",
                    "[1366px] DDF Value ascending, dashes last: [['ddf', 'ascending']] [None, 0.0, 13.9, 16.1, 17.3, 26.5, 30.6, 30.6, 32.6, 34.1]")
        self.assertEqual(KILLED, classify(Outcome(errors=observed), dashes).kind)
        unsorted = ("[1366px] DDF Value descending, dashes last: [None, 13.9, 34.1, 0.0]",) + observed[1:]
        self.assertEqual(HARNESS, classify(Outcome(errors=unsorted), dashes).kind, "dashes first plus a broken numeric sort is two failures")

    # JEG-1296: with JEG-1282's ranking fix the verdict-text mutant returns its list, and three other checks that read the same
    # verdict text fire with it. Each consequence is pinned to that empty verdict, so the same checks failing some other way stay stray.
    VERDICT_TEXT = (   # as observed in Chromium on #1149 (87b4f7b4)
        "[1366px] verdict cells ['', '', '', '', '', '', '', '', '', '']",
        "[1366px] the defense row: {'name': 'Arizona Cardinals', 'pos': 'DEF', 'ddf': '— no value', 'vaw': '— no value', 'market': '— no value', "
        "'starter': '— no value', 'bench': '— no value', 'drop': '— no value', 'verdict': '', 'reason': 'Arizona Cardinals: kickers and defenses are not evaluated.'}",
        "[1366px] the Verdict header does not return to the ranked order",
        "[390px] a card has no verdict banner",
        "[390px] verdict cells ['', '', '', '', '', '', '', '', '', '']",
        "[390px] the defense row: {'name': 'Arizona Cardinals', 'pos': 'DEF', 'ddf': '—no value', 'vaw': '—no value', 'market': '—no value', "
        "'starter': '—no value', 'bench': '—no value', 'drop': '—no value', 'verdict': '', 'reason': 'Arizona Cardinals: kickers and defenses are not evaluated.'}",
    )

    def test_verdict_text_consequences_are_pinned_to_the_empty_verdict(self):
        m = load_fixture()["mutants"]["no verdict text"]
        self.assertEqual(KILLED, classify(Outcome(errors=self.VERDICT_TEXT), m).kind)
        swaps = {
            "a verdict cell that is not empty": ("verdict cells ['', ''", "verdict cells ['Skip', ''"),
            "the defense priced instead of a dash": ("'ddf': '— no value'", "'ddf': '12.3'"),
            "the defense given a verdict": ("'verdict': '', 'reason'", "'verdict': 'Skip', 'reason'"),
            "the defense reason changed": ("kickers and defenses are not evaluated.", "worth a pickup."),
            "a defense row that is not a defense": ("'pos': 'DEF'", "'pos': 'RB'"),
        }
        for case, (old, new) in swaps.items():
            with self.subTest(case=case):
                lines = list(self.VERDICT_TEXT)
                i = next(i for i, line in enumerate(lines) if old in line)
                lines[i] = lines[i].replace(old, new, 1)
                self.assertNotEqual(KILLED, classify(Outcome(errors=tuple(lines)), m).kind)
        moved = self.VERDICT_TEXT + ("[1366px] a card has no verdict banner",)   # the card banner is a phone check
        self.assertEqual(HARNESS, classify(Outcome(errors=moved), m).kind)

    def test_suite_table_reader_rejects_a_changed_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "test_changed.py"
            changed.write_text("def test_guard_fails_on_broken_builds(self):\n    broken = [1, 2]\n", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "no `broken"):
                suite_mutants(changed)

    def test_every_mutant_designates_a_diagnostic_at_a_run_width(self):
        fixture = load_fixture()
        widths = {w for w, _ in fixture["viewports"]}
        for name, m in entries(fixture).items():
            with self.subTest(mutation=name):
                self.assertTrue(m["designated"], "no designated diagnostic")
                for entry in m["designated"] + m.get("consequences", []):
                    self.assertTrue(entry["widths"] and set(entry["widths"]) <= widths, f"widths {entry['widths']} not all in {sorted(widths)}")
                    compiled = re.compile(entry["pattern"])
                    self.assertIsNone(re.fullmatch(entry["pattern"], "page errors ['Error: boom']", re.S), "a pattern that matches a page error")
                    if "values" in entry:
                        self.assertIn(entry["values"], ORDERS)
                        self.assertIn("values", compiled.groupindex, "an ordered entry needs a (?P<values>...) group")
                for c in m.get("consequences", []):
                    self.assertTrue(c.get("why"), f"consequence {c['pattern']!r} has no reason")

    def test_known_false_greens_name_their_defect_and_a_way_to_prove_the_check(self):
        fixture = load_fixture()
        stand_ins = {v["stands_in_for"]: name for name, v in fixture.get("variants", {}).items()}
        for name, m in entries(fixture).items():
            with self.subTest(mutation=name):
                expect = m["expect"]
                self.assertIn(expect["kind"], (KILLED, HARNESS))
                if expect["kind"] == HARNESS:
                    self.assertRegex(expect.get("defect", ""), r"^JEG-\d+$", "a known false green names its defect ticket")
                    self.assertTrue(expect.get("why") and expect.get("exception") and expect.get("message"))
                    re.compile(expect["message"])
                    self.assertTrue(name in stand_ins or expect.get("no_variant"), "a well-formed variant, or the reason none can exist")
        for name, v in fixture.get("variants", {}).items():
            with self.subTest(variant=name):
                self.assertEqual(KILLED, v["expect"]["kind"], "a variant exists to show the designated check kills")
                self.assertEqual(HARNESS, fixture["mutants"][v["stands_in_for"]]["expect"]["kind"])


# ---------------------------------------------------------------------------------------------------------------------------
# Chromium: the real harness, real mutants, real injected failures.

class MutationSpecificityRenderTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        _render_env.ensure_built()
        cls.fixture = load_fixture()
        cls.baseline = run()
        if isinstance(cls.baseline.exception, unittest.SkipTest):   # no browser locally: skip; RENDER_TESTS_REQUIRED=1 raises instead
            raise cls.baseline.exception

    def assert_baseline_clean(self):
        b = self.baseline
        self.assertIsNone(b.exception, f"the clean baseline could not run, so no mutant result means anything: {b.exception!r}")
        self.assertEqual((), b.errors, "the clean baseline fails, so no mutant result means anything")

    def test_baseline_is_clean(self):
        self.assert_baseline_clean()

    def test_each_mutant_classifies_as_recorded_then_the_restored_control_passes(self):
        """Killed means the designated check caught it; an entry recorded as a known false green must fail in its recorded way."""
        self.assert_baseline_clean()
        before = digests()
        problems = []
        for name, m in entries(self.fixture).items():
            outcome = run(mutant_overrides([name], self.fixture))
            verdict = classify(outcome, m)
            report(name, verdict, outcome)
            problems += expectation_problems(name, m["expect"], outcome, verdict)
        control = run({file: (path.read_text(encoding="utf-8"), KINDS[file]) for file, path in SOURCES.items()})
        self.assertEqual([], problems)
        self.assertIsNone(control.exception, f"restored control could not run: {control.exception!r}")
        self.assertEqual((), control.errors, "the original files served through the override route fail")
        self.assertEqual(before, digests(), "a production source, the suite or the fixture changed during the run")

    def test_injected_browser_unavailable_is_harness(self):
        self.assert_baseline_clean()
        injection = self.fixture["injections"]["browser unavailable"]
        overrides = mutant_overrides([injection["mutant"]], self.fixture)
        with tempfile.TemporaryDirectory() as tmp:
            not_a_browser = Path(tmp) / "not-a-browser"
            not_a_browser.write_text("not a browser\n", encoding="utf-8")
            not_a_browser.chmod(0o644)
            for required, expected in (("1", RuntimeError), ("", unittest.SkipTest)):
                with self.subTest(RENDER_TESTS_REQUIRED=required), \
                        mock.patch.dict(os.environ, {"CHROMIUM_PATH": str(not_a_browser), "RENDER_TESTS_REQUIRED": required}):
                    outcome = run(overrides)
                    self.assertIsInstance(outcome.exception, expected)
                    self.assertIn("Chromium is not available", str(outcome.exception))
                    self.assertTrue(legacy_caught(outcome), "the old rule counts this as a kill")
                    self.assertEqual(HARNESS, classify(outcome, self.fixture["mutants"][injection["mutant"]]).kind)

    def test_injected_navigation_timeout_is_harness(self):
        self.assert_baseline_clean()
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        injection = self.fixture["injections"]["navigation timeout"]
        outcome = run(mutant_overrides([injection["mutant"]], self.fixture, append=injection["append"]), viewports=((1366, 768),))
        self.assertIsInstance(outcome.exception, PlaywrightTimeout, f"want a navigation timeout, got {outcome!r}")
        self.assertTrue(legacy_caught(outcome), "the old rule counts this as a kill")
        self.assertEqual(HARNESS, classify(outcome, self.fixture["mutants"][injection["mutant"]]).kind)

    def test_injected_unrelated_page_error_is_harness(self):
        self.assert_baseline_clean()
        injection = self.fixture["injections"]["unrelated page error"]
        designation = self.fixture["mutants"][injection["mutant"]]
        outcome = run(mutant_overrides([injection["mutant"]], self.fixture, append=injection["append"]))
        self.assertTrue(any(injection["marker"] in line for line in outcome.errors), f"the injected page error was not served: {outcome!r}")
        verdict = classify(outcome, designation)
        self.assertEqual(HARNESS, verdict.kind, verdict.detail)
        self.assertTrue(all("page errors" in line for line in verdict.detail), verdict.detail)
        self.assertEqual(KILLED, classify(only_designated(outcome, designation), designation).kind,
                         "without the page error this run is a kill, so the page error alone made it a harness failure")
        self.assertTrue(legacy_caught(outcome))

    def test_injected_unrelated_diagnostic_is_harness(self):
        self.assert_baseline_clean()
        injection = self.fixture["injections"]["unrelated diagnostic"]
        designation = self.fixture["mutants"][injection["judged_as"]]
        outcome = run(mutant_overrides(injection["mutants"], self.fixture))
        verdict = classify(outcome, designation)
        self.assertEqual(HARNESS, verdict.kind, verdict.detail)
        unrelated = [re.compile(d["pattern"], re.S) for d in self.fixture["mutants"][injection["unrelated"]]["designated"]]
        self.assertTrue(all((t := TAGGED.fullmatch(line)) and any(p.fullmatch(t[2]) for p in unrelated) for line in verdict.detail),
                        f"the stray lines should be the {injection['unrelated']!r} diagnostic: {verdict.detail}")
        self.assertEqual(KILLED, classify(only_designated(outcome, designation), designation).kind)
        self.assertTrue(legacy_caught(outcome))


if __name__ == "__main__":
    unittest.main()
