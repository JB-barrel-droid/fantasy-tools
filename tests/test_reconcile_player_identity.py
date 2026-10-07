"""JEG-438: nightly identity reconcile planner (offline, synthetic data).

Each rule is negative-tested against the broken state it prevents.
"""
import unittest
from datetime import datetime, timedelta, timezone

from pipelines import reconcile_player_identity as rec
from pipelines.lib.player_resolver import PlayerResolver

NOW = datetime(2026, 10, 7, 8, 30, tzinfo=timezone.utc)
OLD = (NOW - timedelta(days=5)).isoformat()
FRESH = (NOW - timedelta(hours=5)).isoformat()

PLAYERS = [
    {"player_key": 785, "full_name": "Kenneth Gainwell", "position": "RB", "active": True, "team": "PIT"},
    {"player_key": 1268, "full_name": "Jalen Moreno-Cropper", "position": "WR", "active": True, "team": "DAL"},
    {"player_key": 1300, "full_name": "Jalen Cropper Smith", "position": "WR", "active": True, "team": "NYG"},
    {"player_key": 4000, "full_name": "Jackson Meeks", "position": "WR", "active": False, "team": "DET"},
    {"player_key": 1370, "full_name": "Puka Nacua", "position": "WR", "active": True, "team": "LA"},
]
XREFS = {"sleeper": {"7567": 785}, "gsis": {}, "espn": {}, "yahoo": {}}


def sleeper(sid, name, pos, team="DAL", active=True, status="Active", **ids):
    return {"sleeper_id": sid, "name": name, "pos": pos, "team": team, "active": active,
            "status": status, **ids}


def alias(i, name, pos, status, key=None, first=OLD, source="cbs"):
    return {"id": i, "source": source, "source_player_name": name, "position": pos,
            "status": status, "player_key": key, "first_seen_at": first, "last_seen_at": first}


