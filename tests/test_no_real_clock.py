"""JEG-1158: bounded static clock guard; run with python -m unittest tests.test_no_real_clock.

Coverage is deliberately explicit: calendar, page calendar/engine, shared render
setup, week-history/contract renders, and the three CI rendered gates. Python
calls use AST (including import aliases); JS and embedded JS use a conservative
lexical check. This is not a general JS parser or a whole-repository clock ban.
Production fallbacks and elapsed-time/diagnostic clocks are allowed by exact
line AND occurrence count, never by file. Removing an exception also fails so
the inventory stays reviewable. No browser, build, network, or make is needed.
"""
from __future__ import annotations

import ast
from collections import Counter
from datetime import date
from pathlib import Path
import re
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = "app/trade-value-chart/assets/product-data.js"
WIDGET = "app/trade-value-chart/assets/curve-widget.js"
GATES = tuple(f"tests/rendered_gate/{name}.mjs" for name in (
    "gate", "gate_flexibility", "bench_share_readout_harness"))
COVERED = (
    "pipelines/nfl_week.py", PRODUCT, WIDGET,
    "tests/_render_env.py", "tests/_league_render.py",
    "tests/test_week_calendar.py", "tests/test_week_history.py",
    "tests/test_v2_contract_render.py", *GATES,
)

# (path, exact stripped source line): (number of reads, reason)
ALLOWLIST = {
    # JEG-1177: the two date.today() defaults became one New York clock
    # (now_utc -> today_ny), read only after set_clock() and DDF_NOW.
    ("pipelines/nfl_week.py", "moment = datetime.now(timezone.utc)"): (
        1, "Production wall clock behind set_clock()/DDF_NOW; content/game defaults read it via today_ny."),
    (PRODUCT, "const now = new Date();"): (
        1, "Production reader clock after explicit/window override returns."),
    (WIDGET, 'checks.set(id, {name, status, detail: detail || "", at: new Date().toISOString(), diagnostics: diagnostics || null});'): (
        1, "Diagnostic check timestamp, not calendar eligibility."),
    (WIDGET, 'checks.set(id, {name, status: "warn", detail: detail || "", at: new Date().toISOString(), diagnostics: diagnostics || null});'): (
        1, "Diagnostic warning timestamp, not calendar eligibility."),
    (GATES[1], "const deadline = Date.now() + timeoutMs;"): (
        1, "Elapsed-time deadline for table settling."),
    (GATES[1], "while (Date.now() < deadline) {"): (
        1, "Elapsed-time polling for table settling."),
}

JS_CLOCK = re.compile(r"\b(?:new\s+Date\s*\(\s*\)|Date\s*\.\s*now\s*\(\s*\)|(?<!new )Date\s*\(\s*\))")


def clock_reads(path, source):
    """Yield (line number, exact line) for clock calls, including embedded JS."""
    lines = source.splitlines()
    if path.endswith(".py"):
        tree = ast.parse(source)
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for item in node.names:
                    aliases[item.asname or item.name] = item.name
            elif isinstance(node, ast.ImportFrom) and node.module == "datetime":
                for item in node.names:
                    aliases[item.asname or item.name] = f"datetime.{item.name}"

        def name(node):
            if isinstance(node, ast.Name):
                return aliases.get(node.id, node.id)
            if isinstance(node, ast.Attribute):
                return f"{name(node.value)}.{node.attr}"
            return ""

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and name(node.func) in {
                "datetime.datetime.now", "datetime.datetime.utcnow",
                "datetime.datetime.today", "datetime.date.today",
                "datetime.now", "datetime.utcnow", "date.today",
            }:
                yield node.lineno, lines[node.lineno - 1].strip()
    # Keep strings: Python render tests contain executable JavaScript in strings.
    searchable = "\n".join(
        "" if line.lstrip().startswith(("#", "//", "*")) else line
        for line in lines)
    for match in JS_CLOCK.finditer(searchable):
        number = searchable.count("\n", 0, match.start()) + 1
        yield number, lines[number - 1].strip()


def violations(files):
    found = Counter()
    errors = []
    for path, source in files.items():
        for number, line in clock_reads(path, source):
            key = (path, line)
            found[key] += 1
            if key not in ALLOWLIST or found[key] > ALLOWLIST[key][0]:
                errors.append(f"{path}:{number}: real clock: {line}")
    for key, (count, reason) in ALLOWLIST.items():
        if key[0] in files and found[key] < count:
            errors.append(f"stale clock exception: {key}: {reason}")
    return errors


