"""League-settings engine for published charts (JEG-332 step 3, league-settings-001).

The chart shows a published source's SAVED values at the saved setup (12
teams, standard roster) and derives every other team count / roster from the
saved 12-team natives with ValueModel.derivePublishedSetup. Since /6 (JEG-482,
Jeremy 2026-10-08: "There shouldn't be some secondary correction layer, the
math is clearly off") that derivation is ONE factor per chart:

  factor  = anchor total / native total over the saved players the live
            anchor prices (the saved factor when it prices fewer than
            MIN_SHARED_FOR_PIE of them)
  indexed = native x factor -- the chart's own order, every setting.

This test pins it to an independent Python reference on browser-mapped inputs
(fixture player_keys + the players island in index.html), with the fixture's
ESPN leg as the anchor (scaled per team count so the factor moves), and:

  * with the fixture's own ESPN leg at the saved setup the engine reproduces
    the SAVED values exactly -- the browser and the pipeline
    (reindex_comparison_section.order_preserving_rescale) are one formula;
  * the order equals the native order at every setting (zero inversions).

Replaced the /1-/5 reference (value above waivers translated onto our
positional maxes), which reordered players across positions.

Discrimination: test_guard_catches_broken_engines mutates value-model.js.
"""
from __future__ import annotations

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


COMBO_PREFIX = {"standard": "standard", "half_ppr": "half", "ppr": "full"}


def fixture_anchor(fixture, pos_of, scoring, teams=12):
    """The fixture's ESPN leg at this scoring as [(key, value)], scaled by
    teams / 12 so the factor differs by setting (the widget passes its live
    anchor; the engine only needs some anchor map)."""
    pk = fixture["player_keys"]
    values = fixture["sources"]["espn"]["combos"][f"{COMBO_PREFIX[scoring]}_12"]["values"]
    out = []
    for slug, value in values.items():
        key = pk.get(slug)
        if isinstance(key, int) and key in pos_of and isinstance(value, (int, float)):
            out.append((key, float(value) * teams / 12.0))
    return out


def browser_inputs(fixture, pos_of, source, scoring, superflex=False):
    """(native, saved, index_total) for the saved 12-team setup, browser-mapped.
    superflex=True overlays the publisher's own superflex values
    (`native_superflex`) on the natives, as curve-widget.js
    savedPublishedNative does when the roster has a superflex slot
    (GAP-SUPERFLEX-PUBLISHER-VALUES)."""
    pk = fixture["player_keys"]
    combo_key = unified.resolve_combo_key(fixture["sources"][source], scoring, 12)
    combo = fixture["sources"][source]["combos"][combo_key]
    natives = combo["native"]
    if superflex and natives and combo.get("native_superflex"):
        natives = {**natives, **combo["native_superflex"]}
    native, saved = [], []
    for slug, value in natives.items():
        key = pk.get(slug)
        if isinstance(key, int) and key in pos_of and value is not None:
            native.append((key, float(value)))
    for slug, value in combo["reindexed"].items():
        key = pk.get(slug)
        if isinstance(key, int) and key in pos_of and value is not None:
            saved.append((key, max(0.0, float(value))))
    return native, saved, combo.get("index_total") or {}


