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
     independent price of the saved natives: Indexed is the natives times one
     factor against the page's live anchor (JEG-482; tests/
     test_published_league_settings_engine.one_factor), player for player;
     the known player (Bijan Robinson) has
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
   * JEG-714: every saved week in the index (not only the served/prior pair)
     loads through getWeekValues under its own label, and a published chart's
     week prices the store's natives for that week times one factor, so a
     mislabelled week file is caught whichever week the charts serve.

JEG-508 (docs/methodology.md "Value Pipeline", VP-6.4 / VP-8 / VP-10): a
saved week is one value-pipeline run on that week's inputs (same league,
included set and pie). The independent check of a chart's prior Indexed
values is now that they are the saved week's natives times ONE factor (the
factor is set against that week's blended DDF Value, which value_check
verifies against the Python reference); the anchor-based price, the ESPN
prior leg (espn_legs_for_week) and the ESPN/VORP/list-order mutations are
retired with the anchor and the two-tier leg.
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
from tests._dist_server import engine_path  # noqa: E402
from tests._holds import with_pinned_holds  # noqa: E402
from tests import _render_env  # noqa: E402
from tests._week_view import has_view, lagging_week, note_lagging  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


HISTORY = ROOT / "data" / "history"
DIST = ROOT / "dist"
WIDGET = ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js"
BIJAN = 217
DELTAS = {}  # source -> Bijan Robinson Δ at Full PPR / 12 (printed by the test)
ZERO_ONLY = {}  # series -> players priced 0.0 on one side only (printed)
UNMATCHED = {}  # base source -> why its served inputs match no saved week (warned)
WEEK_STATE = {}  # the default week view the page resolved (JEG-1177; getWeekState)
FIXTURE_ASSET = "assets/comparison-sources-data.json"


def _fixture_today(fixture=None):
    """A date in the content week of the served data.  Tests pin
    window.TRADE_VALUE_TODAY to this so the page's content-week clock matches
    the data it serves -- otherwise the real clock (or a built_at that lands
    in a newer week than the data) breaks eligibility (JEG-675, JEG-787,
    JEG-791).

    When the chain builds in week N+1 but the published charts are still week
    N, built_at is in week N+1 while the data is week N.  The pin must be in
    the data's own week so the page never claims a newer week than exists."""
    from nfl_week import content_week_start, section_content_week, content_week
    from datetime import date as _date
    if fixture is None:
        fixture = json.loads((DIST / FIXTURE_ASSET).read_text(encoding="utf-8"))
    built_at = fixture["built_at"][:10]
    # The data's content week is the max content week of the fixture's source
    # sections (what the page would label each source).
    data_weeks = [w for s in (fixture.get("sources") or {}).values()
                  if (w := section_content_week(s)) is not None]
    if not data_weeks:
        return built_at
    data_week = max(data_weeks)
    build_week = content_week(_date.fromisoformat(built_at))
    if build_week <= data_week:
        return built_at  # built_at is in (or before) the data's week: use it
    # built_at is in a newer week: pin to the last day of the data's week
    # (the Monday before the next Tuesday flip).
    next_week_start = content_week_start(data_week + 1)
    return (next_week_start - __import__("datetime").timedelta(days=1)).isoformat()


