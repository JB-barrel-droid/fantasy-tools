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


class FirstLiveHolds(unittest.TestCase):
    """The first live pulse with holds (2026-10-09 23:40Z) held two sources on states that are not bad data."""

    def test_a_player_printed_at_one_unit_and_not_stored_does_not_hold(self):
        """Razzball: Scotty Miller printed 0.1 per game in every scoring, not stored. Absent means 0."""  # noqa
        env = T.ProjEnv()
        # a stored WR at 0.0 keeps the page's lowest WR value below Miller's (no row-cap churn)
        env.pub[100] = ("Filler Player0", "WR", {"std": "0.0", "half": "0.0", "full": "0.0"})
        env.stored.append({"player_key": 100, "snap": "2026-10-08", "created_at": "2026-10-08T12:00:00+00:00",
                           "std": 0.0, "half": 0.0, "full": 0.0})
        for combo in env.chart["sources"]["razzball"]["combos"].values():
            combo["native"]["filler player0"] = 0.0
        env.pub[101] = ("Filler Player1", "WR", {"std": "0.1", "half": "0.1", "full": "0.1"})
        r, _ = env.run()
        s1 = r["stages"]["publisher_vs_stored"]
        self.assertEqual("amber", s1["status"], s1["summary"])
        self.assertIsNone(r["hold"])
        env.pub[101] = ("Filler Player1", "WR", {"std": "0.3", "half": "0.4", "full": "0.5"})  # a real value: held
        r, _ = env.run()
        self.assertEqual("fidelity: publisher_vs_stored", (r["hold"] or {}).get("reason"))

    def resaved_env(self, written):
        """The chart was built at 19:28 from the 10-08 rows; then the day was re-saved, dropping Josh Allen
        and adding Tyreek Hill (the save replaces the day's set)."""
        env = T.ProjEnv()
        env.chart["sources"]["razzball"]["lineage"]["raw_built_at"] = "2026-10-08T19:28:12Z"
        env.stored = [r for r in env.stored if r["player_key"] != 1]
        env.stored.append({"player_key": 6, "snap": "2026-10-08", "created_at": "2026-10-08T12:00:00+00:00",
                           "std": 3.0, "half": 3.5, "full": 4.0})
        env.pub = {k: v for k, v in env.pub.items() if k != 1}
        env.pub[6] = ("Tyreek Hill", "WR", {"std": "3.0", "half": "3.5", "full": "4.0"})
        for row in env.stored:
            row["_written_at"] = written
        env.probe = {"acked_fp": "fp-saved", "acked_at": written}
        return env

    def test_a_player_swap_from_a_re_save_after_the_build_does_not_hold(self):
        r, _ = self.resaved_env("2026-10-08T23:25:00+00:00").run()
        s2 = r["stages"]["stored_vs_chart"]
        self.assertEqual("amber", s2["status"], s2["summary"])
        self.assertIsNone(r["hold"])

    def test_a_re_saved_row_whose_stamp_did_not_move_does_not_hold(self):
        """CBS rest of season 2026-10-09: the 23:25Z save changed Tank Dell's values, but his row kept its
        11:25Z `_written_at` (the upsert does not move it). The snapshot's last write (a new row at 23:25Z)
        is after the chart's 22:41Z build: amber until the next chain run, not a hold."""
        env = T.ProjEnv()
        env.chart["sources"]["razzball"]["lineage"]["raw_built_at"] = "2026-10-08T19:28:12Z"
        for row in env.stored:
            row["_written_at"] = "2026-10-08T12:00:00+00:00"  # stamps that never moved
        env.stored.append({"player_key": 4, "snap": "2026-10-08", "created_at": "2026-10-08T23:25:00+00:00",
                           "_written_at": "2026-10-08T23:25:00+00:00", "std": 2.0, "half": 2.5, "full": 3.0})
        env.pub[4] = ("Brock Bowers", "TE", {"std": "2.0", "half": "2.5", "full": "3.0"})
        env.probe = {"acked_fp": "fp-saved", "acked_at": "2026-10-08T23:25:04+00:00"}
        env.chart["sources"]["razzball"]["combos"]["half_12"]["native"]["jahmyr gibbs"] = 20.1  # the older value
        r, _ = env.run()
        s2 = r["stages"]["stored_vs_chart"]
        self.assertEqual("amber", s2["status"], s2["summary"])
        self.assertIsNone(r["hold"])

    def test_the_same_swap_before_the_build_is_a_chart_fault_and_holds(self):
        r, _ = self.resaved_env("2026-10-08T18:00:00+00:00").run()
        self.assertEqual("red", r["stages"]["stored_vs_chart"]["status"])
        self.assertEqual("fidelity: stored_vs_chart", (r["hold"] or {}).get("reason"))


