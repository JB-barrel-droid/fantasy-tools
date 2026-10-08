"""Published charts in the "VORP vs waivers" and "Adjusted values" views at any
league setting (JEG332-VORP-VIEWS, published-views-001/1).

ValueModel.derivePublishedViews derives both views for every published chart
from its saved 12-team native values, at whatever scoring / team count / roster
the reader picks:

  * VORP vs waivers: value above the setting's waiver line, from the server's
    own translation (unified.translate_ranked `vorp`), times one factor per
    chart so its total equals the anchor's total (no re-tiering).
  * Adjusted values: grouped position x role (starter = dedicated + flex
    count at the position, bench = the rest of the rostered players); each
    group shares the anchor's group total in proportion to value above
    waivers; then one factor puts the batch's top player at 70.
  Below the waiver line: 0 in both.

This test pins the JS to an independent Python reference built on
unified.translate_ranked, on the same browser-mapped fixture inputs the engine
test uses, for 4 sources x 3 scorings x 8/10/12/14 teams x 4 roster shapes,
and checks the invariants a reader relies on (group totals = the anchor's,
adjusted top = 70, zero exactly where the Indexed engine is zero).

Discrimination: test_guard_catches_broken_views mutates value-model.js.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_published_league_settings_engine import (
    DRIVER, FIXTURE, POSITIONS, SCORINGS, SHAPES, SOURCES, VALUE_MODEL,
    _cases, browser_inputs, browser_players, peers_ranked, run_js,
)
from pipelines.vorp_translation import unified
from pipelines import value_reference

TOL = 1e-9


def budgets_for(teams, shape, n_players):
    """Deterministic, setting- and chart-dependent anchor group totals (the
    views take them as an input; the widget measures them off the live anchor
    over each chart's player set)."""
    base = {"QB": (14.0, 2.0), "RB": (60.0, 11.0), "WR": (58.0, 10.0), "TE": (13.0, 2.0)}
    cover = n_players / 250.0
    out = {}
    for pos, (starter, bench) in base.items():
        out[pos] = {"starter": starter * teams * (shape[pos] + 0.5 * shape["FLEX"]) / 3.0,
                    "bench": bench * teams * (shape["BENCH"] + 1) / 7.0 * cover}
    return out


def expected_views(inputs, teams, shape, pos_of):
    """Independent reference: {src: {"vorp": {key: v}, "adj": {key: v}}}.
    inputs: {src: (native [(key, value)], keys [key], budgets)}. The math is
    the production reference's (pipelines/value_reference.derive_views, the
    one the chain's engine-vs-reference check runs, JEG-479)."""
    batch = {src: (dict(native), list(keys), budgets) for src, (native, keys, budgets) in inputs.items()}
    natives = {src: dict(native) for src, (native, _k, _b) in inputs.items()}
    return value_reference.derive_views(batch, natives, lambda k: pos_of[int(k)], teams, shape)


INDEXED_PRECISION = 0.1  # translate_ranked rounds `translated` to 1 decimal


def rounding_band_violations(native, keys, teams, shape, pos_of, our_max, peers=None):
    """Players in `keys` (Indexed 0, views non-zero) that are NOT explained by
    the Indexed engine's 0.1 rounding. A key is explained only if the server's
    own translation, at this setting and on the Indexed engine's own positional
    maxes, prices it strictly above the waiver line with an UNROUNDED Indexed
    value below half the precision (so it displays as 0.0). How many such
    players exist depends on each week's data (a publisher on a large native
    scale has more of them); which players qualify does not.
    native: [(key, value)]; our_max: the Indexed engine's maxes (driver's
    ourMax). Unrounded values come from translate_ranked with every max scaled
    by 1e6: its 0.1 rounding then lands at 1e-7 of our scale."""
    if not keys:
        return []
    boost = 1e6
    ranked = {p: [] for p in POSITIONS}
    for key, value in native:
        ranked[pos_of[key]].append((str(key), str(key), float(value)))
    for p in POSITIONS:
        ranked[p].sort(key=lambda r: -r[2])
    at = unified.translate_ranked(ranked, teams, shape["BENCH"], shape["FLEX"],
                                  slots={p: shape[p] for p in POSITIONS},
                                  superflex_count=shape.get("SUPERFLEX", 0),
                                  our_max={p: float(our_max[p]) * boost for p in POSITIONS},
                                  peers=peers_ranked(peers or {}, pos_of))
    out = []
    for key in sorted(keys, key=str):
        t = at["translated"].get(str(key))
        if t is None:
            out.append(f"{key}: at/below the waiver line but priced in the views")
            continue
        unrounded = t["translated"] / boost
        if not 0 < unrounded < INDEXED_PRECISION / 2:
            out.append(f"{key}: Indexed 0 but unrounded Indexed value is {unrounded:.6f}")
    return out


READER_SETTINGS = [("ppr", 8, "std", SHAPES[0][1]), ("standard", 14, "qb2-te2", SHAPES[3][1]),
                   ("half_ppr", 10, "bench8-flex2-rb3", SHAPES[1][1])]


def zero_set_failures(model_path=VALUE_MODEL, settings=READER_SETTINGS):
    """A player is 0 in the views exactly where the Indexed engine is 0 (same
    waiver line), except a player above the line whose Indexed value displays
    as 0.0 only because of the 0.1 rounding (rounding_band_violations)."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pos_of = browser_players()
    cases, refs = view_cases(fixture, pos_of, settings)
    results = run_views(cases, model_path)
    failures = []
    for res, (scoring, teams, label, shape, inputs) in zip(results, refs):
        if "error" in res:
            failures.append(f"{scoring}/{teams}/{label}: JS raised {res['error']}")
            continue
        indexed = run_js(_cases(fixture, pos_of, [(s, scoring, teams, label, shape) for s in SOURCES]),
                         model_path)
        for src, idx in zip(SOURCES, indexed):
            tag = f"{src} {scoring}/{teams}/{label}"
            vorp, adj = res["sources"][src]["vorp"], res["sources"][src]["adj"]
            zero_views = {k for k, v in vorp.items() if v == 0}
            zero_indexed = {k for k, v in idx["values"].items() if v == 0}
            if zero_views != {k for k, v in adj.items() if v == 0}:
                failures.append(f"{tag}: VORP and Adjusted views disagree on who is 0")
            # V2-WAIVER-COVERAGE (Jeremy 2026-10-07): a short chart whose
            # waiver line is extrapolated past its list at EVERY position can
            # legitimately have nobody at 0 (CBS lists ~115 players). Any other
            # chart must still have players at 0 (the waiver line applied).
            waiver = res["sources"][src].get("waiver") or {}
            all_imputed = bool(waiver.get("positions")) and all(
                w["method"] == "imputed_from_other_charts" for w in waiver["positions"].values())
            if not zero_views and not all_imputed:
                failures.append(f"{tag}: nobody is 0 in the views")
            extra = zero_views - zero_indexed
            if extra:
                failures.append(f"{tag}: {len(extra)} players 0 in the views but priced in Indexed")
            failures += [f"{tag} {msg}" for msg in rounding_band_violations(
                inputs[src][0], zero_indexed - zero_views, teams, shape, pos_of, idx["ourMax"],
                {other: inputs[other][0] for other in inputs if other != src})]
    return failures


def view_cases(fixture, pos_of, settings):
    """One batch case per (scoring, teams, shape): all four published charts."""
    cases, refs = [], []
    for scoring, teams, label, shape in settings:
        sources, inputs, pos = {}, {}, {}
        for source in SOURCES:
            native, saved, _ = browser_inputs(fixture, pos_of, source, scoring)
            keys = [k for k, _ in saved]
            budgets = budgets_for(teams, shape, len(keys))
            sources[source] = {"native": native, "keys": keys, "budgets": budgets}
            inputs[source] = (native, keys, budgets)
            pos.update({str(k): pos_of[k] for k, _ in native + saved})
        cases.append({"teams": teams, "shape": shape, "sources": sources, "pos": pos})
        refs.append((scoring, teams, label, shape, inputs))
    return cases, refs


def run_views(cases, model_path=VALUE_MODEL):
    proc = subprocess.run(["node", str(DRIVER), str(model_path)],
                          input=json.dumps({"mode": "views", "cases": cases}),
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise AssertionError(f"node driver failed: {proc.stderr[:2000]}")
    return json.loads(proc.stdout)["results"]


def all_view_settings():
    return [(s, t, label, shape) for s in SCORINGS for t in (8, 10, 12, 14) for label, shape in SHAPES]


def check(settings, model_path=VALUE_MODEL):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pos_of = browser_players()
    cases, refs = view_cases(fixture, pos_of, settings)
    results = run_views(cases, model_path)
    failures, n, max_diff = [], 0, 0.0
    for res, (scoring, teams, label, shape, inputs) in zip(results, refs):
        tag = f"{scoring}/{teams}/{label}"
        if "error" in res:
            failures.append(f"{tag}: JS raised {res['error']}")
            continue
        exp = expected_views(inputs, teams, shape, pos_of)
        for src in SOURCES:
            for view in ("vorp", "adj"):
                got = {int(k): v for k, v in res["sources"][src][view].items()}
                want = exp[src][view]
                if set(got) != set(want):
                    failures.append(f"{tag} {src} {view}: player sets differ")
                    continue
                for k, v in want.items():
                    d = abs(v - got[k])
                    max_diff = max(max_diff, d)
                    n += 1
                    if d > TOL:
                        failures.append(f"{tag} {src} {view} {k}: expected {v} got {got[k]}")
                        break
    return failures, n, max_diff, results, refs


class PublishedViewsEngine(unittest.TestCase):
    def test_views_match_reference_at_every_setting(self):
        failures, n, max_diff, results, refs = check(all_view_settings())
        print(f"\n[JEG332-VORP-VIEWS engine] batches={len(refs)} values_compared={n} "
              f"max_abs_diff={max_diff} failures={len(failures)}")
        self.assertEqual(failures, [], "\n".join(failures[:20]))
        self.assertGreater(n, 30000)
        self.assertEqual({r["version"] for r in results}, {"published-views-001/3"})

    def test_reader_invariants(self):
        """VORP-vs-waivers totals are the anchor's and keep the publisher's own
        order; the adjusted top is exactly 70; a player is 0 in the views
        where the Indexed engine prices 0."""
        self.assertEqual(zero_set_failures(), [])
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        pos_of = browser_players()
        cases, refs = view_cases(fixture, pos_of, READER_SETTINGS)
        results = run_views(cases)
        for res, (scoring, teams, label, shape, inputs) in zip(results, refs):
            tops = [max(res["sources"][s]["adj"].values()) for s in SOURCES]
            self.assertAlmostEqual(max(tops), 70.0, places=9)
            for src in SOURCES:
                tag = f"{src} {scoring}/{teams}/{label}"
                budgets = inputs[src][2]
                groups = res["sources"][src]["groups"]
                vorp = res["sources"][src]["vorp"]
                adj = res["sources"][src]["adj"]
                # VORP vs waivers: the chart's total is the anchor's total, and
                # one factor per chart keeps the publisher's own cross-position
                # order (no re-tiering): order by native == order by view value.
                total = sum(b for g in budgets.values() for b in g.values())
                self.assertAlmostEqual(sum(vorp.values()), total, places=6, msg=tag)
                # groups[] are value above waivers in publisher units, so the
                # view/publisher ratio is the same at every position.
                ratios = set()
                for pos in POSITIONS:
                    native_vaw = groups[pos]["starter"] + groups[pos]["bench"]
                    shown = sum(v for k, v in vorp.items() if pos_of[int(k)] == pos)
                    if native_vaw > 0:
                        ratios.add(round(shown / native_vaw, 9))
                self.assertEqual(len(ratios), 1, f"{tag}: per-position factors {ratios}")
                # Adjusted: every group holding a priced player carries exactly
                # its anchor budget times the batch's 70-anchor factor.
                funded = sum(budgets[p][r] for p in POSITIONS for r in ("starter", "bench")
                             if groups[p][r] > 0)
                self.assertAlmostEqual(sum(adj.values()), funded * res["adjScale"], places=6, msg=tag)
                self.assertTrue(all(groups[p]["starter"] > 0 for p in POSITIONS), tag)

    def test_guard_catches_broken_views(self):
        source = VALUE_MODEL.read_text(encoding="utf-8")
        mutations = {
            # within-group weight back to the raw published value (saved recipe)
            "weight-native": ("info.set(String(row.key), {pos: pos, role: role, vorp: t.vorp});",
                              "info.set(String(row.key), {pos: pos, role: role, vorp: t.native});"),
            # flex starters counted as bench
            "flex-as-bench": ("var nStart = p.n_dedicated + (p.n_superflex || 0) + p.n_flex;",
                              "var nStart = p.n_dedicated + (p.n_superflex || 0);"),
            # JEG332-SUPERFLEX-FLEX: superflex starters counted as bench
            "superflex-as-bench": ("var nStart = p.n_dedicated + (p.n_superflex || 0) + p.n_flex;",
                                   "var nStart = p.n_dedicated + p.n_flex;"),
            # adjusted: anchor group budgets ignored (raw value above waivers)
            "budget-ignored": ("w = groupTotal > 0 && isFinite(budget) && budget > 0 ? budget * row.vorp / groupTotal : 0;",
                               "w = row.vorp;"),
            # VORP vs waivers re-tiered onto the group budgets (the Adjusted recipe)
            "vorp-retiered": ("v = row.vorp * vorpScale;",
                              "v = groups[row.pos][row.role] > 0 ? Number((budgets[row.pos] || {})[row.role]) * row.vorp / groups[row.pos][row.role] : 0;"),
            # VORP vs waivers left in publisher units (no shared total)
            "vorp-unscaled": ("var vorpScale = vorpSum > 0 ? total / vorpSum : 0;", "var vorpScale = 1;"),
            # adjusted view not anchored at 70
            "adj-unanchored": ("out.adjScale = out.batchMax > 0 ? VIEW_TOP_OF_SCALE / out.batchMax : 0;",
                               "out.adjScale = 1;"),
            # roster ignored by the views (always the saved setup)
            "views-saved-setup-only": ("var setting = settingForShape(opts.teams, shape);\n    var posOf",
                                       "var setting = settingForShape(12, SAVED_SETUP_SHAPE);\n    var posOf"),
        }
        settings = [s for s in all_view_settings() if s[0] == "ppr"]
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in mutations.items():
                self.assertEqual(source.count(old), 1, f"mutation anchor for {name} moved")
                broken = Path(tmp) / f"value-model-{name}.js"
                broken.write_text(source.replace(old, new))
                failures = check(settings, broken)[0]
                print(f"\n[JEG332-VORP-VIEWS negative test] {name}: {len(failures)} failures")
                self.assertGreater(len(failures), 0, f"mutation {name} was NOT caught")

    def test_zero_set_guard_catches_waiver_leaks(self):
        """The zero-set invariant (zero_set_failures) catches views that price
        players the Indexed engine prices 0 for any reason other than its 0.1
        rounding. Replaced a count (`< 5` such players), which was empirical
        against Week 4 FantasyCalc and went red on Week 5 data (6 players, all
        legitimately above the waiver line); the count also could not see a
        leak of fewer than 5 sub-waiver players."""
        source = VALUE_MODEL.read_text(encoding="utf-8")
        mutations = {
            # one sub-waiver player per position (the first one off the
            # roster) leaks a sliver into the views: 4 players per chart, under
            # the old count of 5.
            "leak-first-below-waiver": (
                "          if (!t) return;",
                "          if (!t) { if (i !== p.n_rostered) return; t = {vorp: 0.1}; }"),
            # the views use a waiver line one bench slot deeper than Indexed
            "views-waiver-deeper": (
                "peers: peersByPosition(peers, posOf)}, setting));",
                "peers: peersByPosition(peers, posOf)}, setting, "
                "{benchPerTeam: setting.benchPerTeam + 1}));"),
            # Indexed zeroes above-waiver players worth a real (visible) amount
            "indexed-drops-small": (
                "if (t) { values.set(key, t.translated); counts.translated += 1; return; }",
                "if (t) { values.set(key, t.translated < 1 ? 0 : t.translated); counts.translated += 1; return; }"),
        }
        self.assertEqual(zero_set_failures(), [], "guard must be green on the real engine")
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in mutations.items():
                self.assertEqual(source.count(old), 1, f"mutation anchor for {name} moved")
                broken = Path(tmp) / f"value-model-{name}.js"
                broken.write_text(source.replace(old, new))
                failures = zero_set_failures(broken)
                print(f"\n[JEG332-VORP-VIEWS zero-set negative test] {name}: {len(failures)} failures")
                self.assertGreater(len(failures), 0, f"mutation {name} was NOT caught")


if __name__ == "__main__":
    unittest.main()
