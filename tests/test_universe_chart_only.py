"""GAP-UNIVERSE-CHART-ONLY (Jeremy, 2026-10-08): a player any current-week
published chart (or projection source) prices gets a row, even when ESPN's
list does not carry him. ESPN then shows "—" (missing, "not on ESPN's
list"), never 0, unless ESPN explicitly lists him at 0 ("ineligible").

Tyreek Hill (player_key 3081) is the case that exposed it: CBS Week 5 prices
him at 8.0 PPR, but he was in neither players.json nor the comparison
fixture's player_keys, so the CBS section dropped him and no page showed him.
"""
import copy
import csv
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import bake_players  # noqa: E402
import build_comparison_source_section as section_builder  # noqa: E402
import sync_universe_keys  # noqa: E402

TYREEK = 3081
FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"


def _reg():
    return bake_players.load_registry(rows=[
        {"player_key": 1, "full_name": "Priced Star", "position": "WR", "active": True},
        {"player_key": 2, "full_name": "Ir Back", "position": "RB", "active": True},
        {"player_key": TYREEK, "full_name": "Tyreek Hill", "position": "WR", "active": True},
        {"player_key": 4, "full_name": "Some Kicker", "position": "K", "active": True},
        {"player_key": 5, "full_name": "Deep Back", "position": "RB", "active": True},
    ])


