"""JEG-1354: players.active follows the active NFL universe, ids first."""
import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import sync_players_active as spa  # noqa: E402

PULLED = "2026-10-20T12:00:00+00:00"


def _sleeper(name, pos, team="SF", news="2026-10-15", **kw):
    e = {"name": name, "pos": pos, "team": team, "active": True, "status": "Active",
         "depth_chart_position": pos, "depth_chart_order": 1}
    if news:
        e["last_news"] = news
    e.update(kw)
    return e


def _player(key, name, pos, active, **md):
    return {"id": f"u{key}", "player_key": key, "full_name": name, "position": pos,
            "active": active, "metadata": md}


def _base(by_id):
    return {"meta": {"pulled_at": PULLED}, "by_sleeper_id": by_id}


class PlanTests(unittest.TestCase):
    def test_current_starter_marked_inactive_is_set_active(self):
        # Brock Purdy's case: on a team, recent news, a gsis id, active=false.
        base = _base({"8183": _sleeper("Brock Purdy", "QB", gsis_id="00-0037834")})
        players = [_player(4561, "Brock Purdy", "QB", False, gsis_id="00-0037834")]
        result = spa.plan(base, players)
        self.assertEqual([r["player_key"] for r in result["activate"]], [4561])
        self.assertEqual(result["activate"][0]["how"], "gsis_id")
        self.assertEqual(result["deactivate"], [])

    def test_name_only_match_activates_at_the_same_position(self):
        base = _base({"6786": _sleeper("CeeDee Lamb", "WR", team="DAL")})
        players = [_player(303, "CeeDee Lamb", "WR", False)]
        self.assertEqual([r["player_key"] for r in spa.plan(base, players)["activate"]], [303])

    def test_name_match_at_another_position_is_not_used(self):
        base = _base({"1": _sleeper("Sam Same", "TE")})
        players = [_player(10, "Sam Same", "WR", False)]
        self.assertEqual(spa.plan(base, players)["activate"], [])

    def test_already_active_player_is_not_patched(self):
        base = _base({"4984": _sleeper("Josh Allen", "QB", team="BUF", gsis_id="00-0034857")})
        players = [_player(869, "Josh Allen", "QB", True, gsis_id="00-0034857")]
        result = spa.plan(base, players)
        self.assertEqual((result["activate"], result["deactivate"]), ([], []))

    def test_retired_player_tied_by_id_is_set_inactive(self):
        # Sleeper never clears a retired player's team; no news for years.
        base = _base({"17": _sleeper("Old Timer", "WR", team="PIT", news="2022-01-01",
                                     gsis_id="00-0011111")})
        players = [_player(5, "Old Timer", "WR", True, gsis_id="00-0011111")]
        result = spa.plan(base, players)
        self.assertEqual([r["player_key"] for r in result["deactivate"]], [5])

    def test_retired_player_reached_by_name_only_keeps_its_flag(self):
        base = _base({"17": _sleeper("Old Timer", "WR", team="PIT", news="2022-01-01")})
        players = [_player(5, "Old Timer", "WR", True)]
        result = spa.plan(base, players)
        self.assertEqual(result["deactivate"], [])

    def test_row_not_in_the_base_is_left_alone(self):
        players = [_player(5, "Nobody Known", "RB", True), _player(6, "Also Unknown", "RB", False)]
        result = spa.plan(_base({}), players)
        self.assertEqual((result["activate"], result["deactivate"]), ([], []))
        self.assertEqual(result["n_unchanged_unreached"], 2)

    def test_row_two_universe_players_resolve_to_is_skipped(self):
        base = _base({"100": _sleeper("Twin Name", "RB", team="KC"),
                      "200": _sleeper("Twin Name", "RB", team="NYJ")})
        players = [_player(7, "Twin Name", "RB", False)]
        result = spa.plan(base, players)
        self.assertEqual(result["activate"], [])
        self.assertEqual([s["player_key"] for s in result["skipped"]], [7])

    def test_out_of_universe_id_does_not_turn_off_a_row_a_universe_player_claims(self):
        base = _base({"1": _sleeper("Kept On", "WR", gsis_id="00-0022222"),
                      "2": _sleeper("Kept On", "WR", team=None, news=None, active=False,
                                    gsis_id="00-0022222")})
        players = [_player(9, "Kept On", "WR", True, gsis_id="00-0022222")]
        self.assertEqual(spa.plan(base, players)["deactivate"], [])

    def test_non_skill_rows_are_never_touched(self):
        base = _base({"50": _sleeper("Kick Er", "K", gsis_id="00-0033333")})
        players = [_player(11, "Kick Er", "K", False, gsis_id="00-0033333")]
        result = spa.plan(base, players)
        self.assertEqual((result["activate"], result["deactivate"]), ([], []))
        self.assertEqual(result["n_skill_rows"], 0)