class ResaveAddsOrDropsLikeAChangedValue(unittest.TestCase):
    """A player added or dropped by a same-day re-save after the chart was built is judged like a changed
    value: amber until the next chain run, never a hold. A re-save that only deletes rows (ESPN prunes the
    players it no longer lists; CBS rest of season replaces the day's set) leaves no newer row stamp, so the
    save is dated by the probe fingerprint acknowledged with it."""

    def env(self, acked_at):
        env = T.ProjEnv()
        env.chart["sources"]["razzball"]["lineage"]["raw_built_at"] = "2026-10-08T19:28:12Z"
        for row in env.stored:
            row["_written_at"] = "2026-10-08T12:00:00+00:00"  # the kept rows' stamps did not move
        env.stored = [r for r in env.stored if r["player_key"] != 1]  # Josh Allen dropped by the re-save
        env.pub = {k: v for k, v in env.pub.items() if k != 1}
        env.probe = {"acked_fp": "fp-saved", "acked_at": acked_at}
        return env

    def test_a_drop_by_a_re_save_after_the_build_does_not_hold(self):
        r, _ = self.env("2026-10-08T23:25:03+00:00").run()
        s2 = r["stages"]["stored_vs_chart"]
        self.assertEqual("amber", s2["status"], s2["summary"])
        self.assertIn("re-saved", s2["summary"])
        self.assertIsNone(r["hold"])

    def test_the_same_drop_saved_before_the_build_is_a_chart_fault_and_holds(self):
        r, _ = self.env("2026-10-08T12:00:05+00:00").run()
        self.assertEqual("fidelity: stored_vs_chart", (r["hold"] or {}).get("reason"))

    def test_an_ack_for_a_newer_snapshot_does_not_excuse_an_older_chart(self):
        env = self.env("2026-10-08T23:25:03+00:00")
        for row in env.stored:
            row["snap"] = "2026-10-07"
        env.chart["sources"]["razzball"]["lineage"]["raw_vintage"] = "2026-10-07"
        env.stored += [dict(r, snap="2026-10-08") for r in env.stored]  # the ack belongs to the 10-08 save
        r, _ = env.run()
        self.assertEqual("red", r["stages"]["stored_vs_chart"]["status"])

    def test_an_added_player_whose_value_differs_from_the_publisher_still_holds(self):
        env = T.ProjEnv()
        env.chart["sources"]["razzball"]["lineage"]["raw_built_at"] = "2026-10-08T19:28:12Z"
        env.stored.append({"player_key": 6, "snap": "2026-10-08", "created_at": "2026-10-08T23:25:00+00:00",
                           "std": 0.0, "half": 0.0, "full": 0.0})  # stored as 0 by the re-save
        env.pub[6] = ("Tyreek Hill", "WR", {"std": "3.0", "half": "3.5", "full": "4.0"})
        env.chart["sources"]["razzball"]["combos"]["half_12"]["native"]["tyreek hill"] = 3.5
        env.probe = {"acked_fp": "fp-saved", "acked_at": "2026-10-08T23:25:03+00:00"}
        r, _ = env.run()
        self.assertEqual("fidelity: publisher_vs_stored", (r["hold"] or {}).get("reason"))


