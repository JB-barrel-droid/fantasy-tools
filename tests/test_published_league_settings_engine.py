"""League-settings engine for published charts (JEG-332 step 3, league-settings-001).

The chart shows a published source's SAVED values at the saved setup (12
teams, standard roster) and derives every other team count / roster from the
saved 12-team inputs with ValueModel.derivePublishedSetup. This test pins
that derivation to an independent Python reference:

  * value above waivers translated at the chosen setting comes from the
    server's own code (unified.translate_ranked);
  * players at or below that setting's waiver line are worth 0 (value above
    waivers is zero by definition; league-settings-001/3, Jeremy 2026-10-07 --
    it replaced the server's fail-safe value: the saved value or the 12-team
    flex-aware pie value);
  * the player set is the saved set at every setting.

Inputs are assembled the way the browser assembles them (fixture
player_keys + the players island in index.html), so an identity mismatch
between the browser and the server's naming-table resolution also fails.

At the saved setup the engine must reproduce the saved values EXACTLY for
every source whose stored translation is current (CBS, FantasyPros); see
risk register JEG332-STORED-DRIFT for USA Today / FantasyCalc.

Discrimination: test_guard_catches_broken_engines mutates value-model.js.
"""
from __future__ import annotations

import functools
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "pipelines" / "lib"))
sys.path.insert(0, str(REPO))

from pipelines.vorp_translation import unified  # noqa: E402

VALUE_MODEL = REPO / "app" / "trade-value-chart" / "assets" / "value-model.js"
DRIVER = REPO / "tests" / "published_engine_driver.js"
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
INDEX = REPO / "app" / "trade-value-chart" / "index.html"
SOURCES = ("cbs", "fantasypros", "usatoday", "fantasycalc")
SCORINGS = ("standard", "half_ppr", "ppr")
POSITIONS = ("QB", "RB", "WR", "TE")
SAVED_SHAPE = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "BENCH": 6}
EXACT_AT_SAVED_SETUP = ("cbs", "fantasypros")  # JEG332-STORED-DRIFT for the others
TOL = 1e-9

SHAPES = [
    ("std", SAVED_SHAPE),
    ("bench8-flex2-rb3", {**SAVED_SHAPE, "RB": 3, "FLEX": 2, "BENCH": 8}),
    ("bench0", {**SAVED_SHAPE, "BENCH": 0}),
    ("qb2-te2", {**SAVED_SHAPE, "QB": 2, "TE": 2}),
    # JEG332-SUPERFLEX-FLEX option A: one dedicated superflex slot.
    ("superflex", {**SAVED_SHAPE, "SUPERFLEX": 1}),
]


def browser_players():
    """canonicalByKey as the widget builds it: island players, QB/RB/WR/TE."""
    html = INDEX.read_text(encoding="utf-8")
    m = re.search(r'<script id="players-data" type="application/json">(.*?)</script>', html, re.S)
    players = json.loads(m.group(1))["players"]
    out = {}
    for p in players:
        key = p.get("player_key")
        name = str(p.get("name") or "").strip()
        if isinstance(key, int) and name and p.get("pos") in POSITIONS:
            out[key] = p["pos"]
    return out


@functools.lru_cache(maxsize=None)
def browser_projection(scoring):
    """ESPN per-game points as the widget passes them (player.espn_ppg[field]),
    from the same players island: {player_key: ppg} for QB/RB/WR/TE."""
    html = INDEX.read_text(encoding="utf-8")
    m = re.search(r'<script id="players-data" type="application/json">(.*?)</script>', html, re.S)
    out = {}
    for p in json.loads(m.group(1))["players"]:
        key = p.get("player_key")
        val = (p.get("espn_ppg") or {}).get(scoring)
        name = str(p.get("name") or "").strip()
        if (isinstance(key, int) and name and p.get("pos") in POSITIONS
                and isinstance(val, (int, float)) and not isinstance(val, bool)):
            out[key] = float(val)
    return out


