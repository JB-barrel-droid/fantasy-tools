"""Week history (docs/v2-design-notes.md "Back-end contract: history").

Three guards, each run against a simulated broken state as well as the real
one:

1. Schema + no-relabel (hermetic). Every committed data/history/week-<N>.json
   validates, and the validator refuses: a Week 4 file carrying Week 3 content
   (an entry moved between files, an entry relabelled, a pull whose content
   date is another week, a FantasyCalc pull made in a later week), a wrong
   fingerprint, a non-numeric native.
2. Append-only (hermetic). A frozen week keeps its entry when a different
   candidate for the same source and week arrives; the open week takes the
   newer one.
3. Δ recompute (browser, built dist/). With the reader at Full PPR, 12 teams,
   standard roster:
   * the engine's prior-week values for FantasyCalc (Week 4, the week before
     the Week 5 it serves) and CBS (Week 3, before its Week 4) equal an
     independent price of the saved natives by the Python translation the
     chain promotes with (pipelines/vorp_translation/unified.translate_natives,
     same peers), player for player; the known player (Bijan Robinson) has
     a prior value equal to that independent price, and Δ = current - prior
     (Week 4 -> 5 FantasyCalc, Week 3 -> 4 CBS) is printed;
   * feeding each source's SERVED saved week back through getWeekValues
     reproduces the chart's current values exactly at a non-default setting
     (10 teams, Half PPR, an extra bench spot), so the accessor is the
     engine's own math and not a second model.
   Discrimination (test_delta_guard_fails_on_broken_states): the same checks
   fail when the Week 4 file is served relabelled as Week 3, when the
   accessor substitutes the served (current) natives for the saved week, and
   when getPriorWeek pairs the served week with itself.
"""
from __future__ import annotations

import contextlib
import copy
import functools
import http.server
import json
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_week_history as H  # noqa: E402

HISTORY = ROOT / "data" / "history"
DIST = ROOT / "dist"
WIDGET = ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js"
BIJAN = 217
DELTAS = {}  # source -> Bijan Robinson Δ at Full PPR / 12 (printed by the test)


def _week(n):
    return json.loads((HISTORY / f"week-{n}.json").read_text())


