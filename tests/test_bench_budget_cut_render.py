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

Same-run invariant (JEG-1253): budgets are compared only inside one run.
Two runs (another week view, another setting, or a loaded league's other
bench level, JEG-1188 "ddf" vs "market") may have different pies and weights;
nothing here asserts that one run's budgets equal another's.

Layers:
  * CheckerTest: the rule on synthetic runs (no node, no browser).
  * EngineTest: value-model.js under node on the worked example (three
    variants), and the same engine with the mutation below, which must fail.
  * TransitionReferenceTest (JEG-1253): deterministic lagging-week coverage
    without a browser. The committed-data week transition replay
    (test_week_history.transition_overrides: CBS and USA Today a week behind)
    priced by the Python reference (value_reference.py, which value_check
    holds to the page) in each week view; the lagging charts are checked in
    their own week's view, and a 1% bench shift in one of them fails there.
  * ServedPageTest: the built engine page on the served data, at four
    settings in every week view, plus the mutation served in place of
    value-model.js, which must fail. ServedTransitionTest: the same page on
    the transition replay, both week views, plus the mutation of a lagging
    chart. Both need Chromium: a skip locally, an error under
    RENDER_TESTS_REQUIRED=1 (CI).

The mutation: one source moves 1% of each position's bench budget to that
position's starter budget (its total stays on the pie).

Overlap, on purpose: the page's own regression guard (curve-widget.js
fixedPieDiagnostics, "fixedPieIndexed") already compares each source's group
totals with the shared budgets and refuses to load when one is off; the
mutation above, served alone, stops the page there (CI run on a9d9f6f). This
test pins the rule independently of that guard: on the page, the mutation is
served with the guard's group check switched off, and this check must still
fail. So loosening or removing the guard cannot let a bench-budget bug through.
"""
from __future__ import annotations

import contextlib
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
SHIFT = 0.01

# The mutation: one source funds 1% of each bench budget as starter budget
# instead (pie-conserving, see the module docstring).
FUND_ANCHOR = "Object.keys(budgets).forEach(function (g) { funded[g] = budgets[g]; });"
WIDGET = ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js"
GUARD_ANCHOR = "const groupsOk = Object.values(groups).every(g => Math.abs(g.total - g.budget) <= tolerance);"


def perturbed_model(source: str) -> str:
    model = VALUE_MODEL.read_text(encoding="utf-8")
    body = model.replace(FUND_ANCHOR, FUND_ANCHOR + (
        f" if (src === {json.dumps(source)}) POSITION_ORDER.forEach(function (pos) {{"
        " var b = vpGroupKey(pos, 'bench'), s = vpGroupKey(pos, 'starter');"
        f" if (!(o.groups[b] > 0 && o.groups[s] > 0)) return; var d = {SHIFT} * funded[b];"
        " funded[b] -= d; funded[s] += d; });"))
    if body == model:
        raise AssertionError("mutation anchor moved: value-model.js no longer funds groups from budgets as "
                             f"{FUND_ANCHOR!r}; update the anchor to the new budget line")
    return body


def guard_off_widget() -> str:
    """curve-widget.js with the page guard's per-group budget check off."""
    widget = WIDGET.read_text(encoding="utf-8")
    body = widget.replace(GUARD_ANCHOR, "const groupsOk = true;")
    if body == widget:
        raise AssertionError(f"guard anchor moved: curve-widget.js no longer has {GUARD_ANCHOR!r}")
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


def from_reference(res: dict) -> dict:
    """value_reference.Setting.result() -> check_run's run shape. A source
    left out of the run (an older week than the view) has no players and no
    weights there, so check_run does not price it."""
    return {"pie": res["pie"], "ddfWeights": res["ddf_weights"], "sources": {
        key: {"rates": d.get("rates") or {}, "weights": d.get("weights") if d.get("players") else None,
              "unfundedMoved": d.get("unfunded_moved") or [], "unfundedGroups": d.get("unfunded_groups") or [],
              "players": [[p["pos"], p.get("bench_slice") or 0.0] for p in (d.get("players") or {}).values()]}
        for key, d in res["sources"].items()}}


