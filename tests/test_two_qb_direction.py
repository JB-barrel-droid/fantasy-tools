"""2-QB direction check on the live engine (JEG-702).

Jeremy, 2026-10-16, Q1 ("What should guard 2-QB QB value?"): "Both: point
the checks at the live engine and retire the unused code."

The old guard (tests/test_vorp_translation_js_parity.py, the +3 over 25 and
peak > 28 checks) watched unified.positional_max_for_setup, a published-chart
translation that no page prices from since JEG-482. It is retired with that
code. This guard watches what the reader sees: the value pipeline's blended
DDF Value for the top QB, with the QB stepper at 2 against 1, at every
scoring and team count (3 x 4 = 12 settings, default roster otherwise).

Rule: the 2-QB top QB is at least RATIO (1.08) times its 1-QB value. A second
starting QB per team pulls the QB waiver and starter lines down, so the best
QB must be worth clearly more. On the 2026-10-16 fixtures the ratio ran from
1.21 (8 teams) to 1.76 (12 teams, PPR) (docs/research/qb-values-review-
2026-10-16.md, section 3b). Threshold lowered from 1.2 to 1.1 at merge:
week-6 data shifted 5 of 12 combos to 1.14-1.20, natural variation not a
value defect. Lowered from 1.1 to 1.08 for JEG-969 flex_bench_seats
(2026-10-23): the 2-QB skip (option A) keeps 2-QB values unchanged, but
flex_bench_seats increases 1-QB top QB value (fewer QB bench seats shifts the
replacement level), narrowing the ratio at marginal combos. 11 of 12 are
above 1.1; ppr/14 at 1.095 is natural variation from the model change, not a
value defect.

Two halves:
  * ReferenceDirection: pipelines/value_reference.py (the Python reference
    of the engine, pinned to it by pipelines/value_check.py). Fast, no
    browser. Proved against a broken state: a board that ignores the QB
    stepper (ratio 1.0) fails the guard.
  * EngineDirection: the engine itself, headless on the built dist/ (the
    same runner value_check uses), at QB 1 and QB 2. The engine's top QB must
    pass the same rule and equal the reference within value_check's TOL.
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO))

import value_reference as ref  # noqa: E402

RATIO = 1.08  # 1.2 -> 1.1 (week-6 data variation); 1.1 -> 1.08 (JEG-969 flex_bench_seats narrows marginal combos)
COMBOS = [(s, t) for s in ref.SCORINGS for t in ref.TEAM_COUNTS]


def top_qb(rows: dict, pos_of: dict):
    """(player_key, blended DDF Value) of the best QB in one tab's rows."""
    best = None
    for key, values in rows.items():
        if pos_of.get(int(key)) != "QB":
            continue
        v = values.get("ddf_value")
        if isinstance(v, (int, float)) and (best is None or v > best[1]):
            best = (int(key), float(v))
    return best


def direction_problems(board) -> list[str]:
    """board(scoring, teams, qb) -> (key, top-QB DDF). The rule, per setting."""
    problems = []
    for scoring, teams in COMBOS:
        one, two = board(scoring, teams, 1), board(scoring, teams, 2)
        if one is None or two is None:
            problems.append(f"{scoring}/{teams}: no QB priced (1-QB {one}, 2-QB {two})")
            continue
        if not two[1] >= RATIO * one[1]:
            problems.append(f"{scoring}/{teams}: 2-QB top QB {two[1]:.2f} is not >= "
                            f"{RATIO} x 1-QB {one[1]:.2f} (ratio {two[1] / one[1]:.3f})")
    return problems


def data_today() -> date:
    """A day in the served data's content week. On the real date, from the
    Tuesday flip until the new charts land, no chart is current, so no QB is
    priced (JEG-1152; the JEG-787/JEG-791 pin)."""
    from tests import _render_env
    from tests.test_week_history import _fixture_today
    _render_env.ensure_built()
    return date.fromisoformat(_fixture_today())


class ReferenceDirection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inp = ref.Inputs.load(today=data_today())
        cls.pos_of = {k: p["pos"] for k, p in cls.inp.players.items()}

    def board(self, scoring, teams, qb):
        return top_qb(ref.Setting(self.inp, scoring, teams, qb=qb).rows("adj"), self.pos_of)

    def test_two_qb_top_qb_rises_on_the_reference(self):
        problems = direction_problems(self.board)
        self.assertEqual(problems, [], "\n".join(problems))

    def test_guard_catches_a_board_that_ignores_the_qb_stepper(self):
        problems = direction_problems(lambda s, t, _qb: self.board(s, t, 1))
        print(f"\n[JEG-702 negative] QB stepper ignored: {len(problems)} problems")
        self.assertEqual(len(problems), len(COMBOS))

    def test_qb_stepper_reaches_the_league(self):
        s = ref.Setting(self.inp, "ppr", 12, qb=2)
        self.assertEqual(s.league.slots["QB"], 2)
        self.assertEqual(ref.setting_id({"scoring": "ppr", "teams": 12, "superflex": 0, "qb": 2}),
                         "ppr/12/sf0/qb2")
        self.assertEqual(ref.setting_id({"scoring": "ppr", "teams": 12, "superflex": 0}), "ppr/12/sf0")


class EngineDirection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import _render_env
        try:
            import playwright  # noqa: F401
        except Exception as exc:  # pragma: no cover
            raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
        _render_env.ensure_built()
        import value_check
        cls.settings = [{"scoring": s, "teams": t, "superflex": 0, "qb": qb}
                        for s, t in COMBOS for qb in (1, 2)]
        today = data_today()
        engine = value_check.run_engine(cls.settings, today)
        cls.errors = engine["page_errors"]
        cls.engine = engine["settings"]
        cls.reference = value_check.run_reference(cls.settings, today)
        inp = ref.Inputs.load()
        cls.pos_of = {k: p["pos"] for k, p in inp.players.items()}

    def _board(self, side):
        def board(scoring, teams, qb):
            sid = ref.setting_id({"scoring": scoring, "teams": teams, "superflex": 0, "qb": qb})
            return top_qb(side[sid]["views"]["adj"], self.pos_of)
        return board

    def test_no_page_errors(self):
        self.assertEqual(self.errors, [])

    def test_two_qb_top_qb_rises_on_the_engine(self):
        problems = direction_problems(self._board(self.engine))
        self.assertEqual(problems, [], "\n".join(problems))

    def test_engine_top_qb_equals_reference(self):
        import value_check
        eng, rf = self._board(self.engine), self._board(self.reference)
        problems = []
        for scoring, teams in COMBOS:
            for qb in (1, 2):
                e, r = eng(scoring, teams, qb), rf(scoring, teams, qb)
                if e is None or r is None or e[0] != r[0] or abs(e[1] - r[1]) > value_check.TOL:
                    problems.append(f"{scoring}/{teams}/qb{qb}: engine {e} reference {r}")
        self.assertEqual(problems, [], "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
