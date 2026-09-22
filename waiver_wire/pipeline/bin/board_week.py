"""Single source of truth for the waiver board's NFL week.

Convention (matches build_waiver_dashboard_data._value_weeks):
- The board serves the upcoming waiver wire and is labeled with the week it
  applies to = observed week + 1, where the observed week is explicit in
  results/imputed_proj_meta.json ("week").
- Fallback when the meta is missing/unreadable: the calendar mapping under
  the season anchor (Week 1 = Wed 2026-09-09 .. Mon 2026-09-14; each later
  week Tue..Mon).

Why this exists (2026-09-17, flaw-034): the board week used to be hardcoded
in 8 files ("bump all seven each run"). The Sep-15 run bumped the label to
"Week 3" one run early and the published dashboard displayed the wrong week
while every derived value in the pipeline said Week 2. Nothing about the
board week is hardcoded anymore — labels AND filenames derive from here.
"""

import json
from datetime import date as _date
from pathlib import Path

LOT = Path(__file__).resolve().parent.parent
RES = LOT / "results"

_SEASON_W1_START = "2026-09-09"  # bump each season (first game of Week 1)


def _nfl_week(date_str):
    """NFL week number for a YYYY-MM-DD date under the season anchor.

    Weeks run Tue..Mon (Week 1 = Wed 2026-09-09 .. Mon 2026-09-14 since the
    season opened on a Wednesday; every later week starts Tuesday).
    """
    d = _date.fromisoformat(str(date_str)[:10])
    anchor = _date.fromisoformat(_SEASON_W1_START)
    return 1 + ((d - anchor).days + 1) // 7


def observed_week():
    """The latest week of played games, from the impute step's own meta."""
    try:
        meta = json.loads((RES / "imputed_proj_meta.json").read_text())
        w = meta.get("week")
        if isinstance(w, int) and w >= 1:
            return w
    except Exception:
        pass
    return None


def board_week_n():
    """The week the board applies to = observed week + 1."""
    obs = observed_week()
    if obs is not None:
        return obs + 1
    return _nfl_week(_date.today().isoformat())


def board_week_label():
    return "Week %d" % board_week_n()


def board_stem():
    """Filename stem for the current board, e.g. 'waiver_board_week2'."""
    return "waiver_board_week%d" % board_week_n()


def delta_stem():
    """Filename stem for the current waiver delta, e.g. 'waiver_delta_week2'."""
    return "waiver_delta_week%d" % board_week_n()


def observed_week_arg():
    """--week value for impute_monday_tv.py: the OBSERVED week, never the
    board week. Clamped >= 1 (preseason/partial-week runs observe week 1)."""
    return max(1, board_week_n() - 1)


if __name__ == "__main__":
    print(board_week_label())