def _week(n):
    return json.loads((HISTORY / f"week-{n}.json").read_text(encoding="utf-8"))


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
            raise _render_env.unavailable("dist/ not built")
        for path in HISTORY.glob("week-*.json"):
            self.assertEqual((served / path.name).read_bytes(), path.read_bytes(), path.name)
        index = json.loads((served / "index.json").read_text(encoding="utf-8"))
        fixture = json.loads((ROOT / "data/fixtures/current/comparison-sources-data.json").read_text(encoding="utf-8"))
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
            bad = json.loads((Path(tmp) / "superseded" / "week-4.json").read_text(encoding="utf-8"))
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

    def test_cbs_rows_before_and_after_the_bake_migration_are_one_version(self):
        # Before cbs_bakes_source_urls_20261008: bake_id NULL and the week
        # overwritten in place (leftover rows keep the older pulled_at). After
        # it: the same rows labelled cbswk5_legacy. Same content either way.
        base = {"season": 2026, "scoring": "ppr", "source_content_date": None, "week": 5, "source": "cbs"}
        rows = [dict(base, player_key=217, native_value=47.0, pulled_at="2026-10-08T11:36:55+00:00"),
                dict(base, player_key=1, native_value=3.0, pulled_at="2026-10-08T11:36:55+00:00"),
                dict(base, player_key=9, native_value=1.0, pulled_at="2026-10-06T11:00:00+00:00")]  # leftover
        before = H.published_entries_from_rows([dict(r, bake_id=None) for r in rows])
        after = H.published_entries_from_rows([dict(r, bake_id="cbswk5_legacy") for r in rows])
        self.assertEqual(len(before), 1)
        self.assertEqual(sorted(before[0]["natives"]["ppr"]), ["1", "217"])
        self.assertEqual(H.fingerprint(before[0]), H.fingerprint(after[0]))

    def test_served_match_ignores_players_outside_the_page_universe(self):
        # CBS Week 5 (2026-10-08) saved Tyreek Hill (3081), whom the page's
        # universe lacks; the served section is the same content without him.
        saved = self._chart("cbs", 5, 47.0, "2026-10-08 11:36:55+00")
        for sc in H.SCORINGS:
            saved["natives"][sc]["3081"] = 7.0
        docs = H.merge({}, [saved], content_week=5, log=self.quiet)
        fixture = {"player_keys": {"bijan": 217}, "sources": {"cbs": {"week_designated": "Week 5", "combos": {
            c: {"native": {"bijan": 47.0}} for c in H.FIXTURE_COMBO.values()}}}}
        index = H.build_index(docs, fixture, {"players": [], "meta": {}}, 5)
        self.assertEqual(index["served"]["cbs"]["week"], 5)
        # A real difference among universe players still matches nothing.
        fixture["sources"]["cbs"]["combos"]["full_12"]["native"]["bijan"] = 46.0
        self.assertIsNone(H.build_index(docs, fixture, {"players": [], "meta": {}}, 5)["served"]["cbs"]["week"])

    def _held_cbs(self):
        """Chain run 37877126939 (2026-10-09): the CBS candidate was held
        (review hold), so the page kept the last promoted Week 5 section,
        built when Tyreek Hill (3081) was outside the universe. The same run
        added him to player_keys, so the saved Week 5 now prices a universe
        player the kept section does not carry."""
        saved = self._chart("cbs", 5, 47.0, "2026-10-08 11:36:55+00")
        for sc in H.SCORINGS:
            saved["natives"][sc]["3081"] = 7.0
        docs = H.merge({}, [saved], content_week=5, log=self.quiet)
        fixture = {"player_keys": {"bijan": 217, "tyreek hill": 3081},
                   "sources": {"cbs": {"week_designated": "Week 5", "combos": {
                       c: {"native": {"bijan": 47.0}} for c in H.FIXTURE_COMBO.values()}}}}
        return docs, fixture

    def test_held_section_built_on_an_older_universe_serves_its_kept_week(self):
        docs, fixture = self._held_cbs()
        index = H.build_index(docs, fixture, {"players": [], "meta": {}}, 5)
        rec = index["served"]["cbs"]
        self.assertEqual(rec["week"], 5, rec.get("reason"))
        self.assertEqual(rec["version"], "superseded")  # not the snapshot as saved
        self.assertEqual(rec["served_from"]["dropped_players"], ["3081"])
        self.assertIn("does not carry", rec["note"])
        # make sync serves exactly the kept section's content as "this week".
        with tempfile.TemporaryDirectory() as tmp:
            served = H.write_served_versions(index, {}, Path(tmp) / "served.json", docs)
        entry = served["sources"]["cbs"]
        self.assertEqual(entry["fingerprint"], rec["entry_fingerprint"])
        self.assertEqual(entry["week"], 5)
        for sc in H.SCORINGS:
            self.assertEqual(entry["natives"][sc], {"217": 47.0})
        H.validate_week_doc({"schema": H.SCHEMA, "season": H.SEASON, "week": 5, "frozen": True,
                             "sources": {"cbs": entry}}, 5)

    def test_held_section_with_a_different_value_still_matches_nothing(self):
        docs, fixture = self._held_cbs()
        fixture["sources"]["cbs"]["combos"]["full_12"]["native"]["bijan"] = 46.0
        rec = H.build_index(docs, fixture, {"players": [], "meta": {}}, 5)["served"]["cbs"]
        self.assertIsNone(rec["week"])
        # A served player the saved week lacks is not a subset either.
        docs, fixture = self._held_cbs()
        fixture["player_keys"]["new guy"] = 9999
        for cell in fixture["sources"]["cbs"]["combos"].values():
            cell["native"]["new guy"] = 3.0
        self.assertIsNone(H.build_index(docs, fixture, {"players": [], "meta": {}}, 5)["served"]["cbs"]["week"])

    def test_gate_warns_on_an_unmatched_source_instead_of_crashing(self):
        index = {"served": {"cbs": {"week": None, "reason": "the served inputs match no saved week"},
                            "espn": {"week": 5}}}
        unmatched = {}
        self.assertIsNone(served_week(index, "cbs_adjusted", unmatched))
        self.assertEqual(served_week(index, "espn_vorp", unmatched), 5)
        self.assertEqual(list(unmatched), ["cbs"])
        self.assertIn("match no saved week", unmatched["cbs"])

    def test_two_qb_rows_in_the_same_bake_are_ignored(self):
        # FantasyCalc saves qb_slots=2 rows in the same bake (superflex
        # publisher values); history is the 1-QB natives only.
        base = {"season": 2026, "scoring": "ppr", "source_content_date": None, "week": 5,
                "source": "fantasycalc", "bake_id": "fcwk5_2026-10-08t1259_v1",
                "pulled_at": "2026-10-08T12:59:15+00:00", "league_teams": 12}
        rows = [dict(base, player_key=217, native_value=9000.0, qb_slots=1),
                dict(base, player_key=217, native_value=7000.0, qb_slots=2),
                dict(base, player_key=1, native_value=500.0, qb_slots=2)]
        [entry] = H.published_entries_from_rows(rows)
        self.assertEqual(entry["natives"]["ppr"], {"217": 9000.0})

    def test_served_superseded_version_is_served_for_its_week(self):
        # The chart serves a FantasyCalc pull newer than the week's Tuesday
        # cut: the index names it and make sync serves it (served.json), so
        # "this week" is exactly what the chart shows.
        sup = {}
        cut = self._chart("fantasycalc", 5, 100.0, "2026-10-06 14:20:24+00")
        newer = self._chart("fantasycalc", 5, 104.0, "2026-10-08 12:59:15+00")
        docs = H.merge({}, [cut, newer], content_week=5, log=self.quiet, superseded=sup)
        self.assertEqual(docs[5]["sources"]["fantasycalc"]["natives"]["ppr"]["217"], 100.0)
        fixture = {"player_keys": {"bijan": 217}, "sources": {"fantasycalc": {"week_designated": "Week 5", "combos": {
            c: {"native": {"bijan": 104.0}} for c in H.FIXTURE_COMBO.values()}}}}
        index = H.build_index(docs, fixture, {"players": [], "meta": {}}, 5, sup)
        rec = index["served"]["fantasycalc"]
        self.assertEqual((rec["week"], rec["version"]), (5, "superseded"))
        with tempfile.TemporaryDirectory() as tmp:
            served = H.write_served_versions(index, sup, Path(tmp) / "served.json")
        self.assertEqual(served["sources"]["fantasycalc"]["natives"]["ppr"]["217"], 104.0)

    def test_timestamp_formats_compare_as_times(self):
        # The base tables return ISO 'T' timestamps, the old view a space: a
        # raw string compare ranks any 'T' stamp above any same-day space one.
        later = self._chart("usatoday", 5, 62.0, "2026-10-07 21:00:00+00", "2026-10-06")
        earlier = self._chart("usatoday", 5, 60.0, "2026-10-07T09:00:00+00:00", "2026-10-06")
        docs = H.merge({}, [later, earlier], content_week=5, log=self.quiet)
        self.assertEqual(docs[5]["sources"]["usatoday"]["natives"]["ppr"]["217"], 62.0)

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