class WeekFileSchemaTest(unittest.TestCase):
    def test_committed_weeks_validate(self):
        docs = H.load_weeks(HISTORY)
        self.assertTrue({2, 3, 4, 5} <= set(docs), sorted(docs))
        for week in (3, 4):
            self.assertTrue(docs[week]["frozen"], f"week {week} should be frozen")
            for source in ("usatoday", "fantasycalc", "fantasypros", "cbs"):
                entry = docs[week]["sources"][source]
                self.assertTrue(entry["complete"], f"{source} week {week} incomplete")
                self.assertEqual(set(entry["natives"]), set(H.SCORINGS))

    def test_week_four_file_cannot_carry_week_three(self):
        w3, w4 = _week(3), _week(4)
        H.validate_week_doc(w4, 4)
        # Week 3 FantasyCalc content placed in the Week 4 file.
        moved = copy.deepcopy(w4)
        moved["sources"]["fantasycalc"] = copy.deepcopy(w3["sources"]["fantasycalc"])
        with self.assertRaises(H.HistoryError):
            H.validate_week_doc(moved, 4)
        # The same content relabelled week 4.
        moved["sources"]["fantasycalc"]["week"] = 4
        with self.assertRaises(H.HistoryError):
            H.validate_week_doc(moved, 4)
        # USA Today's content date moved into Week 3 under a Week 4 label.
        relabel = copy.deepcopy(w4)
        relabel["sources"]["usatoday"]["week_evidence"]["content_date"] = "2026-09-23"
        with self.assertRaises(H.HistoryError):
            H.validate_week_doc(relabel, 4)
        # A whole Week 3 document saved as week-4.json.
        with self.assertRaises(H.HistoryError):
            H.validate_week_doc(w3, 4)

    def test_rows_are_dated_by_content_not_label(self):
        base = {"season": 2026, "scoring": "full", "player_key": 217, "native_value": 70.0,
                "bake_id": None}
        ok = [dict(base, source="usatoday", week=3, source_content_date="2026-09-23",
                   pulled_at="2026-10-01 00:00:00+00")]
        self.assertEqual(H.published_entries_from_rows(ok)[0]["week"], 3)
        wrong = [dict(base, source="usatoday", week=4, source_content_date="2026-09-23",
                      pulled_at="2026-10-01 00:00:00+00")]
        with self.assertRaises(H.HistoryError):
            H.published_entries_from_rows(wrong)
        late_fc = [dict(base, source="fantasycalc", week=4, source_content_date=None,
                        pulled_at="2026-10-06 14:20:24+00")]
        with self.assertRaises(H.HistoryError):
            H.published_entries_from_rows(late_fc)
        early_cbs = [dict(base, source="cbs", week=4, source_content_date=None,
                          pulled_at="2026-09-25 22:23:54+00")]
        with self.assertRaises(H.HistoryError):
            H.published_entries_from_rows(early_cbs)

    def test_fingerprint_and_values_are_checked(self):
        w4 = _week(4)
        tampered = copy.deepcopy(w4)
        cells = tampered["sources"]["cbs"]["natives"]["ppr"]
        first = next(iter(cells))
        cells[first] = cells[first] + 1
        with self.assertRaises(H.HistoryError):
            H.validate_week_doc(tampered, 4)
        bad = copy.deepcopy(w4)
        bad["sources"]["cbs"]["natives"]["ppr"][first] = "9"
        bad["sources"]["cbs"]["fingerprint"] = "x"
        with self.assertRaises(H.HistoryError):
            H.validate_week_doc(bad, 4)

    def test_served_copy_matches_store(self):
        served = DIST / "assets" / "history"
        if not served.exists():
            self.skipTest("dist/ not built")
        for path in HISTORY.glob("week-*.json"):
            self.assertEqual((served / path.name).read_bytes(), path.read_bytes(), path.name)
        index = json.loads((served / "index.json").read_text())
        fixture = json.loads((ROOT / "data/fixtures/current/comparison-sources-data.json").read_text())
        self.assertEqual(index["fixture_built_at"], fixture["built_at"])


