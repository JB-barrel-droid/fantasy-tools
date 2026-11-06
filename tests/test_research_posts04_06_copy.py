"""JEG-1257: text checks on research posts 4 to 6 (drafts, not on the site).

Local only, not in test-core: `python3 -m unittest tests.test_research_posts04_06_copy`.
Checks the posts use JEG-1212's three source families (published charts,
observed-trade estimates, projections), link only to Writing routes the app
serves (the Value chart, where #1071's source groups and player-detail
comparisons explain the families, or a Writing route), date their evidence to the measured Week 8 build (never as a fresher
week), and keep the measured figures recorded in docs/research/data/posts04_06/.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "docs" / "research" / "posts"
DATA = ROOT / "docs" / "research" / "data" / "posts04_06"
FILES = {
    4: POSTS / "04-how-we-rescale-trade-charts.md",
    5: POSTS / "05-missing-zero-one-source.md",
    6: POSTS / "06-trade-confidence.md",
}

# Labels retired by JEG-1212 (#1071) or by the refresh, and undated "now" wording.
STALE = [
    "four trade charts", "Trade charts (as published)", "Trade charts (rescaled)",
    "FantasyCalc chart", "What the market will pay", "seven sources",
    "as published on October 28", "readout of October 29", "Week 9",
    "this week's", "is the charts,",
]
# "this week" survives only inside the site's own wording for a source that is out.
THIS_WEEK_OK = ["not yet published this week", "No source available this week"]
# The Methodology page (#writing/how-values) still carries pre-#1071 wording, so the
# posts point to the Value chart for the families until that page is updated.
ROUTE = re.compile(r"^#(player-values|writing/(how-values|manifesto|research(/[a-z0-9-]+)?))$")
EVIDENCE = "October 28, 2026 at 23:27 UTC"
HOLD_CAVEAT = "CBS rest of season and Razzball, were on hold as lagging"


def text(n):
    return FILES[n].read_text()


def flat(s):
    return re.sub(r"\s+", " ", s)


class PostsCopyTest(unittest.TestCase):
    def test_no_stale_labels(self):
        for n in FILES:
            body = flat(text(n))
            for label in STALE:
                self.assertNotIn(label, body, f"post {n}: stale label {label!r}")
            rest = body
            for ok in THIS_WEEK_OK:
                rest = rest.replace(ok, "")
            self.assertNotRegex(rest, r"(?i)\bthis week\b", f"post {n}: undated 'this week'")

    def test_three_source_families(self):
        for n in FILES:
            body = flat(text(n))
            for phrase in ("published charts (USA Today, FantasyPros and CBS)" if n != 4 else
                           "USA Today, FantasyPros and CBS",
                           "FantasyCalc", "observed-trade estimate", "CBS rest of season and Razzball"):
                self.assertIn(phrase, body, f"post {n}: missing {phrase!r}")
            self.assertRegex(body, r"(?i)published charts?", f"post {n}")
            self.assertRegex(body, r"(?i)\bprojections?\b", f"post {n}")
            # FantasyCalc is never listed as one of the published charts.
            self.assertNotRegex(body, r"published charts? \((?:[^)]*)FantasyCalc", f"post {n}")

    def test_links_are_app_routes(self):
        for n in FILES:
            body = text(n)
            targets = re.findall(r"\]\(([^)]*)\)", body)
            self.assertIn("#player-values", targets, f"post {n}: no link to the Value chart")
            for target in targets:
                self.assertRegex(target, ROUTE, f"post {n}: link {target!r} is not a route the app serves")
            self.assertNotRegex(body, r"https?://|JEG-\d|\.py\b|\bdocs/|\bapp/v2", f"post {n}: internal reference")
        # The routes the posts use are ones the app serves.
        v2 = (ROOT / "app" / "v2" / "v2.js").read_text()
        self.assertIn('base === "#player-values" ? "values"', v2)
        self.assertIn('"#writing/how-values"', v2)
        # The explanation the posts point to is the one #1071 shipped.
        views = (ROOT / "app" / "v2" / "source-views.js").read_text()
        for label in ("Published charts", "Observed-trade estimates", "Projections", "Published chart average"):
            self.assertIn(label, views)

    def test_evidence_is_dated_to_the_measured_build(self):
        meta = json.loads((DATA / "run_meta.json").read_text())
        self.assertTrue(meta["fixture_built_at"].startswith("2026-10-28T23:27"))
        self.assertEqual(meta["content_week"], 8)
        for n in FILES:
            body = text(n)
            self.assertIn(EVIDENCE, flat(body), f"post {n}")
            self.assertIn("Week 8 figures, not current-week ones", flat(body), f"post {n}")
            self.assertIn("Measured once, Week 8", body, f"post {n}: Sources table")
        self.assertIn("Historical, October 8, 2026", text(4))

    def test_held_projection_caveat(self):
        excluded = json.loads((DATA / "post05.json").read_text())["excluded"]
        for key in ("cbsros", "razzball"):
            self.assertTrue(excluded[key].startswith("held:"), key)
        for n in (5, 6):
            self.assertIn(HOLD_CAVEAT, flat(text(n)), f"post {n}")
            self.assertIn("so both are counted", flat(text(n)), f"post {n}")

    def test_fill_in_wording_held_for_jeg_1201(self):
        # Describes main today (peers are the other trade-value inputs). Rewrite with the
        # readout rerun only when JEG-1201 lands; update this assertion then.
        self.assertIn("scaled from the other trade-value sources that list him", flat(text(4)))
        self.assertIn("from the other trade-value inputs that list him", flat(text(5)))

    def test_measured_figures_retained(self):
        p4 = json.loads((DATA / "post04.json").read_text())
        top = {f["chart"]: f["top_rescaled"] for f in p4["factors"] if f["scoring"] == "ppr" and f["teams"] == 12}
        published = round((top["usatoday"] + top["fantasypros"] + top["cbs"]) / 3, 1)
        body4 = flat(text(4))
        self.assertIn(f"({top['usatoday']} + {top['fantasypros']} + {top['cbs']}) / 3 = {published}", body4)
        self.assertIn(f"observed-trade estimate, {top['fantasycalc']},", body4)
        self.assertIn("2,091 of the 79,272", body4)
        p6 = json.loads((DATA / "post06.json").read_text())["worked_trade"]
        body6 = flat(text(6))
        nets = p6["chart_nets"]
        self.assertIn(f"{nets['usatoday']} on the USA Today chart", body6)
        self.assertIn(f"+{nets['fantasycalc']} on FantasyCalc's observed-trade estimate", body6)
        self.assertIn(p6["site_deal_read"]["title"], body6)
        p5 = json.loads((DATA / "post05.json").read_text())
        self.assertIn(f"{p5['low_confidence']['projections']} of {p5['rows']} players in Week 8", flat(text(5)))


if __name__ == "__main__":
    unittest.main()
