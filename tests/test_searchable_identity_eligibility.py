"""JEG-1505: searchable eligibility is separate from production active/pricing."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import unittest

from pipelines.lib.searchable_identity_eligibility import build_searchable_identities
from pipelines.lib import nfl_universe

ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 11, 4)


def player(key=568, name="Brandon Aiyuk", pos="WR", **ids):
    return {"player_key": key, "full_name": name, "position": pos,
            "active": False, "metadata": ids}


def base(**entries):
    return {"by_sleeper_id": entries}


def event(_kind, on, key=568, **changes):
    # Synthetic lifecycle examples, never a real retirement dataset.
    return {"player_key": key, "kind": _kind, "date": on,
            "source": "https://example.invalid/transactions/" + on, **changes}


def select(rows, snapshot=None, events=(), **kw):
    return build_searchable_identities(rows, snapshot or {}, events, as_of=AS_OF, **kw)


class SearchableIdentityEligibilityTest(unittest.TestCase):
    def test_committed_identity_selection_preserves_all_keys_and_aiyuk_once(self):
        snapshot = json.loads((ROOT / "data/inputs/sleeper_identity_base.json").read_text())
        baked = json.loads((ROOT / "data/fixtures/current/players.json").read_text())["players"]
        canonical = [{"player_key": p["player_key"], "full_name": p["name"],
                      "position": p["pos"], "metadata": {"sleeper_id": p.get("sleeper_id")}}
                     for p in baked]
        priced = [p["player_key"] for p in baked if not p.get("universe_only")]
        result = select(canonical, snapshot, priced_player_keys=priced)
        keys = [p["player_key"] for p in result["identities"]]
        expected = {p["player_key"] for p in baked if p["pos"] in {"QB", "RB", "WR", "TE"}}
        self.assertEqual(set(keys), expected)
        self.assertEqual(len(keys), len(expected))
        matches = [p for p in result["identities"] if p["player_key"] == 568]
        self.assertEqual(len(matches), 1)
        self.assertEqual((matches[0]["sleeper_id"], matches[0]["pricing_status"]),
                         ("6803", "unavailable"))
        self.assertIn(568, result["eligible_player_keys"])

    def test_committed_aiyuk_once_selectable_and_explicitly_unavailable(self):
        snapshot = json.loads((ROOT / "data/inputs/sleeper_identity_base.json").read_text())
        baked = json.loads((ROOT / "data/fixtures/current/players.json").read_text())["players"]
        matches = [p for p in baked if p["player_key"] == 568]
        self.assertEqual(len(matches), 1)
        self.assertEqual((matches[0]["sleeper_id"], matches[0]["universe_only"]), ("6803", True))
        result = select([player(sleeper_id="6803")], snapshot, priced_player_keys=[])
        self.assertEqual(result["eligible_player_keys"], [568])
        self.assertEqual(len(result["identities"]), 1)
        row = result["identities"][0]
        self.assertEqual((row["player_key"], row["sleeper_id"], row["name"]),
                         (568, "6803", "Brandon Aiyuk"))
        self.assertTrue(row["selectable"])
        self.assertEqual(row["pricing_status"], "unavailable")
        self.assertIn("No chart or projection", row["unpriced_reason"])
        self.assertNotIn("espn_ros", row)
        self.assertNotIn("value", row)

    def test_inactive_free_agent_with_no_news_is_retained(self):
        for news in (None, "2001-01-01", "bad date"):
            with self.subTest(news=news):
                result = select([player(sleeper_id="6803")], base(**{
                    "6803": {"pos": "WR", "active": False, "team": None,
                             "status": "Inactive", "last_news": news}}))
                self.assertEqual(result["eligible_player_keys"], [568])
                self.assertEqual(result["identities"][0]["eligibility_status"], "unknown")

    def test_ir_pup_practice_squad_and_stale_rostered_player_retained(self):
        for status, injury in (("Inactive", "IR"), ("Inactive", "PUP"),
                               ("Practice Squad", None), ("Inactive", None)):
            with self.subTest(status=status, injury=injury):
                result = select([player(sleeper_id="6803")], base(**{
                    "6803": {"pos": "WR", "team": "SF", "active": False,
                             "status": status, "injury_status": injury}}))
                self.assertEqual(result["eligible_player_keys"], [568])
                self.assertEqual(result["identities"][0]["roster_status"], status)

    def test_absent_provider_row_and_absent_ids_preserve_known_identity(self):
        for ids in ({}, {"sleeper_id": "6803"}):
            with self.subTest(ids=ids):
                result = select([player(**ids)])
                self.assertEqual(result["eligible_player_keys"], [568])
                self.assertEqual(result["identities"][0]["pricing_status"], "unknown")

    def test_retirement_preserves_history_and_later_return_restores_same_key(self):
        rows = [player(sleeper_id="6803")]
        retired = event("retired", "2024-05-01")
        result = select(rows, events=[retired])
        self.assertEqual(result["eligible_player_keys"], [])
        row = result["identities"][0]
        self.assertEqual((row["player_key"], row["eligibility_status"]), (568, "retired"))
        self.assertEqual(row["lifecycle_history"], [retired])
        returned = event("returned", "2026-10-01")
        result = select(rows, events=[returned, retired])
        self.assertEqual(result["eligible_player_keys"], [568])
        row = result["identities"][0]
        self.assertEqual((row["player_key"], row["sleeper_id"], row["eligibility_status"]),
                         (568, "6803", "returned"))
        self.assertEqual(row["lifecycle_history"], [retired, returned])

    def test_future_return_does_not_override_retirement(self):
        result = select([player()], events=[event("retired", "2024-05-01"),
                                          event("returned", "2027-01-01")])
        self.assertEqual(result["eligible_player_keys"], [])
        self.assertEqual(len(result["identities"][0]["lifecycle_history"]), 2)

    def test_lifecycle_evidence_requires_source_date_and_known_key(self):
        for changes in ({"source": ""}, {"source": "unsourced"}, {"date": ""},
                        {"date": "2026-02-30"}, {"player_key": 999}, {"kind": "inactive"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                select([player()], events=[event("retired", "2024-05-01", **changes)])

    def test_adversarial_malformed_source_urls_are_rejected(self):
        sources = ["https://:443/retirement", "https://@/retirement",
                   "https:// /retirement", "https://exa mple.invalid/retirement",
                   "https://example.invalid\n/retirement"]
        for source in sources:
            with self.subTest(source=source), self.assertRaises(ValueError):
                select([player()], events=[event("retired", "2024-05-01", source=source)])

    def test_source_urls_reject_raw_controls_and_malformed_ports(self):
        sources = [f"https://example.invalid/retire{char}ment"
                   for char in ("\t", "\r", "\x00", "\x1f", "\x7f", "\u00a0")]
        sources += ["https://example.invalid:not-a-port/retirement",
                    "https://example.invalid:65536/retirement"]
        for source in sources:
            with self.subTest(source=source), self.assertRaises(ValueError):
                select([player()], events=[event("retired", "2024-05-01", source=source)])

    def test_well_formed_source_urls_are_preserved_without_fetching_or_trust_claims(self):
        # Syntax controls only; none is a real retirement record or fetched.
        sources = ["https://example.invalid/retirement", "http://example.invalid/retirement",
                   "https://example.invalid:443/retirement?record=1#notice",
                   "https://[2001:db8::1]:443/retirement",
                   "https://example.invalid/retirement%20notice"]
        for source in sources:
            with self.subTest(source=source):
                supplied = event("retired", "2024-05-01", source=source)
                result = select([player()], events=[supplied])
                self.assertEqual(result["eligible_player_keys"], [])
                self.assertEqual(result["identities"][0]["lifecycle_history"], [supplied])

    def test_same_day_contradictory_evidence_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "conflicting lifecycle"):
            select([player()], events=[event("retired", "2024-05-01"),
                                      event("returned", "2024-05-01")])

    def test_duplicate_canonical_key_is_rejected_without_choosing_a_row(self):
        with self.assertRaisesRegex(ValueError, "duplicate player_key"):
            select([player(), player(name="Other Name")])

    def test_provider_id_shared_by_canonical_keys_is_rejected(self):
        rows = [player(sleeper_id="6803"), player(569, "Other Name", sleeper_id="6803")]
        result = select(rows, base(**{"6803": {"pos": "WR"}}))
        self.assertEqual(result["eligible_player_keys"], [])
        self.assertEqual(len(result["identities"]), 2)
        self.assertEqual(len(result["issues"]), 2)
        self.assertTrue(all(r["sleeper_id"] is None for r in result["identities"]))

    def test_gsis_bridge_preserves_key_without_name_guessing(self):
        result = select([player(gsis_id="00-test")], base(**{
            "6803": {"pos": "WR", "gsis_id": "00-test", "name": "Different provider label"}}))
        self.assertEqual(result["eligible_player_keys"], [568])
        self.assertEqual(result["identities"][0]["sleeper_id"], "6803")
        # A matching name alone never invents a provider mapping.
        result = select([player()], base(**{"6803": {"pos": "WR", "name": "Brandon Aiyuk"}}))
        self.assertIsNone(result["identities"][0]["sleeper_id"])

    def test_ambiguous_gsis_conflicting_ids_and_position_are_rejected(self):
        cases = [
            (player(gsis_id="00-test"), {"1": {"pos": "WR", "gsis_id": "00-test"},
                                       "2": {"pos": "WR", "gsis_id": "00-test"}}),
            (player(sleeper_id="1", gsis_id="00-test"),
             {"1": {"pos": "WR", "gsis_id": "00-other"}}),
            (player(sleeper_id="1", gsis_id="00-test"),
             {"1": {"pos": "WR"}, "2": {"pos": "WR", "gsis_id": "00-test"}}),
            (player(sleeper_id="1"), {"1": {"pos": "TE"}}),
        ]
        for row, entries in cases:
            with self.subTest(entries=entries):
                result = select([row], {"by_sleeper_id": entries})
                self.assertEqual(result["eligible_player_keys"], [])
                self.assertIsNone(result["identities"][0]["sleeper_id"])
                self.assertEqual(len(result["issues"]), 1)

    def test_cross_id_claims_cannot_map_two_keys_to_one_sleeper(self):
        result = select([player(sleeper_id="6803"), player(569, gsis_id="00-test")],
                        base(**{"6803": {"pos": "WR", "gsis_id": "00-test"}}))
        self.assertEqual(result["eligible_player_keys"], [])
        self.assertEqual(len(result["issues"]), 2)

    def test_provider_only_shared_gsis_preserves_both_identities_but_rejects_selection(self):
        rows = [player(1, "First Player", sleeper_id="100"),
                player(2, "Second Player", sleeper_id="200")]
        snapshot = base(**{"100": {"pos": "WR", "gsis_id": "00-shared"},
                           "200": {"pos": "WR", "gsis_id": "00-shared"}})
        result = select(rows, snapshot)
        self.assertEqual(result["eligible_player_keys"], [])
        self.assertEqual([r["player_key"] for r in result["identities"]], [1, 2])
        self.assertEqual(result["issues"], [
            {"player_key": 1, "reason": "multiple Sleeper ids share one GSIS id"},
            {"player_key": 2, "reason": "multiple Sleeper ids share one GSIS id"},
        ])
        for row in result["identities"]:
            self.assertFalse(row["selectable"])
            self.assertIsNone(row["sleeper_id"])
            self.assertIsNone(row["gsis_id"])

    def test_inputs_and_priced_rows_unchanged_and_output_detached(self):
        rows = [player(sleeper_id="6803")]
        rows[0]["espn_ros"] = {"ppr": 17.25}
        snapshot = base(**{"6803": {"pos": "WR", "status": "Inactive"}})
        events = [event("returned", "2026-01-01")]
        priced_keys = [568]
        before = deepcopy((rows, snapshot, events, priced_keys))
        result = select(rows, snapshot, events, priced_player_keys=priced_keys)
        self.assertEqual(result["identities"][0]["pricing_status"], "available")
        result["identities"][0]["lifecycle_history"][0]["source"] = "changed"
        self.assertEqual((rows, snapshot, events, priced_keys), before)
        self.assertNotIn("espn_ros", result["identities"][0])

    def test_deterministic_key_order_and_no_extra_provider_identities(self):
        rows = [player(569), player(568)]
        result = select(rows, base(**{"unkeyed": {"pos": "WR", "name": "New Person"}}))
        self.assertEqual(result, select(reversed(rows)))
        self.assertEqual(result["eligible_player_keys"], [568, 569])

    def test_search_selection_does_not_replace_production_universe_policy(self):
        snapshot = base(**{"6803": {"name": "Brandon Aiyuk", "pos": "WR",
                                    "active": False, "team": None, "last_news": None}})
        snapshot["meta"] = {"pulled_at": "2026-11-03T09:17:14+00:00"}
        before = deepcopy(snapshot)
        self.assertEqual(nfl_universe.active_universe(snapshot), {})
        self.assertEqual(select([player(sleeper_id="6803")], snapshot)["eligible_player_keys"], [568])
        self.assertEqual(nfl_universe.active_universe(snapshot), {})
        self.assertEqual(snapshot, before)

    def test_invalid_keys_and_non_skill_positions_cannot_create_identities(self):
        for key in (True, 1.5, 0, -1, "568.0"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                select([player(key)])
        result = select([player(1, pos="K"), player(2, pos="DST")])
        self.assertEqual(result["identities"], [])
        self.assertEqual(result["eligible_player_keys"], [])


if __name__ == "__main__":
    unittest.main()