class AppendOnlyTest(unittest.TestCase):
    def _candidate(self, week, value, pulled):
        return {"source": "fantasycalc", "kind": "published_chart", "week": week,
                "week_evidence": {"rule": "week_column_pull", "week_column": week, "pulled_at": pulled},
                "origin": "test", "pulled_at": pulled, "bake_ids": [], "complete": True,
                "natives": {s: {"217": value} for s in H.SCORINGS}, "sort_key": [pulled, 1]}

    def test_frozen_week_keeps_its_entry(self):
        docs = H.merge({}, [self._candidate(4, 100.0, "2026-10-01 00:00:00+00")], content_week=5, log=lambda *_: None)
        self.assertTrue(docs[4]["frozen"])
        before = docs[4]["sources"]["fantasycalc"]["fingerprint"]
        docs = H.merge(docs, [self._candidate(4, 999.0, "2026-10-05 00:00:00+00")], content_week=5, log=lambda *_: None)
        self.assertEqual(docs[4]["sources"]["fantasycalc"]["fingerprint"], before)
        self.assertEqual(docs[4]["sources"]["fantasycalc"]["natives"]["ppr"]["217"], 100.0)
        H.validate_week_doc(docs[4], 4)

    def _projection(self, values, snapshot="2026-10-02"):
        return H.projection_entry("cbsros", {"217": values}, snapshot, "test", "players.json")

    def test_frozen_projection_rebases_only_to_finer_same_content(self):
        quiet = lambda *_: None
        docs = H.merge({}, [self._projection([17.53, 19.67, 21.81])], content_week=5, log=quiet)
        self.assertTrue(docs[4]["frozen"])
        # The same 10-02 content at bake_players' finer precision replaces it,
        # so the served week stays matched after a precision change.
        docs = H.merge(docs, [self._projection([17.529, 19.671, 21.814])], content_week=5, log=quiet)
        self.assertEqual(docs[4]["sources"]["cbsros"]["ppg"]["217"], [17.529, 19.671, 21.814])
        # Different content (a value that does not round to the saved one, or
        # another snapshot date) never replaces a frozen entry.
        for cand in (self._projection([17.6011, 19.671, 21.814]),
                     self._projection([17.5291, 19.6711, 21.8141], snapshot="2026-10-01")):
            before = copy.deepcopy(docs[4]["sources"]["cbsros"])
            docs = H.merge(docs, [cand], content_week=5, log=quiet)
            self.assertEqual(docs[4]["sources"]["cbsros"]["ppg"], before["ppg"])
        # Coarser values are not "finer".
        docs = H.merge(docs, [self._projection([17.53, 19.67, 21.81])], content_week=5, log=quiet)
        self.assertEqual(docs[4]["sources"]["cbsros"]["ppg"]["217"], [17.529, 19.671, 21.814])
        H.validate_week_doc(docs[4], 4)

    def test_open_week_takes_the_newer_pull(self):
        docs = H.merge({}, [self._candidate(5, 100.0, "2026-10-06 00:00:00+00")], content_week=5, log=lambda *_: None)
        self.assertFalse(docs[5]["frozen"])
        docs = H.merge(docs, [self._candidate(5, 120.0, "2026-10-07 00:00:00+00")], content_week=5, log=lambda *_: None)
        self.assertEqual(docs[5]["sources"]["fantasycalc"]["natives"]["ppr"]["217"], 120.0)
        docs = H.merge(docs, [self._candidate(5, 90.0, "2026-10-05 00:00:00+00")], content_week=5, log=lambda *_: None)
        self.assertEqual(docs[5]["sources"]["fantasycalc"]["natives"]["ppr"]["217"], 120.0)