class ChainCaptureOrderTest(unittest.TestCase):
    def test_history_is_captured_after_promotion_and_before_the_commit(self):
        # 2026-10-08: CBS Week 5 promoted at 12:11 while the only capture ran
        # before the chain, so the committed index was built against the old
        # fixture. A capture after the chain step must exist.
        text = (ROOT / ".github/workflows/rebuild-chain.yml").read_text(encoding="utf-8")
        names = [line.split("- name:", 1)[1].strip() for line in text.splitlines() if "- name:" in line]
        chain = names.index("Rebuild comparison chain (if fixture stale)")
        commit = names.index("Commit and push if changed")
        after = [i for i, n in enumerate(names) if n.startswith("Capture week history") and chain < i < commit]
        self.assertTrue(after, "no week-history capture between the chain and the commit")


class EspnLegsRetiredTest(unittest.TestCase):
    """GAP-508-DEAD-BAKES (JEG-539): assets/history/espn-legs.json, the prior
    ESPN two-tier legs rebuilt at `make sync`, has no reader since JEG-508
    (the page prices a saved ESPN week from its saved espn_ppg through the
    value pipeline). The bake and its writer are retired."""

    def test_week_history_has_no_espn_leg_writer(self):
        self.assertFalse(hasattr(H, "espn_legs_for_week"))
        self.assertFalse(hasattr(H, "write_espn_legs"))

    def test_sync_does_not_write_espn_legs(self):
        text = (ROOT / "pipelines/sync_dashboard_artifacts.py").read_text(encoding="utf-8")
        self.assertNotIn("espn-legs", text)
        self.assertNotIn("write_espn_legs", text)

    def test_no_page_asset_reads_espn_legs(self):
        assets = ROOT / "app/trade-value-chart"
        readers = [str(p.relative_to(ROOT)) for p in [*assets.glob("assets/*.js"), assets / "index.html"]
                   if "espn-legs" in p.read_text(encoding="utf-8")]
        self.assertEqual(readers, [])


# ------------------------------------------------------------------ browser

READY = "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()"
# JEG-1177: every check runs in the week view of the week the series serves
# (setWeek; null = the default view). During a transition a lagging source is
# priced only in its own week's view, never against the other week's blend.
SET_WEEK = "(c, week) => { if (c.setWeek) c.setWeek(week); }"
PRIOR = """async ([keys, week]) => {
  const c = window.TradeValueCurveControls;
  (""" + SET_WEEK + """)(c, week);
  c.setScoring('ppr'); c.setTeams(12);
  const out = {};
  for (const k of keys) {
    const prior = await c.getPriorWeek(k);
    const row = c.getAllRows().find(r => r.player_key === 217);
    out[k] = {prior, current: row ? row.values[k] : null};
  }
  return out;
}"""
SELF = """async ([keys, week]) => {
  const c = window.TradeValueCurveControls;
  (""" + SET_WEEK + """)(c, week);
  // One extra bench spot over the saved setup, however many week groups run.
  if (window.__selfBench === undefined) window.__selfBench = c.getRosterShape().BENCH + 1;
  c.setScoring('half'); c.setTeams(10); c.setRosterSpot('BENCH', window.__selfBench);
  const index = await (await fetch('assets/history/index.json')).json();
  const rows = c.getAllRows();
  const base = k => k.endsWith('_vorp') ? k.slice(0, -5) : k.endsWith('_adjusted') ? k.replace(/_adjusted$/, '') : k;
  const out = {};
  for (const k of keys) {
    const week = index.served[base(k)].week;
    const r = await c.getWeekValues(k, week);
    const errors = [], zeroOnly = [];
    if (!r.available) { out[k] = {errors: [`week ${week}: ${r.reason}`], zeroOnly}; continue; }
    let compared = 0;
    rows.forEach(row => {
      const v = row.values[k];
      const p = r.values[row.player_key];
      if (v == null && p == null) return;
      compared += 1;
      if (v != null && p != null && Math.abs(v - p) <= 1e-9) return;
      // ESPN only: a player one side prices at 0.0 and the other lacks is the
      // leg/players.json identity edge (reported, GAP-ESPN-LEG-STATUS-EDGE).
      if (k === 'espn' && (v == null ? p : v) === 0) { zeroOnly.push(row.name); return; }
      // JEG-479 row rules (Jeremy 2026-10-08/09): the row shows 0 for a player
      // below a fully loaded chart's floor whom the saved week does not price,
      // and blanks an identity-fallback adjustment cell the week still prices.
      // The history accessor returns the saved week as priced.
      const chartSeries = ['usatoday', 'fantasycalc', 'fantasypros', 'cbs'].includes(base(k));
      if (chartSeries && v === 0 && p == null) return;
      const why = (row.missingReasons || {})[k] || '';
      if (chartSeries && v == null && (why.startsWith('Not enough players') || why.startsWith('Adjustment fit refused'))) return;
      errors.push(`${row.name}: chart ${v}, week ${week} ${p}`);
    });
    if (!compared) errors.push('no player compared');
    out[k] = {errors, zeroOnly};
  }
  return out;
}"""
# JEG-479 "Build prior week": the charts' VORP vs waivers / Adjusted values
# for a saved week are derivePublishedViews on that week's saved natives.
# Run after SELF (Half PPR, 10 teams, an extra bench spot: off the saved
# setup, so the tabs derive their views): the served week fed back through
# getWeekValues reproduces each chart's tab values exactly.
VIEW_SELF = """async ([keys, week]) => {
  const c = window.TradeValueCurveControls;
  (""" + SET_WEEK + """)(c, week);
  const view = v => document.querySelector(`#viewModeTabs [data-view-mode=${v}]`).click();
  const index = await (await fetch('assets/history/index.json')).json();
  const out = {};
  for (const v of ['vorp', 'adj']) {
    view(v);
    const rows = c.getAllRows();
    for (const k of keys) {
      const week = index.served[k].week;
      const r = await c.getWeekValues(k, week);
      const errors = [];
      if (!r.available) { out[`${k} (${v})`] = {errors: [`week ${week}: ${r.reason}`], zeroOnly: []}; continue; }
      let compared = 0;
      rows.forEach(row => {
        const a = row.values[k], b = r.values[row.player_key];
        if (a == null && b == null) return;
        compared += 1;
        if (a != null && b != null && Math.abs(a - b) <= 1e-9) return;
        // The JEG-479 row rules, as in SELF: the row shows 0 for a player a
        // fully loaded chart does not price; the accessor returns the week as priced.
        if (a === 0 && b == null) return;
        const why = (row.missingReasons || {})[k] || '';
        if (a == null && why.startsWith('Not enough players')) return;
        errors.push(`${row.name}: tab ${a}, week ${week} ${b}`);
      });
      if (!compared) errors.push('no player compared');
      out[`${k} (${v})`] = {errors, zeroOnly: []};
    }
  }
  view('indexed');
  return out;
}"""
ESPN_PRIOR_KEYS = ('espn', 'espn_vorp', 'cbsros_vorp', 'razzball_vorp',
                   'usatoday_adjusted', 'fantasycalc_adjusted', 'fantasypros_adjusted', 'cbs_adjusted')