def browser_peers(fixture, pos_of, source, scoring, superflex=False):
    """V2-WAIVER-COVERAGE: the OTHER published charts' saved 12-team natives,
    browser-mapped ({peer: [(key, value)]}), as the widget passes them."""
    return {peer: browser_inputs(fixture, pos_of, peer, scoring, superflex)[0]
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


MIN_SHARED_FOR_PIE = 40


def one_factor(native, saved, anchor):
    """Python reference for ValueModel.derivePublishedSetup /6.
    native, saved: {key: value}; anchor: {key: value} or None."""
    keys = [k for k in saved if k in native]
    shared = [k for k in keys if anchor is not None and k in anchor]
    a_total = sum(max(0.0, anchor[k]) for k in shared)
    n_total = sum(max(0.0, native[k]) for k in shared)
    if len(shared) < MIN_SHARED_FOR_PIE or a_total <= 0 or n_total <= 0:
        a_total = sum(max(0.0, saved[k]) for k in keys)
        n_total = sum(max(0.0, native[k]) for k in keys)
    factor = a_total / n_total if a_total > 0 and n_total > 0 else 0.0
    return {k: max(0.0, native[k]) * factor for k in keys}


def expected_derived(source, scoring, teams, shape, fixture=None, pos_of=None, anchor=None):
    """Independent reference for the published chart's Indexed values at a
    setting (key -> value). anchor: {key: value} -- the page's live anchor in
    the render tests; default the fixture's ESPN leg scaled like _cases."""
    fixture = fixture or json.loads(FIXTURE.read_text(encoding="utf-8"))
    pos_of = pos_of or browser_players()
    superflex = shape.get("SUPERFLEX", 0) > 0
    native, saved, _ = browser_inputs(fixture, pos_of, source, scoring, superflex)
    if teams == 12 and shape == SAVED_SHAPE:
        return dict(saved)
    if anchor is None:
        anchor = dict(fixture_anchor(fixture, pos_of, scoring, teams))
    return one_factor(dict(native), dict(saved), anchor)


def _cases(fixture, pos_of, settings):
    cases = []
    for source, scoring, teams, label, shape in settings:
        # With a superflex slot the widget overlays every chart's own
        # native_superflex (savedPublishedNative), for the chart and its peers.
        superflex = shape.get("SUPERFLEX", 0) > 0
        native, saved, index_total = browser_inputs(fixture, pos_of, source, scoring, superflex)
        anchor = fixture_anchor(fixture, pos_of, scoring, teams)
        cases.append({"source": source, "scoring": scoring, "teams": teams, "label": label,
                      "shape": shape, "native": native, "saved": saved,
                      "index_total": index_total, "anchor": anchor,
                      "pos": {str(k): pos_of[k] for k, _ in native + saved + anchor}})
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


def inversions(native, values):
    """Pairs the chart ranks strictly apart whose engine order is not the same."""
    keys = sorted((k for k in values if k in native), key=lambda k: -native[k])
    bad = 0
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if native[a] != native[b] and not values[a] > values[b]:
                bad += 1
    return bad


def run_engine(settings, model_path=VALUE_MODEL):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pos_of = browser_players()
    cases = _cases(fixture, pos_of, settings)
    results = run_js(cases, model_path)
    failures, max_diff, n = [], 0.0, 0
    for case, res, setting in zip(cases, results, settings):
        source, scoring, teams, label, shape = setting
        tag = f"{source}/{scoring}/{teams}/{label}"
        if "error" in res:
            failures.append(f"{tag}: JS raised {res['error']}")
            continue
        got = {int(k): v for k, v in res["values"].items()}
        expected = one_factor(dict(case["native"]), dict(case["saved"]), dict(case["anchor"]))
        problems, d = compare_maps(expected, got)
        max_diff, n = max(max_diff, d), n + len(expected)
        if problems:
            failures.append(f"{tag}: {problems[:3]}")
        bad = inversions(dict(case["native"]), got)
        if bad:
            failures.append(f"{tag}: {bad} order inversions against the native order")
    return failures, max_diff, n, results


class PublishedLeagueSettingsEngine(unittest.TestCase):
    def test_engine_matches_reference_at_every_setting(self):
        failures, max_diff, n, results = run_engine(all_settings())
        print(f"\n[JEG-482 engine] settings={len(all_settings())} values_compared={n} "
              f"max_abs_diff={max_diff} failures={len(failures)}")
        self.assertEqual(failures, [], "\n".join(failures[:20]))
        self.assertLessEqual(max_diff, TOL)
        self.assertGreater(n, 20000)
        self.assertEqual({r["version"] for r in results}, {"league-settings-001/6"})
        self.assertEqual({r["basis"] for r in results}, {"anchor"})
        for r in results:
            self.assertTrue(all(v >= 0 for v in r["values"].values()))

    def test_saved_setup_is_exactly_the_standard_12_team_roster(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        pos_of = browser_players()
        probe = [("cbs", "ppr", t, label, shape) for t in (8, 12, 14)
                 for label, shape in SHAPES]
        res = run_js(_cases(fixture, pos_of, probe))
        flags = {(t, label): r["savedSetup"] for (_, _, t, label, _), r in zip(probe, res)}
        self.assertEqual([k for k, v in flags.items() if v], [(12, "std")])

    def test_fixture_leg_reproduces_the_saved_values(self):
        """The pipeline and the browser are one formula: with the fixture's
        own ESPN leg as the anchor, at the saved setup, the engine returns the
        saved Indexed values for every chart and scoring."""
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        pos_of = browser_players()
        settings = [(src, sc, 12, "std", SAVED_SHAPE) for src in SOURCES for sc in SCORINGS]
        results = run_js(_cases(fixture, pos_of, settings))
        for (src, sc, *_), res, case in zip(settings, results, _cases(fixture, pos_of, settings)):
            got = {int(k): v for k, v in res["values"].items()}
            saved = dict(case["saved"])
            self.assertEqual(set(got), set(saved), f"{src}/{sc}")
            worst = max(abs(got[k] - saved[k]) / max(1.0, saved[k]) for k in saved)
            self.assertLess(worst, 1e-9, f"{src}/{sc}")

    def test_thin_anchor_keeps_the_saved_factor(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        pos_of = browser_players()
        case = _cases(fixture, pos_of, [("usatoday", "ppr", 8, "std", SAVED_SHAPE)])[0]
        case["anchor"] = case["anchor"][:10]
        res = run_js([case])[0]
        self.assertEqual(res["basis"], "saved")
        got = {int(k): v for k, v in res["values"].items()}
        saved = dict(case["saved"])
        self.assertLess(max(abs(got[k] - saved[k]) for k in saved), 1e-9)

    def test_superflex_cases_carry_publisher_superflex_values(self):
        """With a superflex slot the engine gets the overlaid natives the
        widget passes (curve-widget.js savedPublishedNative); the 1-QB
        natives must give different values."""
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        pos_of = browser_players()
        carriers = [s for s in SOURCES
                    if fixture["sources"][s]["combos"][unified.resolve_combo_key(
                        fixture["sources"][s], "ppr", 12)].get("native_superflex")]
        if not carriers:
            self.skipTest("fixture carries no native_superflex")
        sf_shape = dict(SHAPES)["superflex"]
        for source in carriers:
            case = _cases(fixture, pos_of, [(source, "ppr", 12, "superflex", sf_shape)])[0]
            one_qb = browser_inputs(fixture, pos_of, source, "ppr")[0]
            self.assertNotEqual(case["native"], one_qb, source)
            got = {int(k): v for k, v in run_js([case])[0]["values"].items()}
            problems, _ = compare_maps(expected_derived(source, "ppr", 12, sf_shape, fixture, pos_of), got)
            self.assertEqual(problems, [], source)
            stale = {**case, "native": one_qb}
            got = {int(k): v for k, v in run_js([stale])[0]["values"].items()}
            problems, _ = compare_maps(expected_derived(source, "ppr", 12, sf_shape, fixture, pos_of), got)
            self.assertGreater(len(problems), 0, f"{source}: 1-QB inputs not caught")

    def test_guard_catches_broken_engines(self):
        source = VALUE_MODEL.read_text(encoding="utf-8")
        mutations = {
            # the removed layer: a per-position correction on top of the factor
            "per-position-factor": (
                "keys.forEach(function (key) { values.set(key, Math.max(0, Number(native.get(key))) * factor); });",
                "keys.forEach(function (key) { values.set(key, Math.max(0, Number(native.get(key))) * factor"
                " * (posOf(key) === \"RB\" ? 1.25 : 1)); });"),
            # the live anchor ignored: always the saved 12-team factor
            "anchor-ignored": ("    if (anchor && anchor.size) {", "    if (false) {"),
            # saved-setup test ignores the roster
            "saved-setup-teams-only": ("if (Number(teams) !== SAVED_SETUP_TEAMS) return false;",
                                       "if (Number(teams) === SAVED_SETUP_TEAMS) return true;"),
        }
        settings = [s for s in all_settings() if s[0] == "cbs" and s[1] == "ppr"]
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in mutations.items():
                self.assertEqual(source.count(old), 1, f"mutation anchor for {name} moved")
                broken = Path(tmp) / f"value-model-{name}.js"
                broken.write_text(source.replace(old, new))
                failures = run_engine(settings, broken)[0]
                if name == "saved-setup-teams-only":
                    res = run_js(_cases(json.loads(FIXTURE.read_text(encoding="utf-8")), browser_players(),
                                        [("cbs", "ppr", 12, "bench0", {**SAVED_SHAPE, "BENCH": 0})]),
                                 broken)
                    failures = failures + ([] if not res[0].get("savedSetup") else ["savedSetup at bench0"])
                print(f"\n[JEG-482 engine negative test] {name}: {len(failures)} failing settings")
                self.assertGreater(len(failures), 0, f"mutation {name} was NOT caught")


if __name__ == "__main__":
    unittest.main()