class WeekSnapshotRuleTest(unittest.TestCase):
    """The week-over-week rule (docs/v2-design-notes.md "Which snapshot is a
    source's week") and HISTORY-WEEK-CAPTURE: one snapshot per source and
    week, every other version kept, never lost."""
    quiet = staticmethod(lambda *_: None)

    def _chart(self, source, week, value, pulled, content_date=None):
        if content_date:
            ev = {"rule": "content_date", "content_date": content_date, "week_column": week, "pulled_at": pulled}
        elif source == "cbs":
            ev = {"rule": "week_column_article", "week_column": week, "pulled_at": pulled}
        else:
            ev = {"rule": "week_column_pull", "week_column": week, "pulled_at": pulled}
        return {"source": source, "kind": "published_chart", "week": week, "week_evidence": ev,
                "origin": f"test {pulled}", "pulled_at": pulled, "bake_ids": [], "complete": True,
                "natives": {s: {"217": value} for s in H.SCORINGS}, "sort_key": [pulled, 1]}

    def test_fantasycalc_takes_the_first_pull_after_the_tuesday_cut(self):
        # Week 5 cut = Tue 2026-10-06 12:00 UTC. Hourly pulls around it, in any order.
        pulls = ["2026-10-06 03:00:00+00", "2026-10-06 11:59:00+00", "2026-10-06 12:05:00+00",
                 "2026-10-06 13:00:00+00", "2026-10-08 09:00:00+00"]
        for order in (pulls, list(reversed(pulls))):
            sup = {}
            docs = H.merge({}, [self._chart("fantasycalc", 5, 100.0 + i, p) for i, p in
                                enumerate(order)], content_week=5, log=self.quiet, superseded=sup)
            entry = docs[5]["sources"]["fantasycalc"]
            self.assertEqual(entry["pulled_at"], "2026-10-06 12:05:00+00")
            self.assertEqual(entry["cut"], "after")
            self.assertEqual(len(sup[5]["versions"]["fantasycalc"]), 4)  # the rest are kept
        # No pull after the cut in the week: the week's latest, flagged.
        docs = H.merge({}, [self._chart("fantasycalc", 5, 1.0, "2026-10-06 03:00:00+00"),
                            self._chart("fantasycalc", 5, 2.0, "2026-10-06 11:00:00+00")],
                       content_week=5, log=self.quiet)
        self.assertEqual(docs[5]["sources"]["fantasycalc"]["pulled_at"], "2026-10-06 11:00:00+00")
        self.assertEqual(docs[5]["sources"]["fantasycalc"]["cut"], "missed")

    def test_article_revision_keeps_both_and_frozen_week_never_swaps(self):
        sup = {}
        first = self._chart("usatoday", 4, 66.0, "2026-09-29 00:00:00+00", "2026-09-29")
        revised = self._chart("usatoday", 4, 68.0, "2026-10-02 00:00:00+00", "2026-09-29")
        docs = H.merge({}, [first], content_week=4, log=self.quiet, superseded=sup)
        docs = H.merge(docs, [revised], content_week=4, log=self.quiet, superseded=sup)
        self.assertEqual(docs[4]["sources"]["usatoday"]["natives"]["ppr"]["217"], 68.0)  # latest revision
        self.assertEqual([v["natives"]["ppr"]["217"] for v in sup[4]["versions"]["usatoday"]], [66.0])
        # Week 5 opens and the first capture freezes week 4; a Week-4 revision
        # saved after that is kept, not swapped in.
        docs = H.merge(docs, [], content_week=5, log=self.quiet, superseded=sup)
        late = self._chart("usatoday", 4, 70.0, "2026-10-07 00:00:00+00", "2026-09-29")
        docs = H.merge(docs, [late], content_week=5, log=self.quiet, superseded=sup)
        self.assertTrue(docs[4]["frozen"])
        self.assertEqual(docs[4]["sources"]["usatoday"]["natives"]["ppr"]["217"], 68.0)
        self.assertEqual(sorted(v["natives"]["ppr"]["217"] for v in sup[4]["versions"]["usatoday"]), [66.0, 70.0])
        # Superseded files go through the same no-relabel guard.
        with tempfile.TemporaryDirectory() as tmp:
            H.write_superseded(sup, Path(tmp))
            self.assertEqual(set(H.load_superseded(Path(tmp))), {4})
            self.assertEqual(sorted(p.name for p in Path(tmp).glob("week-*.json")), [])  # not served
            bad = json.loads((Path(tmp) / "superseded" / "week-4.json").read_text())
            bad["versions"]["usatoday"][0]["week_evidence"]["content_date"] = "2026-09-23"
            with self.assertRaises(H.HistoryError):
                H.validate_superseded_doc(bad, 4)

    def test_every_bake_is_a_version_and_overwrite_leftovers_are_not(self):
        base = {"season": 2026, "scoring": "ppr", "source_content_date": "2026-09-29", "week": 4,
                "source": "usatoday"}
        rows = [dict(base, player_key=217, native_value=66.0, pulled_at="2026-09-29 00:00:00+00", bake_id="b1"),
                dict(base, player_key=1, native_value=5.0, pulled_at="2026-09-29 00:00:00+00", bake_id="b1"),
                dict(base, player_key=217, native_value=68.0, pulled_at="2026-10-02 00:00:00+00", bake_id="b2"),
                # b2 overwritten in place on 10-03: player 1 dropped, left behind at 10-02.
                dict(base, player_key=1, native_value=4.0, pulled_at="2026-10-02 00:00:00+00", bake_id="b3"),
                dict(base, player_key=217, native_value=69.0, pulled_at="2026-10-03 00:00:00+00", bake_id="b3")]
        entries = H.published_entries_from_rows(rows)
        got = sorted((e["bake_ids"][0], sorted(e["natives"]["ppr"].items())) for e in entries)
        self.assertEqual(got, [("b1", [("1", 5.0), ("217", 66.0)]), ("b2", [("217", 68.0)]),
                               ("b3", [("217", 69.0)])])

    def test_index_matches_a_served_superseded_version(self):
        sup = {}
        older = self._chart("usatoday", 5, 60.0, "2026-10-06 00:00:00+00", "2026-10-06")
        newer = self._chart("usatoday", 5, 62.0, "2026-10-07 00:00:00+00", "2026-10-06")
        docs = H.merge({}, [older, newer], content_week=5, log=self.quiet, superseded=sup)
        fixture = {"player_keys": {"bijan": 217}, "sources": {"usatoday": {"week_designated": "Week 5", "combos": {
            c: {"native": {"bijan": 60.0}} for c in H.FIXTURE_COMBO.values()}}}}
        index = H.build_index(docs, fixture, {"players": [], "meta": {}}, 5, sup)
        self.assertEqual(index["served"]["usatoday"]["week"], 5)
        self.assertEqual(index["served"]["usatoday"]["version"], "superseded")
        # Without the kept versions (the old behaviour) the served week is lost.
        self.assertIsNone(H.build_index(docs, fixture, {"players": [], "meta": {}}, 5)["served"]["usatoday"]["week"])


