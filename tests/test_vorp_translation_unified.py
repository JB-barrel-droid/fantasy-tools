#!/usr/bin/env python3
"""Tests for pipelines/vorp_translation/unified.py (JEG-62).

Covers roster-math scaling across league sizes, the waiver-line/VORP/
translation pipeline on synthetic inputs, the no-per-source-branching
invariant, and the Supabase write grain (pure row-building + stubbed
client — no DB dependency, CI-safe).
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines" / "vorp_translation"))
sys.path.insert(0, str(ROOT / "pipelines"))

import unified  # noqa: E402
from build_ddf_two_tier_leg import REF_FLEX_COUNT  # noqa: E402


def synthetic_result():
    """Minimal translate-shaped result: two positions, known values."""
    return {
        'source': 'usatoday',
        'scoring': 'half_ppr',
        'teams': 12,
        'week': 4,
        'positions': {
            'RB': {
                'n_dedicated': 24, 'n_flex': 4, 'n_bench': 36, 'n_rostered': 64,
                'waiver_line_value': 10.0, 'waiver_method': 'roster_determined',
                'max_vorp': 40.0, 'total_vorp': 200.0, 'scale_factor': 1.75,
                'implied_weight': 0.5,
            },
            'WR': {
                'n_dedicated': 36, 'n_flex': 6, 'n_bench': 24, 'n_rostered': 66,
                'waiver_line_value': 8.0, 'waiver_method': 'roster_determined',
                'max_vorp': 32.0, 'total_vorp': 200.0, 'scale_factor': 1.718,
                'implied_weight': 0.5,
            },
        },
        'ranked': {
            'RB': [('rb1', 'Alpha Back', 50.0), ('rb2', 'Beta Back', 10.0),
                   ('rb3', 'Gamma Back', 5.0)],
            'WR': [('wr1', 'Alpha Wide', 40.0), ('wr2', 'Beta Wide', 8.0)],
        },
        'translated': {
            'rb1': {'name': 'Alpha Back', 'pos': 'RB', 'native': 50.0,
                    'vorp': 40.0, 'translated': 70.0},
            'wr1': {'name': 'Alpha Wide', 'pos': 'WR', 'native': 40.0,
                    'vorp': 32.0, 'translated': 55.0},
        },
    }


class TestRosterScaling(unittest.TestCase):
    def test_bench_grows_with_teams(self):
        b10 = unified.bench_for_teams(10)
        b12 = unified.bench_for_teams(12)
        b14 = unified.bench_for_teams(14)
        self.assertLess(sum(b10.values()), sum(b12.values()))
        self.assertLess(sum(b12.values()), sum(b14.values()))

    def test_bench_per_team_default_six(self):
        b = unified.bench_for_teams(12)
        total = sum(b.values())
        self.assertAlmostEqual(total / 12, 6.0, delta=1.0)

    def test_flex_sums_to_teams_times_flex_count(self):
        for teams in (10, 12, 14):
            f = unified.flex_for_teams(teams)
            self.assertEqual(sum(f.values()), teams * REF_FLEX_COUNT,
                             f"flex must sum to {teams}x{REF_FLEX_COUNT}")

    def test_rostered_equals_parts(self):
        r = unified.rostered_for_teams(12)
        for pos, counts in r.items():
            self.assertEqual(
                counts['rostered'],
                counts['dedicated'] + counts['flex'] + counts['bench'],
                f"{pos}: rostered must equal dedicated+flex+bench",
            )

    def test_dedicated_scales_linearly_with_teams(self):
        r10 = unified.rostered_for_teams(10)
        r12 = unified.rostered_for_teams(12)
        for pos in r12:
            self.assertEqual(r12[pos]['dedicated'], r10[pos]['dedicated'] * 12 // 10)


class TestComboResolution(unittest.TestCase):
    def test_exact_key_preferred(self):
        sdata = {'combos': {'half_12': {}, 'half_12_qb1': {}}}
        self.assertEqual(unified.resolve_combo_key(sdata, 'half_ppr', 12), 'half_12')

    def test_qb_split_falls_back_to_qb1(self):
        sdata = {'combos': {'half_12_qb2': {}, 'half_12_qb1': {}}}
        self.assertEqual(unified.resolve_combo_key(sdata, 'half_ppr', 12), 'half_12_qb1')

    def test_no_match_fails_closed(self):
        with self.assertRaises(SystemExit):
            unified.resolve_combo_key({'combos': {}}, 'half_ppr', 12)


class TestTranslatePipeline(unittest.TestCase):
    def _fake_load(self, source, scoring, teams, fixture_path=None):
        by_pos = {
            'QB': [('Qb One', 20.0), ('Qb Two', 5.0)],
            'RB': [('Rb One', 40.0), ('Rb Two', 12.0), ('Rb Three', 4.0)],
            'WR': [],
            'TE': [],
        }
        keys = {n.lower(): n.lower().replace(' ', '_') + '_key'
                for pos in by_pos for n, _ in by_pos[pos]}
        return by_pos, keys

    def test_waiver_line_is_first_non_rostered(self):
        with patch.object(unified, 'load_native_values', self._fake_load):
            with patch.object(unified, 'rostered_for_teams',
                              return_value={'QB': {'dedicated': 0, 'flex': 0,
                                                   'bench': 0, 'rostered': 1},
                                            'RB': {'dedicated': 0, 'flex': 0,
                                                   'bench': 0, 'rostered': 1},
                                            'WR': {'dedicated': 0, 'flex': 0,
                                                   'bench': 0, 'rostered': 0},
                                            'TE': {'dedicated': 0, 'flex': 0,
                                                   'bench': 0, 'rostered': 0}}):
                res = unified.translate_source('usatoday')
        # QB: 1 rostered -> waiver = second player's 5.0
        self.assertEqual(res['positions']['QB']['waiver_line_value'], 5.0)
        self.assertEqual(res['positions']['QB']['waiver_method'], 'roster_determined')
        # VORP = native - waiver; max QB VORP = 15 -> scale = 25/15
        self.assertAlmostEqual(res['translated']['qb_one_key']['vorp'], 15.0)
        self.assertAlmostEqual(res['translated']['qb_one_key']['translated'],
                               15.0 * 25.0 / 15.0)
        # Qb Two has zero VORP -> excluded from translated
        self.assertNotIn('qb_two_key', res['translated'])
        # translated keyed by canonical player_key, never display name
        self.assertNotIn('Qb One', res['translated'])

    def test_no_per_source_branching(self):
        """Same inputs -> same outputs regardless of source name."""
        with patch.object(unified, 'load_native_values', self._fake_load):
            a = unified.translate_source('usatoday')
            b = unified.translate_source('fantasypros')
        self.assertEqual(a['positions'], b['positions'])
        self.assertEqual(a['translated'], b['translated'])

    def test_unresolvable_name_fails_closed(self):
        def bad_load(source, scoring, teams, fixture_path=None):
            by_pos, keys = self._fake_load(source, scoring, teams)
            del keys['qb one']  # drop the key: must fail, not write keyless
            return by_pos, keys
        with patch.object(unified, 'load_native_values', bad_load):
            with self.assertRaises(SystemExit):
                unified.translate_source('usatoday')


class TestWriteRows(unittest.TestCase):
    def test_three_tables_and_grain(self):
        res = synthetic_result()
        assumptions, vorps, translated = unified.build_write_rows(res)
        self.assertEqual(len(assumptions), 2)  # one row per position
        # every ranked player gets a VORP row (5 total), with pos_rank
        self.assertEqual(len(vorps), 5)
        rb_ranks = [r['pos_rank'] for r in vorps if r['position'] == 'RB']
        self.assertEqual(rb_ranks, [1, 2, 3])
        # only vorp>0 players get translated rows
        self.assertEqual(len(translated), 2)

    def test_vorp_math(self):
        res = synthetic_result()
        _, vorps, _ = unified.build_write_rows(res)
        rb1 = next(r for r in vorps if r['player_key'] == 'rb1')
        self.assertEqual(rb1['native_value'], 50.0)
        self.assertEqual(rb1['vorp_value'], 40.0)  # 50 - 10 waiver
        rb3 = next(r for r in vorps if r['player_key'] == 'rb3')
        self.assertEqual(rb3['vorp_value'], 0.0)  # below waiver line

    def test_unique_keys_present(self):
        res = synthetic_result()
        assumptions, vorps, translated = unified.build_write_rows(res)
        for row in assumptions:
            for k in ('source', 'scoring', 'league_teams', 'week', 'season',
                      'position', 'n_rostered', 'waiver_line_value'):
                self.assertIn(k, row)
        for row in vorps + translated:
            for k in ('source', 'scoring', 'league_teams', 'week', 'season',
                      'player_key', 'position'):
                self.assertIn(k, row)

    def test_write_upserts_with_stub(self):
        calls = []

        class StubClient:
            def post(self, table, body, params="", prefer=""):
                calls.append((table, body, params, prefer))
                return []

        with patch.object(unified, '_sb', return_value=StubClient()):
            counts = unified._write_to_supabase(synthetic_result())

        tables = [c[0] for c in calls]
        self.assertEqual(tables, [unified.TBL_ASSUMPTIONS, unified.TBL_VORP,
                                  unified.TBL_TRANSLATED])
        for table, body, params, prefer in calls:
            self.assertIn('on_conflict=', params)
            self.assertEqual(prefer, 'resolution=merge-duplicates')
        self.assertEqual(counts[unified.TBL_ASSUMPTIONS], 2)
        self.assertEqual(counts[unified.TBL_VORP], 5)
        self.assertEqual(counts[unified.TBL_TRANSLATED], 2)


if __name__ == '__main__':
    unittest.main()