def expected_max(scoring, teams, shape, pos_of=None):
    """League-following positional maxes (JEG332-DERIVED-PEAKS) from the
    server's own code, on the projections the browser passes."""
    pos_of = pos_of or browser_players()
    proj = {p: [] for p in POSITIONS}
    for key, val in browser_projection(scoring).items():
        proj[pos_of[key]].append((str(key), str(key), val))
    for rows in proj.values():
        rows.sort(key=lambda r: -r[2])
    return unified.positional_max_for_setup(proj, teams, shape["BENCH"], shape["FLEX"],
                                            slots={p: shape[p] for p in POSITIONS},
                                            superflex_count=shape.get("SUPERFLEX", 0))


def browser_inputs(fixture, pos_of, source, scoring):
    """(native, saved, index_total) for the saved 12-team setup, browser-mapped."""
    pk = fixture["player_keys"]
    combo_key = unified.resolve_combo_key(fixture["sources"][source], scoring, 12)
    combo = fixture["sources"][source]["combos"][combo_key]
    native, saved = [], []
    for slug, value in combo["native"].items():
        key = pk.get(slug)
        if isinstance(key, int) and key in pos_of and value is not None:
            native.append((key, float(value)))
    for slug, value in combo["reindexed"].items():
        key = pk.get(slug)
        if isinstance(key, int) and key in pos_of and value is not None:
            saved.append((key, max(0.0, float(value))))
    return native, saved, combo.get("index_total") or {}


def browser_peers(fixture, pos_of, source, scoring):
    """V2-WAIVER-COVERAGE: the OTHER published charts' saved 12-team natives,
    browser-mapped ({peer: [(key, value)]}), as the widget passes them."""
    return {peer: browser_inputs(fixture, pos_of, peer, scoring)[0]
            for peer in SOURCES if peer != source
            and _has_combo(fixture, peer, scoring)}


def _has_combo(fixture, source, scoring):
    try:
        unified.resolve_combo_key(fixture["sources"][source], scoring, 12)
        return True
    except SystemExit:
        return False


def peers_ranked(peers, pos_of):
    """{peer: [(key, value)]} -> translate_ranked's peers argument."""
    out = {}
    for peer, native in peers.items():
        by_pos = {p: [] for p in POSITIONS}
        for key, value in native:
            by_pos[pos_of[key]].append((str(key), float(value)))
        out[peer] = by_pos
    return out


def expected_derived(source, scoring, teams, shape, fixture=None, pos_of=None):
    """Independent reference for the derived published chart (key -> value)."""
    fixture = fixture or json.loads(FIXTURE.read_text())
    pos_of = pos_of or browser_players()
    ranked, key_by_name = unified.load_native_values(source, scoring, 12)
    ranked_keyed = {pos: [(key_by_name[unified.norm_player_name(n)], n, v) for n, v in rows]
                    for pos, rows in ranked.items()}
    native, saved, index_total = browser_inputs(fixture, pos_of, source, scoring)
    if teams == 12 and shape == SAVED_SHAPE:
        return dict(saved)
    slots = {p: shape[p] for p in POSITIONS}
    at = unified.translate_ranked(ranked_keyed, teams, shape["BENCH"], shape["FLEX"], slots=slots,
                                  superflex_count=shape.get("SUPERFLEX", 0),
                                  our_max=expected_max(scoring, teams, shape, pos_of),
                                  peers=peers_ranked(browser_peers(fixture, pos_of, source, scoring),
                                                     pos_of))
    out = {}
    for key, _value in saved:
        t = at["translated"].get(str(key))
        out[key] = t["translated"] if t is not None else 0.0
    return out


@functools.lru_cache(maxsize=None)
def saved_setup_translated_keys(source, scoring):
    """Player keys (str) the server's own translation prices above the
    waiver line at the saved setup (12 teams, standard roster)."""
    ranked, key_by_name = unified.load_native_values(source, scoring, 12)
    ranked_keyed = {pos: [(key_by_name[unified.norm_player_name(n)], n, v) for n, v in rows]
                    for pos, rows in ranked.items()}
    peers = peers_ranked(browser_peers(json.loads(FIXTURE.read_text()), browser_players(),
                                       source, scoring), browser_players())
    return frozenset(unified.translate_ranked(ranked_keyed, 12, peers=peers)["translated"])


