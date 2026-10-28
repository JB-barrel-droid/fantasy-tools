"""JEG-1189 (follow-up to JEG-859): the budget-cut bench total is the same
for every source.

JEG-859 found the Health check's bench totals differ about 62-81% across
sources. That is the role cut (a player's whole Adjusted value is "bench" when
his source ranks him between the starter and rostered lines; app/v2/audit-pie.js)
and the spread is source shape: expected, and not checked here (Jeremy picked
A+C on 2026-10-27). The engine's own budget cut is different: each player's
bench part is rate[pos|bench] x benchSlice (value-model.js VP-5), so a source's
bench total at a position is the funded bench budget, pie x W[pos|bench], the
same for every source. tools/research/bench_spread_by_cut.py measured it (0.0%
spread, week 7). This test pins it, so a real bench-budget bug fails test-core.

Rule checked, per pipeline run (one league setting, one week view):
  * every source the run priced (it has weights) has, at each position, a
    budget-cut bench total equal to pie x W[pos|bench] (to 1e-6 of the pie);
  * so the totals are identical across those sources (also checked directly);
  * the one exception is a group the engine itself reports it could not fund
    (VP-5 unfundedMoved / unfundedGroups): that source's bench there is 0.
    The page shows those; they are printed here, not hidden.

Lagging sources (JEG-1175 / JEG-1177): sources update on different days, so
a chart can serve a week behind the newest. The page prices one week view at a
time and a chart on an older week is left out of the newer view, so the check
runs in every week view the page offers (getWeekState().weeks, setWeek):
each source is compared with the sources sharing its week. A chart whose week
has no view is named on stderr, never failed and never silently dropped.

Three layers:
  * CheckerTest: the rule on synthetic runs (no node, no browser).
  * EngineTest: value-model.js under node on the worked example (three
    variants), and the same engine with one source's bench budget perturbed
    by 1%, which must fail.
  * ServedPageTest: the built engine page on the served data, at four
    settings in every week view, plus the 1% perturbation served in place of
    value-model.js, which must fail. Needs Chromium: a skip locally, an error
    under RENDER_TESTS_REQUIRED=1 (CI).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import ENGINE_URL, serve

ROOT = Path(__file__).resolve().parents[1]
VALUE_MODEL = ROOT / "app" / "trade-value-chart" / "assets" / "value-model.js"
POSITIONS = ("QB", "RB", "WR", "TE")
REL_TOL = 1e-6
PERTURB = 1.01

# The mutation: one source's bench groups funded at 101% of the shared budget.
FUND_ANCHOR = "Object.keys(budgets).forEach(function (g) { funded[g] = budgets[g]; });"


def perturbed_model(source: str) -> str:
    model = VALUE_MODEL.read_text(encoding="utf-8")
    body = model.replace(FUND_ANCHOR, (
        "Object.keys(budgets).forEach(function (g) { funded[g] = budgets[g]"
        f" * (src === {json.dumps(source)} && /\\|bench$/.test(g) ? {PERTURB} : 1); }});"))
    if body == model:
        raise AssertionError("mutation anchor moved: value-model.js no longer funds groups from budgets as "
                             f"{FUND_ANCHOR!r}; update the anchor to the new budget line")
    return body


def unfunded_bench(src: dict) -> set:
    """Bench groups the engine reports it could not fund for this source."""
    out = {m.get("from") for m in src.get("unfundedMoved") or []}
    out |= {u.get("group") for u in src.get("unfundedGroups") or []}
    return {g for g in out if isinstance(g, str) and g.endswith("|bench")}


def bench_totals(src: dict) -> dict:
    """{pos: sum of rate[pos|bench] x benchSlice} over the source's players."""
    rates = src.get("rates") or {}
    out = {pos: 0.0 for pos in POSITIONS}
    for pos, bench_slice in src["players"]:
        if pos in out:
            out[pos] += (rates.get(f"{pos}|bench") or 0.0) * (bench_slice or 0.0)
    return out