class EspnAmberThenResync(unittest.TestCase):
    """Jeremy, 2026-10-10 (JEG-520): ESPN intraday drift is "Amber, then re-sync". ESPN revises projections
    during the day without changing the date. A live value that differs from a row saved before ESPN's last
    change is amber ("update available") and triggers an automatic re-sync. Only a mismatch that survives the
    re-sync is red, which then holds the source."""

    WF = "espn-supabase-sync.yml"

    def moved(self):
        env = T.ProjEnv()
        env.resync_workflow = self.WF
        env.pub[2] = ("Jahmyr Gibbs", "RB", {"std": "0.0", "half": "0.0", "full": "0.0"})  # ESPN moved him to IR
        env.live = {"ok": True, "fingerprint": "fp-after-news", "error": None}  # after the 12:00 save
        return env

    def test_a_row_saved_before_espns_last_change_is_update_available_and_re_syncs(self):
        env = self.moved()
        r, _ = env.run()
        s1 = r["stages"]["publisher_vs_stored"]
        self.assertEqual("amber", s1["status"], s1["summary"])
        self.assertIn("update available", s1["summary"])
        self.assertIsNone(r["hold"])
        req = env.doc["resyncs"]["razzball"]
        self.assertEqual((self.WF, True, "fp-after-news"), (req["workflow"], req["dispatch"], req["fingerprint"]))

    def test_the_change_probe_seeing_new_content_also_re_syncs(self):
        env = self.moved()
        env.probe = dict(env.probe, last_ok=True, last_fp="fp-after-news", last_probe_at="2026-10-08T22:00:00Z")
        r, _ = env.run()
        self.assertEqual("amber", r["stages"]["publisher_vs_stored"]["status"])
        self.assertTrue(env.doc["resyncs"]["razzball"]["dispatch"])
        env.probe.update(dispatched_fp="fp-after-news", dispatched_at="2026-10-08T22:00:01Z")  # probe sent it
        env.run()
        self.assertFalse(env.doc["resyncs"]["razzball"]["dispatch"])

    def test_a_re_sync_already_requested_for_this_version_is_not_sent_again(self):
        env = self.moved()
        env.run()
        env.previous = env.doc
        env.run()
        req = env.doc["resyncs"]["razzball"]
        self.assertFalse(req["dispatch"])
        self.assertEqual(env.previous["resyncs"]["razzball"]["requested_at"], req["requested_at"])
        env.live = {"ok": True, "fingerprint": "fp-second-edit", "error": None}  # ESPN changed again
        env.run()
        self.assertTrue(env.doc["resyncs"]["razzball"]["dispatch"])

    def test_a_mismatch_that_survives_the_re_sync_is_red_and_holds(self):
        env = self.moved()
        env.stored = [dict(r, created_at="2026-10-08T22:30:00+00:00") for r in env.stored]  # the re-sync's save
        env.probe = {"acked_fp": "fp-after-news", "acked_at": "2026-10-08T22:30:04+00:00"}  # it read ESPN's edit
        r, _ = env.run()  # stored still has Gibbs' old value: the re-sync did not fix it
        s1 = r["stages"]["publisher_vs_stored"]
        self.assertEqual("red", s1["status"], s1["summary"])
        self.assertEqual("fidelity: publisher_vs_stored", (r["hold"] or {}).get("reason"))
        self.assertNotIn("razzball", env.doc["resyncs"])

    def test_no_fingerprint_with_the_save_re_syncs_so_the_next_save_names_its_content(self):
        env = T.ProjEnv()
        env.resync_workflow = self.WF
        env.stored[0].update(half=0.0)
        env.probe = {"acked_fp": "fp-saved", "acked_at": "2026-10-08T09:00:00+00:00"}  # acked another save
        r, _ = env.run()
        self.assertEqual("amber", r["stages"]["publisher_vs_stored"]["status"])
        self.assertTrue(env.doc["resyncs"]["razzball"]["dispatch"])

    def test_sources_without_a_re_sync_workflow_request_none(self):
        env = self.moved()
        env.resync_workflow = None
        r, _ = env.run()
        self.assertEqual("amber", r["stages"]["publisher_vs_stored"]["status"])
        self.assertEqual({}, env.doc["resyncs"])

    def test_espn_names_its_sync_workflow(self):
        from fidelity_sources import espn  # noqa: PLC0415
        self.assertEqual(self.WF, espn.RESYNC_WORKFLOW)
        self.assertTrue((ROOT / ".github" / "workflows" / self.WF).exists())

    def test_the_pulse_workflow_dispatches_the_requested_re_syncs(self):
        wf = (ROOT / ".github" / "workflows" / "fidelity-pulse.yml").read_text(encoding="utf-8")
        self.assertIn("--resync-dispatches", wf)
        self.assertIn("gh workflow run", wf)


