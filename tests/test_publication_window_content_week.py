"""Publication windows count days within the content week (starts Tuesday).

2026-10-06 regression: on the Tuesday a new content week opened, cbsros
(publishes Wednesday) was scored "6 days since publish day" -> MISSED_WINDOW
-> import gate RED, the day BEFORE its publish day."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipelines.lib.publication_windows import get_publication_status  # noqa: E402

TUE, WED, THU, FRI = date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)


class ContentWeekWindowTest(unittest.TestCase):
    def test_wednesday_publisher_is_not_late_on_tuesday(self):
        status, reason = get_publication_status("cbsros", 4, 5, TUE)
        self.assertEqual("yellow", status, reason)
        self.assertIn("not due yet", reason)

    def test_wednesday_publisher_grace_then_red(self):
        self.assertEqual("yellow", get_publication_status("cbsros", 4, 5, WED)[0])
        self.assertEqual("yellow", get_publication_status("cbsros", 4, 5, THU)[0])
        self.assertEqual("red", get_publication_status("cbsros", 4, 5, FRI)[0])

    def test_tuesday_publisher_unchanged(self):
        self.assertEqual("yellow", get_publication_status("usatoday", 4, 5, TUE)[0])
        self.assertEqual("yellow", get_publication_status("usatoday", 4, 5, WED)[0])
        self.assertEqual("red", get_publication_status("usatoday", 4, 5, THU)[0])

    def test_two_weeks_behind_is_still_red(self):
        self.assertEqual("red", get_publication_status("cbsros", 3, 5, TUE)[0])


if __name__ == "__main__":
    unittest.main()