class AliasReconcileTest(unittest.TestCase):
    def setUp(self):
        self.r = PlayerResolver(PLAYERS, [], XREFS)

    def plan(self, aliases, sl=()):
        return {a["id"]: a for a in rec.plan_alias_reconcile(self.r, aliases, list(sl), NOW)}

    def test_provisional_confirmed_by_exact_name_is_promoted(self):
        acts = self.plan([alias(1, "Kenneth Gainwell Jr.", "RB", "provisional", 785)])
        self.assertEqual((acts[1]["action"], acts[1]["player_key"]), ("promote", 785))
        self.assertIsNone(acts[1]["note"])

    def test_provisional_with_wrong_key_is_replaced_and_noted(self):
        acts = self.plan([alias(1, "Kenneth Gainwell", "RB", "provisional", 1268)])
        self.assertEqual(acts[1]["player_key"], 785)
        self.assertIn("1268", acts[1]["note"])

    def test_fuzzy_is_not_evidence(self):
        # "Jalen Cropper" fuzzy-matches 1268, but the nightly job turns fuzzy off:
        # without a Sleeper record it must not promote.
        acts = self.plan([alias(1, "Jalen Cropper", "WR", "provisional", 1268, first=FRESH)])
        self.assertEqual(acts[1]["action"], "keep")

    def test_unique_sleeper_player_with_xref_promotes(self):
        acts = self.plan([alias(1, "Ken Gainwell", "RB", "unmatched")],
                         [sleeper("7567", "Ken Gainwell", "RB")])
        # Sleeper spells it the same way and its id 7567 is already ours (785)
        self.assertEqual((acts[1]["action"], acts[1]["player_key"]), ("promote", 785))

    def test_nickname_variant_is_proposed_never_promoted(self):
        # Decision identity-name-variants-001: "Kenny" for "Kenneth" is a proposal.
        acts = self.plan([alias(1, "Kenny Gainwell", "RB", "provisional", 785, first=FRESH)],
                         [sleeper("7567", "Kenneth Gainwell", "RB")])
        self.assertEqual(acts[1]["action"], "queue")
        self.assertEqual(acts[1]["proposed_key"], 785)
        self.assertNotIn("player_key", acts[1])
        sb = FakeSb()
        rec.apply_actions(sb, LIVE, [], list(acts.values()), NOW.isoformat())
        self.assertEqual([(b["status"], b["player_key"]) for t, b, _ in sb.patches], [("review", 785)])

    def test_new_player_needs_an_nfl_team(self):
        # Decision identity-new-players-001: a free agent is queued, not inserted.
        acts = self.plan([alias(1, "Matt Hibner", "TE", "unmatched")],
                         [sleeper("13324", "Matt Hibner", "TE", team=None)])
        self.assertEqual(acts[1]["action"], "queue")
        self.assertIn("not insertable", acts[1]["note"])

    def test_insert_gate(self):
        self.assertTrue(rec.may_insert(sleeper("1", "A B", "WR", team="BAL")))
        self.assertFalse(rec.may_insert(sleeper("1", "A B", "WR", team=None)))
        self.assertFalse(rec.may_insert(sleeper("1", "A B", "WR", team="BAL", active=False)))
        self.assertFalse(rec.may_insert(sleeper("1", "A B", "OL", team="BAL")))

    def test_unique_sleeper_player_not_held_is_inserted(self):
        acts = self.plan([alias(1, "Matt Hibner", "TE", "unmatched")],
                         [sleeper("13324", "Matt Hibner", "TE", team="BAL")])
        self.assertEqual(acts[1]["action"], "insert_player")
        self.assertEqual(acts[1]["sleeper"]["sleeper_id"], "13324")

    def test_name_held_at_another_position_is_queued_not_inserted(self):
        # 2026-10-07 dry run: "Jackson Meeks" TE in Sleeper, players 4000 is a WR.
        aliases = [alias(1, "Jackson Meeks", "TE", "unmatched")]
        sl = [sleeper("13999", "Jackson Meeks", "TE")]
        acts = self.plan(aliases, sl)
        self.assertEqual(acts[1]["action"], "queue")
        self.assertIn("4000", acts[1]["note"])
        # broken state: without the held-elsewhere guard this would insert a duplicate
        orig = rec.existing_elsewhere
        rec.existing_elsewhere = lambda r, s: []
        try:
            self.assertEqual(self.plan(aliases, sl)[1]["action"], "insert_player")
        finally:
            rec.existing_elsewhere = orig

    def test_two_sleeper_namesakes_never_guess(self):
        acts = self.plan([alias(1, "Chris Smith", "WR", "unmatched")],
                         [sleeper("1", "Chris Smith", "WR"), sleeper("2", "Chris Smith", "WR")])
        self.assertEqual(acts[1]["action"], "queue")

    def test_age_decides_queue_vs_keep(self):
        acts = self.plan([alias(1, "Nobody Known", "WR", "unmatched", first=OLD),
                          alias(2, "Nobody Else", "WR", "unmatched", first=FRESH)])
        self.assertEqual(acts[1]["action"], "queue")
        self.assertEqual(acts[2]["action"], "keep")

    def test_verified_rows_are_untouched(self):
        self.assertEqual(self.plan([alias(1, "Kenny Gainwell", "RB", "verified", 785)]), {})


class UniverseSyncTest(unittest.TestCase):
    def setUp(self):
        self.r = PlayerResolver(PLAYERS, [], XREFS)

    def test_missing_sleeper_id_added_for_held_player(self):
        adds = rec.plan_universe_sync(self.r, [sleeper("9493", "Puka Nacua", "WR", team="LA")])
        self.assertEqual([(a["id_type"], a["external_id"], a["player_key"]) for a in adds],
                         [("sleeper", "9493", 1370)])

    def test_ghosts_and_free_agents_add_nothing(self):
        sl = [sleeper("138", "Ben Roethlisberger", "QB", team="PIT"),          # not held
              sleeper("9493", "Puka Nacua", "WR", team=None),                   # no team
              sleeper("9494", "Puka Nacua", "WR", status="Inactive")]           # not Active
        self.assertEqual(rec.plan_universe_sync(self.r, sl), [])

    def test_existing_ids_are_never_repointed(self):
        # 7567 already maps to 785; a Sleeper row claiming it for someone else adds nothing
        sl = [sleeper("7567", "Puka Nacua", "WR", team="LA")]
        adds = rec.plan_universe_sync(self.r, sl)
        self.assertEqual([a for a in adds if a["id_type"] == "sleeper"], [])

    def test_position_mismatch_never_links(self):
        self.assertEqual(rec.plan_universe_sync(self.r, [sleeper("1", "Jackson Meeks", "TE")]), [])


