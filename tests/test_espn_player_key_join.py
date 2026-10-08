#!/usr/bin/env python3
"""Regression test: ESPN section builder must join leg -> fixture by numeric
player_key, never by name slug.

Bug caught 2026-09-30: build_espn_section_from_ddf_leg.py joined on
player_norm strings. Slug variations ('cameron skattebo' in the leg vs
'cam skattebo' in the fixture; 'travis etienne jr' vs 'travis etienne')
silently dropped players from the ESPN section — the fixture kept stale
values (Skattebo 41.9 vs leg 28.7, Etienne 36.9 vs leg 16.8) because the
fresh values could not map.

The fix: load_leg_values/load_leg_ppg key by player_key, and the section
loop maps player_key -> fixture slug via fixture['player_keys'].
"""

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

from build_espn_section_from_ddf_leg import (  # noqa: E402
    SCORING_MAP, TEAM_COUNTS, find_fresh_leg, load_leg_ppg, load_leg_values,
)

FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
# leg slug -> fixture slug -> both must map to the same numeric key
SLUG_VARIATIONS = [
    ("cameron skattebo", "cam skattebo", 3664),
    ("travis etienne jr", "travis etienne", 810),
]


def _fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class EspnPlayerKeyJoinTest(unittest.TestCase):
    def test_leg_loaders_key_by_player_key(self):
        """Leg loaders must return player_key-keyed dicts, not name-keyed."""
        leg_path = find_fresh_leg("half_ppr")
        vals = load_leg_values(leg_path)
        ppgs = load_leg_ppg(leg_path)
        self.assertTrue(vals, f"no values in {leg_path}")
        self.assertTrue(all(isinstance(k, int) for k in vals), "values not keyed by int player_key")
        self.assertTrue(all(isinstance(k, int) for k in ppgs), "ppgs not keyed by int player_key")
        for leg_slug, _, key in SLUG_VARIATIONS:
            self.assertIn(key, vals, f"{leg_slug} (key {key}) missing from leg values")

    def test_slug_variations_resolve_via_player_key(self):
        """The slug pairs that broke must resolve to the same player_key in the
        fixture's player_keys registry."""
        player_keys = _fixture().get("player_keys", {})
        for _, fixture_slug, expected_key in SLUG_VARIATIONS:
            fkey = player_keys.get(fixture_slug)
            self.assertIsNotNone(fkey, f"fixture slug {fixture_slug!r} not in player_keys")
            self.assertEqual(int(fkey), expected_key)

    def test_fixture_espn_section_matches_leg(self):
        """Every ESPN combo carries the leg's own value for every leg player
        the fixture knows by key: the slug-variation players are present and
        fresh (not stale, not dropped), and an explicit leg zero (Achane on
        IR, JEG-13) is carried as 0.0, not left out.

        Was pinned to the 2026-09-30 numbers (Skattebo 28.7, Etienne 16.8),
        which every weekly ESPN refresh changes; the rule is leg == fixture.
        """
        fixture = _fixture()
        key_to_slug = {}
        for slug, key in fixture.get("player_keys", {}).items():
            key_to_slug.setdefault(int(key), slug)
        combos = fixture["sources"]["espn"]["combos"]
        for scoring, word in SCORING_MAP.items():
            leg_vals = load_leg_values(find_fresh_leg(scoring))
            expected = {key_to_slug[k]: round(v, 1) for k, v in leg_vals.items() if k in key_to_slug}
            for _, fixture_slug, key in SLUG_VARIATIONS:
                self.assertIn(fixture_slug, expected, f"{scoring}: key {key} did not join to {fixture_slug!r}")
            for teams in TEAM_COUNTS:
                values = combos[f"{word}_{teams}"]["values"]
                wrong = {s: (values.get(s), v) for s, v in expected.items() if values.get(s) != v}
                self.assertEqual(wrong, {}, f"espn {word}_{teams}: fixture != leg (fixture, leg)")


if __name__ == "__main__":
    unittest.main()
