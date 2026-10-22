"""JEG-856 Part B: every source link goes to a real page, not a site root.

The one place source URLs live is assets/comparison-sources-data.json, sources.<id>.url (or, for the
projection sources, sources.<id>.source_url). The v2 front end (sourceUrl in app/v2/v2.js) and the
single-source build-up view (JEG-849) read that same field. The weekly pipeline rewrites it for the
weekly articles (promote_comparison_section.py takes it from source_provenance.source_url).

Checks, offline: each charted/projection source id has an https URL with a real path (no bare domain
root); weekly article URLs carry the current week number; static pages are on a known-good allowlist
(each verified with a live HTTP + page-text check on 2026-10-22, see the PR).
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app" / "trade-value-chart" / "assets" / "comparison-sources-data.json"
FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"

# Sources the site charts or lists, and the one sources.<id> field that carries the page.
SOURCE_IDS = ["usatoday", "fantasycalc", "fantasypros", "cbs", "cbsros", "razzball"]
# ESPN has no stable public direct page (needs a decision, JEG-856); it is deliberately link-less.
NO_LINK_YET = {"espn"}
WEEKLY_ARTICLES = ["usatoday", "fantasypros", "cbs"]
STATIC_PAGES = {"fantasycalc": "https://fantasycalc.com/trade-value-chart"}


def source_url(sources: dict, sid: str) -> str:
    s = sources.get(sid) or {}
    return s.get("url") or s.get("source_url") or ""


def problems(doc: dict) -> list[str]:
    sources = doc["sources"]
    out = []
    for sid in SOURCE_IDS:
        url = source_url(sources, sid)
        if not url:
            out.append(f"{sid}: no URL")
            continue
        p = urlparse(url)
        if p.scheme != "https" or not p.netloc:
            out.append(f"{sid}: not https: {url}")
        if p.path in ("", "/"):
            out.append(f"{sid}: bare domain root: {url}")
    for sid, want in STATIC_PAGES.items():
        if source_url(sources, sid) != want:
            out.append(f"{sid}: expected {want}, got {source_url(sources, sid)}")
    for sid in WEEKLY_ARTICLES:
        week = (sources.get(sid) or {}).get("week_designated") or ""
        m = re.search(r"(\d+)", str(week))
        url = source_url(sources, sid)
        if m and not re.search(rf"week-{m.group(1)}\b", url):
            out.append(f"{sid}: URL not tied to {week}: {url}")
    return out


class SourceLinkUrls(unittest.TestCase):
    def test_published_data(self):
        self.assertEqual(problems(json.loads(DATA.read_text())), [])

    def test_fixture_feeding_the_pipeline(self):
        # promote keeps the fixture url when a source has no article url, so the fixture must be right too.
        self.assertEqual(problems(json.loads(FIXTURE.read_text())), [])

    def test_guard_catches_bare_root_and_stale_week(self):
        doc = json.loads(DATA.read_text())
        doc["sources"]["fantasycalc"]["url"] = "https://fantasycalc.com"
        found = problems(doc)
        self.assertTrue(any("bare domain root" in p for p in found), found)
        doc = json.loads(DATA.read_text())
        doc["sources"]["fantasypros"]["url"] = doc["sources"]["fantasypros"]["url"].replace("week-7", "week-6")
        self.assertTrue(any("not tied" in p for p in problems(doc)))
        doc = json.loads(DATA.read_text())
        del doc["sources"]["razzball"]["source_url"]
        self.assertTrue(any("no URL" in p for p in problems(doc)))


if __name__ == "__main__":
    unittest.main()
