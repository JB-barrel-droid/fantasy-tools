"""Synthetic boundary cases, not a claimed live FantasyPros schema fixture."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from pipelines import pull_fantasypros_market as pull
from pipelines.lib import fantasypros_market_identity as identity


def page(players):
    return '<html><script>const initialPlayers = ' + json.dumps(players) + ';</script></html>'


class ExtractionTests(unittest.TestCase):
    def test_preserves_full_container_null_zero_and_histories(self):
        players = {"123": {"name": "A }; B", "market": None, "expert": 0,
                           "history": [{"date": "2026-11-04", "value": None}]}}
        self.assertEqual(players, pull.extract_initial_players(page(players), min_rows=1))

    def test_array_container_is_preserved(self):
        players = [{"id": 1, "market": None}]
        self.assertEqual(players, pull.extract_initial_players(page(players), min_rows=1))

    def test_comments_and_strings_are_not_declarations(self):
        decoys = '''<script>
        // const initialPlayers = {"fake": {"value": 1}};
        /* let initialPlayers = {"fake": {"value": 1}}; */
        const text = 'var initialPlayers = {"fake": {"value": 1}};';
        const template = `var initialPlayers = {"fake": {"value": 1}};`;
        </script>'''
        with self.assertRaisesRegex(pull.PullError, "found 0"):
            pull.extract_initial_players(decoys, min_rows=1)
        players = {"real": {"market": None}}
        self.assertEqual(players, pull.extract_initial_players(decoys + page(players), min_rows=1))

    def test_rejects_duplicate_declaration_even_when_identical(self):
        html = page({"1": {"market": 1}})
        with self.assertRaisesRegex(pull.PullError, "found 2"):
            pull.extract_initial_players(html + html, min_rows=1)

    def test_missing_truncated_and_non_player_containers_fail_closed(self):
        for html in ("<html>sign in</html>", page({}), page({"1": {"market": 1}}),
                     page({str(i): None for i in range(400)})):
            with self.subTest(html=html[:50]), self.assertRaises(pull.PullError):
                pull.extract_initial_players(html)

    def test_rejects_js_expressions_duplicate_keys_and_nonfinite_values(self):
        for expression in ('JSON.parse("[]")', '{1: {market: 2}}',
                           '{"1": {"market": NaN}}', '{"1": {"market": 1e999}}',
                           '{"1": {"market": 1}, "1": {"market": 2}}',
                           '{"1": {"market": 1, "market": null}}',
                           '{"1": {"market": 1}} || stealSession()'):
            with self.subTest(expression=expression), self.assertRaises(pull.PullError):
                pull.extract_initial_players('<script>var initialPlayers = ' + expression + ';</script>', min_rows=1)

    def test_cli_failure_leaves_prior_capture_untouched(self):
        with tempfile.TemporaryDirectory() as root:
            html, out = Path(root) / "page.html", Path(root) / "capture.json"
            html.write_text("<html>challenge</html>")
            out.write_text("prior capture")
            self.assertEqual(1, pull.main(["--scoring", "ppr", "--html", str(html), "--out", str(out)]))
            self.assertEqual("prior capture", out.read_text())
            self.assertFalse(out.with_name(out.name + ".tmp").exists())

    def test_cli_capture_is_explicitly_not_publishable(self):
        with tempfile.TemporaryDirectory() as root:
            html, out = Path(root) / "page.html", Path(root) / "capture.json"
            players = {str(i): {"market": None} for i in range(pull.MIN_ROWS)}
            html.write_text(page(players))
            self.assertEqual(0, pull.main(["--scoring", "half_ppr", "--html", str(html), "--out", str(out)]))
            capture = json.loads(out.read_text())
            self.assertFalse(capture["publishable"])
            self.assertIsNone(capture["source_values_timestamp"])
            self.assertEqual("saved_html_replay", capture["acquisition"])
            self.assertEqual(html.read_text(), capture["source_html"])
            self.assertEqual(players, capture["initialPlayers"])
            self.assertNotIn("standard", pull.URLS)


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.players = Path(self.temp.name) / "players.json"
        self.records = [{"name": "Josh Allen", "pos": "QB", "team": "BUF", "player_key": 869},
                        {"name": "Puka Nacua", "pos": "WR", "team": "LAR", "player_key": 22}]
        self.write_players()
        self.row = {"player_name": "Josh Allen", "pos": "QB", "team": "BUF",
                    "source_player_id": "fp-1", "native_value": 500}

    def write_players(self):
        self.players.write_text(json.dumps({"players": self.records}))

    def map(self, rows):
        return identity.map_rows(rows, players_path=self.players)

    def test_keyed_join_preserves_native_null_and_source_id(self):
        for value in (None, 0, 500, 1000):
            with self.subTest(value=value):
                rows, excluded = self.map([{**self.row, "native_value": value}])
                self.assertEqual(869, rows[0]["player_key"])
                self.assertEqual("fp-1", rows[0]["source_player_id"])
                self.assertEqual(value, rows[0]["native_value"])
                self.assertEqual([], excluded)

    def test_even_single_name_match_requires_correct_position_and_team(self):
        for overrides in ({"pos": "RB"}, {"team": "NYJ"}, {"team": ""}, {"pos": None}):
            with self.subTest(overrides=overrides), self.assertRaises(identity.IdentityError):
                self.map([{**self.row, **overrides}])

    def test_shared_team_aliases_are_supported(self):
        rows, _ = self.map([{**self.row, "player_name": "Puka Nacua", "team": "LA", "pos": "WR"}])
        self.assertEqual(22, rows[0]["player_key"])

    def test_shared_suffix_and_nickname_normalization(self):
        self.records.append({"name": "Kenneth Walker III", "pos": "RB", "team": "SEA", "player_key": 3})
        self.write_players()
        rows, _ = self.map([{**self.row, "player_name": "Ken Walker", "pos": "RB", "team": "SEA"}])
        self.assertEqual(3, rows[0]["player_key"])

    def test_invalid_source_id_and_duplicate_canonical_key_fail_closed(self):
        for source_id in (None, True, ""):
            with self.subTest(source_id=source_id), self.assertRaises(identity.IdentityError):
                self.map([{**self.row, "source_player_id": source_id}])
        self.records.append(dict(self.records[0]))
        self.write_players()
        with self.assertRaisesRegex(identity.IdentityError, "duplicate canonical"):
            self.map([self.row])

    def test_ambiguous_keyed_roster_fails_closed(self):
        self.records.append({**self.records[0], "player_key": 900})
        self.write_players()
        with self.assertRaisesRegex(identity.IdentityError, "ambiguous"):
            self.map([self.row])

    def test_unknown_source_id_cannot_be_mistaken_for_canonical_key(self):
        with self.assertRaisesRegex(identity.IdentityError, "unmatched"):
            self.map([{**self.row, "player_name": "Unknown Player", "source_player_id": 869}])

    def test_source_and_canonical_duplicates_fail_closed(self):
        for second in (copy.deepcopy(self.row), {**self.row, "source_player_id": "fp-2"}):
            with self.subTest(second=second), self.assertRaises(identity.IdentityError):
                self.map([self.row, second])

    def test_invalid_and_absent_values_fail_closed(self):
        for value in (True, "500", -1, 1001, float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(identity.IdentityError):
                self.map([{**self.row, "native_value": value}])
        without = dict(self.row)
        del without["native_value"]
        with self.assertRaises(identity.IdentityError):
            self.map([without])

    def test_k_dst_have_explicit_exclusion_receipts(self):
        rows, excluded = self.map([self.row, {"source_player_id": "k", "pos": "K"},
                                  {"source_player_id": "dst", "pos": "DST"}])
        self.assertEqual(1, len(rows))
        self.assertEqual(["K", "DST"], [row["pos"] for row in excluded])


if __name__ == "__main__":
    unittest.main()
