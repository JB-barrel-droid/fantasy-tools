"""JEG-807 (2026-10-22): the CBS ROS puller stores the table's position.

CBS prints fullbacks inside the RB table with "(FB)" in the player cell.
Storing the cell's FB made the saver's resolver answer position_conflict
(public.players lists Kyle Juszczyk, Andrew Beck and Michael Burton at RB)
and drop them to review; the pulse reader keeps the table position, finds
them on the page and not in the store, and held CBS ROS red with every
value equal (pulse 39740353223: "3 publisher players not stored").
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "pipelines", ROOT / "pipelines" / "lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pull_cbs_ros_projections as pull  # noqa: E402


def row_html(name: str, cell_pos: str, team: str, layout: list[str]) -> str:
    cell = ('<td><span class="CellPlayerName--long"><a href="/x">' + name + '</a>'
            '<span class="CellPlayerName-position"> ' + cell_pos + ' </span>'
            '<span class="CellPlayerName-team"> ' + team + ' </span></span></td>')
    stats = {"gp": "12", "fpts": "48.0", "fppg": "4.0", "rec": "10"}
    tds = "".join(f"<td>{stats.get(k, '1')}</td>" for k in layout)
    return '<tr class="TableBase-bodyTr">' + cell + tds + "</tr>"


class TablePositionTests(unittest.TestCase):
    def test_fullback_in_the_rb_table_is_stored_as_rb(self):
        html = row_html("Kyle Juszczyk", "FB", "SF", pull.LAYOUTS["RB"])
        rows, review = pull.parse_position("RB", html)
        self.assertEqual([], review)
        self.assertEqual(1, len(rows))
        self.assertEqual("RB", rows[0]["pos"], "the table's position is the stored position")
        self.assertEqual("FB", rows[0]["cell_pos"], "the cell's position is kept for the record")

    def test_a_plain_rb_row_is_unchanged(self):
        html = row_html("Bijan Robinson", "RB", "ATL", pull.LAYOUTS["RB"])
        rows, _ = pull.parse_position("RB", html)
        self.assertEqual(("RB", "RB"), (rows[0]["pos"], rows[0]["cell_pos"]))
        self.assertEqual(48.0, rows[0]["ros_standard"])


if __name__ == "__main__":
    unittest.main()