ESPN_PRIOR = """async ([keys, week]) => {
  const c = window.TradeValueCurveControls;
  (""" + SET_WEEK + """)(c, week);
  c.setScoring('ppr'); c.setTeams(12);
  const out = {};
  for (const k of keys) {
    const r = await c.getPriorWeek(k);
    let changed = 0;
    c.getAllRows().forEach(row => {
      const now = row.values[k], before = r.values?.[row.player_key];
      if (now != null && before != null && Math.abs(now - before) > 1e-9) changed += 1;
    });
    out[k] = {available: r.available, reason: r.reason || null, week: r.week, priorWeek: r.priorWeek,
              n: r.values ? Object.keys(r.values).length : 0, changed, values: k === 'espn' ? r.values : null};
  }
  return out;
}"""
# JEG-714: every saved week the page serves (index.weeks), not only the
# served/prior pair. Run 568 (2026-10-17): once every chart served Week 6,
# no chart's prior was Week 4, so a relabelled week-4.json went unread by
# the guard although the page still serves it to getWeekValues.
ALL_WEEKS = """async (pairs) => {
  const c = window.TradeValueCurveControls;
  (""" + SET_WEEK + """)(c, null);
  c.setScoring('ppr'); c.setTeams(12);
  const out = {};
  for (const [k, week] of pairs) {
    const r = await c.getWeekValues(k, week);
    out[`${k}@${week}`] = {available: r.available, reason: r.reason || null, week: r.week,
                           values: r.available ? r.values : null};
  }
  return out;
}"""


def _saved_natives(source, week):
    """A saved week's natives at Full PPR over the charted players."""
    from tests.test_published_league_settings_engine import browser_players
    pos_of = browser_players()
    natives = _week(week)["sources"][source]["natives"]["ppr"]
    return {int(k): float(v) for k, v in natives.items() if int(k) in pos_of}


@contextlib.contextmanager
def _server(overrides):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def translate_path(self, path):
            # JEG-453: /classic/ is the build-only engine page here.
            return engine_path(path) or super().translate_path(path)

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


SERVED_WEEK_SOURCES = ("usatoday", "fantasycalc", "fantasypros", "cbs", "cbsros", "razzball", "espn",
                       "espn_vorp", "cbsros_vorp", "razzball_vorp",
                       "usatoday_adjusted", "fantasycalc_adjusted", "fantasypros_adjusted", "cbs_adjusted")


def _base(key):
    """The fixture section a served series comes from (same rule as SELF's base())."""
    for suffix in ("_vorp", "_adjusted"):
        if key.endswith(suffix):
            return key[: -len(suffix)]
    return key


def served_sources(held=None):
    """The served-week check's sources that the fixture carries (2026-10-08).

    A chart absent from the fixture is dropped by the page, so it has no
    served week to check; a present chart is checked in full. The ESPN anchor
    must be present. held: the held roots the page saw (default: the
    committed fixture's)."""
    sources = json.loads((ROOT / "data" / "fixtures" / "current" /
                          "comparison-sources-data.json").read_text(encoding="utf-8"))["sources"]
    if "espn" not in sources:
        raise AssertionError("the ESPN anchor section is missing from the fixture")
    # JEG-569 part 2: a held section is dropped from the output (no computation on
    # old data), so it has no served week or prior week to check.
    held = held_roots(sources) if held is None else held
    return [k for k in SERVED_WEEK_SOURCES if _base(k) in sources and _base(k) not in held]


def held_roots(sources=None):
    sources = sources or json.loads((ROOT / "data" / "fixtures" / "current" /
                                     "comparison-sources-data.json").read_text(encoding="utf-8"))["sources"]
    return {k for k, v in sources.items() if isinstance(v, dict) and v.get("validationHold")}


def served_week(index, series, unmatched):
    """The saved week a series' base source serves (index served.week), or
    None, recorded in `unmatched`. A held source serves its kept section's
    week (JEG-479 holds). A source whose served inputs match no saved week
    (a fresh bake not saved yet, or a history bug like JEG-492) is a warning,
    not a gate failure (Jeremy, 2026-10-09, JEG-507): the page shows that
    series' prior week as unavailable with the reason."""
    base = series.split("_")[0]
    rec = (index.get("served") or {}).get(base) or {}
    if isinstance(rec.get("week"), int):
        return rec["week"]
    unmatched[base] = (f"the served {base} inputs have no saved week "
                       f"({rec.get('reason') or 'not in the history index'})")
    return None


def by_served_week(index, keys):
    """{served week (None for an unmatched source): [series]} in key order,
    so each group is checked in the week view of the week it serves."""
    groups = {}
    for key in keys:
        rec = (index.get("served") or {}).get(key.split("_")[0]) or {}
        week = rec.get("week") if isinstance(rec.get("week"), int) else None
        groups.setdefault(week, []).append(key)
    return groups