def check_run(run: dict, label: str):
    """(problems, compared, notes) for one pipeline run.

    run: {"pie", "ddfWeights", "sources": {src: {"rates", "weights",
    "unfundedMoved", "unfundedGroups", "players": [[pos, benchSlice], ...]}}}."""
    problems, notes = [], []
    pie = run.get("pie")
    if not isinstance(pie, (int, float)) or pie <= 0:
        return [f"{label}: no pie ({pie!r})"], [], notes
    tol = REL_TOL * max(1.0, pie)
    budgets = {pos: pie * (run.get("ddfWeights") or {}).get(f"{pos}|bench", 0.0) for pos in POSITIONS}
    priced = {k: s for k, s in (run.get("sources") or {}).items() if s.get("weights")}
    compared = sorted(priced)
    if len(compared) < 2:
        problems.append(f"{label}: only {compared} priced, nothing to compare")
    by_pos = {pos: {} for pos in POSITIONS}
    for key in compared:
        src = priced[key]
        unfunded = unfunded_bench(src)
        totals = bench_totals(src)
        for pos in POSITIONS:
            if f"{pos}|bench" in unfunded:
                notes.append(f"{label}: {key} {pos} bench budget {budgets[pos]:.3f} unfunded (engine-reported)")
                want = 0.0
            else:
                want = budgets[pos]
                by_pos[pos][key] = totals[pos]
            if abs(totals[pos] - want) > tol:
                problems.append(f"{label}: {key} {pos} budget-cut bench {totals[pos]:.6f}, "
                                f"shared bench budget {want:.6f} (pie {pie} x W)")
    for pos, vals in by_pos.items():
        if len(vals) >= 2 and max(vals.values()) - min(vals.values()) > tol:
            lo, hi = min(vals, key=vals.get), max(vals, key=vals.get)
            problems.append(f"{label}: {pos} budget-cut bench differs across sources: "
                            f"{lo} {vals[lo]:.6f} vs {hi} {vals[hi]:.6f}")
    return problems, compared, notes


def from_driver(out: dict) -> dict:
    """tests/value_pipeline_driver.js output -> check_run's run shape."""
    return {"pie": out["pie"], "ddfWeights": out["ddf_weights"], "sources": {
        key: {"rates": s["rates"], "weights": s["weights"], "unfundedMoved": s["unfunded_moved"],
              "unfundedGroups": s["unfunded_groups"],
              "players": [[p["pos"], p["bench_slice"]] for p in s["players"].values()]}
        for key, s in out["sources"].items()}}


# --- the served page ---------------------------------------------------------

# (scoring, teams, bench-share override or None). The override takes the
# engine's other weight path (bsInput set, VP-4) instead of ES-15.1.
SETTINGS = [("ppr", 12, None), ("half_ppr", 10, None), ("standard", 14, None), ("ppr", 12, 0.10)]

SET = """([scoring, teams, override]) => {
  const c = window.TradeValueCurveControls;
  c.setWeek(null);
  c.setScoring(scoring); c.setTeams(teams);
  c.setBenchShareOverride(override, false);
  const st = c.getWeekState ? c.getWeekState() : null;
  return st ? {week: st.week, weeks: st.weeks, servedWeeks: st.servedWeeks} : null;
}"""

READ = """(week) => {
  const c = window.TradeValueCurveControls;
  if (week !== null) c.setWeek(week);
  const st = c.getWeekState ? c.getWeekState() : null;
  const ins = c.getInspection(), vp = ins.valuePipeline;
  const out = {week: st ? st.week : null, pie: vp ? vp.pie : null, ddfWeights: vp ? vp.ddfWeights : null,
    benchShareApplied: vp ? vp.benchShareApplied : null, sources: {}};
  if (!vp) return out;
  for (const [key, s] of Object.entries(vp.sources)) {
    out.sources[key] = {rates: s.rates, weights: s.weights, unfundedMoved: s.unfundedMoved || [],
      unfundedGroups: s.unfundedGroups || [],
      players: Object.values(ins.players[key] || {}).map(p => [p.pos, p.benchSlice || 0])};
  }
  return out;
}"""


