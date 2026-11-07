"""JEG-1565: the trade value audit draft is reproducible and stays private.

- the page's data file equals a fresh run of pipelines/research_trade_value_audit.py;
- every number quoted in the page text (data-n spans) equals the script output;
- the page is noindex, unlisted (not in Learn's list, not a root page) and no other page links to it;
- the framework's banned words stay off the page.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import research_trade_value_audit as audit  # noqa: E402

PAGE = ROOT / "app" / "next" / "research" / "trade-value-audit.html"
DATA = ROOT / "app" / "next" / "research" / "trade-value-audit-data.json"
SCRIPT = ROOT / "app" / "next" / "research" / "trade-value-audit.js"


def fmt(v) -> str:
    """Same as the page's fmt(): the script's value as written."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


class Spans(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.found, self.text = [], [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.stack.append(a.get("data-n"))
        if a.get("data-n"):
            self.found.append([a["data-n"], ""])

    def handle_endtag(self, tag):
        if self.stack:
            self.stack.pop()

    def handle_data(self, data):
        self.text.append(data)
        if self.stack and self.stack[-1] and self.found:
            self.found[-1][1] += data


def lookup(data, path):
    cur = data
    for key in path.split("."):
        cur = cur[int(key)] if isinstance(cur, list) else cur[key]
    return cur


class AuditData(unittest.TestCase):
    """The article is one snapshot (week 9). Once the weekly refresh replaces
    data/fixtures/current, a fresh run describes a different week: the
    reproduction test then skips (check out the commit that published the
    snapshot to reproduce it), and the page-vs-data checks keep running."""

    @classmethod
    def setUpClass(cls):
        cls.saved = json.loads(DATA.read_text(encoding="utf-8"))
        cls.html = PAGE.read_text(encoding="utf-8")
        fixture = json.loads(audit.vr.FIXTURE.read_text(encoding="utf-8"))
        cls.same_snapshot = fixture.get("built_at") == cls.saved["fixture_built_at"]
        cls.fresh = json.loads(audit.dump(audit.build())) if cls.same_snapshot else cls.saved

    def test_data_file_equals_a_fresh_run(self):
        if not self.same_snapshot:
            self.skipTest("fixture moved past the week 9 snapshot; reproduce at the publishing commit")
        self.assertEqual(self.fresh, self.saved, "run: python3 pipelines/research_trade_value_audit.py")

    def test_every_quoted_number_equals_the_script(self):
        p = Spans()
        p.feed(self.html)
        self.assertGreater(len(p.found), 60)
        for path, text in p.found:
            with self.subTest(path=path):
                self.assertEqual(fmt(lookup(self.fresh, path)), text.strip())

    def test_headline_facts(self):
        h = self.fresh["headline"]
        self.assertEqual(0, h["fantasypros_numbers_changed_pct"])
        self.assertEqual(0, h["fantasycalc_top_flex_reordered"])
        f = self.fresh["fantasycalc_scoring_factors"]
        self.assertLessEqual(f["RB"]["spread"], 0.002)
        self.assertLessEqual(f["WR"]["spread"], 0.002)
        for k in audit.CHARTS:
            self.assertGreaterEqual(h["pairs_raw"][k], h["pairs_after_waiver"][k])

    def test_scorecard_levels_follow_the_rules(self):
        card = self.fresh["scorecard"]
        self.assertEqual("Weak", card["fantasypros"]["scoring"]["label"])
        self.assertEqual("OK", card["fantasycalc"]["scoring"]["label"])
        self.assertEqual("Weak", card["cbs"]["depth"]["label"])
        for k in audit.PROJ:
            self.assertEqual("Not measured", card[k]["balance"]["label"])
        self.assertEqual("Not measured", card["dynastyprocess"]["balance"]["label"])
        self.assertEqual("Weak", card["dynastyprocess"]["scoring"]["label"])

    def test_named_min_and_max_in_the_text(self):
        """Section 9 names the charts at the ends of the like-for-like range."""
        c = {k: v for k, v in self.fresh["dynastyprocess"]["rank_corr_common"].items() if k != "n"}
        self.assertEqual("fantasypros", min(c, key=c.get))
        self.assertEqual("fantasycalc", max(c, key=c.get))

    def test_scoring_claims_come_from_the_publishers_raw_output(self):
        prov = self.fresh["scoring_provenance"]
        self.assertEqual([100] * 5, prov["identical_std_vs_ppr_pct_by_week"]["fantasypros"])
        caps = prov["fantasycalc_captures"]
        self.assertEqual("week 4 cache", caps[0]["capture"])
        self.assertGreater(caps[0]["RB"]["reordered"], 0)
        for cap in caps[1:]:  # every capture from 2026-10-04 on, live pull included
            for p in ("RB", "WR", "TE"):
                self.assertEqual(0, cap[p]["reordered"], cap["capture"])
        self.assertTrue(all("ppr=0" in c["urls"][0] and "ppr=1" in c["urls"][1] for c in caps if "urls" in c))

    def test_depth_against_the_waiver_line(self):
        dv = self.fresh["depth_vs_waiver"]
        for p in ("QB", "RB", "WR", "TE"):
            cbs = dv["sources"]["cbs"]["12"][p]
            self.assertEqual("short", cbs["class"])
            self.assertEqual(cbs["rostered"] - cbs["listed"], cbs["unpriced"])
            self.assertEqual("past", dv["sources"]["usatoday"]["12"][p]["class"])
        past = {k: v["12"]["value_past_line_pct"] for k, v in dv["sources"].items()}
        self.assertEqual("usatoday", max(past, key=past.get))

    def test_curve_readout_names_line_up_with_values(self):
        for sc, lines in self.fresh["curves"].items():
            for k, vals in lines.items():
                self.assertEqual(len(vals), len(self.fresh["curve_players"][sc][k]), (sc, k))
        self.assertEqual(len(self.fresh["dynastyprocess"]["curve"]), len(self.fresh["dynastyprocess"]["curve_players"]))

    def test_dynastyprocess_snapshot_is_licensed_and_dated(self):
        folder = audit.DP_DIR
        self.assertIn("GNU GENERAL PUBLIC LICENSE", (folder / "LICENSE").read_text(encoding="utf-8"))
        self.assertIn("GPL-3.0", (folder / "SOURCE.md").read_text(encoding="utf-8"))
        for day in audit.DP_DATES:
            self.assertTrue((folder / f"values-players-{day}.csv").exists(), day)
        self.assertEqual(audit.DP_CURRENT, self.fresh["dynastyprocess"]["snapshot"])


class StaysPrivate(unittest.TestCase):
    def test_page_is_noindex(self):
        self.assertIn('<meta name="robots" content="noindex, nofollow">', PAGE.read_text(encoding="utf-8"))

    def test_not_listed_or_linked(self):
        posts = (ROOT / "app" / "next" / "learn" / "posts.json").read_text(encoding="utf-8")
        self.assertNotIn("trade-value-audit", posts)
        import build_root_pages
        self.assertFalse(any("research" in f for f in (*build_root_pages.ROOT_PAGES, *build_root_pages.ROOT_FILES)))
        for path in (ROOT / "app").rglob("*"):
            if path.is_file() and path.suffix in {".html", ".js", ".json", ".md", ".txt"} and "research" not in path.parts:
                self.assertNotIn("trade-value-audit", path.read_text(encoding="utf-8", errors="ignore"), str(path))


class Wording(unittest.TestCase):
    def test_banned_words(self):
        p = Spans()
        p.feed(PAGE.read_text(encoding="utf-8"))
        text = " ".join(p.text) + " " + SCRIPT.read_text(encoding="utf-8")
        self.assertNotRegex(text, re.compile(r"player pool", re.I))
        bare = [m.start() for m in re.finditer(r"\bmarket\b", text, re.I) if text[max(0, m.start() - 5):m.start()].lower() != "live "]
        self.assertEqual([], bare, "the bare word 'market' is banned; use 'Live market' or 'Analyst charts'")
        self.assertNotRegex(text, re.compile(r"\b(demo|illustrative|mock)\b", re.I))


if __name__ == "__main__":
    unittest.main()