def unmatched_prior(series, res):
    """A series whose served week the index could not match has no prior
    week: the engine must say so with a reason, never price one."""
    if res.get("available") or not res.get("reason"):
        return [f"{series}: the served week is unmatched but the engine reported "
                f"available={res.get('available')} reason={res.get('reason')!r}"]
    return []


def saved_week_failures(page, index, held):
    """JEG-714: every saved week in the index, read through the engine's
    getWeekValues at Full PPR / 12, must load under its own label and, for a
    published chart, price the STORE's natives for that week (data/history,
    not the served copy) times one factor (VP-6.4). A served week file that is
    relabelled or carries another week's content fails here whichever week the
    charts serve now."""
    charted = json.loads((ROOT / "data" / "fixtures" / "current" /
                          "comparison-sources-data.json").read_text(encoding="utf-8"))["sources"]
    pairs = sorted((src, int(week)) for week, rec in (index.get("weeks") or {}).items()
                   for src in (rec.get("sources") or {})
                   if src in charted and src not in held)
    if not pairs:
        return ["no saved week to check"]
    failures = []
    results = page.evaluate(ALL_WEEKS, [list(p) for p in pairs])
    for (src, week) in pairs:
        res = results[f"{src}@{week}"]
        if not res["available"]:
            failures.append(f"{src} Week {week}: saved week unavailable ({res['reason']})")
            continue
        served = (index.get("served") or {}).get(src) or {}
        if src not in H.PUBLISHED or (served.get("week") == week and served.get("version") == "superseded"):
            continue  # projections: availability only; a served kept version is SELF's check
        native = _saved_natives(src, week)
        values = {int(k): v for k, v in (res["values"] or {}).items()}
        ratios = [values[k] / v for k, v in native.items() if v > 0 and k in values]
        missing = [k for k, v in native.items() if v > 0 and k not in values]
        if not ratios or missing or max(ratios) - min(ratios) > 1e-9 * max(ratios):
            failures.append(f"{src} Week {week}: values are not one factor on the saved Week {week} "
                            f"natives ({len(missing)} saved players missing)")
    return failures


def collect(overrides=None):
    """Failures of the Δ checks against the built dist/ (with optional
    served-file overrides that simulate a broken state)."""
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    if not (DIST / "assets" / "history" / "index.json").exists():
        raise _render_env.unavailable("dist/ is not built with history")
    # Every published chart whose week before the served one is saved (on
    # 2026-10-08: USA Today / FantasyCalc / FantasyPros Week 4, CBS Week 3).
    # The page and this check read the same index (an override included).
    index = json.loads((overrides or {}).get("assets/history/index.json") or
                       (DIST / "assets" / "history" / "index.json").read_text(encoding="utf-8"))
    expected, failures = {}, []
    fixture_override = (overrides or {}).get(FIXTURE_ASSET)
    UNMATCHED.clear()
    for source in H.PUBLISHED:
        served = served_week(index, source, UNMATCHED)
        if served and source in (index["weeks"].get(str(served - 1)) or {}).get("sources", {}):
            expected[source] = served - 1
    if not expected:
        failures.append("no published chart has a saved prior week")
    with _server(overrides or {}) as url, sync_playwright() as playwright:
        exe = _render_env.chromium_executable(playwright)
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            # Pin the content-week clock to the fixture's own week so the
            # page never sees a newer week than the data it serves (JEG-787).
            today = _fixture_today(json.loads(fixture_override) if fixture_override else None)
            page.add_init_script(f"window.TRADE_VALUE_TODAY = {json.dumps(today)};")
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            page.goto(url, wait_until="networkidle", timeout=120000)
            page.wait_for_function(READY, timeout=30000)
            # JEG-787: verify the pin puts the page in the data's own content
            # week -- the bug this guards is the real clock advancing past it.
            page_week = page.evaluate(
                "() => window.TradeValueProductData?.getSourceFreshness?.()?.current_content_week")
            served_weeks = {s.get("week") for s in index.get("served", {}).values()} - {None}
            if page_week and served_weeks and page_week > max(served_weeks):
                failures.append(
                    f"content-week pin failed: page sees week {page_week} "
                    f"but data only has week {max(served_weeks)}")
            WEEK_STATE.clear()
            WEEK_STATE.update(page.evaluate("() => window.TradeValueCurveControls.getWeekState?.() || {}") or {})
            prior = {}
            for week, keys in by_served_week(index, H.PUBLISHED).items():
                prior.update(page.evaluate(PRIOR, [keys, week]))
            for source in sorted(set(H.PUBLISHED) & set(UNMATCHED)):
                failures += unmatched_prior(source, prior[source]["prior"])
            for source, week in expected.items():
                native = _saved_natives(source, week)
                got = prior[source]["prior"]
                if not got.get("available"):
                    failures.append(f"{source}: prior week unavailable ({got.get('reason')})")
                    continue
                if got.get("priorWeek") != week or got.get("week") != week:
                    failures.append(f"{source}: prior week {got.get('priorWeek')}, want {week}")
                values = {int(k): v for k, v in got["values"].items()}
                missing = [k for k in native if k not in values]
                if missing:
                    failures.append(f"{source}: {len(missing)} saved-week players not priced")
                # VP-6.4: Indexed = the saved natives times one factor.
                ratios = [values[k] / v for k, v in native.items() if v > 0 and k in values]
                factor = ratios[0] if ratios else None
                if not ratios or max(ratios) - min(ratios) > 1e-9 * max(ratios):
                    failures.append(f"{source}: prior Indexed is not one factor on the Week {week} natives")
                want = {k: v * factor for k, v in native.items()} if factor else {}
                # The known player: Δ is the chart's current value minus the
                # saved week priced at the same setting.
                current = prior[source]["current"]
                # JEG-1176: a chart lagging the default view is read in its
                # served week's view (PRIOR sets it); when the page offers no
                # view for that week (chain run 40624176718: CBS a week behind
                # and red-held, so no transition) it has no current value.
                # That is lagging, not a failure: noted, its prior week still
                # checked, only the Δ left out.
                lag = lagging_week(WEEK_STATE, source)
                no_view = current is None and lag is not None and not has_view(WEEK_STATE, lag)
                if no_view:
                    note_lagging("week history", [source], lag, WEEK_STATE, "its Δ is not checked in the browser")
                if BIJAN not in values or (current is None and not no_view):
                    failures.append(f"{source}: Bijan Robinson missing (prior {values.get(BIJAN)}, current {current})")
                elif BIJAN not in want or abs(values[BIJAN] - want[BIJAN]) > 1e-9:
                    failures.append(f"{source}: Bijan prior {values[BIJAN]}, natives x factor {want.get(BIJAN)}")
                elif not no_view:
                    DELTAS[source] = round(current - values[BIJAN], 1)
            # (Runs before SELF, which changes the roster.) Prior weeks for ESPN, VORP vs waivers and Adjusted (HISTORY-ESPN-PRIOR).
            # The holds the page saw: a served fixture override's, else the committed fixture's.
            held = held_roots(json.loads(fixture_override)["sources"]) if fixture_override else held_roots()
            espn_prior = {}
            for week, keys in by_served_week(index, ESPN_PRIOR_KEYS).items():
                espn_prior.update(page.evaluate(ESPN_PRIOR, [keys, week]))
            for source, res in espn_prior.items():
                if _base(source) in held:
                    continue
                # Published charts were reported above; report a projection once.
                served = served_week(index, source, UNMATCHED)
                if served is None:
                    failures += unmatched_prior(source, res)
                    continue
                if not res["available"]:
                    if (source.split("_")[0] in index["weeks"].get(str(served - 1), {}).get("sources", {})):
                        failures.append(f"{source}: prior week unavailable ({res['reason']})")
                    continue
                if res["priorWeek"] != served - 1 or res["n"] == 0:
                    failures.append(f"{source}: prior week {res['priorWeek']} with {res['n']} values")
                if res["changed"] == 0:  # the served week passed off as the prior one
                    failures.append(f"{source}: prior week identical to the served values")

            failures += saved_week_failures(page, index, held)

            # An unmatched source has no served week to reproduce.
            # JEG-1177: each source is checked in the view of its OWN served
            # week, so a source still on Week N while others serve N+1 is
            # checked against Week N (lag is not a failure), and its served
            # file must still equal its saved Week N exactly.
            # The holds the page saw (a replay can clear a lagging chart's
            # hold, transition_overrides), so a served chart is checked.
            served = [k for k in served_sources(held) if k.split("_")[0] not in UNMATCHED]
            self_results = {}
            for week, keys in by_served_week(index, served).items():
                self_results.update(page.evaluate(SELF, [keys, week]))
                self_results.update(page.evaluate(VIEW_SELF, [[k for k in keys if k in H.PUBLISHED], week]))
            for source, res in self_results.items():
                if res["errors"]:
                    failures.append(f"{source} served week != chart: {res['errors'][:2]} ({len(res['errors'])} players)")
                if len(res["zeroOnly"]) > 5:
                    failures.append(f"{source}: {len(res['zeroOnly'])} zero-only membership differences")
                elif res["zeroOnly"]:
                    ZERO_ONLY[source] = res["zeroOnly"]
            failures += [f"page error: {e}" for e in errors]
            page.close()
        finally:
            browser.close()
    return failures


