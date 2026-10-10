"""Published-chart reference helpers and the saved-setup rule (JEG-332 step 3, league-settings-001).

The backend saves ONE setup per scoring (12 teams, standard roster). The
widget asks ValueModel.isSavedSetup whether the reader's league is that
setup; every published chart value comes from runValuePipeline (JEG-508,
VP-6.4: the chart's natives times one factor).

This module keeps the independent Python reference for a published chart's
Indexed values at a setting (one_factor, expected_derived: ONE factor per
chart, so the chart keeps its own order, JEG-482) and the browser-mapped
fixture readers that the render and superflex tests import.

JEG-539 retired the browser derivation it used to pin
(ValueModel.derivePublishedSetup, league-settings-001/6), its node driver and
the engine-vs-reference tests: nothing on the page called it after JEG-508.
What stays tested here is the live saved-setup rule, with a broken engine
that must be caught.
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
    """Python reference for a published chart's Indexed values at a setting
    (one factor per chart, JEG-482; formerly pinned to the retired
    ValueModel.derivePublishedSetup /6).
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


SAVED_SETUP_DRIVER = r"""
const VM = require(process.argv[1]);
const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(cases.map(c => VM.isSavedSetup(c.teams, c.shape))));
"""


def saved_setup_flags(model_path=VALUE_MODEL, teams=(8, 12, 14)):
    """{(teams, shape label): ValueModel.isSavedSetup} over SHAPES."""
    probe = [(t, label, shape) for t in teams for label, shape in SHAPES]
    proc = subprocess.run(["node", "-e", SAVED_SETUP_DRIVER, str(model_path)],
                          input=json.dumps([{"teams": t, "shape": shape} for t, _, shape in probe]),
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError(f"node driver failed: {proc.stderr[:2000]}")
    return {(t, label): flag for (t, label, _), flag in zip(probe, json.loads(proc.stdout))}


class SavedSetupRule(unittest.TestCase):
    def test_saved_setup_is_exactly_the_standard_12_team_roster(self):
        flags = saved_setup_flags()
        self.assertEqual([k for k, v in flags.items() if v], [(12, "std")])

    def test_guard_catches_a_teams_only_saved_setup(self):
        source = VALUE_MODEL.read_text(encoding="utf-8")
        old = "if (Number(teams) !== SAVED_SETUP_TEAMS) return false;"
        self.assertEqual(source.count(old), 1, "mutation anchor moved")
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "value-model-saved-setup-teams-only.js"
            broken.write_text(source.replace(old, "if (Number(teams) === SAVED_SETUP_TEAMS) return true;"))
            flags = saved_setup_flags(broken)
        self.assertNotEqual([k for k, v in flags.items() if v], [(12, "std")])


class DerivationRetired(unittest.TestCase):
    """JEG-539: the retired browser derivation stays gone from the engine."""

    def test_engine_has_no_published_derivation(self):
        source = VALUE_MODEL.read_text(encoding="utf-8")
        for name in ("function derivePublishedSetup", "function derivePublishedViews",
                     "function publishedWaiverInfo", "PUBLISHED_DERIVATION_VERSION",
                     "PUBLISHED_VIEWS_VERSION"):
            self.assertNotIn(name, source)


if __name__ == "__main__":
    unittest.main()