@contextlib.contextmanager
def transition_reference():
    """(Inputs, History, lagging keys, newest week) for the committed-data
    week transition replay (test_week_history.transition_overrides), read by
    the Python reference from a temporary copy of the served history."""
    import shutil
    _render_env.ensure_built()
    sys.path.insert(0, str(ROOT / "pipelines"))
    from tests import test_week_history as W
    import value_reference as R
    if not (W.DIST / "assets" / "history" / "index.json").exists():
        raise AssertionError("dist/ has no week history after the build: the transition replay cannot run")
    lagging = ("cbs", "usatoday")
    overrides = W.transition_overrides(lagging=lagging)
    with tempfile.TemporaryDirectory() as tmp:
        hist = Path(tmp) / "history"
        shutil.copytree(W.DIST / "assets" / "history", hist)
        (hist / "index.json").write_text(overrides["assets/history/index.json"], encoding="utf-8")
        fixture = Path(tmp) / "fixture.json"
        fixture.write_text(overrides[W.FIXTURE_ASSET], encoding="utf-8")
        yield R, R.Inputs.load(fixture), R.History(hist), lagging, W.newest_week(lagging), overrides


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


def page_runs(overrides=None, settings=None):
    """[(label, run)] for every setting x week view, plus lagging notes.
    settings: (scoring, teams, override) triples, default SETTINGS."""
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
            page.on("console", lambda m: errors.append(f"console {m.type}: {m.text}") if m.type == "error" else None)
            page.wait_for_function("() => (window.TradeValueCurveControls && window.TradeValueCurveControls.isReady())"
                                   " || /unavailable/i.test(document.querySelector('#curve-status')?.textContent || '')",
                                   timeout=120000)
            if not page.evaluate("() => !!(window.TradeValueCurveControls && window.TradeValueCurveControls.isReady())"):
                status = page.evaluate("() => document.querySelector('#curve-status')?.textContent || ''")
                raise AssertionError(f"engine page not ready: {status[:300]}; errors: {errors[:3]}")
            for scoring, teams, override in settings or SETTINGS:
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


def annotated(test):
    """Annotate a failing or erroring test's exception (see annotate)."""
    import functools
    import traceback

    @functools.wraps(test)
    def run(self):
        try:
            return test(self)
        except unittest.SkipTest:
            raise
        except BaseException as exc:
            tail = traceback.format_exception(exc)[-3:]
            annotate(f"JEG-1189 {test.__name__}", [f"{type(exc).__name__}: {exc}"[:900], "".join(tail)[-900:]])
            raise
    return run


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

    def test_runs_are_compared_only_within_themselves(self):
        # Same-run invariant (JEG-1253): a second run with its own pie and
        # weights (another week view, or a loaded league's market bench level
        # beside its DDF level) passes on its own budgets. Its totals differ
        # from the first run's and that is not a problem.
        ddf, market = _synthetic(), _synthetic()
        market["pie"] = 120.0
        for pos in POSITIONS:
            market["ddfWeights"][f"{pos}|bench"] = 0.15
        market["ddfWeights"] = dict(market["ddfWeights"])
        for src in market["sources"].values():
            src["rates"] = {g: r * 120.0 * 0.15 / 12.5 for g, r in src["rates"].items()}
        problems, compared, _ = check_runs([("ddf level", ddf), ("market level", market)])
        self.assertEqual(problems, [])
        self.assertEqual(set(compared), {"ddf level", "market level"})
        self.assertNotAlmostEqual(bench_totals(ddf["sources"]["a"])["QB"], bench_totals(market["sources"]["a"])["QB"])

    def test_a_source_from_another_run_fails_on_this_runs_budget(self):
        # Why a lagging chart is read in its own week's view: priced against
        # another run's budget it is off that budget.
        run, other = _synthetic(), _synthetic()
        for src in other["sources"].values():
            src["rates"] = {g: r * 1.2 for g, r in src["rates"].items()}
        run["sources"]["lag"] = other["sources"]["a"]
        problems, _, _ = check_run(run, "syn")
        self.assertTrue(any(" lag QB " in p for p in problems), problems)


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
                    out = run_engine(model=model, variant=variant)
                    problems, _, _ = check_run(from_driver(out), str(variant))
                    self.assertTrue(any(" c2 " in p for p in problems),
                                    f"a 1% bench-to-starter shift in c2 was NOT caught: {problems}")
                    # Only the perturbed source is off its budget.
                    off = {p.split(": ", 1)[1].split(" ", 1)[0] for p in problems if "differs" not in p}
                    self.assertEqual(off, {"c2"}, problems)
                    # The shift keeps c2's total on the pie, so the page's
                    # fixedPieIndexed guard cannot see it; only this check does.
                    total = sum(p["adjusted"] for p in out["sources"]["c2"]["players"].values())
                    self.assertAlmostEqual(total, out["pie"], delta=REL_TOL * out["pie"])


