"""JEG-667: a shorter chart list passes the coverage review when the VP-2.4
fill-in (OC-5) reaches the rosterable set; the names are a warning.

Jeremy, 2026-10-16: "When lists get longer or shorter we need to follow the
conventions we've set, filling in where needed from other charts to get to
full rosters in leagues."

The CBS Week 6 shape: the half-PPR list lost 4 mid-list WR and 4 TE (absent
from the article or published as '--'). Before this change the review held
CBS (`coverage:half_12/WR` and `/TE` fail, more than the 3-player churn
tolerance). The first test fails without the fix. The hold cases prove the
gate keeps holding a pipeline loss and a position fill-in cannot reach.

Runs the Python reference on the committed fixture and players.json, so the
fill-in is the real one (other charts as peers, real projections).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
import review_comparison_candidate as r  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "data/fixtures/current/comparison-sources-data.json"
PLAYERS = REPO / "data/fixtures/current/players.json"
SOURCE, COMBO = "cbs", "half_12"


class CoverageFillInTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text())
        cls.pos_of = {p["player_key"]: p["pos"] for p in json.loads(PLAYERS.read_text())["players"]}
        cls.keys = cls.fixture["player_keys"]
        fx = cls.fixture["sources"][SOURCE]["combos"][COMBO]
        cls.fx = fx

        def ranked(pos):
            return sorted((s for s in fx["native"] if cls.pos_of.get(cls.keys.get(s)) == pos),
                          key=lambda s: -float(fx["native"][s]))
        cls.wr, cls.te = ranked("WR"), ranked("TE")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def review(self, drop=(), keep_listed=(), add=None, accepted=None):
        fx = self.fx
        native = {s: v for s, v in fx["native"].items() if s not in drop}
        for s in keep_listed:          # listed by CBS but unpriced: a pipeline loss
            native[s] = fx["native"][s]
        reidx = {s: fx["reindexed"][s] for s in native if s in fx["reindexed"] and s not in keep_listed}
        for s, v in (add or {}).items():
            native[s] = v
            reidx[s] = 0.0
        n = {p: sum(1 for s in reidx if self.pos_of.get(self.keys.get(s)) == p)
             for p in r.POSITIONS}
        cand = {
            "schema": "trade-value-comparison-section-reindexed-v1",
            "source_key": SOURCE, "reindex_status": "complete", "asof": "2026-10-14",
            "week_designated": "Week 6", "content_vintage": "Week 6",
            "combos": {COMBO: {"native": native, "reindexed": reidx,
                               "player_keys": {s: self.keys[s] for s in native},
                               "n": n, "index_total": fx["index_total"]}},
            "review_rows": [],
        }
        path = self.tmp / "cand.json"
        path.write_text(json.dumps(cand))
        acc = self.tmp / "accepted.json"
        if accepted is not None:
            acc.write_text(json.dumps({"entries": accepted}))
        rep = r.review_candidate(str(path), fixture_path=FIXTURE, players_path=PLAYERS,
                                 no_live_verify=True,
                                 coverage_accepted_path=str(acc if accepted is not None
                                                            else self.tmp / "none.json"))
        checks = {c["name"]: c for c in rep["checks"]}
        return rep, checks

    def week6_drop(self):
        # 4 mid-list WR and 4 TE, beyond the 3-player churn tolerance and not tail.
        return tuple(self.wr[20:24]) + tuple(self.te[6:10])

    def test_shorter_list_passes_as_named_warning_when_fill_in_reaches(self):
        drop = self.week6_drop()
        rep, checks = self.review(drop=drop)
        for pos in ("WR", "TE"):
            cov = checks[f"coverage:{COMBO}/{pos}"]
            self.assertEqual(cov["status"], "warn", cov["detail"])
            self.assertIn("fill-in reaches the rosterable set", cov["detail"])
            self.assertIn("list changed (warning", cov["detail"])
        for s in drop:
            self.assertTrue(any(s in c["detail"] for c in checks.values()), s)
        self.assertEqual(rep["verdict"], "ready",
                         [c for c in rep["checks"] if c["status"] == "fail"])

    def test_convention_governs_over_a_recorded_floor_accept(self):
        # #668/#669 recorded a CBS Week 6 floor accept (WR 41 / TE 10). The
        # fill-in convention is the rule; the accept is only a fallback, so a
        # list fill-in covers passes on the convention, not on the accept.
        drop = self.week6_drop()
        n = {"WR": len(self.wr) - 4, "TE": len(self.te) - 4}
        entries = [{"source": SOURCE, "combo": COMBO, "pos": p, "week": 6,
                    "approved_by": "Jeremy", "approved_on": "2026-10-16",
                    "reason": "refresh floor", "floor": n[p]} for p in ("WR", "TE")]
        _, checks = self.review(drop=drop, accepted=entries)
        for pos in ("WR", "TE"):
            cov = checks[f"coverage:{COMBO}/{pos}"]
            self.assertEqual(cov["status"], "warn", cov["detail"])
            self.assertIn("fill-in reaches the rosterable set", cov["detail"])
            self.assertNotIn("accepted", cov["detail"].lower(), cov["detail"])

    def test_pipeline_loss_still_holds(self):
        drop = self.week6_drop()
        _, checks = self.review(drop=drop, keep_listed=drop[:1])
        cov = checks[f"coverage:{COMBO}/WR"]
        self.assertEqual(cov["status"], "fail", cov["detail"])
        self.assertIn("pipeline loss", cov["detail"])

    def test_position_fill_in_cannot_reach_still_holds(self):
        # CBS lists no TE at all: VP-2.4b does not fill a position the chart
        # does not price, so the rosterable set cannot be reached.
        _, checks = self.review(drop=tuple(self.te))
        cov = checks[f"coverage:{COMBO}/TE"]
        self.assertEqual(cov["status"], "fail", cov["detail"])
        self.assertIn("lists no TE", cov["detail"])

    def test_projection_source_is_never_filled_in(self):
        ok, detail = r.coverage_fill_in_reaches("espn", "half_12", "WR", {}, FIXTURE, PLAYERS)
        self.assertFalse(ok)
        self.assertIn("not a chart", detail)

    def test_membership_change_at_equal_length_is_a_named_warning(self):
        gone = self.wr[-1]
        new = next(s for s, k in self.keys.items()
                   if self.pos_of.get(k) == "WR" and s not in self.fx["native"])
        rep, checks = self.review(drop=(gone,), add={new: float(self.fx["native"][gone])})
        cov = checks.get(f"coverage_list:{COMBO}/WR")
        self.assertIsNotNone(cov, list(checks))
        self.assertEqual(cov["status"], "warn")
        self.assertIn(gone, cov["detail"])
        self.assertIn(new, cov["detail"])


class ChainStatusListChangeTest(unittest.TestCase):
    def test_promoted_list_change_is_named_in_the_status(self):
        import rebuild_comparison_chain as chain
        review = {"checks": [
            {"name": "coverage:half_12/TE", "status": "warn", "detail": "..."},
            {"name": "coverage:half_12/WR", "status": "pass", "detail": "..."}],
            "combos": {"half_12": {"coverage": {"TE": {
                "fixture": 14, "candidate": 10, "dropped": ["dalton kincaid", "kenyon sadiq"],
                "added": []}}}}}
        lines = chain.list_change_warnings("cbs-half-12-section", review)
        self.assertEqual(len(lines), 1)
        self.assertIn("half_12/TE list 14 -> 10", lines[0])
        self.assertIn("dalton kincaid", lines[0])
        text = chain.describe_result({"status": "ok", "promoted": 3, "sections": 3,
                                      "list_change_warnings": lines})
        self.assertIn("WARNING list changed", text)
        self.assertIn("kenyon sadiq", text)


if __name__ == "__main__":
    unittest.main()
