"""JEG-436: the coverage check names the players it lost and tolerates only
small, named, tail-of-list publisher churn.

Background: the 2026-10-07 13:33Z rebuild chain held FantasyCalc's week-5
bake on `coverage:full_12_qb1/WR` (76 < 78) and `/TE` (26 < 28) with the
detail "no dropped players identified". Two defects:
  - the baseline was the fixture's recorded index_total.n_priced (WR 78 /
    TE 28), stale against the fixture's own priced set (WR 76 / TE 27);
  - the dropped list kept only fixture players whose reindexed value was
    truthy, and since JEG332-STORED-DRIFT the tail is stored at exactly 0.0.
The real week-5 churn was TE: Pat Freiermuth and Terrance Ferguson left the
FantasyCalc list and Mike Gesicki joined (27 -> 26); WR swapped Kayshon
Boutte for Keon Coleman (76 -> 76).

Every case below runs against a hermetic fixture + players file. The
tolerated case and the stale-baseline case FAIL on the pre-JEG-436 reviewer
(negative proof recorded in docs/claude-log.md); the hold cases prove the
rule stays fail-closed for large, non-tail, still-listed, identity-loss,
live-contradicted and unnamed drops.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
import review_comparison_candidate as r  # noqa: E402

COMBO = "full_12_qb1"


def _te_slugs(n):
    return [f"te player {i}" for i in range(n)]


def build(tmp, *, fx_te=27, recorded_te=None, cand_drop=(), cand_add=(),
          cand_n_te=None, keep_listed=(), review_rows=(), source="fantasycalc",
          fx_wr=10, recorded_wr=None, cand_n_wr=None, zero_te=0):
    """Fixture with fx_te TE + fx_wr WR priced; candidate drops/adds TE slugs.

    TE natives descend from 5800 (te player 0) to a tail near 20; every
    fixture player is priced (reindexed entry, tail players at 0.0 as the
    JEG332-STORED-DRIFT translation stores them).
    """
    tes = _te_slugs(fx_te)
    wrs = [f"wr player {i}" for i in range(fx_wr)]
    extra = list(cand_add)
    players, keys = [], {}
    for i, s in enumerate(tes + extra):
        keys[s] = 7000 + i
        players.append({"name": s.title(), "pos": "TE", "player_key": keys[s]})
    for i, s in enumerate(wrs):
        keys[s] = 8000 + i
        players.append({"name": s.title(), "pos": "WR", "player_key": keys[s]})
    te_native = {s: (5800.0 if i == 0 else max(20.0, 3000.0 / (i + 1) - 60 * i))
                 for i, s in enumerate(tes)}
    for s in tes[len(tes) - zero_te:] if zero_te else ():
        te_native[s] = 0.0       # listed at native 0 (USA Today QB shape)
    wr_native = {s: 9000.0 - 500 * i for i, s in enumerate(wrs)}
    fx_native = {**te_native, **wr_native}
    fx_reidx = {s: (0.0 if v < 300 else round(v / 200, 2)) for s, v in fx_native.items()}
    fixture = {
        "player_keys": keys,
        "sources": {source: {"combos": {COMBO: {
            "native": fx_native,
            "reindexed": fx_reidx,
            "index_total": {
                "TE": {"factor": 0.007, "pre_total": 1.0,
                       "n_priced": recorded_te if recorded_te is not None else fx_te},
                "WR": {"factor": 0.007, "pre_total": 1.0,
                       "n_priced": recorded_wr if recorded_wr is not None else fx_wr},
            },
        }}}},
    }
    c_native = {s: v for s, v in fx_native.items() if s not in cand_drop}
    for s in keep_listed:          # listed by the source, but unpriced
        c_native[s] = fx_native[s]
    for s in extra:
        c_native[s] = 40.0
    c_reidx = {s: fx_reidx.get(s, 0.0) for s in c_native if s not in keep_listed}
    te_set = set(tes) | set(extra)
    n_te = sum(1 for s in c_reidx if s in te_set)
    n_wr = sum(1 for s in c_reidx if s in set(wrs))
    cand = {
        "schema": "trade-value-comparison-section-reindexed-v1",
        "source_key": source, "reindex_status": "complete", "asof": "2026-10-06",
        "combos": {COMBO: {
            "native": c_native,
            "reindexed": c_reidx,
            "player_keys": {s: keys[s] for s in c_native},
            "n": {"TE": cand_n_te if cand_n_te is not None else n_te,
                  "WR": cand_n_wr if cand_n_wr is not None else n_wr},
            "index_total": {"global": {"factor": 0.007, "pre_total": 1.0},
                            "TE": {"factor": 0.007, "pre_total": 1.0},
                            "WR": {"factor": 0.007, "pre_total": 1.0}},
        }},
        "review_rows": list(review_rows),
    }
    paths = {}
    for name, obj in (("fixture", fixture), ("cand", cand),
                      ("players", {"players": players})):
        p = tmp / f"{name}.json"
        p.write_text(json.dumps(obj))
        paths[name] = str(p)
    return paths


def review(paths, **kw):
    kw.setdefault("no_live_verify", True)
    return r.review_candidate(paths["cand"], fixture_path=paths["fixture"],
                              players_path=paths["players"], **kw)


def check(report, name):
    found = [c for c in report["checks"] if c["name"] == name]
    return found[0] if found else None


class CoverageChurnTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    # -- the real week-5 shape --------------------------------------------
    def test_week5_tail_churn_is_named_and_tolerated(self):
        tes = _te_slugs(27)
        paths = build(self.tmp, fx_te=27, recorded_te=28,
                      cand_drop=(tes[25], tes[26]), cand_add=("mike gesicki",))
        rep = review(paths)
        cov = check(rep, f"coverage:{COMBO}/TE")
        self.assertIsNotNone(cov, rep["checks"])
        self.assertEqual(cov["status"], "warn", cov)
        self.assertIn(tes[25], cov["detail"])
        self.assertIn(tes[26], cov["detail"])
        self.assertIn("mike gesicki", cov["detail"])
        self.assertEqual(rep["verdict"], "ready",
                         [c for c in rep["checks"] if c["status"] == "fail"])
        detail = rep["combos"][COMBO]["coverage"]["TE"]
        self.assertEqual(detail["dropped"], sorted([tes[25], tes[26]]))
        self.assertEqual(detail["fixture"], 27)
        self.assertEqual(detail["fixture_recorded_n_priced"], 28)

    def test_stale_recorded_count_alone_is_not_a_drop(self):
        # FantasyCalc WR: recorded 78, priced set 76, candidate 76.
        paths = build(self.tmp, fx_wr=10, recorded_wr=12)
        rep = review(paths)
        self.assertIsNone(check(rep, f"coverage:{COMBO}/WR"), rep["checks"])
        self.assertEqual(check(rep, f"coverage_baseline:{COMBO}/WR")["status"], "warn")
        self.assertEqual(rep["verdict"], "ready")

    # -- stays fail-closed ----------------------------------------------------
    def test_large_drop_holds(self):
        tes = _te_slugs(30)
        paths = build(self.tmp, fx_te=30, cand_drop=tuple(tes[26:30]))  # 4 > cap 3
        cov = check(review(paths), f"coverage:{COMBO}/TE")
        self.assertEqual(cov["status"], "fail")
        self.assertIn("tolerance", cov["detail"])

    def test_many_left_with_replacements_holds(self):
        # Net drop 2 is within the cap, but 4 players left (cap 3).
        tes = _te_slugs(30)
        paths = build(self.tmp, fx_te=30, cand_drop=tuple(tes[26:30]),
                      cand_add=("new te a", "new te b"))
        cov = check(review(paths), f"coverage:{COMBO}/TE")
        self.assertEqual(cov["status"], "fail")
        self.assertIn("4 players left the priced set", cov["detail"])

    def test_count_below_named_set_is_judged_on_the_set(self):
        # One named tail drop, and the candidate's RECORDED count says 22
        # while its priced set holds 26. Pre-follow-up this asserted a hold on
        # "net drop 5" -- the mixed recorded-vs-set basis that held USA Today
        # full_12/QB on 2026-10-07 (recorded 32 vs set 35, nothing dropped).
        # The coverage drop is judged on the sets (net 1, tail churn -> warn);
        # the candidate's own count/set disagreement is surfaced as an
        # UNEXPLAINED coverage_count warn, never silently.
        tes = _te_slugs(27)
        paths = build(self.tmp, cand_drop=(tes[26],), cand_n_te=22)
        rep = review(paths)
        cov = check(rep, f"coverage:{COMBO}/TE")
        self.assertEqual(cov["status"], "warn", cov)
        self.assertIn("net -1", cov["detail"])
        cnt = check(rep, f"coverage_count:{COMBO}/TE")
        self.assertEqual(cnt["status"], "warn")
        self.assertIn("UNEXPLAINED", cnt["detail"])

    def test_non_tail_drop_holds(self):
        tes = _te_slugs(27)
        paths = build(self.tmp, cand_drop=(tes[0],))  # the top TE vanished
        cov = check(review(paths), f"coverage:{COMBO}/TE")
        self.assertEqual(cov["status"], "fail")
        self.assertIn("not tail-of-list", cov["detail"])
        self.assertIn(tes[0], cov["detail"])

    def test_listed_but_unpriced_holds(self):
        tes = _te_slugs(27)
        paths = build(self.tmp, cand_drop=(tes[26],), keep_listed=(tes[26],))
        cov = check(review(paths), f"coverage:{COMBO}/TE")
        self.assertEqual(cov["status"], "fail")
        self.assertIn("still listed", cov["detail"])

    def test_identity_loss_in_review_rows_holds(self):
        tes = _te_slugs(27)
        rows = ({"reason": "unresolved_player_key", "player_key": 7026,
                 "player_norm": "te player 26"},)
        paths = build(self.tmp, cand_drop=(tes[26],), review_rows=rows)
        rep = r.review_candidate(paths["cand"], triage_path=None,
                                 fixture_path=paths["fixture"],
                                 players_path=paths["players"], no_live_verify=True)
        cov = check(rep, f"coverage:{COMBO}/TE")
        self.assertEqual(cov["status"], "fail")
        self.assertIn("identity loss", cov["detail"])

    def test_recorded_count_below_unchanged_set_is_not_a_drop(self):
        # Candidate count says 25 but its priced set is unchanged. Pre-follow-up
        # this asserted a hold ("none named") -- that assertion pinned the
        # mixed-basis defect: no player left the priced set, so there is no
        # coverage loss. The disagreement is a visible warn instead.
        paths = build(self.tmp, cand_n_te=25)
        rep = review(paths)
        self.assertIsNone(check(rep, f"coverage:{COMBO}/TE"), rep["checks"])
        self.assertEqual(check(rep, f"coverage_count:{COMBO}/TE")["status"], "warn")
        self.assertEqual(rep["verdict"], "ready")

    def test_usatoday_zero_native_shape_is_not_a_drop(self):
        # The real 2026-10-07 USA Today full_12/QB hold: fixture and candidate
        # both price 35 players, 3 of them at native 0.0 (excluded from the
        # flex-aware pie's bucket count by design), so both RECORD 32. The
        # pre-fix reviewer compared candidate recorded 32 with fixture set 35
        # and held. Fails on 87b6203^..origin/main (#392) -- see the log.
        paths = build(self.tmp, fx_te=27, zero_te=3, recorded_te=24,
                      cand_n_te=24)
        rep = review(paths)
        self.assertIsNone(check(rep, f"coverage:{COMBO}/TE"), rep["checks"])
        cnt = check(rep, f"coverage_count:{COMBO}/TE")
        self.assertEqual(cnt["status"], "warn")
        self.assertIn("explained by the flex-aware pie", cnt["detail"])
        self.assertEqual(rep["verdict"], "ready",
                         [c for c in rep["checks"] if c["status"] == "fail"])

    def test_genuine_set_drop_still_counted_on_the_set(self):
        # Guard against over-correction: zero-native players in the set do
        # not hide a real loss. 3 zero-natives + 4 tail players dropped holds.
        tes = _te_slugs(30)
        paths = build(self.tmp, fx_te=30, zero_te=3, cand_drop=tuple(tes[22:26]),
                      cand_n_te=23)
        cov = check(review(paths), f"coverage:{COMBO}/TE")
        self.assertEqual(cov["status"], "fail")
        self.assertIn("net drop 4", cov["detail"])

    # -- live list read a day after the bake (fcwk5, 2026-10-07) -------------
    def _live(self, tes_live):
        live = [{"player": {"name": n.title(), "position": "TE"}, "value": v}
                for n, v in tes_live]

        def fake(req, timeout=60):
            return io.BytesIO(json.dumps(live).encode())
        return fake

    def test_dropped_player_live_only_below_depth_falls_to_tail_rule(self):
        # Real shape: the bake (pulled 10-06) lost 2 tail TEs and gained 1
        # (27 -> 26); the 10-07 live list has one of them back as its LAST TE
        # (rank 27 > candidate depth 26). Not provably a pipeline loss: the
        # tail rule decides (warn), and the detail names the live rank.
        tes = _te_slugs(27)
        paths = build(self.tmp, fx_te=27, cand_drop=(tes[25], tes[26]),
                      cand_add=("mike gesicki",))
        live = [(s, 6000.0 - 200 * i) for i, s in enumerate(tes[:25])]
        live += [("mike gesicki", 54.0), (tes[26], 20.0)]
        with mock.patch.object(r.urllib.request, "urlopen", self._live(live)), \
                mock.patch.object(r, "verify_top25_live",
                                  lambda *a, **k: (True, "stub")):
            rep = review(paths, no_live_verify=False)
        cov = check(rep, f"coverage:{COMBO}/TE")
        self.assertEqual(cov["status"], "warn", cov)
        self.assertIn("live tail", cov["detail"])
        self.assertIn("TE27/27", cov["detail"])
        self.assertNotIn("still priced live", cov["detail"])

    def test_dropped_player_live_within_depth_still_holds(self):
        # Same drop, but the live list ranks the missing player 20th of 27 --
        # inside the candidate's depth 26. The bake should have had him:
        # pipeline loss, hold. This is the live contradiction rule intact.
        tes = _te_slugs(27)
        paths = build(self.tmp, fx_te=27, cand_drop=(tes[25], tes[26]),
                      cand_add=("mike gesicki",))
        live = [(s, 6000.0 - 200 * i) for i, s in enumerate(tes[:19])]  # 6000..2400
        live += [(tes[26], 2100.0), ("mike gesicki", 54.0)]           # rank 20
        live += [(f"other te {i}", 40.0 - i) for i in range(6)]       # 27 TEs
        with mock.patch.object(r.urllib.request, "urlopen", self._live(live)), \
                mock.patch.object(r, "verify_top25_live",
                                  lambda *a, **k: (True, "stub")):
            rep = review(paths, no_live_verify=False)
        cov = check(rep, f"coverage:{COMBO}/TE")
        self.assertEqual(cov["status"], "fail", cov)
        self.assertIn("still priced live", cov["detail"])

    def test_live_contradiction_overrides_tail_rule(self):
        tes = _te_slugs(27)
        paths = build(self.tmp, cand_drop=(tes[26],))
        live = [{"player": {"name": "TE Player 26"}, "value": 55}]

        def fake(req, timeout=60):
            return io.BytesIO(json.dumps(live).encode())
        with mock.patch.object(r.urllib.request, "urlopen", fake), \
                mock.patch.object(r, "verify_top25_live",
                                  lambda *a, **k: (True, "stub")):
            rep = review(paths, no_live_verify=False)
        cov = check(rep, f"coverage:{COMBO}/TE")
        self.assertEqual(cov["status"], "fail")
        self.assertIn("still priced live", cov["detail"])

    def test_live_confirmed_drop_passes(self):
        tes = _te_slugs(27)
        paths = build(self.tmp, cand_drop=(tes[26],))

        def fake(req, timeout=60):
            return io.BytesIO(json.dumps([{"player": {"name": "Someone"},
                                           "value": 9}]).encode())
        with mock.patch.object(r.urllib.request, "urlopen", fake):
            rep = review(paths, no_live_verify=False)
        self.assertEqual(check(rep, f"coverage:{COMBO}/TE")["status"], "pass")

    def test_source_without_live_api_uses_tail_rule(self):
        tes = _te_slugs(27)
        paths = build(self.tmp, cand_drop=(tes[26],), source="usatoday")
        rep = review(paths, no_live_verify=False)
        self.assertEqual(check(rep, f"coverage:{COMBO}/TE")["status"], "warn")


if __name__ == "__main__":
    unittest.main()