class DeltaRecomputeTest(unittest.TestCase):
    def test_prior_week_is_engine_math_on_saved_inputs(self):
        self.assertEqual(collect(), [])
        print(f"Bijan Robinson Δ (Full PPR, 12 teams): {DELTAS}")
        if ZERO_ONLY:
            print(f"0.0-only membership differences (reported): {ZERO_ONLY}")
        for base, why in UNMATCHED.items():
            print(f"::warning title=week history::{base}: {why}; its prior week shows as unavailable")

    def test_delta_guard_fails_on_broken_states(self):
        widget = WIDGET.read_text(encoding="utf-8")
        relabelled = _week(3)
        relabelled_doc = json.dumps(dict(_week(4), week=3))
        substitute = widget.replace(
            'const values = familyOf(key) === "projection" ? historyPpg(found.entry) : historyNatives(found.entry);',
            "const values = currentNatives(key);")
        self.assertNotEqual(substitute, widget)
        same_week = widget.replace("const prior = served.week - 1;", "const prior = served.week;")
        self.assertNotEqual(same_week, widget)
        served_ignored = widget.replace('if (servedRec?.week === week && servedRec?.version === "superseded") {',
                                        'if (false) {')
        self.assertNotEqual(served_ignored, widget)
        cases = {
            "week-4 file served relabelled as week 3": {"assets/history/week-4.json": relabelled_doc},
            "week-4 file served with week-3 content": {"assets/history/week-4.json": json.dumps(dict(relabelled, week=4))},
            "accessor substitutes the served natives": {"assets/curve-widget.js": substitute},
            "prior paired with the served week": {"assets/curve-widget.js": same_week},
        }
        index = json.loads((DIST / "assets" / "history" / "index.json").read_text(encoding="utf-8")) \
            if (DIST / "assets" / "history" / "index.json").exists() else {}
        if any(r.get("version") == "superseded" for r in (index.get("served") or {}).values()):
            cases["served week read from the week's snapshot, not the served version"] = {
                "assets/curve-widget.js": served_ignored}
        # JEG-714 (chain runs 552-568): once every chart serves Week 6, no
        # chart's prior is Week 4, yet week-4.json is still served. The same
        # broken files must be caught then too. The index marks any chart
        # serving Week 5 unmatched (a warning), the state of run 568.
        if index:
            rolled = copy.deepcopy(index)
            for base, rec in rolled["served"].items():
                if rec.get("week") == 5:
                    rolled["served"][base] = {"week": None, "reason": "the served inputs match no saved week"}
            rolled_doc = json.dumps(rolled)
            self.assertEqual(collect({"assets/history/index.json": rolled_doc}), [])
            cases["week-4 file relabelled as week 3, no chart's prior is Week 4"] = {
                "assets/history/index.json": rolled_doc, "assets/history/week-4.json": relabelled_doc}
            cases["week-4 file with week-3 content, no chart's prior is Week 4"] = {
                "assets/history/index.json": rolled_doc,
                "assets/history/week-4.json": json.dumps(dict(relabelled, week=4))}
        for name, overrides in cases.items():
            with self.subTest(name):
                self.assertNotEqual(collect(overrides), [], f"{name} was not caught")

    def _unmatched_index(self):
        # Run 37877126939 (2026-10-09): the index could not match the served
        # ESPN inputs (and so espn_vorp) to a saved week; the gate crashed on
        # None - 1. Same for a published chart.
        index = json.loads((DIST / "assets" / "history" / "index.json").read_text(encoding="utf-8"))
        for base in ("espn", "usatoday"):
            index["served"][base] = {"week": None, "reason": "the served inputs match no saved week"}
        return json.dumps(index)

    def _unmatched_overrides(self):
        # Held-proof (JEG-675, Jeremy 2026-10-16: "Give the tests a fixed,
        # held-proof fixture"): the premise needs ESPN and USA Today unheld,
        # so serve the pinned holds (tests/_holds.py). Chain run 573
        # (JEG-chain573) held ESPN and this test went red on the data.
        fixture = json.loads((DIST / FIXTURE_ASSET).read_text(encoding="utf-8"))
        return {"assets/history/index.json": self._unmatched_index(),
                FIXTURE_ASSET: json.dumps(with_pinned_holds(fixture), separators=(",", ":"))}

    def test_unmatched_served_week_is_a_warning_not_a_crash(self):
        # Jeremy, 2026-10-09 (JEG-507): warn, don't block, as long as the
        # engine reports the prior week unavailable with a reason.
        self.assertEqual(collect(self._unmatched_overrides()), [])
        self.assertEqual(sorted(UNMATCHED), ["espn", "usatoday"])
        self.assertTrue(all("match no saved week" in why for why in UNMATCHED.values()), UNMATCHED)

    def test_unmatched_guard_fails_when_the_engine_guesses_a_week(self):
        widget = WIDGET.read_text(encoding="utf-8")
        # The engine guesses the newest saved week for an unmatched source.
        guesses = widget.replace(
            "if (!served || !Number.isInteger(served.week)) {",
            "if (served && !Number.isInteger(served.week)) "
            "return {served: {...served, week: Math.max(...Object.keys(index.weeks || {}).map(Number))}}; "
            "if (!served) {")
        self.assertNotEqual(guesses, widget)
        failures = collect({**self._unmatched_overrides(), "assets/curve-widget.js": guesses})
        self.assertTrue([f for f in failures if "the served week is unmatched but" in f], failures)