# ------------------------------------------------------------------ browser

READY = "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()"
PRIOR = """async () => {
  const c = window.TradeValueCurveControls;
  c.setScoring('ppr'); c.setTeams(12);
  const out = {};
  for (const k of ['usatoday', 'fantasycalc', 'fantasypros', 'cbs']) {
    const prior = await c.getPriorWeek(k);
    const row = c.getAllRows().find(r => r.player_key === 217);
    out[k] = {prior, current: row ? row.values[k] : null};
  }
  return out;
}"""
SELF = """async () => {
  const c = window.TradeValueCurveControls;
  c.setScoring('half'); c.setTeams(10); c.setRosterSpot('BENCH', c.getRosterShape().BENCH + 1);
  const index = await (await fetch('assets/history/index.json')).json();
  const rows = c.getAllRows();
  const out = {};
  for (const k of ['usatoday', 'fantasycalc', 'fantasypros', 'cbs', 'cbsros', 'razzball']) {
    const week = index.served[k].week;
    const r = await c.getWeekValues(k, week);
    const errors = [];
    if (!r.available) { out[k] = [`week ${week}: ${r.reason}`]; continue; }
    rows.forEach(row => {
      const v = row.values[k];
      const p = r.values[row.player_key];
      if (v == null && p == null) return;
      if (v == null || p == null || Math.abs(v - p) > 1e-9) errors.push(`${row.name}: chart ${v}, week ${week} ${p}`);
    });
    out[k] = errors;
  }
  return out;
}"""


def _python_prior(source, week):
    """Independent price of a saved week at Full PPR / 12 / standard roster."""
    from vorp_translation import unified as U
    fixture = json.loads((ROOT / "data/fixtures/current/comparison-sources-data.json").read_text())
    slug_of = {v: k for k, v in fixture["player_keys"].items()}
    natives = _week(week)["sources"][source]["natives"]["ppr"]
    slugged = {slug_of[int(k)]: v for k, v in natives.items() if int(k) in slug_of}
    result = U.translate_natives(slugged, 12, peers=U.peer_natives(fixture, source, "ppr"))
    return {int(k): result["translated"].get(k, 0.0) for k in result["evaluated"]}


@contextlib.contextmanager
def _server(overrides):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = self.path.split("?")[0].lstrip("/")
            body = overrides.get(path)
            if body is not None:
                data = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json" if path.endswith(".json") else "text/javascript")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            super().do_GET()

    handler = functools.partial(Handler, directory=str(DIST))
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/classic/"
        finally:
            server.shutdown()