def page_runs(overrides=None):
    """[(label, run)] for every setting x week view, plus lagging notes."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise _render_env.unavailable(f"playwright not installed: {exc}")
    from tests.test_week_history import _fixture_today
    runs, notes = [], []
    with serve(overrides=overrides) as base, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(executable_path=_render_env.chromium_executable(pw),
                                         args=_render_env.HERMETIC_ARGS)
        except Exception as exc:  # noqa: BLE001 - Playwright raises its own Error type
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.add_init_script(f"window.TRADE_VALUE_TODAY = {json.dumps(_fixture_today())};")
            page.goto(f"{base}/{ENGINE_URL}")
            page.wait_for_function("() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()",
                                   timeout=120000)
            for scoring, teams, override in SETTINGS:
                setting = f"{scoring}/{teams}" + (f"/bench{override:.0%}" if override is not None else "")
                state = page.evaluate(SET, [scoring, teams, override])
                weeks = (state or {}).get("weeks") or [None]
                for week in weeks:
                    run = page.evaluate(READ, week)
                    if week is not None and run["week"] != week:
                        runs.append((f"{setting} week {week}", {"pie": None, "error": f"page stayed on {run['week']}"}))
                        continue
                    if override is not None and abs((run.get("benchShareApplied") or 0) - override) > 1e-9:
                        runs.append((f"{setting} week {run['week']}",
                                     {"pie": None, "error": "the bench-share override did not reach the pipeline"}))
                        continue
                    runs.append((f"{setting} week {run['week']}", run))
                served = (state or {}).get("servedWeeks") or {}
                lagging = sorted(k for k, w in served.items()
                                 if isinstance(w, int) and state.get("weeks") and w not in state["weeks"])
                if lagging:
                    notes.append(f"{setting}: {', '.join(f'{k} (Week {served[k]})' for k in lagging)} "
                                 f"serve a week with no view {state['weeks']}; not compared")
            runs.extend(("page error", {"pie": None, "error": e}) for e in errors)
        finally:
            browser.close()
    return runs, notes


def check_runs(runs):
    problems, compared, notes = [], {}, []
    for label, run in runs:
        if run.get("error"):
            problems.append(f"{label}: {run['error'][:300]}")
            continue
        p, c, n = check_run(run, label)
        problems += p
        notes += n
        compared[label] = c
    return problems, compared, notes


def annotate(title, lines, level="error"):
    """Surface lines as GitHub check annotations under Actions (job logs are
    not always readable; annotations are), else print them to stderr."""
    import os
    for line in list(lines)[:10]:
        text = str(line).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::{level} title={title}::{text}", flush=True)
        else:
            print(f"[{title}] {line}", file=sys.stderr)


# --- tests -------------------------------------------------------------------

def _synthetic():
    """Three sources, one position each way; every bench total = pie x W."""
    weights = {f"{p}|{r}": 0.125 for p in POSITIONS for r in ("starter", "bench")}
    pie = 100.0  # bench budget 12.5 per position
    src = lambda scale: {"rates": {f"{p}|bench": 12.5 / (10.0 * scale) for p in POSITIONS}, "weights": weights,
                         "unfundedMoved": [], "unfundedGroups": [],
                         "players": [[p, 4.0 * scale] for p in POSITIONS] + [[p, 6.0 * scale] for p in POSITIONS]}
    return {"pie": pie, "ddfWeights": weights, "sources": {"a": src(1.0), "b": src(2.0), "c": src(0.5)}}


class CheckerTest(unittest.TestCase):
    def test_identical_bench_passes(self):
        problems, compared, _ = check_run(_synthetic(), "syn")
        self.assertEqual(problems, [])
        self.assertEqual(compared, ["a", "b", "c"])

    def test_one_source_perturbed_fails(self):
        run = _synthetic()
        run["sources"]["b"]["players"][0][1] *= 1.01  # QB bench slice of one player
        problems, _, _ = check_run(run, "syn")
        self.assertTrue(any(" b QB " in p for p in problems), problems)
        self.assertTrue(any("differs across sources" in p for p in problems), problems)

    def test_unpriced_source_is_not_compared(self):
        run = _synthetic()
        run["sources"]["lag"] = {"rates": {}, "weights": None, "unfundedMoved": [], "unfundedGroups": [],
                                 "players": []}
        problems, compared, _ = check_run(run, "syn")
        self.assertEqual(problems, [])
        self.assertNotIn("lag", compared)

    def test_engine_reported_unfunded_bench_is_zero_and_noted(self):
        run = _synthetic()
        c = run["sources"]["c"]
        c["players"] = [pl for pl in c["players"] if pl[0] != "TE"] + [["TE", 0.0]]
        c["unfundedMoved"] = [{"from": "TE|bench", "to": "TE|starter", "amount": 12.5}]
        problems, _, notes = check_run(run, "syn")
        self.assertEqual(problems, [])
        self.assertTrue(any("c TE" in n for n in notes), notes)

    def test_unreported_zero_bench_fails(self):
        run = _synthetic()
        c = run["sources"]["c"]
        c["players"] = [pl for pl in c["players"] if pl[0] != "TE"]
        problems, _, _ = check_run(run, "syn")
        self.assertTrue(any(" c TE " in p for p in problems), problems)

    def test_single_source_run_is_not_a_pass(self):
        run = _synthetic()
        run["sources"] = {"a": run["sources"]["a"]}
        problems, _, _ = check_run(run, "syn")
        self.assertTrue(any("nothing to compare" in p for p in problems), problems)


class EngineTest(unittest.TestCase):
    VARIANTS = (None, "variant_expected_starts", "variant_bench_share_0_10")

    def test_worked_example_bench_is_identical(self):
        from tests.test_value_pipeline_engine import run_engine
        for variant in self.VARIANTS:
            with self.subTest(variant=variant):
                problems, compared, _ = check_run(from_driver(run_engine(variant=variant)), str(variant))
                self.assertEqual(problems, [])
                self.assertGreaterEqual(len(compared), 5)

    def test_perturbed_source_budget_fails(self):
        from tests.test_value_pipeline_engine import run_engine
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "value-model.js"
            model.write_text(perturbed_model("c2"), encoding="utf-8")
            for variant in self.VARIANTS:
                with self.subTest(variant=variant):
                    problems, _, _ = check_run(from_driver(run_engine(model=model, variant=variant)), str(variant))
                    self.assertTrue(any(" c2 " in p for p in problems),
                                    f"a 1% bench-budget perturbation of c2 was NOT caught: {problems}")
                    # Only the perturbed source is off its budget.
                    off = {p.split(": ", 1)[1].split(" ", 1)[0] for p in problems if "differs" not in p}
                    self.assertEqual(off, {"c2"}, problems)


class ServedPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _render_env.ensure_built()
        try:
            cls.runs, cls.lagging = page_runs()
        except unittest.SkipTest:
            raise
        except Exception as exc:
            annotate("JEG-1189 bench budget cut", [f"served page could not be read: {exc!r}"[:600]])
            raise

    def test_budget_cut_bench_identical_in_every_week_view(self):
        problems, compared, notes = check_runs(self.runs)
        annotate("JEG-1189 bench budget cut", self.lagging + notes, level="notice")
        if problems:
            annotate("JEG-1189 bench budget cut", problems)
        annotate("JEG-1189 bench budget cut", [f"{len(compared)} runs: "
                 + "; ".join(f"{k}: {', '.join(v)}" for k, v in compared.items())], level="notice")
        self.assertGreaterEqual(len(compared), len(SETTINGS))
        self.assertEqual(problems, [], "\n".join(problems[:25]))

    def test_perturbed_source_budget_fails_on_the_page(self):
        problems, compared, _ = check_runs(self.runs)
        first = next((label for label, run in self.runs if not run.get("error")), None)
        self.assertIsNotNone(first, "no clean run to pick a source from")
        source = compared[first][0]
        runs, _ = page_runs({"assets/value-model.js": perturbed_model(source).encode("utf-8")})
        broken, _, _ = check_runs(runs)
        if not any(f" {source} " in p for p in broken):
            annotate("JEG-1189 bench budget cut mutation", [f"{source} x{PERTURB} not caught"] + broken)
        print(f"\n[bench budget cut mutation] {source} bench funded x{PERTURB}: {len(broken)} problems, "
              f"e.g. {broken[:1]}", file=sys.stderr)
        self.assertTrue(any(f" {source} " in p for p in broken),
                        f"a 1% bench-budget perturbation of {source} was NOT caught: {broken[:5]}")


if __name__ == "__main__":
    unittest.main()
