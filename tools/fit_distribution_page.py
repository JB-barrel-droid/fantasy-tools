"""Fit label distribution on the real built page (JEG-1096).

tests/node/fit_diagnostic.cjs counts fit labels on synthetic engine rows. This counts them the way a manager sees them:
the built dist served locally, a fixture league seeded into the workspace, league-wide Trade opportunities read from
window.TradeValueLeague.ui.result.rows, grouped by `overall` (natural / market / force).

The page clock is pinned to the served data's week (tests/_render_env.pin_data_week_script), as the render tests do;
without the pin, between the Tuesday week flip and the new week's charts landing, every chart is excluded and the page
shows "No trade chart is available this week" with no rows at all.

Needs a built dist (`make sync`) and Playwright with Chromium.

  python3 tools/fit_distribution_page.py                    # 20-team fixture as teams 0, 3, 7 and the 4-team fixture
  python3 tools/fit_distribution_page.py 20team:0 12team:2  # league:team-index pairs ("fixture" = the file's own team)
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import _league_render as L  # noqa: E402
from tests import _render_env  # noqa: E402

DEFAULT = ["20team:0", "20team:3", "20team:7", "4team:fixture"]
LABELS = ("natural", "market", "force")
ROWS = "() => ((window.TradeValueLeague.ui.result || {}).rows || []).map(r => r.overall)"
MSG = "() => ((document.getElementById('v2LgOppsMsg') || {}).textContent || '').trim()"


def main(argv: list[str]) -> int:
    pairs = []
    for arg in argv or DEFAULT:
        name, _, team = arg.partition(":")
        pairs.append((name, "fixture" if team in ("", "fixture") else int(team)))
    print(f"{'league':<10}{'you':>8}{'total':>7}" + "".join(f"{label:>10}" for label in LABELS) + "  note")
    with L.browser_on_build() as (browser, base):
        for name, mine in pairs:
            page = L.open_page(browser, base, width=1440, height=900, init_script=_render_env.pin_data_week_script())
            L.seed(page, name, mine=mine)
            L.wait_opps(page, timeout=120000)
            counts = collections.Counter(page.evaluate(ROWS))
            total = sum(counts.values())
            cells = "".join(f"{counts.get(label, 0):>5} {100 * counts.get(label, 0) / total if total else 0:>3.0f}%" for label in LABELS)
            other = sorted(set(counts) - set(LABELS))
            note = page.evaluate(MSG) if not total else (f"unexpected labels {other}" if other else "")
            print(f"{name:<10}{str(mine):>8}{total:>7}{cells}  {note}")
            page.context.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
