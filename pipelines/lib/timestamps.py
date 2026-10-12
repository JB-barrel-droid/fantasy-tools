"""Tolerant ISO-8601 timestamp parsing (JEG-625, 2026-10-12).

``datetime.fromisoformat`` only accepts 3 or 6 fractional-second digits and
rejects a trailing ``Z`` before Python 3.11. Publishers and our own writers emit
1-digit fractions (``...30.1+00:00``) and ``Z`` suffixes, so the same stamp
parsed on 3.11+ but raised on 3.9/3.10. ``parse_iso_timestamp`` normalizes just
those two things and then defers to ``fromisoformat``: any input 3.11 already
parses gives the identical result, and anything else still raises ValueError.
"""
from __future__ import annotations

import re
from datetime import datetime

# <date><T| ><hh:mm:ss>.<digits><optional tz>; the tz tail is validated so a
# malformed tail is left untouched and fromisoformat rejects it.
_FRACTION = re.compile(
    r"^(?P<head>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})\.(?P<frac>\d+)"
    r"(?P<tz>[+-]\d{2}(?::?\d{2}(?::?\d{2})?)?)?$"
)


def parse_iso_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp; raise ValueError when it is not one."""
    if not isinstance(value, str):
        raise TypeError(f"timestamp must be a string, got {type(value).__name__}")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    match = _FRACTION.match(text)
    if match:
        frac = match.group("frac")[:6].ljust(6, "0")
        text = f"{match.group('head')}.{frac}{match.group('tz') or ''}"
    return datetime.fromisoformat(text)
