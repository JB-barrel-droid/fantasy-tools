#!/usr/bin/env python3
"""Check every source link in the trade value audit (JEG-1565) and record the result.

Writes data/research/jeg1565/link-check.json: one row per link with HTTP status,
final URL and check time. Hosts whose robots.txt disallows automated agents for
us (USA Today, ESPN) are recorded as "not_checked_robots" rather than fetched.
tests/test_research_trade_value_audit.py fails when a recorded link is dead or a
link on the page has no record. Run with Python 3.12 (3.9 on macOS fails TLS to some hosts): python3 pipelines/check_trade_value_audit_links.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))
from research_trade_value_audit import SOURCE_LINKS  # noqa: E402

OUT = REPO / "data" / "research" / "jeg1565" / "link-check.json"
UA = "fantasy-tools link check (JEG-1565)"
ROBOTS_BLOCKED = ("usatoday.com", "espn.com")


def check(url: str) -> dict:
    if any(h in url for h in ROBOTS_BLOCKED):
        return {"status": "not_checked_robots", "final_url": url}
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return {"status": resp.status, "final_url": resp.geturl()}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "final_url": url}
    except Exception as exc:  # network or TLS error: record it
        return {"status": f"error: {type(exc).__name__}", "final_url": url}
    return {"status": "error", "final_url": url}


def main() -> int:
    rows = []
    for link in SOURCE_LINKS:
        res = check(link["url"])
        rows.append({"url": link["url"], **res, "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
        time.sleep(1)
    OUT.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    bad = [r for r in rows if not (isinstance(r["status"], int) and 200 <= r["status"] < 400) and r["status"] != "not_checked_robots"]
    for r in rows:
        print(r["status"], r["url"])
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