class HeldSourceInThePulse(unittest.TestCase):
    def held_env(self, stage="publisher_vs_stored", identity="bake_v1"):
        env = T.Env()
        env.chart["sources"]["usatoday"]["validationHold"] = {
            "reason": f"fidelity: {stage}", "root": "usatoday", "stage": stage, "identity": identity,
            "since": "2026-10-08T18:00:00Z", "restored_from": "B-good"}  # served from an older chart
        return env

    def test_a_held_section_kept_from_this_build_is_checked_as_usual(self):
        """CBS rest of season 2026-10-10 00:09Z: a held projection keeps this build's section, so once the
        chain rebuilt it from the stored save, stage 2 sees chart == stored and the hold is released."""
        env = T.ProjEnv()
        env.chart["sources"]["razzball"]["validationHold"] = {
            "reason": "fidelity: stored_vs_chart", "root": "razzball", "stage": "stored_vs_chart",
            "identity": "2026-10-08@2026-10-08T12:00:00Z", "since": "2026-10-08T18:00:00Z", "restored_from": None}
        r, _ = env.run()
        self.assertEqual("green", r["stages"]["stored_vs_chart"]["status"])
        self.assertIsNone(r["hold"])
        env.chart["sources"]["razzball"]["combos"]["half_12"]["native"]["jahmyr gibbs"] = 1.0  # still wrong
        r, _ = env.run()
        self.assertEqual("fidelity: stored_vs_chart", (r["hold"] or {}).get("reason"))

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
        # JEG-508 (VP-10/VP-11) retired the *_adjusted sections: the engine
        # derives the deprecated cbs_adjusted alias, and its hold, from cbs.
        self.assertEqual({"cbs"}, held_sections(out))
        hold = out["sources"]["cbs"]["validationHold"]
        self.assertEqual("fidelity: publisher_vs_stored", hold["reason"])
        self.assertEqual(("cbs", 4, "B-good"), (hold["root"], hold["kept_week"], hold["restored_from"]))
        self.assertEqual("good:cbs", out["sources"]["cbs"]["tag"])  # served from the last good chart
        for sec, s in out["sources"].items():
            if sec != "cbs":
                self.assertEqual(f"new:{sec}", s["tag"], sec)  # every other source publishes this run's
        self.assertEqual(["cbs"], report["cbs"]["restored"])

    def test_projection_hold_keeps_its_section_labelled(self):
        out, report = fh.apply_fidelity_holds(fixture(), {"espn": self.HOLD},
                                              lambda root: fixture(tag="good"), 5, TODAY)
        self.assertEqual({"espn"}, held_sections(out))
        self.assertEqual("new:espn", out["sources"]["espn"]["tag"])
        self.assertEqual([], report["espn"]["restored"])

    def test_no_last_good_chart_keeps_the_section_held(self):
        out, _ = fh.apply_fidelity_holds(fixture(), {"usatoday": self.HOLD}, lambda root: None, 5, TODAY)
        self.assertEqual({"usatoday"}, held_sections(out))
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
