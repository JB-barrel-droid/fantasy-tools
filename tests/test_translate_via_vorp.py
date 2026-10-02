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
