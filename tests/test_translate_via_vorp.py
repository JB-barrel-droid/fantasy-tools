#!/usr/bin/env python3
"""Tests for pipelines/translate_via_vorp.py (JEG-64).

Covers: combo-name parsing, VORP substitution, numeric-key identity
(fixture-level fallback when the combo carries no player_keys), the fail-safe
fallback to reindex values on Supabase errors/empty grains, and the JEG-64
regression guard: USA Today RB top > 65 after translation, which FAILS on the
reindexed state.

CI-safe: Supabase reads are stubbed; no network. The fixture under test is
committed repo data (data/fixtures/current), not data/raw.
"""
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))

import translate_via_vorp as tv  # noqa: E402

FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"


def top_rb_value(combo):
    pos_by_key = {str(p["player_key"]): p["pos"]
                  for p in json.loads(PLAYERS.read_text())["players"]}
    pk = combo.get("player_keys", {}) or {}
    best = None
    for slug, val in (combo.get("reindexed") or {}).items():
        if pos_by_key.get(str(pk.get(slug))) == "RB" and isinstance(val, (int, float)):
            best = val if best is None or val > best else best
    return best


class TestComboParsing(unittest.TestCase):
    def test_standard_shapes(self):
        self.assertEqual(tv.parse_combo("half_12"), ("half_ppr", 12))
        self.assertEqual(tv.parse_combo("half_12_qb1"), ("half_ppr", 12))
        self.assertEqual(tv.parse_combo("full_14"), ("ppr", 14))
        self.assertEqual(tv.parse_combo("standard_10"), ("standard", 10))

    def test_unknown(self):
        self.assertIsNone(tv.parse_combo("weird"))
        self.assertIsNone(tv.parse_combo("half"))
        self.assertIsNone(tv.parse_combo(""))


class TestSubstitution(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_text())
        self.usatoday_half = self.fixture["sources"]["usatoday"]["combos"]["half_12"]

    def test_translated_values_replace_reindexed(self):
        combo = deepcopy(self.usatoday_half)
        # usatoday/half_12 player_keys are numeric; translate two slugs.
        translated = {"164": 42.0, "28": 30.0}  # aaron jones, aaron rodgers
        report = tv.apply_combo("usatoday", "half_12", combo, translated,
                                self.fixture.get("player_keys", {}), {})
        self.assertEqual(report["method"], "vorp-supabase")
        self.assertEqual(combo["reindexed"]["aaron jones"], 42.0)
        self.assertEqual(combo["reindexed"]["aaron rodgers"], 30.0)
        self.assertEqual(combo["translation"]["method"], "vorp-supabase")
        self.assertEqual(combo["translation"]["n_translated"], 2)
        # The substitution is documented in fit alongside the old quantile record.
        self.assertIn("vorp_translation", combo.get("fit", {}))
        self.assertEqual(combo["fit"]["vorp_translation"]["method"], "vorp-supabase")
        # Untouched players keep reindexed values.
        self.assertEqual(combo["reindexed"]["adonai mitchell"],
                         self.usatoday_half["reindexed"]["adonai mitchell"])

    def test_identity_uses_fixture_keys_when_combo_keys_empty(self):
        # fantasypros combos carry EMPTY player_keys; identity must resolve
        # through the fixture-level map (brock purdy -> 4561).
        combo = deepcopy(self.fixture["sources"]["fantasypros"]["combos"]["half_12"])
        self.assertFalse(combo.get("player_keys"))  # missing/empty on these combos
        translated = {"4561": 25.5}  # brock purdy, QB
        report = tv.apply_combo("fantasypros", "half_12", combo, translated,
                                self.fixture.get("player_keys", {}), {})
        self.assertEqual(report["method"], "vorp-supabase")
        self.assertEqual(combo["reindexed"]["brock purdy"], 25.5)

    def test_empty_grain_is_reindex_fallback(self):
        combo = deepcopy(self.usatoday_half)
        before = deepcopy(combo["reindexed"])
        report = tv.apply_combo("usatoday", "half_12", combo, {},
                                self.fixture.get("player_keys", {}), {})
        self.assertEqual(report["method"], "reindex-fallback")
        self.assertEqual(combo["reindexed"], before)

    def test_supabase_error_never_raises(self):
        doc = deepcopy(self.fixture)
        def boom(*a, **k):
            raise ConnectionError("network down")
        with patch.object(tv, "fetch_translated", side_effect=boom):
            summary = tv.translate_document(doc, week=4, season=2026, strict=False)
        for r in summary["reports"]:
            self.assertEqual(r["method"], "reindex-fallback")
        # Values untouched.
        self.assertEqual(
            doc["sources"]["usatoday"]["combos"]["half_12"]["reindexed"],
            self.fixture["sources"]["usatoday"]["combos"]["half_12"]["reindexed"])

    def test_strict_raises(self):
        doc = deepcopy(self.fixture)
        def boom(*a, **k):
            raise ConnectionError("network down")
        with patch.object(tv, "fetch_translated", side_effect=boom):
            with self.assertRaises(ConnectionError):
                tv.translate_document(doc, week=4, season=2026, strict=True)

    def test_non_published_sources_untouched(self):
        doc = deepcopy(self.fixture)
        called = []
        def fake_fetch(source, *a, **k):
            called.append(source)
            return {}
        with patch.object(tv, "fetch_translated", side_effect=fake_fetch):
            tv.translate_document(doc, week=4, season=2026)
        for s in called:
            self.assertIn(s, tv.AS_PUBLISHED_SOURCES)
        self.assertNotIn("translation", doc["sources"]["espn"]["combos"]["half_12"])


