"""A fidelity pulse red holds that source, with per-source tolerance (JEG-520).

Jeremy 2026-10-09: a red in the pulse holds the source, "though with some
tolerance ... to understand the difference between day to day adjustments vs
old/bad data". Done when a seeded stale or bad snapshot holds exactly that
source, and a normal day-to-day change does not hold.

Hermetic: the pulse runs on the synthetic worlds of tests/test_fidelity_pulse.py
(publisher == stored == chart, then one fault seeded); the chain side
(pipelines/fidelity_hold.py) runs on a small fixture.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import fidelity_hold as fh  # noqa: E402
import fidelity_pulse as fp  # noqa: E402
import value_check as vc  # noqa: E402
from tests import test_fidelity_pulse as T  # noqa: E402

TODAY = date(2026, 10, 9)


def fixture(week_label="Week 5", built_at="2026-10-09T20:00:00+00:00", tag="new"):
    """Every section the chain knows, each tagged so a restore is visible."""
    secs = {}
    for root, d in vc.SOURCE_DERIVED.items():
        for sec in d["sections"]:
            secs[sec] = {"week_designated": week_label, "tag": f"{tag}:{sec}"}
    return {"built_at": built_at, "sources": secs}


def held_sections(fx):
    return {sec for sec, s in fx["sources"].items() if isinstance(s, dict) and s.get("validationHold")}


class PulseHoldsExactlyTheBadSource(unittest.TestCase):
    """Seeded stale or bad data -> a hold on that source only."""

    def holds(self, env, sources=fp.TRADE_CHARTS):
        _, doc, _ = env.run(sources)
        return doc["holds"]

    def test_baseline_holds_nothing(self):
        self.assertEqual({}, self.holds(T.Env()))

    def test_stored_value_differs_from_the_same_article_holds_that_source(self):
        env = T.Env()
        name, pos, vals, sf = env.pub["usatoday"][2]
        env.pub["usatoday"][2] = (name, pos, dict(vals, std=vals["std"] + 3), sf)  # page unchanged since the save
        holds = self.holds(env)
        self.assertEqual(["usatoday"], sorted(holds))
        self.assertEqual("fidelity: publisher_vs_stored", holds["usatoday"]["reason"])

    def test_served_chart_differs_from_stored_holds(self):
        env = T.Env()
        env.chart["sources"]["cbs"]["combos"]["half_12"]["native"]["jahmyr gibbs"] = 99.0
        holds = self.holds(env)
        self.assertEqual(["cbs"], sorted(holds))
        self.assertEqual("stored_vs_chart", holds["cbs"]["stage"])

    def test_wrong_week_holds(self):
        env = T.Env()
        env.page_week["cbs"] = 4  # the page is week 4, stored rows say week 5
        self.assertEqual(["cbs"], sorted(self.holds(env)))

    def test_missing_block_of_players_holds(self):
        env = T.Env()
        env.stored["usatoday"] = T.stored_rows("usatoday", {1: T.CHART[1]}, url=T.URLS["usatoday"])
        self.assertIn("usatoday", self.holds(env))

    def test_fantasycalc_broken_save_holds(self):
        env = T.Env()
        for k in list(env.pub["fantasycalc"]):
            name, pos, vals, sf = env.pub["fantasycalc"][k]
            env.pub["fantasycalc"][k] = (name, pos, {s: v * 3 for s, v in vals.items()}, sf)
        self.assertEqual(["fantasycalc"], sorted(self.holds(env, ["fantasycalc"])))

    def test_projection_same_version_difference_holds(self):
        env = T.ProjEnv()
        env.stored[0].update(std=0.0, half=0.0, full=0.0)  # zeroed on save; publisher unchanged
        r, _ = env.run()
        self.assertEqual("fidelity: publisher_vs_stored", r["hold"]["reason"])


class NormalChangeDoesNotHold(unittest.TestCase):
    """Day-to-day movement stays amber (alert only), never a hold."""

    def test_fantasycalc_live_movement_inside_the_band(self):
        env = T.Env()
        for k in list(env.pub["fantasycalc"])[:10]:
            name, pos, vals, sf = env.pub["fantasycalc"][k]
            env.pub["fantasycalc"][k] = (name, pos, {s: v + 7 for s, v in vals.items()}, sf)
        res, doc, _ = env.run(["fantasycalc"])
        self.assertEqual("amber", res["fantasycalc"]["status"])
        self.assertEqual({}, doc["holds"])

    def test_article_revised_after_the_save_is_update_available(self):
        env = T.Env()
        env.revised["cbs"] = "2026-10-08T20:00:00Z"  # after the 15:00 save, 3 h ago
        name, pos, vals, sf = env.pub["cbs"][2]
        env.pub["cbs"][2] = (name, pos, dict(vals, std=vals["std"] + 1), sf)
        res, doc, _ = env.run(["cbs"])
        self.assertIn("update available", res["cbs"]["stages"]["publisher_vs_stored"]["summary"])
        self.assertEqual({}, doc["holds"])

    def test_projection_daily_update(self):
        env = T.ProjEnv()
        env.pub[2] = ("Jahmyr Gibbs", "RB", {"std": "0.0", "half": "0.0", "full": "0.0"})
        env.live = {"ok": True, "fingerprint": "fp-after-news", "error": None}
        r, _ = env.run()
        self.assertEqual("amber", r["status"])
        self.assertIsNone(r["hold"])

    def test_amber_and_unknown_never_hold(self):
        result = {"stages": {n: {"status": s} for n, s in zip(fp.STAGES, ("amber", "unknown", "amber", "red", "amber"))}}
        # reference_vs_engine red is the JEG-479 value check's hold, not this one
        self.assertIsNone(fp.hold_decision(result, "b1", None, T.NOW))


class HeldSourceInThePulse(unittest.TestCase):
    def held_env(self, stage="publisher_vs_stored", identity="bake_v1"):
        env = T.Env()
        env.chart["sources"]["usatoday"]["validationHold"] = {
            "reason": f"fidelity: {stage}", "root": "usatoday", "stage": stage, "identity": identity,
            "since": "2026-10-08T18:00:00Z"}
        return env

    def test_hold_releases_when_stored_matches_the_publisher_again(self):
        env = self.held_env()
        env.chart["sources"]["usatoday"]["combos"]["half_12"]["native"]["jahmyr gibbs"] = 1.0  # kept old section
        res, doc, _ = env.run(["usatoday"])
        self.assertEqual("n/a", res["usatoday"]["stages"]["stored_vs_chart"]["status"])
        self.assertEqual({}, doc["holds"])

    def test_chart_hold_stays_until_a_newer_save(self):
        env = self.held_env("stored_vs_chart", identity="bake_v1")
        res, doc, _ = env.run(["usatoday"])
        self.assertEqual("red", res["usatoday"]["stages"]["stored_vs_chart"]["status"])
        self.assertEqual("2026-10-08T18:00:00Z", doc["holds"]["usatoday"]["since"])
        env = self.held_env("stored_vs_chart", identity="bake_v0")  # a newer save exists now
        _, doc, _ = env.run(["usatoday"])
        self.assertEqual({}, doc["holds"])

    def test_last_good_is_carried_forward_while_held(self):
        holds = {"cbs": {"reason": "fidelity: stored_vs_chart"}}
        prev_clean = {"site": {"built_at": "B1"}, "holds": {}, "last_good": {"cbs": "B0"}}
        self.assertEqual("B1", fp.last_good(["cbs"], holds, {"built_at": "B2"}, prev_clean)["cbs"])
        prev_held = {"site": {"built_at": "B2"}, "holds": holds, "last_good": {"cbs": "B1"}}
        self.assertEqual("B1", fp.last_good(["cbs"], holds, {"built_at": "B3"}, prev_held)["cbs"])
        self.assertEqual("B3", fp.last_good(["cbs"], {}, {"built_at": "B3"}, prev_held)["cbs"])

    def test_holds_changed_flags_a_new_or_ended_hold(self):
        env = T.Env()
        _, doc, _ = env.run(["usatoday"])
        self.assertFalse(doc["holds_changed"])
        prev = {"holds": {"usatoday": {"reason": "fidelity: freshness"}}}
        doc2, _ = fp.run(["usatoday"], fetch=T.FakeFetch(env.build_pages()), store=T.FakeStore(env.stored),
                         ident=fp.Identity.load(T.PLAYERS + T.FILLER), site_doc=env.chart, site_error=None,
                         report=None, report_where="n/a", now=T.NOW, previous=prev)
        self.assertTrue(doc2["holds_changed"])


class ChainAppliesTheHold(unittest.TestCase):
    HOLD = {"stage": "publisher_vs_stored", "reason": "fidelity: publisher_vs_stored", "identity": "b2",
            "since": "2026-10-09T21:51:00Z", "summary": "39 value mismatches"}

    def test_exactly_the_held_source_and_its_derived_sections(self):
        good = fixture("Week 4", built_at="B-good", tag="good")
        out, report = fh.apply_fidelity_holds(fixture(), {"cbs": self.HOLD}, lambda root: good, 5, TODAY)
        self.assertEqual({"cbs", "cbs_adjusted"}, held_sections(out))
        for sec in ("cbs", "cbs_adjusted"):
            hold = out["sources"][sec]["validationHold"]
            self.assertEqual("fidelity: publisher_vs_stored", hold["reason"])
            self.assertEqual(("cbs", 4, "B-good"), (hold["root"], hold["kept_week"], hold["restored_from"]))
            self.assertEqual(f"good:{sec}", out["sources"][sec]["tag"])  # served from the last good chart
        for sec, s in out["sources"].items():
            if sec not in ("cbs", "cbs_adjusted"):
                self.assertEqual(f"new:{sec}", s["tag"], sec)  # every other source publishes this run's
        self.assertEqual(["cbs", "cbs_adjusted"], report["cbs"]["restored"])

    def test_projection_hold_keeps_its_section_labelled(self):
        out, report = fh.apply_fidelity_holds(fixture(), {"espn": self.HOLD},
                                              lambda root: fixture(tag="good"), 5, TODAY)
        self.assertEqual({"espn"}, held_sections(out))
        self.assertEqual("new:espn", out["sources"]["espn"]["tag"])
        self.assertEqual([], report["espn"]["restored"])

    def test_no_last_good_chart_keeps_the_section_held(self):
        out, _ = fh.apply_fidelity_holds(fixture(), {"usatoday": self.HOLD}, lambda root: None, 5, TODAY)
        self.assertEqual({"usatoday", "usatoday_adjusted"}, held_sections(out))
        self.assertIsNone(out["sources"]["usatoday"]["validationHold"]["kept_week"])

    def test_release_only_fidelity_holds_the_pulse_dropped(self):
        fx = fixture()
        fx["sources"]["cbs"]["validationHold"] = {"reason": "fidelity: freshness", "root": "cbs"}
        fx["sources"]["usatoday"]["validationHold"] = {"reason": "fidelity: stored_vs_chart", "root": "usatoday"}
        fx["sources"]["espn"]["validationHold"] = {"reason": "engine and Python reference disagree on espn",
                                                   "root": "espn"}
        self.assertEqual(["cbs"], fh.release_fidelity_holds(fx, {"usatoday": self.HOLD}))
        self.assertEqual({"usatoday", "espn"}, held_sections(fx))
        # and the JEG-479 release leaves fidelity holds alone
        self.assertEqual(["espn"], vc.release_holds(fx, []))
        self.assertEqual({"usatoday"}, held_sections(fx))

    def test_chain_status_lists_the_hold(self):
        _, report = fh.apply_fidelity_holds(fixture(), {"cbs": self.HOLD}, lambda root: None, 5, TODAY)
        status = fh.update_chain_status({"status": "green", "held": []}, report, 5)
        self.assertEqual(["cbs"], status["held"])
        self.assertEqual("published_with_holds", status["status"])
        self.assertEqual("fidelity: publisher_vs_stored", status["held_detail"]["cbs"]["reason"])

    def test_pulse_holds_ignores_unknown_roots(self):
        self.assertEqual(["cbs"], sorted(fh.pulse_holds({"holds": {"cbs": self.HOLD, "nope": self.HOLD}})))


class LastGoodFixtureFromGit(unittest.TestCase):
    def test_finds_the_commit_with_that_built_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            run = lambda *a: subprocess.run(["git", *a], cwd=tmp, check=True, capture_output=True)  # noqa: E731
            run("init", "-q")
            run("config", "user.email", "t@example.com")
            run("config", "user.name", "t")
            path = repo / vc.FIXTURE_REL
            path.parent.mkdir(parents=True)
            for built, tag in (("B1", "one"), ("B2", "two"), ("B3", "three")):
                path.write_text(json.dumps(fixture(built_at=built, tag=tag), indent=2))
                run("add", "-A")
                run("commit", "-qm", built)
            got = fh.fixture_with_built_at("B2", repo=repo)
            self.assertEqual("two:cbs", got["sources"]["cbs"]["tag"])
            self.assertIsNone(fh.fixture_with_built_at("B9", repo=repo))
            self.assertIsNone(fh.fixture_with_built_at(None, repo=repo))


if __name__ == "__main__":
    unittest.main()