SCORING_PREFIX = {"ppr": "full", "half_ppr": "half", "standard": "standard"}


def newest_week(exclude=("cbs", "usatoday")):
    """The newest week the built dist/ serves, over the charts not in
    `exclude`. Committed data and a chain rebuild differ here (on 2026-10-28
    the chain built Week 8 while the committed dist/ served Week 7), so the
    transition replay is set relative to it, not to a fixed week."""
    index = json.loads((DIST / "assets" / "history" / "index.json").read_text(encoding="utf-8"))
    return max(v["week"] for k, v in index["served"].items()
               if k not in exclude and isinstance(v.get("week"), int))


def transition_overrides(lagging=("cbs", "usatoday"), week=None, corrupt=None):
    """JEG-1177 sentinel: replay a week transition from committed data. The
    `lagging` charts serve their saved Week `week` (default: the week before
    newest_week(); the served fixture carries exactly those natives and the
    index says so) while every other source serves the newer week, as on
    2026-10-27 (USA Today and CBS on Week 7, the rest on Week 8). Any hold on
    a lagging chart is cleared: the replay serves its saved week, and a red
    hold would hide it from the view lists (a test that wants one adds it).
    corrupt: a source whose served file has one player's value changed, so it
    no longer equals its own saved week."""
    if week is None:
        week = newest_week(lagging) - 1
    index = json.loads((DIST / "assets" / "history" / "index.json").read_text(encoding="utf-8"))
    fixture = json.loads((DIST / FIXTURE_ASSET).read_text(encoding="utf-8"))
    slug_of = {}
    for slug, key in sorted((fixture.get("player_keys") or {}).items()):
        slug_of.setdefault(int(key), slug)
    saved = _week(week)
    for src in lagging:
        entry = saved["sources"][src]
        index["served"][src] = {"week": week, "version": "snapshot", "fingerprint": entry["fingerprint"],
                                "label_week": week}
        section = fixture["sources"][src]
        section["week_designated"] = section["content_vintage"] = f"Week {week}"
        for field in ("validationHold", "promotionHold"):
            section.pop(field, None)
        for scoring, prefix in SCORING_PREFIX.items():
            natives = {slug_of[int(k)]: v for k, v in entry["natives"][scoring].items() if int(k) in slug_of}
            if src == corrupt:
                slug = slug_of.get(BIJAN) or sorted(natives)[0]
                natives[slug] = natives[slug] * 1.07
            combos = [k for k in section["combos"] if k.startswith(f"{prefix}_12")]
            assert combos, f"{src} has no {prefix} 12-team combo"
            for combo in combos:
                section["combos"][combo]["native"] = dict(natives)
    return {"assets/history/index.json": json.dumps(index),
            FIXTURE_ASSET: json.dumps(fixture, separators=(",", ":"))}