class TestQbDivergenceGuard(unittest.TestCase):
    """The JEG-62 grain has no qb dimension. When a source's qb-split
    variants diverge (fantasycalc 8/10/14t), the non-canonical variant must
    fall back to the reindex -- a single grain must not serve both."""

    def _section(self, qb2_native):
        def combo(native):
            return {"reindexed": {s: v * 0.5 for s, v in native.items()},
                    "native": dict(native),
                    "player_keys": {s: str(i) for i, s in enumerate(native)}}
        return {"source_key": "fantasycalc",
                "combos": {"half_8_qb1": combo({"a": 100.0, "b": 50.0}),
                           "half_8_qb2": combo(qb2_native)}}

    def test_diverging_qb2_falls_back(self):
        doc = self._section({"a": 900.0, "b": 450.0})  # materially different
        with patch.object(tv, "fetch_translated", return_value={"0": 70.0, "1": 30.0}):
            summary = tv.translate_document(doc, week=4, season=2026)
        by_combo = {r["combo"]: r for r in summary["reports"]}
        self.assertEqual(by_combo["half_8_qb1"]["method"], "vorp-supabase")
        self.assertEqual(by_combo["half_8_qb2"]["method"], "reindex-fallback")
        self.assertIn("qb", (by_combo["half_8_qb2"].get("reason") or "").lower())
        # The mis-applied values are gone; reindexed keeps its own numbers.
        self.assertEqual(doc["combos"]["half_8_qb2"]["reindexed"]["a"], 450.0)

    def test_identical_qb_variants_both_translate(self):
        doc = self._section({"a": 100.0, "b": 50.0})  # 12t-style identical
        with patch.object(tv, "fetch_translated", return_value={"0": 70.0, "1": 30.0}):
            summary = tv.translate_document(doc, week=4, season=2026)
        by_combo = {r["combo"]: r for r in summary["reports"]}
        self.assertEqual(by_combo["half_8_qb1"]["method"], "vorp-supabase")
        self.assertEqual(by_combo["half_8_qb2"]["method"], "vorp-supabase")