class TransitionReferenceTest(unittest.TestCase):
    """Deterministic lagging-week coverage (JEG-1253; JEG-1189 left it as
    "claimed, not confirmed" because the served data had no transition).
    Runs in test-core with no browser: the Python reference prices the replay
    in each week view, as the page does (no carry-forward, JEG-1177)."""

    SETTINGS = [("ppr", 12, None), ("ppr", 12, 0.10)]  # the replay rewrites the 12-team combos

    @classmethod
    def setUpClass(cls):
        cls.runs, cls.views, cls.priced = [], {}, {}
        with transition_reference() as (R, inp, hist, lagging, newest, _):
            cls.lagging, cls.newest = lagging, newest
            for scoring, teams, override in cls.SETTINGS:
                setting = f"{scoring}/{teams}" + (f"/bench{override:.0%}" if override is not None else "")
                view = R.Setting(inp, scoring, teams, hist=hist, bench_share_override=override).week_view()
                cls.views[setting] = view
                for week in (view or {}).get("weeks") or []:
                    res = R.Setting(inp, scoring, teams, hist=hist, bench_share_override=override,
                                    week=week).result()
                    label = f"{setting} week {week}"
                    run = from_reference(res)
                    cls.runs.append((label, run))
                    cls.priced[label] = sorted(k for k, s in run["sources"].items() if s["weights"])

    def test_the_replay_is_a_transition(self):
        # Guards the sentinel: two views, the lagging charts serve the older
        # one and are left out of the newer one.
        for setting, view in self.views.items():
            self.assertEqual(view["weeks"], [self.newest, self.newest - 1], setting)
            self.assertEqual({k: view["served_weeks"].get(k) for k in self.lagging},
                             {k: self.newest - 1 for k in self.lagging}, setting)
            newer, older = f"{setting} week {self.newest}", f"{setting} week {self.newest - 1}"
            self.assertEqual(set(self.lagging) & set(self.priced[newer]), set(), self.priced[newer])
            self.assertTrue(set(self.lagging) <= set(self.priced[older]), self.priced[older])

    def test_budget_cut_bench_identical_in_each_week_view(self):
        problems, compared, notes = check_runs(self.runs)
        if notes:
            print("\n".join(["", *notes]), file=sys.stderr)
        self.assertEqual(len(compared), 2 * len(self.SETTINGS))
        for label, keys in compared.items():
            self.assertGreaterEqual(len(keys), 5, (label, keys))
        self.assertEqual(problems, [], "\n".join(problems[:25]))

    def test_a_lagging_chart_bench_shift_fails_in_its_own_view(self):
        # Mutation: the lagging chart's QB bench rate cut 1% (the bench check
        # reads only the bench side). Only its own week's view prices it, so
        # only that view may fail, naming it.
        source = self.lagging[0]
        broken = []
        for label, run in self.runs:
            run = json.loads(json.dumps(run))
            src = run["sources"][source]
            if src["weights"]:
                src["rates"]["QB|bench"] = (src["rates"].get("QB|bench") or 0.0) * (1 - SHIFT)
            broken.append((label, run))
        problems, _, _ = check_runs(broken)
        self.assertTrue(problems, f"a {SHIFT:.0%} QB bench shift in lagging {source} was NOT caught")
        self.assertTrue(all(f" {source} " in p or "differs across sources" in p for p in problems), problems)
        self.assertEqual({p.split(" week ", 1)[1].split(":", 1)[0] for p in problems}, {str(self.newest - 1)},
                         problems)


