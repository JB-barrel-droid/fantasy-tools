"""parse_iso_timestamp: 1-digit fractions and Z work on every Python we run;
inputs 3.11 already parses are unchanged; garbage still raises (JEG-625)."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from lib.timestamps import parse_iso_timestamp  # noqa: E402

UTC = timezone.utc


class ParseIsoTimestamp(unittest.TestCase):
    def test_one_digit_fraction(self):
        self.assertEqual(
            datetime(2026, 10, 9, 3, 25, 30, 100000, tzinfo=UTC),
            parse_iso_timestamp("2026-10-09T03:25:30.1+00:00"))

    def test_other_fraction_lengths(self):
        for text, micro in [("2", 200000), ("12", 120000), ("1234", 123400),
                            ("12345", 123450), ("1234567", 123456), ("123456789", 123456)]:
            self.assertEqual(micro, parse_iso_timestamp(f"2026-10-09T03:25:30.{text}+00:00").microsecond, text)

    def test_trailing_z_with_and_without_fraction(self):
        self.assertEqual(datetime(2026, 10, 9, 3, 25, 30, tzinfo=UTC),
                         parse_iso_timestamp("2026-10-09T03:25:30Z"))
        self.assertEqual(datetime(2026, 10, 9, 3, 25, 30, 500000, tzinfo=UTC),
                         parse_iso_timestamp("2026-10-09T03:25:30.5Z"))

    def test_naive_and_offset_and_space_separator(self):
        self.assertIsNone(parse_iso_timestamp("2026-10-09T03:25:30.7").tzinfo)
        self.assertEqual(timedelta(hours=-5), parse_iso_timestamp("2026-10-09 03:25:30.7-05:00").utcoffset())

    def test_equivalent_to_fromisoformat_for_inputs_old_pythons_accept(self):
        for text in ["2026-10-09T03:25:30", "2026-10-09T03:25:30+00:00", "2026-10-09T03:25:30.123+00:00",
                     "2026-10-09T03:25:30.123456-05:00", "2026-10-09", "2026-10-09T03:25",
                     "2026-10-09 03:25:30.123456"]:
            self.assertEqual(datetime.fromisoformat(text), parse_iso_timestamp(text), text)

    def test_invalid_still_raises(self):
        for text in ["", "garbage", "2026-13-09T03:25:30.1+00:00",                     "2026-10-09T03:25:30.1x", "2026-10-09T25:25:30.1Z", "ZZ", "2026-10-09T03:25:30.1+00:0"]:
            with self.assertRaises(ValueError, msg=text):
                parse_iso_timestamp(text)

    def test_non_string_raises_type_error(self):
        with self.assertRaises(TypeError):
            parse_iso_timestamp(None)


class NoRawDatetimeFromisoformat(unittest.TestCase):
    """Production code parses stamps through parse_iso_timestamp; raw
    datetime.fromisoformat breaks on 1-digit fractions before Python 3.11."""

    DATE_ONLY_OK = {"pipelines/load_value_check.py", "pipelines/fidelity_pulse.py",
                    "pipelines/fidelity_sources/razzball.py", "pipelines/lib/timestamps.py"}

    def test_no_raw_calls(self):
        offenders = []
        for sub in ("pipelines", "tools", "app"):
            for path in (ROOT / sub).rglob("*.py"):
                rel = path.relative_to(ROOT).as_posix()
                if rel in self.DATE_ONLY_OK:
                    continue
                for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    code = line.split("#", 1)[0]
                    if "datetime.fromisoformat(" in code:
                        offenders.append(f"{rel}:{n}")
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