def _cases(fixture, pos_of, settings):
    cases = []
    for source, scoring, teams, label, shape in settings:
        native, saved, index_total = browser_inputs(fixture, pos_of, source, scoring)
        projection = sorted(browser_projection(scoring).items())
        peers = browser_peers(fixture, pos_of, source, scoring)
        peer_rows = [row for rows in peers.values() for row in rows]
        cases.append({"source": source, "scoring": scoring, "teams": teams, "label": label,
                      "shape": shape, "native": native, "saved": saved,
                      "index_total": index_total, "projection": projection, "peers": peers,
                      "pos": {str(k): pos_of[k] for k, _ in native + saved + projection + peer_rows}})
    return cases


def run_js(cases, model_path=VALUE_MODEL):
    proc = subprocess.run(["node", str(DRIVER), str(model_path)],
                          input=json.dumps({"cases": cases}),
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise AssertionError(f"node driver failed: {proc.stderr[:2000]}")
    return json.loads(proc.stdout)["results"]


def compare_maps(expected, got):
    """Return (problems, max_abs_diff) comparing key->value maps."""
    problems, max_diff = [], 0.0
    if set(expected) != set(got):
        problems.append(f"player sets differ: missing={sorted(set(expected) - set(got))[:5]} "
                        f"extra={sorted(set(got) - set(expected))[:5]}")
    for key in set(expected) & set(got):
        d = abs(float(expected[key]) - float(got[key]))
        max_diff = max(max_diff, d)
        if d > TOL:
            problems.append(f"{key}: expected {expected[key]} got {got[key]}")
    return problems, max_diff


def all_settings():
    out = []
    for source in SOURCES:
        for scoring in SCORINGS:
            for teams in (8, 10, 12, 14):
                for label, shape in SHAPES:
                    out.append((source, scoring, teams, label, shape))
    return out


def run_engine(settings, model_path=VALUE_MODEL):
    fixture = json.loads(FIXTURE.read_text())
    pos_of = browser_players()
    cases = _cases(fixture, pos_of, settings)
    results = run_js(cases, model_path)
    failures, max_diff, n = [], 0.0, 0
    for case, res, setting in zip(cases, results, settings):
        source, scoring, teams, label, shape = setting
        if "error" in res:
            failures.append(f"{source}/{scoring}/{teams}/{label}: JS raised {res['error']}")
            continue
        got = {int(k): v for k, v in res["values"].items()}
        if teams == 12 and shape == SAVED_SHAPE:
            # The engine at the saved setup vs what is SAVED, for every player
            # the server translated (above the 12-team waiver line). Since
            # league-settings-001/3 the engine prices the rest at 0 while the
            # saved fixture still carries the server's fail-safe for them; the
            # chart never runs the engine at the saved setup (it reads the
            # saved values), so only the translated players must match.
            if source not in EXACT_AT_SAVED_SETUP:
                continue
            base = saved_setup_translated_keys(source, scoring)
            expected = {k: (v if str(k) in base else 0.0) for k, v in case["saved"]}
        else:
            expected = expected_derived(source, scoring, teams, shape, fixture, pos_of)
        problems, d = compare_maps(expected, got)
        max_diff, n = max(max_diff, d), n + len(expected)
        if problems:
            failures.append(f"{source}/{scoring}/{teams}/{label}: {problems[:3]}")
    return failures, max_diff, n, results


class PublishedLeagueSettingsEngine(unittest.TestCase):
    def test_engine_matches_reference_at_every_setting(self):
        failures, max_diff, n, results = run_engine(all_settings())
        print(f"\n[JEG-332 engine] settings={len(all_settings())} values_compared={n} "
              f"max_abs_diff={max_diff} failures={len(failures)}")
        self.assertEqual(failures, [], "\n".join(failures[:20]))
        self.assertLessEqual(max_diff, TOL)
        self.assertGreater(n, 20000)
        self.assertEqual({r["version"] for r in results}, {"league-settings-001/5"})
        self.assertEqual({r["positionalMax"] for r in results}, {unified.POSITIONAL_MAX_VERSION})
        # Every value the chart would plot is finite and non-negative.
        for r in results:
            self.assertTrue(all(v >= 0 for v in r["values"].values()))

    def test_saved_setup_is_exactly_the_standard_12_team_roster(self):
        fixture = json.loads(FIXTURE.read_text())
        pos_of = browser_players()
        probe = [("cbs", "ppr", t, label, shape) for t in (8, 12, 14)
                 for label, shape in SHAPES]
        res = run_js(_cases(fixture, pos_of, probe))
        flags = {(t, label): r["savedSetup"] for (_, _, t, label, _), r in zip(probe, res)}
        self.assertEqual([k for k, v in flags.items() if v], [(12, "std")])

    def test_below_waiver_players_are_zero(self):
        """At 8 teams fewer players clear the waiver line than at 12; every
        player at or below it is worth exactly 0 -- not the saved 12-team value
        and not the 12-team pie value (league-settings-001/3). Replaces the
        pre-2026-10-07 pin of the server's fail-safe, which Jeremy reversed."""
        fixture = json.loads(FIXTURE.read_text())
        pos_of = browser_players()
        for source in SOURCES:
            case = _cases(fixture, pos_of, [(source, "ppr", 8, "std", SAVED_SHAPE)])
            res = run_js(case)[0]
            saved = dict(case[0]["saved"])
            zeros = [int(k) for k, v in res["values"].items() if v == 0]
            self.assertGreater(res["belowWaiver"], 0, source)
            self.assertEqual(res["belowWaiver"], len(zeros), source)
            # Those players had a positive saved value: the rule moved them.
            self.assertTrue(any(saved[k] > 0 for k in zeros), source)

    def test_guard_catches_broken_engines(self):
        source = VALUE_MODEL.read_text()
        mutations = {
            # below-waiver players keep their saved 12-team value (pre-/3 fail-safe)
            "below-waiver-keeps-saved": ("values.set(key, 0); counts.belowWaiver += 1;",
                                         "values.set(key, Number(savedValue)); counts.belowWaiver += 1;"),
            # translation ignored: every player zero
            "translation-dropped": ("if (t) { values.set(key, t.translated);", "if (false) { values.set(key, t.translated);"),
            # bench stepper ignored by the translation
            "bench-ignored": ("benchPerTeam: Number(shape.BENCH),", "benchPerTeam: 6,"),
            # saved-setup test ignores the roster
            "saved-setup-teams-only": ("if (Number(teams) !== SAVED_SETUP_TEAMS) return false;",
                                       "if (Number(teams) === SAVED_SETUP_TEAMS) return true;"),
            # JEG332-DERIVED-PEAKS: projection ignored -> maxes back to fixed OUR_MAX
            "maxes-fixed": ("if (opts.projection && opts.projection.size) {", "if (false) {"),
        }
        settings = [s for s in all_settings() if s[0] == "cbs" and s[1] == "ppr"]
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in mutations.items():
                self.assertEqual(source.count(old), 1, f"mutation anchor for {name} moved")
                broken = Path(tmp) / f"value-model-{name}.js"
                broken.write_text(source.replace(old, new))
                failures = run_engine(settings, broken)[0]
                if name == "saved-setup-teams-only":
                    res = run_js(_cases(json.loads(FIXTURE.read_text()), browser_players(),
                                        [("cbs", "ppr", 12, "bench0", {**SAVED_SHAPE, "BENCH": 0})]),
                                 broken)
                    failures = failures + ([] if not res[0].get("savedSetup") else ["savedSetup at bench0"])
                print(f"\n[JEG-332 engine negative test] {name}: {len(failures)} failing settings")
                self.assertGreater(len(failures), 0, f"mutation {name} was NOT caught")


if __name__ == "__main__":
    unittest.main()