class ServedTransitionTest(unittest.TestCase):
    """The served page on the same transition replay: both week views, and a
    lagging chart's mutation (guard off) caught in its own week's view."""

    SETTINGS = [("ppr", 12, None)]

    @classmethod
    def setUpClass(cls):
        _render_env.ensure_built()
        with transition_reference() as (_R, _inp, _hist, lagging, newest, overrides):
            cls.lagging, cls.newest = lagging, newest
            cls.overrides = {k: v.encode("utf-8") for k, v in overrides.items()}
        try:
            cls.runs, cls.notes = page_runs(cls.overrides, cls.SETTINGS)
        except unittest.SkipTest:
            raise
        except Exception as exc:
            annotate("JEG-1253 bench budget cut transition", [f"served page could not be read: {exc!r}"[:600]])
            raise

    @annotated
    def test_both_week_views_pass_and_lagging_charts_are_compared(self):
        problems, compared, notes = check_runs(self.runs)
        annotate("JEG-1253 bench budget cut transition", self.notes + notes + [
            f"{k}: {', '.join(v)}" for k, v in compared.items()], level="notice")
        self.assertEqual(sorted(compared), sorted(f"ppr/12 week {w}" for w in (self.newest, self.newest - 1)),
                         compared)
        self.assertEqual(set(self.lagging) & set(compared[f"ppr/12 week {self.newest}"]), set(), compared)
        self.assertTrue(set(self.lagging) <= set(compared[f"ppr/12 week {self.newest - 1}"]), compared)
        self.assertEqual(problems, [], "\n".join(problems[:25]))

    @annotated
    def test_a_lagging_chart_mutation_fails_in_its_own_view(self):
        source = self.lagging[0]
        runs, _ = page_runs({**self.overrides,
                             "assets/value-model.js": perturbed_model(source).encode("utf-8"),
                             "assets/curve-widget.js": guard_off_widget().encode("utf-8")}, self.SETTINGS)
        broken, _, _ = check_runs(runs)
        mine = [p for p in broken if f" {source} " in p]
        self.assertTrue(mine, f"a {SHIFT:.0%} bench-to-starter shift in lagging {source} was NOT caught: {broken[:5]}")
        self.assertTrue(all(f"week {self.newest - 1}:" in p for p in mine), mine)


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

    @annotated
    def test_budget_cut_bench_identical_in_every_week_view(self):
        problems, compared, notes = check_runs(self.runs)
        annotate("JEG-1189 bench budget cut", self.lagging + notes, level="notice")
        if problems:
            annotate("JEG-1189 bench budget cut", problems)
        annotate("JEG-1189 bench budget cut", [f"{len(compared)} runs: "
                 + "; ".join(f"{k}: {', '.join(v)}" for k, v in compared.items())], level="notice")
        self.assertGreaterEqual(len(compared), len(SETTINGS))
        self.assertEqual(problems, [], "\n".join(problems[:25]))

    @annotated
    def test_perturbed_source_budget_fails_on_the_page(self):
        problems, compared, _ = check_runs(self.runs)
        first = next((label for label, run in self.runs if not run.get("error")), None)
        self.assertIsNotNone(first, "no clean run to pick a source from")
        source = compared[first][0]
        runs, _ = page_runs({"assets/value-model.js": perturbed_model(source).encode("utf-8"),
                             "assets/curve-widget.js": guard_off_widget().encode("utf-8")})
        broken, _, _ = check_runs(runs)
        if not any(f" {source} " in p for p in broken):
            annotate("JEG-1189 bench budget cut mutation", [f"{source} {SHIFT:.0%} shift not caught"] + broken)
        print(f"\n[bench budget cut mutation] {source} {SHIFT:.0%} of bench budget to starter: {len(broken)} problems, "
              f"e.g. {broken[:1]}", file=sys.stderr)
        self.assertTrue(any(f" {source} " in p for p in broken),
                        f"a 1% bench-to-starter shift in {source} was NOT caught: {broken[:5]}")


if __name__ == "__main__":
    unittest.main()
