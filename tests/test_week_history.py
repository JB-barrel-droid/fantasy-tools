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
from tests import _render_env  # noqa: E402


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


class EspnPriorLegTest(unittest.TestCase):
    """HISTORY-ESPN-PRIOR: a saved ESPN week's leg is rebuilt with the
    pipeline's leg code. Proof it is the pipeline's leg: the SERVED week's
    rebuild equals the fixture's ESPN combos (built by
    build_espn_section_from_ddf_leg) on every player both price."""

    def _diff(self, entry):
        fixture = json.loads((ROOT / "data/fixtures/current/comparison-sources-data.json").read_text(encoding="utf-8"))
        players = json.loads((ROOT / "data/fixtures/current/players.json").read_text(encoding="utf-8"))
        legs = H.espn_legs_for_week(entry, players)["legs"]
        out = {}
        for scoring, word in (("standard", "standard"), ("half_ppr", "half"), ("ppr", "full")):
            combo = fixture["sources"]["espn"]["combos"][f"{word}_12"]
            fx = {str(combo["player_keys"][s]): v for s, v in combo["values"].items()}
            leg = legs[scoring]
            shared = set(fx) & set(leg)
            out[scoring] = ([k for k in shared if abs(fx[k] - leg[k]) > 1e-9],
                            [k for k in set(fx) ^ set(leg) if (fx[k] if k in fx else leg[k]) != 0.0],
                            len(shared))
        return out

    def test_served_week_rebuild_is_the_fixture_leg(self):
        index = json.loads((HISTORY / "index.json").read_text(encoding="utf-8"))
        week = index["served"]["espn"]["week"]
        self.assertIsNotNone(week)
        for scoring, (diff, nonzero_only, shared) in self._diff(_week(week)["sources"]["espn"]).items():
            self.assertGreater(shared, 300, scoring)
            self.assertEqual(diff, [], scoring)
            self.assertEqual(nonzero_only, [], scoring)  # membership differs only at 0.0

    def test_rebuild_catches_changed_projections(self):
        index = json.loads((HISTORY / "index.json").read_text(encoding="utf-8"))
        entry = copy.deepcopy(_week(index["served"]["espn"]["week"])["sources"]["espn"])
        top = max(entry["ppg"], key=lambda k: entry["ppg"][k][2])
        entry["ppg"][top] = [x * 0.8 for x in entry["ppg"][top]]
        self.assertTrue(any(diff for diff, _, _ in self._diff(entry).values()))


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
SELF = """async (keys) => {
  const c = window.TradeValueCurveControls;
  c.setScoring('half'); c.setTeams(10); c.setRosterSpot('BENCH', c.getRosterShape().BENCH + 1);
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
      errors.push(`${row.name}: chart ${v}, week ${week} ${p}`);
    });
    if (!compared) errors.push('no player compared');
    out[k] = {errors, zeroOnly};
  }
  return out;
}"""
ESPN_PRIOR = """async () => {
  const c = window.TradeValueCurveControls;
  c.setScoring('ppr'); c.setTeams(12);
  const out = {};
  for (const k of ['espn', 'espn_vorp', 'cbsros_vorp', 'razzball_vorp',
                   'usatoday_adjusted', 'fantasycalc_adjusted', 'fantasypros_adjusted', 'cbs_adjusted']) {
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


def _python_prior(source, week, anchor):
    """Independent price of a saved week at Full PPR / 12 / standard roster:
    the saved natives times one factor against the page's live anchor
    (JEG-482), over the charted players (canonical QB/RB/WR/TE)."""
    from tests.test_published_league_settings_engine import browser_players, one_factor
    pos_of = browser_players()
    natives = _week(week)["sources"][source]["natives"]["ppr"]
    native = {int(k): float(v) for k, v in natives.items() if int(k) in pos_of}
    return one_factor(native, native, anchor)


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


def served_sources():
    """The served-week check's sources that the fixture carries (2026-10-08).

    A chart absent from the fixture is dropped by the page, so it has no
    served week to check; a present chart is checked in full. The ESPN anchor
    must be present."""
    sources = json.loads((ROOT / "data" / "fixtures" / "current" /
                          "comparison-sources-data.json").read_text(encoding="utf-8"))["sources"]
    if "espn" not in sources:
        raise AssertionError("the ESPN anchor section is missing from the fixture")
    return [k for k in SERVED_WEEK_SOURCES if _base(k) in sources]


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
    index = json.loads((DIST / "assets" / "history" / "index.json").read_text(encoding="utf-8"))
    expected = {}
    for source in H.PUBLISHED:
        served = index["served"][source]["week"]
        if served and source in (index["weeks"].get(str(served - 1)) or {}).get("sources", {}):
            expected[source] = served - 1
    failures = [] if expected else ["no published chart has a saved prior week"]
    with _server(overrides or {}) as url, sync_playwright() as playwright:
        exe = _render_env.chromium_executable(playwright)
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            page.goto(url, wait_until="networkidle", timeout=120000)
            page.wait_for_function(READY, timeout=30000)
            prior = page.evaluate(PRIOR)
            anchor = {int(k): v for k, v in page.evaluate(
                "() => Object.fromEntries([...window.TradeValueCurveHarness.sourceMaps().get('espn').entries()])").items()}
            for source, week in expected.items():
                want = _python_prior(source, week, anchor)
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
            # (Runs before SELF, which changes the roster.) Prior weeks for ESPN, VORP vs waivers and Adjusted (HISTORY-ESPN-PRIOR).
            # ESPN at the reference share is that week's leg as the pipeline
            # builds it (espn_legs_for_week), player for player.
            players = json.loads((ROOT / "data/fixtures/current/players.json").read_text(encoding="utf-8"))
            for source, res in page.evaluate(ESPN_PRIOR).items():
                served = index["served"][source.split("_")[0]]["week"]
                if not res["available"]:
                    if (source.split("_")[0] in index["weeks"].get(str(served - 1), {}).get("sources", {})):
                        failures.append(f"{source}: prior week unavailable ({res['reason']})")
                    continue
                if res["priorWeek"] != served - 1 or res["n"] == 0:
                    failures.append(f"{source}: prior week {res['priorWeek']} with {res['n']} values")
                if res["changed"] == 0:  # the served week passed off as the prior one
                    failures.append(f"{source}: prior week identical to the served values")
                if source == "espn":
                    entry = _week(served - 1)["sources"]["espn"]
                    want = H.espn_legs_for_week(entry, players)["legs"]["ppr"]
                    got = {k: v for k, v in res["values"].items() if v != 0}
                    # The anchor's live cells map the 1-dp leg onto the
                    # full-precision two-tier values (near identity at the
                    # reference share), so allow the leg's own rounding.
                    bad = [k for k, v in got.items() if k in want and abs(v - want[k]) > 0.06]
                    if bad or not got:
                        failures.append(f"espn prior != pipeline leg on {len(bad)} players, e.g. "
                                        f"{[(k, got[k], want[k]) for k in bad[:4]]}")
            for source, res in page.evaluate(SELF, served_sources()).items():
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

    def test_delta_guard_fails_on_broken_states(self):
        widget = WIDGET.read_text(encoding="utf-8")
        relabelled = _week(3)
        relabelled_doc = json.dumps(dict(_week(4), week=3))
        substitute = widget.replace("const native = historyNatives(entry);",
                                    "const native = savedPublishedNative(source);")
        self.assertNotEqual(substitute, widget)
        same_week = widget.replace("const prior = served.week - 1;", "const prior = served.week;")
        self.assertNotEqual(same_week, widget)
        espn_served_leg = widget.replace("const leg = saved?.legs?.[scoringField()];",
                                          "const leg = legs?.weeks?.[String(week + 1)]?.legs?.[scoringField()];")
        self.assertNotEqual(espn_served_leg, widget)
        vorp_served = widget.replace("values: buildVorpMap(series, ppg),", "values: buildVorpMap(series),")
        self.assertNotEqual(vorp_served, widget)
        served_ignored = widget.replace('if (servedRec?.week === week && servedRec?.version === "superseded") {',
                                        'if (false) {')
        self.assertNotEqual(served_ignored, widget)
        cases = {
            "week-4 file served relabelled as week 3": {"assets/history/week-4.json": relabelled_doc},
            "week-4 file served with week-3 content": {"assets/history/week-4.json": json.dumps(dict(relabelled, week=4))},
            "accessor substitutes the served natives": {"assets/curve-widget.js": substitute},
            "prior paired with the served week": {"assets/curve-widget.js": same_week},
            "ESPN prior reads the served week's leg": {"assets/curve-widget.js": espn_served_leg},
            "VORP prior prices the served projections": {"assets/curve-widget.js": vorp_served},
        }
        index = json.loads((DIST / "assets" / "history" / "index.json").read_text(encoding="utf-8")) \
            if (DIST / "assets" / "history" / "index.json").exists() else {}
        if any(r.get("version") == "superseded" for r in (index.get("served") or {}).values()):
            cases["served week read from the week's snapshot, not the served version"] = {
                "assets/curve-widget.js": served_ignored}
        for name, overrides in cases.items():
            with self.subTest(name):
                self.assertNotEqual(collect(overrides), [], f"{name} was not caught")


if __name__ == "__main__":
    unittest.main()