class GuardAndWriteTests(unittest.TestCase):
    def test_plan_that_changes_most_rows_is_refused(self):
        result = {"activate": [{}] * 8, "deactivate": [], "n_skill_rows": 10}
        self.assertTrue(spa.too_big(result))
        self.assertFalse(spa.too_big({"activate": [{}] * 7, "deactivate": [], "n_skill_rows": 10}))
        self.assertTrue(spa.too_big({"activate": [], "deactivate": [], "n_skill_rows": 0}))

    def test_write_patches_only_the_active_column_by_player_key(self):
        calls = []

        class FakeSb:
            @staticmethod
            def patch(table, body, params):
                calls.append((table, body, params))

        keys = list(range(1, spa.PATCH_BATCH + 2))
        spa.write(FakeSb, {"activate": [{"player_key": k} for k in keys],
                           "deactivate": [{"player_key": 999}]})
        self.assertEqual([c[1] for c in calls], [{"active": True}, {"active": True}, {"active": False}])
        self.assertTrue(all(c[0] == "players" for c in calls))
        self.assertEqual(calls[1][2], f"?player_key=in.({spa.PATCH_BATCH + 1})")
        self.assertEqual(calls[2][2], "?player_key=in.(999)")


class MainDryRunTests(unittest.TestCase):
    """main() writes only with --write, and never when the guard refuses the plan."""

    def _run(self, argv, players):
        calls = []
        fake = types.ModuleType("sbclient")
        fake.get_all = lambda table, params: [dict(p) for p in players]
        fake.patch = lambda table, body, params: calls.append((table, body, params))
        base = _base({"8183": _sleeper("Brock Purdy", "QB", gsis_id="00-0037834")})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "base.json"
            path.write_text(json.dumps(base), encoding="utf-8")
            with mock.patch.dict(sys.modules, {"sbclient": fake}), \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = spa.main(["--base", str(path), *argv])
        return code, calls

    # One row to turn on among two skill rows: 1 change is under the 75% guard.
    SMALL = [_player(4561, "Brock Purdy", "QB", False, gsis_id="00-0037834"),
             _player(6, "Not In Base", "RB", True)]
    # One row to turn on and nothing else: 1 of 1 rows is over the guard.
    TOO_BIG = SMALL[:1]

    def test_default_run_is_a_dry_run(self):
        code, calls = self._run([], self.SMALL)
        self.assertEqual(code, 0)
        self.assertEqual(calls, [])

    def test_write_flag_patches(self):
        code, calls = self._run(["--write"], self.SMALL)
        self.assertEqual(code, 0)
        self.assertEqual(calls, [("players", {"active": True}, "?player_key=in.(4561)")])

    def test_refused_plan_writes_nothing_even_with_write_flag(self):
        for argv in ([], ["--write"]):
            with self.subTest(argv=argv):
                code, calls = self._run(argv, self.TOO_BIG)
                self.assertEqual(code, 1)
                self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
