#!/usr/bin/env python3
"""Non-blocking staleness report for Maintained docs (JEG-583 / JEG-601).

Reads the tables in docs/README.md. Every row whose Status is Maintained
carries an Owner ticket and a Verified date (YYYY-MM-DD, or "unknown").
A row is reported when:
- Verified is "unknown" or missing (never verified, or not recorded), or
- Verified is more than 30 days before today (stale; needs a refresh ticket), or
- Owner is "unknown" (no owner ticket recorded).

Always exits 0: this is a report, not a gate. Use --strict to exit 1 when
anything is reported (for local use only).
"""
import argparse
import datetime as dt
import pathlib
import re
import sys

README = pathlib.Path(__file__).resolve().parent.parent / "docs" / "README.md"
MAX_AGE_DAYS = 30
ROW = re.compile(r"^\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*(\w+)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|")


def parse_rows(text):
    """Return (name, path, status, owner, verified) for each doc row with the new columns."""
    rows = []
    for line in text.splitlines():
        m = ROW.match(line)
        if m:
            rows.append(m.groups())
    return rows


def findings(text, today):
    """Return a list of (path, reason) for Maintained rows needing attention."""
    out = []
    for _name, path, status, owner, verified in parse_rows(text):
        if status != "Maintained":
            continue
        if not re.fullmatch(r"JEG-\d+", owner):
            out.append((path, "no owner ticket recorded"))
        try:
            age = (today - dt.date.fromisoformat(verified)).days
        except ValueError:
            out.append((path, "no last-verified date recorded"))
            continue
        if age > MAX_AGE_DAYS:
            out.append((path, f"last verified {verified}, {age} days ago (limit {MAX_AGE_DAYS})"))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--today", help="override today's date (YYYY-MM-DD)")
    parser.add_argument("--strict", action="store_true", help="exit 1 if anything is reported")
    args = parser.parse_args(argv)
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    found = findings(README.read_text(), today)
    total = sum(1 for r in parse_rows(README.read_text()) if r[2] == "Maintained")
    print(f"doc staleness report ({today}): {len(found)} finding(s) across {total} Maintained docs")
    for path, reason in found:
        print(f"  {path}: {reason}")
    return 1 if (found and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
