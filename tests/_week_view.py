"""Reading a chart that lags the page's week view (JEG-1175 / JEG-1176).

During a week transition each source serves its own week. The page
(curve-widget.js, ValueModel.weekState) shows one week view: the default is
week N+1 once more than half the DDF Value sources serve it, else N. There is
no carry-forward (Jeremy, 2026-10-27): a chart still on an older week is left
out of the newer view, so its curve is empty there.

A render test that reads a chart from the default view must not report such a
chart as missing. The rule here: a chart outside the default view and serving
an older week is read in its own week's view (setWeek), or, when the page
offers no view for that week, reported as lagging (a stderr note, never a
silent skip; stale is a warning, JEG-1176 rule 6). Any other absent chart is a
real gap and stays the caller's failure.

The view's missing_sources names only the charts that feed DDF Value; a chart
on a red review hold (validationHold, hold_level "red") is hidden from it
(JEG-569) and so is in neither list, yet the page still leaves it out of a
newer view. So the test is "not in the view's sources and serving an older
week". A red-held chart that lags alone makes no transition at all (the DDF
Value sources all serve the newest week), so it has no view of its own:
chain run 40624176718 (CBS on Week 7, red-held, the rest on Week 8).
"""
from __future__ import annotations

import sys

WEEK_STATE = "() => window.TradeValueCurveControls.getWeekState?.() || null"
SET_WEEK = "(w) => window.TradeValueCurveControls.setWeek(w)"


def lagging_week(state, key):
    """The week a chart left out of the page's week view still serves, when
    it is lagging (a week before the view's); else None.

    state is getWeekState() (week, weeks, views[w].sources and
    missing_sources, servedWeeks)."""
    if not state:
        return None
    week = state.get("week")
    view = (state.get("views") or {}).get(str(week)) or {}
    served = (state.get("servedWeeks") or {}).get(key)
    if key in (view.get("sources") or []):
        return None
    if not isinstance(served, int) or not isinstance(week, int) or served >= week:
        return None
    return served


def has_view(state, week):
    """True when the page offers a week view for `week`."""
    return week in ((state or {}).get("weeks") or [])


def note_lagging(label, keys, week, state, what):
    """The stderr note for lagging charts whose week has no view, so a chart
    that stops updating does not leave a check unseen."""
    print(f"{label}: {', '.join(keys)} still on Week {week}, older than every week view "
          f"{(state or {}).get('weeks')}; {what}", file=sys.stderr)


def own_week_reads(page, keys, read, label, what="not checked in the browser", state=None):
    """Re-read the lagging charts among `keys` in their own week's view.

    keys: charts the caller found absent from the page's default view.
    read: read(keys_of_one_week), called with the page on that week's view.
    state: the default view's getWeekState() (read from the page if None).

    Returns {"reads": {week: read result}, "weeks": {key: week read in},
    "lagging": {key: served week with no view}}. A key in none of them is not
    lagging: a real gap the caller reports. The page is put back on its
    default view afterwards."""
    if state is None:
        state = page.evaluate(WEEK_STATE)
    out = {"reads": {}, "weeks": {}, "lagging": {}}
    by_week = {}
    for key in keys:
        week = lagging_week(state, key)
        if week is not None:
            by_week.setdefault(week, []).append(key)
    for week, group in sorted(by_week.items()):
        if not has_view(state, week):
            out["lagging"].update({key: week for key in group})
            note_lagging(label, group, week, state, what)
            continue
        page.evaluate(SET_WEEK, week)
        out["reads"][week] = read(group)
        out["weeks"].update({key: week for key in group})
    if out["reads"]:
        page.evaluate(SET_WEEK, None)
    return out