class WeekTransitionSentinelTest(unittest.TestCase):
    """JEG-1175 / JEG-1177: chain runs 40546427066 and 40555873437 failed
    post-rebuild validation ("cbs served week != chart", "usatoday served week
    != chart") because USA Today and CBS still served Week 7 while the rest
    served Week 8, and the page priced the Week 7 charts against the Week 8
    blend (one constant factor off, 0.99946). A lagging source is not a
    failure; a source whose served file is not its own saved week is."""

    def test_mixed_transition_passes(self):
        failures = collect(transition_overrides())
        self.assertEqual(failures, [])
        # 5 of 7 DDF Value sources serve week N (Week 7 in committed data):
        # more than half, so it is the default view and the two week N-1
        # charts are its missing sources.
        n = newest_week()
        self.assertEqual(WEEK_STATE.get("week"), n, WEEK_STATE)
        self.assertEqual(WEEK_STATE.get("weeks"), [n, n - 1], WEEK_STATE)
        self.assertEqual(WEEK_STATE["views"][str(n)]["missing_sources"], ["cbs", "usatoday"], WEEK_STATE)
        self.assertEqual(WEEK_STATE["views"][str(n - 1)]["missing_sources"], [], WEEK_STATE)

    def test_corrupted_single_source_file_still_fails(self):
        failures = collect(transition_overrides(corrupt="cbs"))
        self.assertTrue([f for f in failures if f.startswith("cbs served week != chart")], failures)

    def test_carry_forward_pricing_fails(self):
        """The pre-fix engine (no week view: the Week 6 charts priced against
        the Week 7 blend) is what the chain saw; the guard must still catch it."""
        widget = WIDGET.read_text(encoding="utf-8")
        no_view = widget.replace("    weekView = resolveWeekView();\n", "    weekView = null;\n")
        self.assertNotEqual(no_view, widget)
        failures = collect({**transition_overrides(), "assets/curve-widget.js": no_view})
        self.assertTrue([f for f in failures if " served week != chart" in f
                         and f.split()[0] in ("cbs", "usatoday", "cbs_adjusted", "usatoday_adjusted")], failures)


    def test_engine_and_python_reference_agree_in_the_transition(self):
        """value_check compare (the chain's other gate) on the same replay:
        the page and value_reference.py price the default Week 7 view value
        for value, with the Week 6 charts out of DDF Value and named."""
        import shutil
        from datetime import date as _date
        import value_check as vc
        overrides = transition_overrides()
        settings = [{"scoring": "ppr", "teams": 12, "superflex": 0},
                    {"scoring": "half_ppr", "teams": 10, "superflex": 1}]
        today = _date.fromisoformat(_fixture_today())
        engine = vc.run_engine(settings, today, overrides={k: v.encode("utf-8") for k, v in overrides.items()})
        with tempfile.TemporaryDirectory() as tmp:
            hist = Path(tmp) / "history"
            shutil.copytree(DIST / "assets" / "history", hist)
            (hist / "index.json").write_text(overrides["assets/history/index.json"], encoding="utf-8")
            fixture = Path(tmp) / "fixture.json"
            fixture.write_text(overrides[FIXTURE_ASSET], encoding="utf-8")
            reference = vc.run_reference(settings, today, fixture=fixture, history=hist)
            import value_reference as R
            lag = newest_week() - 1
            lagged = R.Setting(R.Inputs.load(fixture), "ppr", 12, hist=R.History(hist), week=lag)
            self.assertEqual(lagged.week_view()["week"], lag)
            self.assertIn("cbs", lagged.state()["included"])
            self.assertEqual(lagged.state()["current_week"], lag)
        report = vc.compare(engine["settings"], reference)
        bad = {k: a["examples"][:2] for k, a in report["series"].items() if a["mismatches"]}
        self.assertEqual(bad, {})
        for sid, r in reference.items():
            self.assertNotIn("cbs", r["composite_inputs"], sid)
            self.assertNotIn("usatoday", r["composite_inputs"], sid)
            self.assertIn("fantasycalc", r["composite_inputs"], sid)
            self.assertTrue(r["composite_excluded"]["cbs"].startswith(f"not yet published for Week {newest_week()}"),
                            sid)


class FixtureTodayPinTest(unittest.TestCase):
    """JEG-791: _fixture_today must return a date in the data's content week,
    not the build week.  When the chain builds in week N+1 but the served
    charts are still week N, pinning to built_at puts the page in week N+1
    and the content-week check fails."""

    def test_pin_uses_data_week_not_build_week(self):
        """Negative-tests the old behaviour: using built_at as the pin date
        fails when built_at is in a newer week than the data.  Writes a
        temporary fixture with a future built_at, calls _fixture_today on
        it, and verifies the pin is in the data's week."""
        from nfl_week import content_week, content_week_start, section_content_week
        from datetime import date as _date, timedelta
        fixture_path = DIST / FIXTURE_ASSET
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        data_weeks = [w for s in (fixture.get("sources") or {}).values()
                      if (w := section_content_week(s)) is not None]
        if not data_weeks:
            self.skipTest("no dated source sections")
        data_week = max(data_weeks)
        original = fixture_path.read_text(encoding="utf-8")
        try:
            # Simulate a built_at one week ahead of the data.
            next_tuesday = content_week_start(data_week + 1)
            future_date = next_tuesday + timedelta(days=1)
            fixture["built_at"] = future_date.isoformat() + "T00:00:00+00:00"
            fixture_path.write_text(json.dumps(fixture, separators=(",", ":")))
            build_week = content_week(future_date)
            self.assertEqual(build_week, data_week + 1,
                             "simulated built_at should be in the next week")
            # The OLD code would return built_at[:10] in week data_week+1.
            old_pin_week = content_week(future_date)
            self.assertGreater(old_pin_week, data_week,
                               "the old pin (built_at) is in a newer week than the data")
            # The NEW code uses the data's content week.
            pin = _fixture_today()
            pin_week = content_week(_date.fromisoformat(pin))
            self.assertEqual(pin_week, data_week,
                             f"_fixture_today pin {pin} should be in data week {data_week}, "
                             f"got week {pin_week}")
        finally:
            fixture_path.write_text(original)

    def test_override_fixture_controls_the_pin_without_rewriting_dist(self):
        from nfl_week import content_week, content_week_start
        from datetime import date as _date
        fixture_path = DIST / FIXTURE_ASSET
        original = fixture_path.read_bytes()
        fixture = {"built_at": content_week_start(8).isoformat() + "T00:00:00Z",
                   "sources": {"fantasycalc": {"week_designated": "Week 6"}}}
        self.assertEqual(content_week(_date.fromisoformat(_fixture_today(fixture))), 6)
        self.assertEqual(fixture_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