class TestNativesTranslation(unittest.TestCase):
    """JEG332-STORED-DRIFT: the chain translates each combo from its OWN natives.

    The stored Supabase grain is written after promotion from the previous
    natives, so reading it during a refresh promotes a stale translation.
    Natives mode must (a) never read Supabase, (b) reproduce
    unified.translate_natives exactly, (c) set at/below-waiver players to 0,
    and (d) follow a native refresh that the stale grain does not.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT))
        from pipelines.vorp_translation import unified
        self.unified = unified
        self.fixture = json.loads(FIXTURE.read_text())

    def _section(self, source="usatoday", combo="full_12"):
        return {"source_key": source,
                "combos": {combo: deepcopy(self.fixture["sources"][source]["combos"][combo])}}

    def test_natives_mode_never_reads_supabase_and_zeroes_below_waiver(self):
        doc = self._section()
        boom = Exception("must not be called")
        with patch.object(tv, "fetch_translated", side_effect=boom) as fetch:
            summary = tv.translate_document(doc, week=4, season=2026, strict=True,
                                            translation="natives")
        fetch.assert_not_called()
        combo = doc["combos"]["full_12"]
        run = self.unified.translate_natives(combo["native"], 12)
        tr = combo["translation"]
        self.assertEqual(tr["translated_from"], "combo-natives")
        n_above = n_below = 0
        for slug, value in combo["reindexed"].items():
            key = run["slug_keys"].get(slug)
            if key in run["translated"]:
                n_above += 1
                self.assertEqual(value, run["translated"][key], slug)
            elif key in run["evaluated"]:
                n_below += 1
                self.assertEqual(value, 0.0, slug)
        self.assertGreater(n_below, 0)
        self.assertEqual((tr["n_translated"], tr["n_below_waiver"]), (n_above, n_below))
        self.assertEqual(summary["combos_vorp_supabase"], 1)

    def test_natives_mode_follows_a_native_refresh_the_stale_grain_misses(self):
        """Negative/discrimination: after a native refresh, the Supabase-grain path
        keeps the old translation (the bug) while natives mode moves with it."""
        base = self._section()
        combo = base["combos"]["full_12"]
        stale_grain = {k: v for k, v in
                       self.unified.translate_natives(combo["native"], 12)["translated"].items()}
        # A refresh: one mid-tier WR's native jumps.
        run = self.unified.translate_natives(combo["native"], 12)
        wr = sorted((s for s, k in run["slug_keys"].items() if k in run["translated"]
                     and self.unified.naming_registry().by_key[int(k)]["position"] == "WR"),
                    key=lambda s: -combo["native"][s])[10]
        combo["native"][wr] = float(combo["native"][wr]) + 12.0
        key = run["slug_keys"][wr]

        via_grain = deepcopy(base)
        with patch.object(tv, "fetch_translated", return_value=stale_grain):
            tv.translate_document(via_grain, week=4, season=2026)
        via_natives = deepcopy(base)
        tv.translate_document(via_natives, week=4, season=2026, translation="natives")

        fresh = self.unified.translate_natives(combo["native"], 12)["translated"][key]
        self.assertNotEqual(fresh, stale_grain[key])
        self.assertEqual(via_grain["combos"]["full_12"]["reindexed"][wr], stale_grain[key])
        self.assertEqual(via_natives["combos"]["full_12"]["reindexed"][wr], fresh)

    def test_chain_uses_natives_mode(self):
        src = (ROOT / "pipelines" / "rebuild_comparison_chain.py").read_text()
        self.assertIn('"--translation", "natives"', src)


class TestJeg64RegressionGuard(unittest.TestCase):
    """Acceptance #4: USA Today RB shows ~70 (not the compressed 48-64
    reindexed band). The guard is state-aware: it must PASS on the translated
    state and would FAIL if the combo ever regresses to reindexed values --
    that is the discrimination proof, read live from the fixture's own
    translation provenance."""

    # Measured 2026-10-02 on the committed reindexed fixture (668282a),
    # before JEG-64: the compressed peak the bug report describes.
    PRE_TRANSLATION_USATODAY_RB_PEAK = 63.97

    def test_usatoday_rb_peak_guard(self):
        fixture = json.loads(FIXTURE.read_text())
        combo = fixture["sources"]["usatoday"]["combos"]["half_12"]
        peak = top_rb_value(combo)
        method = (combo.get("translation") or {}).get("method")
        if method == "vorp-supabase":
            self.assertGreater(
                peak, 65,
                "translated USA Today RB peak must clear 65 "
                f"(got {peak})")
        else:
            # Reindexed (or never-translated) state: the guard FAILS --
            # this is the pre-JEG-64 condition the ticket fixes.
            self.assertLess(
                peak, 65,
                f"reindexed RB peak {peak} unexpectedly clears 65; "
                "the guard's discrimination premise needs review")
            self.assertLess(self.PRE_TRANSLATION_USATODAY_RB_PEAK, 65)


if __name__ == "__main__":
    unittest.main()