def collect(overrides=None):
    """Failures of the Δ checks against the built dist/ (with optional
    served-file overrides that simulate a broken state)."""
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except Exception as exc:
        raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc
    if not (DIST / "assets" / "history" / "index.json").exists():
        raise unittest.SkipTest("dist/ is not built with history")
    # Every published chart whose week before the served one is saved (on
    # 2026-10-08: USA Today / FantasyCalc / FantasyPros Week 4, CBS Week 3).
    index = json.loads((DIST / "assets" / "history" / "index.json").read_text())
    expected = {}
    for source in H.PUBLISHED:
        served = index["served"][source]["week"]
        if served and source in (index["weeks"].get(str(served - 1)) or {}).get("sources", {}):
            expected[source] = (served - 1, _python_prior(source, served - 1))
    failures = [] if expected else ["no published chart has a saved prior week"]
    with _server(overrides or {}) as url, sync_playwright() as playwright:
        exe = None
        for cand in (Path(playwright.chromium.executable_path),
                     Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")):
            if cand.exists():
                exe = str(cand)
                break
        try:
            browser = playwright.chromium.launch(executable_path=exe)
        except PlaywrightError as exc:
            raise unittest.SkipTest(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            page.goto(url, wait_until="networkidle", timeout=120000)
            page.wait_for_function(READY, timeout=30000)
            prior = page.evaluate(PRIOR)
            for source, (week, want) in expected.items():
                got = prior[source]["prior"]
                if not got.get("available"):
                    failures.append(f"{source}: prior week unavailable ({got.get('reason')})")
                    continue
                if got.get("priorWeek") != week or got.get("week") != week:
                    failures.append(f"{source}: prior week {got.get('priorWeek')}, want {week}")
                values = {int(k): v for k, v in got["values"].items()}
                if set(values) != set(want):
                    failures.append(f"{source}: {len(set(want) ^ set(values))} players differ from the saved week")
                bad = [k for k in want if k in values and abs(values[k] - want[k]) > 1e-9]
                if bad:
                    failures.append(f"{source}: {len(bad)} prior values differ from the Python price, "
                                    f"e.g. {bad[0]}: {values[bad[0]]} vs {want[bad[0]]}")
                # The known player: Δ is the chart's current value minus the
                # saved week priced at the same setting.
                current = prior[source]["current"]
                if BIJAN not in values or current is None:
                    failures.append(f"{source}: Bijan Robinson missing (prior {values.get(BIJAN)}, current {current})")
                elif abs(values[BIJAN] - want[BIJAN]) > 1e-9:
                    failures.append(f"{source}: Bijan prior {values[BIJAN]}, Python {want[BIJAN]}")
                else:
                    DELTAS[source] = round(current - values[BIJAN], 1)
            for source, errs in page.evaluate(SELF).items():
                if errs:
                    failures.append(f"{source} served week != chart: {errs[:2]} ({len(errs)} players)")
            failures += [f"page error: {e}" for e in errors]
            page.close()
        finally:
            browser.close()
    return failures


class DeltaRecomputeTest(unittest.TestCase):
    def test_prior_week_is_engine_math_on_saved_inputs(self):
        self.assertEqual(collect(), [])
        print(f"Bijan Robinson Δ (Full PPR, 12 teams): {DELTAS}")

    def test_delta_guard_fails_on_broken_states(self):
        widget = WIDGET.read_text()
        relabelled = _week(3)
        relabelled_doc = json.dumps(dict(_week(4), week=3))
        substitute = widget.replace("const native = historyNatives(entry);",
                                    "const native = savedPublishedNative(source);")
        self.assertNotEqual(substitute, widget)
        same_week = widget.replace("const prior = served.week - 1;", "const prior = served.week;")
        self.assertNotEqual(same_week, widget)
        cases = {
            "week-4 file served relabelled as week 3": {"assets/history/week-4.json": relabelled_doc},
            "week-4 file served with week-3 content": {"assets/history/week-4.json": json.dumps(dict(relabelled, week=4))},
            "accessor substitutes the served natives": {"assets/curve-widget.js": substitute},
            "prior paired with the served week": {"assets/curve-widget.js": same_week},
        }
        for name, overrides in cases.items():
            with self.subTest(name):
                self.assertNotEqual(collect(overrides), [], f"{name} was not caught")


if __name__ == "__main__":
    unittest.main()