def _csv(rows):
    fd, p = tempfile.mkstemp(suffix=".csv", text=True)
    cols = ["player", "pos", "team", "eligible"]
    with os.fdopen(fd, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    return p


def _cbs_snapshot(tmp, rows, superflex=None):
    d = Path(tmp) / "cbs" / "week-5"
    d.mkdir(parents=True)
    snap = {"source": "cbs", "rows": rows, "default_teams": 12}
    if superflex is not None:
        snap["superflex_rows"] = superflex
    (d / "snapshot.json").write_text(json.dumps(snap), encoding="utf-8")
    (d / "snapshot-manifest.json").write_text(json.dumps(
        {"week_designated": "Week 5", "content_vintage": "Week 5"}), encoding="utf-8")
    return d / "snapshot.json"


def _row(name, key, pos, value, scoring="ppr"):
    return {"player_name": name, "source_player_id": key, "pos": pos,
            "scoring": scoring, "teams": 12, "value": value, "native_value": value}


class ChartUniverseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_chart_only_player_is_priced_and_counted_in_depth(self):
        _cbs_snapshot(self.tmp, [
            _row("Priced Star", 1, "WR", 30.0),
            _row("Tyreek Hill", TYREEK, "WR", 8.0),
            _row("Some Kicker", 4, "K", 1.0),
            _row("Nobody Known", 999, "WR", 2.0),
        ])
        snaps = bake_players.latest_chart_snapshots(self.tmp)
        priced, depth = bake_players.published_chart_universe(snaps, _reg())
        self.assertEqual({1, TYREEK}, set(priced))           # K and unknowns excluded
        self.assertEqual(["cbs"], priced[TYREEK]["sources"])
        self.assertEqual("Week 5", depth["cbs"]["week"])
        self.assertEqual(2, depth["cbs"]["by_combo"]["ppr-12"]["WR"])
        self.assertEqual(0, depth["cbs"]["by_combo"]["ppr-12"]["RB"])

    def test_name_only_rows_resolve_through_the_canonical_table(self):
        # A file-built snapshot row has no canonical key: the name resolves.
        _cbs_snapshot(self.tmp, [{"player_name": "Tyreek Hill", "pos": "WR",
                                  "scoring": "ppr", "teams": 12, "value": 8.0}])
        priced, _ = bake_players.published_chart_universe(
            bake_players.latest_chart_snapshots(self.tmp), _reg())
        self.assertIn(TYREEK, priced)

    def test_superflex_only_player_counts_but_not_in_one_qb_depth(self):
        _cbs_snapshot(self.tmp, [_row("Priced Star", 1, "WR", 30.0)],
                      superflex=[_row("Tyreek Hill", TYREEK, "WR", 6.0)])
        priced, depth = bake_players.published_chart_universe(
            bake_players.latest_chart_snapshots(self.tmp), _reg())
        self.assertEqual(["cbs:superflex"], priced[TYREEK]["sources"])
        self.assertEqual(1, depth["cbs"]["by_combo"]["ppr-12"]["WR"])

    def test_chart_only_player_gets_an_absent_row_not_an_espn_zero(self):
        espn_csv = _csv([{"player": "Priced Star", "pos": "WR", "eligible": "True"},
                         {"player": "Ir Back", "pos": "RB", "eligible": "False"}])
        espn_med = {1: {"comps": {"receptions": 1.0}, "pos": "WR", "team": "BUF"}}
        out = bake_players.espn_zero_universe(
            espn_csv, None, espn_med, _reg(),
            priced_elsewhere={TYREEK: ["cbs"], 2: ["cbs"], 1: ["cbs"], 4: ["cbs"]})
        # Regression caught: Tyreek had no row at all.
        self.assertEqual("absent", out[TYREEK]["espn_status"])
        self.assertEqual(["cbs"], out[TYREEK]["universe_sources"])
        # ESPN explicitly lists Ir Back at 0: that stays ESPN's 0.
        self.assertEqual("ineligible", out[2]["espn_status"])
        # ESPN-priced players are never duplicated; K is not carried.
        self.assertNotIn(1, out)
        self.assertNotIn(4, out)

    def test_projection_universe_needs_a_positive_projection(self):
        out = bake_players.projection_universe({
            "razzball": {5: {"standard": 1.0, "half_ppr": 1.2, "ppr": 1.4},
                         6: {"standard": 0.0, "half_ppr": 0.0, "ppr": 0.0}},
            "cbsros": {5: {"standard": 1.0, "half_ppr": 1.0, "ppr": 1.0}}})
        self.assertEqual({5: ["cbsros", "razzball"]}, out)


class FixtureKeysTest(unittest.TestCase):
    """The section builder keys a chart row only through the fixture's
    player_keys; a players.json player without a slug was dropped there."""

    def _reference(self, tmp):
        ref = {
            "schema": section_builder.INPUT_SCHEMA,
            "source": "cbs",
            "fetched_at": "2026-10-08T11:36:55Z",
            "source_provenance": {"content_vintage": "Week 5"},
            "rows": [{"player_key": TYREEK, "canonical_name": "Tyreek Hill",
                      "scoring": "ppr", "teams": 12, "value": 8.0, "native_value": 8.0}],
        }
        p = Path(tmp) / "cbs-reference.json"
        p.write_text(json.dumps(ref), encoding="utf-8")
        return p

    def test_chart_only_player_gets_the_charts_value_in_the_section(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for slug, key in list(fixture["player_keys"].items()):
            if key == TYREEK:  # start from the pre-fix universe
                del fixture["player_keys"][slug]
        fixture_path = Path(tmp) / "comparison-sources-data.json"
        fixture_path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
        players_path = Path(tmp) / "players.json"
        players_path.write_text(json.dumps({"players": [
            {"player_key": TYREEK, "name": "Tyreek Hill", "pos": "WR", "team": "MIA",
             "espn_status": "absent"}]}), encoding="utf-8")

        added = sync_universe_keys.sync_files(players_path, fixture_path)
        self.assertEqual([("tyreek hill", TYREEK)], added)

        section = section_builder.build_section(
            self._reference(tmp), fixture_path, section_key="cbs", meta={})
        combo = section["combos"]["full_12"]
        self.assertEqual(8.0, combo["native"]["tyreek hill"])
        self.assertEqual(TYREEK, combo["player_keys"]["tyreek hill"])

    def test_sync_only_adds_and_never_rekeys(self):
        fixture = {"player_keys": {"tyreek hill": 77}, "display": {}, "teams": {}}
        before = copy.deepcopy(fixture["player_keys"])
        added = sync_universe_keys.sync(fixture, [
            {"player_key": TYREEK, "name": "Tyreek Hill", "team": "MIA"},
            {"player_key": 77, "name": "Someone Else"}])
        self.assertEqual([("tyreek hill-3081", TYREEK)], added)
        self.assertEqual(77, fixture["player_keys"]["tyreek hill"])
        self.assertTrue(set(before.items()) <= set(fixture["player_keys"].items()))


class CommittedUniverseTest(unittest.TestCase):
    """Data check (fails until the chain re-bakes with the expanded universe):
    every player the served week's published charts price has a players.json
    row and a fixture slug. Tyreek Hill is the named case."""

    def test_every_published_chart_player_has_a_row(self):
        index = json.loads((ROOT / "data" / "history" / "index.json").read_text(encoding="utf-8"))
        players = {p["player_key"] for p in
                   json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]}
        fixture_keys = set(json.loads(FIXTURE.read_text(encoding="utf-8"))["player_keys"].values())
        missing = {}
        for source in bake_players.PUBLISHED_CHART_SOURCES:
            week = ((index.get("served") or {}).get(source) or {}).get("week")
            path = ROOT / "data" / "history" / f"week-{week}.json"
            if not week or not path.is_file():
                continue
            entry = json.loads(path.read_text(encoding="utf-8"))["sources"].get(source) or {}
            keys = {int(k) for cells in (entry.get("natives") or {}).values() for k in cells}
            gone = sorted(k for k in keys if k not in players or k not in fixture_keys)
            if gone:
                missing[source] = gone
        self.assertEqual({}, missing)


if __name__ == "__main__":
    unittest.main()