class NoRealClockTest(unittest.TestCase):
    def test_covered_sources(self):
        files = {p: (ROOT / p).read_text(encoding="utf-8") for p in COVERED}
        self.assertEqual(violations(files), [])

    def test_deliberate_real_clock_reads_fail(self):
        for source in (
            "from datetime import datetime\nx = datetime.now()",
            "import datetime as dt\nx = dt.datetime.now()",
            "from datetime import date as D\nx = D.today()",
            "x = date.today()", 'script = "new Date()"',
            'script = "Date.now()"',
        ):
            with self.subTest(source=source):
                self.assertTrue(violations({"tests/probe.py": source}))
        for source in ("const day = new Date();", "const day = Date.now();",
                       "const day = new\nDate ( );", "const day = Date();"):
            with self.subTest(source=source):
                self.assertTrue(violations({"probe.js": source}))

    def test_injected_dates_are_not_clock_reads(self):
        self.assertEqual(list(clock_reads("probe.js", 'new Date("2026-10-27");')), [])
        self.assertEqual(list(clock_reads("probe.py", "date(2026, 10, 27)")), [])

    def test_duplicate_allowed_read_is_rejected(self):
        source = (ROOT / PRODUCT).read_text(encoding="utf-8")
        self.assertTrue(violations({PRODUCT: source + "\nconst now = new Date();\n"}))

    def test_real_clock_mutation_fails_in_every_covered_file(self):
        for path in COVERED:
            source = (ROOT / path).read_text(encoding="utf-8")
            mutation = ("\nclock_regression = date.today()\n" if path.endswith(".py")
                        else "\nconst clockRegression = Date.now();\n")
            with self.subTest(path=path):
                errors = violations({path: source + mutation})
                self.assertEqual(len(errors), 1, errors)
                self.assertIn("real clock:", errors[0])

    def test_injected_calendar_never_reads_host_date(self):
        from pipelines import nfl_week

        class NoHostDate(date):
            @classmethod
            def today(cls):
                raise AssertionError("injected calendar read the real clock")

        with patch.object(nfl_week, "date", NoHostDate):
            for day, content, game in ((date(2026, 10, 22), 7, 7),
                                       (date(2026, 10, 27), 8, 7)):
                with self.subTest(today=day):
                    self.assertEqual(nfl_week.content_week(day), content)
                    self.assertEqual(nfl_week.game_week(day), game)
                    self.assertEqual(nfl_week.current_nfl_week(day), content)

    def test_page_fallback_remains_after_injection(self):
        source = (ROOT / PRODUCT).read_text(encoding="utf-8")
        # Pin the small injection boundary so the allowed fallback cannot move
        # ahead of, or replace, the override without review.
        self.assertIn('''function todayIsoDay(override) {
    const forced = isoDay(override !== undefined ? override
      : (typeof window !== "undefined" ? window.TRADE_VALUE_TODAY : null));
    if (forced) return forced;
    const now = new Date();''', source)

    def test_ci_gates_keep_page_pin_before_navigation(self):
        for path in GATES:
            source = (ROOT / path).read_text(encoding="utf-8")
            with self.subTest(path=path):
                pin = source.index('await page.addInitScript(`window.TRADE_VALUE_TODAY = ${JSON.stringify(process.env.TRADE_VALUE_TODAY)};`);')
                self.assertLess(pin, source.index("await page.goto("))

    def test_normal_suite_includes_guard(self):
        from tests import run_suite
        self.assertEqual(run_suite.suite_guards("test-unit-modules"),
                         ["python3 -m unittest tests.test_no_real_clock"])
        self.assertEqual(run_suite.suite_guards("unrelated"), [])
        guard = "python3 -m unittest tests.test_no_real_clock"
        with patch.object(run_suite, "recipe_lines", return_value=["next-test"]), \
                patch.object(run_suite, "run", return_value=[guard]) as run, \
                patch("builtins.print"):
            self.assertEqual(run_suite.main(["test-unit-modules"]), 1)
            run.assert_called_once_with([guard, "next-test"], ROOT)


if __name__ == "__main__":
    unittest.main()