class AlertTest(unittest.TestCase):
    def test_thresholds(self):
        ok, msgs = rec.alert_state({"cbs": {"provisional": 2, "unmatched": 3, "review": 0}})
        self.assertTrue(ok)
        ok, msgs = rec.alert_state({"cbs": {"provisional": 2, "unmatched": 4, "review": 0}})
        self.assertFalse(ok)
        self.assertIn("cbs", msgs[0])
        many = {f"s{i}": {"unmatched": 4} for i in range(4)}
        ok, msgs = rec.alert_state(many)
        self.assertFalse(ok)
        self.assertIn("all sources", msgs[-1])

    def test_open_counts_window_and_actions(self):
        aliases = [alias(1, "A B", "WR", "unmatched", first=FRESH),
                   alias(2, "C D", "WR", "provisional", 785, first=FRESH),
                   alias(3, "E F", "WR", "unmatched", first=(NOW - timedelta(days=30)).isoformat())]
        counts = rec.open_counts(aliases, [{"id": 2, "action": "promote"}], NOW)
        self.assertEqual(counts["cbs"], {"verified": 1, "provisional": 0, "unmatched": 1, "review": 0})


class FakeSb:
    """Records writes; returns a uuid for each inserted player."""
    def __init__(self):
        self.posts, self.patches = [], []

    def post(self, table, rows, params="", prefer=""):
        self.posts.append((table, rows))
        if table == "players":
            return [{"id": f"uuid-{rows[0]['player_key']}"}]
        return None

    def patch(self, table, body, params=""):
        self.patches.append((table, body, params))


LIVE = {
    "sources": [{"name": "sleeper", "id": "src-sleeper"}],
    "players": [{"player_key": p["player_key"], "id": f"uuid-{p['player_key']}", "league_id": "nfl"}
                for p in PLAYERS],
    "teams": [{"abbreviation": "BAL", "id": "team-bal"}],
}


class ApplyActionsTest(unittest.TestCase):
    """Two sources naming the same new player must produce ONE players row."""

    def actions(self):
        r = PlayerResolver(PLAYERS, [], XREFS)
        aliases = [alias(1, "Matt Hibner", "TE", "unmatched", source="cbs"),
                   alias(2, "Matt Hibner", "TE", "unmatched", source="fantasycalc")]
        return rec.plan_alias_reconcile(r, aliases, [sleeper("13324", "Matt Hibner", "TE", team="BAL")], NOW)

    def test_one_insert_for_one_new_player_named_twice(self):
        acts = self.actions()
        self.assertEqual([a["action"] for a in acts], ["insert_player", "insert_player"])
        sb = FakeSb()
        stats = rec.apply_actions(sb, LIVE, [], acts, NOW.isoformat())
        inserts = [rows for t, rows in sb.posts if t == "players"]
        self.assertEqual(len(inserts), 1, "the same Sleeper player was inserted twice")
        self.assertEqual(stats["players_added"], 1)
        keys = {a["player_key"] for a in acts}
        self.assertEqual(keys, {max(p["player_key"] for p in PLAYERS) + 1})
        promoted = [b for t, b, _ in sb.patches if t == "player_name_aliases"]
        self.assertEqual([b["player_key"] for b in promoted], [keys.pop()] * 2)


if __name__ == "__main__":
    unittest.main()
