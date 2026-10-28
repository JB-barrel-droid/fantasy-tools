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
            secs[sec] = {"week_designated": week_label, "tag": f"{tag}:{sec}",
                         "combos": {"ppr_12": {"native": {"a": 1.0}}}}
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

    def test_a_player_printed_at_one_unit_and_not_stored_is_amber_hold(self):
        """Razzball: Scotty Miller printed 0.1 per game in every scoring, not stored. Absent means 0.
        JEG-726: this is a merely-lagging amber hold (visible label, not hidden from DDF)."""  # noqa
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
        # JEG-726: a negligible absence is a merely-lagging amber hold, not no hold.
        self.assertIsNotNone(r["hold"])
        self.assertEqual("amber", r["hold"]["hold_level"])
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


class ChartSnapshotReplacedByANewerSave(unittest.TestCase):
    """2026-10-10 06:17Z: ESPN keeps one current set. The 05:44Z sync re-dated it 2026-10-10, while the
    chart still showed 2026-10-09 because the chain had not rebuilt yet. Stage 2 found "no stored ESPN
    snapshot 2026-10-09" and held ESPN. A held ESPN failed the chain's validate, so the chart could not
    catch up: a deadlock on correct data. A chart behind a newer stored set is amber until the next chain
    run. Freshness turns it red after PROJECTION_RED_DAYS."""

    def env(self):
        env = T.ProjEnv()
        env.chart["sources"]["razzball"]["lineage"]["raw_vintage"] = "2026-10-07"  # the chart's older set
        return env  # stored holds only the 2026-10-08 set (the older one was replaced)

    def test_a_chart_behind_the_one_stored_set_is_amber_hold(self):
        """JEG-726: a chart behind the stored set is merely lagging => amber hold
        (visible label, not hidden from DDF Value)."""
        r, _ = self.env().run()
        s2 = r["stages"]["stored_vs_chart"]
        self.assertEqual("amber", s2["status"], s2["summary"])
        self.assertIn("2026-10-08", s2["summary"])
        self.assertIsNotNone(r["hold"])
        self.assertEqual("amber", r["hold"]["hold_level"])

    def test_a_chart_snapshot_newer_than_anything_stored_still_holds(self):
        env = self.env()
        env.chart["sources"]["razzball"]["lineage"]["raw_vintage"] = "2026-10-09"
        r, _ = env.run()
        self.assertEqual("fidelity: stored_vs_chart", (r["hold"] or {}).get("reason"))


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

    def test_held_source_keeps_combos(self):
        out, report = fh.apply_fidelity_holds(fixture(), {"cbs": self.HOLD}, 5)
        # JEG-569 part 2 (Jeremy, 2026-10-12): the held source is grayed out but its combos are KEPT so the
        # engine still includes it in the pipeline; the validationHold flag is the signal.
        held = {sec for sec, s in out["sources"].items()
                if isinstance(s, dict) and s.get("validationHold")}
        self.assertIn("cbs", held)
        self.assertTrue(out["sources"]["cbs"]["combos"])
        hold = out["sources"]["cbs"]["validationHold"]
        self.assertEqual("fidelity: publisher_vs_stored", hold["reason"])
        self.assertEqual("cbs", hold["root"])
        # _adjusted derivative also stripped
        if "cbs_adjusted" in out["sources"]:
            self.assertTrue(out["sources"]["cbs_adjusted"]["combos"])
        # every source keeps its combos
        for sec, s in out["sources"].items():
            if isinstance(s, dict) and "combos" in s:
                self.assertTrue(s["combos"], f"{sec} combos should not be empty")

    def test_projection_hold_keeps_combos(self):
        out, report = fh.apply_fidelity_holds(fixture(), {"espn": self.HOLD}, 5)
        self.assertTrue(out["sources"]["espn"]["combos"])
        hold = out["sources"]["espn"]["validationHold"]
        self.assertEqual("fidelity: publisher_vs_stored", hold["reason"])
        self.assertEqual("espn", hold["root"])

    def test_hold_without_last_good_keeps_combos(self):
        out, _ = fh.apply_fidelity_holds(fixture(), {"usatoday": self.HOLD}, 5)
        self.assertTrue(out["sources"]["usatoday"]["combos"])

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
        _, report = fh.apply_fidelity_holds(fixture(), {"cbs": self.HOLD}, 5)
        status = fh.update_chain_status({"status": "green", "held": []}, report, 5)
        self.assertEqual(["cbs"], status["held"])
        self.assertEqual("published_with_holds", status["status"])
        self.assertEqual("fidelity: publisher_vs_stored", status["held_detail"]["cbs"]["reason"])

    def test_pulse_holds_ignores_unknown_roots(self):
        self.assertEqual(["cbs"], sorted(fh.pulse_holds({"holds": {"cbs": self.HOLD, "nope": self.HOLD}})))


# LastGoodFixtureFromGit removed: fixture_with_built_at retired by JEG-569
# part 2 (no restoration from last-good builds; combos are stripped).


class AmberHoldPolicy(unittest.TestCase):
    """JEG-726: amber fidelity holds (merely lagging) must never hide a source
    from DDF Value / projection ordering.  Only red holds hide.

    Negative-tested: simulate all three projections amber-held => projections
    still present; simulate a red hold => still hidden."""

    AMBER_HOLD = {"stage": "stored_vs_chart", "reason": "fidelity: stored_vs_chart",
                  "hold_level": "amber", "identity": "b2",
                  "since": "2026-10-09T21:51:00Z", "summary": "chart is stale"}
    RED_HOLD = {"stage": "publisher_vs_stored", "reason": "fidelity: publisher_vs_stored",
                "hold_level": "red", "identity": "b2",
                "since": "2026-10-09T21:51:00Z", "summary": "39 value mismatches"}

    def test_amber_hold_carries_hold_level_amber(self):
        """An amber hold writes hold_level='amber' into validationHold."""
        out, report = fh.apply_fidelity_holds(fixture(), {"espn": self.AMBER_HOLD}, 5)
        hold = out["sources"]["espn"]["validationHold"]
        self.assertEqual("amber", hold["hold_level"])
        self.assertEqual("amber", report["espn"]["hold_level"])

    def test_red_hold_carries_hold_level_red(self):
        """A red hold writes hold_level='red' into validationHold."""
        out, report = fh.apply_fidelity_holds(fixture(), {"espn": self.RED_HOLD}, 5)
        hold = out["sources"]["espn"]["validationHold"]
        self.assertEqual("red", hold["hold_level"])
        self.assertEqual("red", report["espn"]["hold_level"])

    def test_all_three_projections_amber_held_still_present(self):
        """The degenerate case: all three projections amber-held must NOT
        produce bench-share None.  Their hold_level is 'amber' so the page
        keeps them in DDF Value."""
        holds = {
            "espn": dict(self.AMBER_HOLD),
            "cbsros": dict(self.AMBER_HOLD),
            "razzball": dict(self.AMBER_HOLD),
        }
        out, report = fh.apply_fidelity_holds(fixture(), holds, 5)
        for proj in ("espn", "cbsros", "razzball"):
            vh = out["sources"][proj]["validationHold"]
            self.assertEqual("amber", vh["hold_level"],
                             f"{proj} should be amber-held, not hidden")
            self.assertTrue(out["sources"][proj]["combos"],
                            f"{proj} combos must be kept")
        # All three are amber => the page should not hide any of them.
        # A red hold on even one would make that one hidden.
        self.assertEqual({"espn", "cbsros", "razzball"},
                         {r for r, d in report.items() if d["hold_level"] == "amber"})

    def test_red_hold_hides_source(self):
        """A red hold on a projection hides it from DDF Value (hold_level='red')."""
        out, report = fh.apply_fidelity_holds(fixture(), {"espn": self.RED_HOLD}, 5)
        hold = out["sources"]["espn"]["validationHold"]
        self.assertEqual("red", hold["hold_level"])
        # The page reads hold_level to decide whether to hide; 'red' means hidden.

    def test_hold_level_defaults_to_red_when_absent(self):
        """A hold without hold_level (legacy) defaults to 'red'."""
        legacy = {"stage": "freshness", "reason": "fidelity: freshness",
                  "identity": "b1", "since": "2026-10-09T21:51:00Z", "summary": "stale"}
        out, report = fh.apply_fidelity_holds(fixture(), {"cbs": legacy}, 5)
        self.assertEqual("red", out["sources"]["cbs"]["validationHold"]["hold_level"])


class HoldIdentitySkipsMismatch(unittest.TestCase):
    """JEG-799 (B2): a hold applies only to the build the pulse measured.

    The pulse records measured_site (the live page's snapshot_fetched_at when it
    ran). If the candidate section's source_provenance.snapshot_fetched_at is
    different, the candidate has newer data and the hold is skipped.

    Negative-tested: when identities match, the hold IS applied (same build),
    confirming the guard catches the exact deadlock the chain would hit."""

    HOLD_WITH_SITE = {
        "stage": "stored_vs_chart", "reason": "fidelity: stored_vs_chart",
        "identity": "b2", "since": "2026-10-09T21:51:00Z",
        "summary": "chart is stale", "measured_site": "2026-10-08T15:00:00Z",
    }

    def _fixture_with_provenance(self, fetched_at):
        """Build a minimal fixture where 'cbs' has a source_provenance."""
        fx = fixture()
        fx["sources"]["cbs"]["source_provenance"] = {"snapshot_fetched_at": fetched_at}
        # Also set on the _adjusted derivative if present
        if "cbs_adjusted" in fx["sources"]:
            fx["sources"]["cbs_adjusted"]["source_provenance"] = {"snapshot_fetched_at": fetched_at}
        return fx

    def test_newer_candidate_skips_hold(self):
        """Candidate has a newer snapshot_fetched_at than the pulse measured:
        the hold was measured on the old build and does not apply."""
        fx = self._fixture_with_provenance("2026-10-09T03:00:00Z")  # newer than measured
        out, report = fh.apply_fidelity_holds(fx, {"cbs": self.HOLD_WITH_SITE}, 5)
        # cbs should NOT be held
        self.assertFalse(
            out["sources"]["cbs"].get("validationHold"),
            "A hold measured on a different build should not apply to a newer candidate")

    def test_same_identity_applies_hold(self):
        """Candidate has the SAME snapshot_fetched_at: the pulse measured this
        exact build, so the hold must apply. This is the negative test proving
        the guard catches the deadlock."""
        fx = self._fixture_with_provenance("2026-10-08T15:00:00Z")  # same as measured
        out, report = fh.apply_fidelity_holds(fx, {"cbs": self.HOLD_WITH_SITE}, 5)
        self.assertTrue(
            out["sources"]["cbs"].get("validationHold"),
            "A hold measured on the same build must apply")
        self.assertEqual("fidelity: stored_vs_chart",
                         out["sources"]["cbs"]["validationHold"]["reason"])

    def test_legacy_hold_without_measured_site_always_applies(self):
        """A hold without measured_site (pre-B2 / legacy) applies unconditionally."""
        legacy = {k: v for k, v in self.HOLD_WITH_SITE.items() if k != "measured_site"}
        fx = self._fixture_with_provenance("2026-10-09T03:00:00Z")
        out, _ = fh.apply_fidelity_holds(fx, {"cbs": legacy}, 5)
        self.assertTrue(
            out["sources"]["cbs"].get("validationHold"),
            "A legacy hold (no measured_site) must apply unconditionally")

    def test_candidate_without_provenance_gets_held(self):
        """If the candidate section has no source_provenance, the identity
        comparison cannot decide, so the hold applies (safe default)."""
        fx = fixture()  # no source_provenance on cbs
        out, _ = fh.apply_fidelity_holds(fx, {"cbs": self.HOLD_WITH_SITE}, 5)
        self.assertTrue(
            out["sources"]["cbs"].get("validationHold"),
            "A candidate without provenance should be held (safe default)")

    def test_all_sources_held_on_old_build_are_released_for_new_build(self):
        """The full deadlock scenario: all 7 sources held on the old page, but
        the candidate fixture has newer data for all of them. All holds should
        be skipped, producing 0 held sections."""
        holds = {}
        for root in vc.SOURCE_DERIVED:
            holds[root] = dict(self.HOLD_WITH_SITE)
        fx = fixture()
        for sec in fx["sources"]:
            fx["sources"][sec]["source_provenance"] = {
                "snapshot_fetched_at": "2026-10-09T03:00:00Z"}  # all newer
        out, report = fh.apply_fidelity_holds(fx, holds, 5)
        held = held_sections(out)
        self.assertEqual(set(), held,
                         "All sources measured on the old build should be released for the new build")


class SkippedHoldLeavesNoStaleHold(unittest.TestCase):
    """JEG-807 (2026-10-22): the 04:08Z chain promoted Week 7 fantasycalc and
    espn sections, the pulse's holds had measured the week-6 live page, the
    B2 skip fired -- and the week-6 red holds already on the sections stayed,
    so the engine hid both from DDF Value. A skipped hold must take an older
    fidelity hold off the candidate; a value-check hold is not the pulse's
    to touch."""

    HOLD = {"stage": "publisher_vs_stored", "reason": "fidelity: publisher_vs_stored",
            "identity": "fcwk7", "since": "2026-10-19T15:40:13Z", "summary": "stale",
            "measured_site": "2026-10-19T22:05:22+00:00", "hold_level": "red"}
    STALE = {"reason": "fidelity: publisher_vs_stored", "root": "fantasycalc", "week": 6,
             "identity": "fcwk6", "hold_level": "red"}

    def test_skip_removes_the_older_fidelity_hold(self):
        fx = fixture()
        for sec in ("fantasycalc", "fantasycalc_adjusted"):
            fx["sources"].setdefault(sec, {"combos": {}})
            fx["sources"][sec]["source_provenance"] = {"snapshot_fetched_at": "2026-10-22T01:55:07+00:00"}
            fx["sources"][sec]["validationHold"] = dict(self.STALE)
        out, report = fh.apply_fidelity_holds(fx, {"fantasycalc": self.HOLD}, 7)
        self.assertFalse(out["sources"]["fantasycalc"].get("validationHold"),
                         "the week-6 hold must not ride on the Week 7 section")
        self.assertFalse(out["sources"]["fantasycalc_adjusted"].get("validationHold"))
        self.assertNotIn("fantasycalc", report, "a skipped hold is not a held source")

    def test_skip_leaves_a_value_check_hold_alone(self):
        fx = fixture()
        fx["sources"]["fantasycalc"]["source_provenance"] = {"snapshot_fetched_at": "2026-10-22T01:55:07+00:00"}
        fx["sources"]["fantasycalc"]["validationHold"] = {"reason": "engine and Python reference disagree",
                                                          "root": "fantasycalc"}
        out, _ = fh.apply_fidelity_holds(fx, {"fantasycalc": self.HOLD}, 7)
        self.assertEqual("engine and Python reference disagree",
                         out["sources"]["fantasycalc"]["validationHold"]["reason"])

    def test_matching_build_still_applies_and_replaces(self):
        """Negative test: the same build the pulse measured is held (the
        stale week-6 hold is replaced by this week's)."""
        fx = fixture()
        fx["sources"]["fantasycalc"]["source_provenance"] = {"snapshot_fetched_at": self.HOLD["measured_site"]}
        fx["sources"]["fantasycalc"]["validationHold"] = dict(self.STALE)
        out, report = fh.apply_fidelity_holds(fx, {"fantasycalc": self.HOLD}, 7)
        self.assertEqual(7, out["sources"]["fantasycalc"]["validationHold"]["week"])
        self.assertEqual("red", report["fantasycalc"]["hold_level"])


class ProjectionIdentity(unittest.TestCase):
    """JEG-807: projection sections carry no snapshot_fetched_at, so B2 had no
    identity on either side and a razzball hold measured on the 10-19 chart
    was applied to the 10-21 candidate. The snapshot date is the identity,
    and the pulse stamps measured_site with the same function."""

    def test_section_identity_by_family(self):
        self.assertEqual("2026-10-21", fh.section_identity({"espn_snapshot": "2026-10-21",
                                                            "fetched_at": "2026-10-22T04:08:32Z"}))
        self.assertEqual("2026-10-21", fh.section_identity({"vintage": "2026-10-21"}))
        self.assertEqual("2026-10-22T01:55:07+00:00", fh.section_identity(
            {"source_provenance": {"snapshot_fetched_at": "2026-10-22T01:55:07+00:00"},
             "fetched_at": "2026-10-22T01:55:07+00:00"}))
        self.assertEqual("2026-09-19", fh.section_identity({"fetched_at": "2026-09-19"}))
        self.assertIsNone(fh.section_identity({"combos": {}}))

    def test_newer_projection_snapshot_skips_the_hold(self):
        hold = {"stage": "stored_vs_chart", "reason": "fidelity: stored_vs_chart", "identity": "2026-10-21@x",
                "since": "2026-10-18T06:40:13Z", "summary": "27 stored players not on the chart",
                "measured_site": "2026-10-19", "hold_level": "red"}
        fx = fixture()
        fx["sources"]["razzball"]["vintage"] = "2026-10-21"
        out, report = fh.apply_fidelity_holds(fx, {"razzball": hold}, 7)
        self.assertFalse(out["sources"]["razzball"].get("validationHold"))
        self.assertNotIn("razzball", report)
        # negative: the build the pulse measured is held
        fx["sources"]["razzball"]["vintage"] = "2026-10-19"
        out, report = fh.apply_fidelity_holds(fx, {"razzball": hold}, 7)
        self.assertTrue(out["sources"]["razzball"].get("validationHold"))
        self.assertIn("razzball", report)

    def test_pulse_stamps_measured_site_with_the_same_identity(self):
        env = T.Env()
        env.chart["sources"]["cbs"]["combos"]["half_12"]["native"]["jahmyr gibbs"] = 99.0
        env.chart["sources"]["cbs"]["source_provenance"]["snapshot_fetched_at"] = "2026-10-07T17:44:10+00:00"
        _, doc, _ = env.run()
        self.assertEqual("2026-10-07T17:44:10+00:00", doc["holds"]["cbs"]["measured_site"])
        self.assertEqual(fh.section_identity(env.chart["sources"]["cbs"]), doc["holds"]["cbs"]["measured_site"])
        self.assertEqual("2026-10-21", fp.measured_site_identity(
            {"sources": {"razzball": {"vintage": "2026-10-21"}}}, "razzball"))


class ChainStatusSeverityIsTheHoldLevel(unittest.TestCase):
    """JEG-807: the chain status said every fidelity hold was amber (labelled
    only) while the fixture held them red (hidden from DDF Value)."""

    RED = {"stage": "stored_vs_chart", "reason": "fidelity: stored_vs_chart", "identity": "a",
           "since": "2026-10-18T06:40:13Z", "summary": "s", "hold_level": "red"}
    AMBER = dict(RED, hold_level="amber")

    def test_red_and_amber_reported_as_they_are(self):
        _, report = fh.apply_fidelity_holds(fixture(), {"razzball": self.RED, "usatoday": self.AMBER}, 7)
        status = fh.update_chain_status({"outcome": "green", "held": [], "hold_severity": "none"}, report, 7)
        self.assertEqual("red", status["held_detail"]["razzball"]["hold_severity"])
        self.assertEqual("amber", status["held_detail"]["usatoday"]["hold_severity"])
        self.assertEqual("red", status["hold_severity"])
        self.assertEqual("published_with_holds", status["outcome"])
        _, report = fh.apply_fidelity_holds(fixture(), {"usatoday": self.AMBER}, 7)
        self.assertEqual("amber", fh.update_chain_status({}, report, 7)["hold_severity"])


class AmberHoldDecision(unittest.TestCase):
    """JEG-726: hold_decision produces amber holds for merely-lagging conditions."""

    def test_stored_vs_chart_value_drift_produces_amber_hold(self):
        """stored_vs_chart amber with a newer bake (value-only drift) -> amber hold."""
        result = {"stages": {
            "publisher_vs_stored": {"status": "green"},
            "stored_vs_chart": {"status": "amber", "behind": {"snapshot": "s2"},
                                "counts": {"missing_on_chart": 0, "extra_on_chart": 0}},
            "freshness": {"status": "green"},
            "scrape_validity": {"status": "green"},
        }}
        hold = fp.hold_decision(result, "id1", None, T.NOW)
        self.assertIsNotNone(hold)
        self.assertEqual("amber", hold["hold_level"])
        self.assertEqual("stored_vs_chart", hold["stage"])

    def test_publisher_vs_stored_small_roster_gap_produces_amber_hold(self):
        """publisher_vs_stored amber with 0 mismatches and <=2 unresolved -> amber hold."""
        result = {"stages": {
            "publisher_vs_stored": {"status": "amber",
                                    "counts": {"mismatched": 0, "missing": 0, "extra": 1,
                                               "unresolved_names": 1}},
            "stored_vs_chart": {"status": "green"},
            "freshness": {"status": "green"},
            "scrape_validity": {"status": "green"},
        }}
        hold = fp.hold_decision(result, "id1", None, T.NOW)
        self.assertIsNotNone(hold)
        self.assertEqual("amber", hold["hold_level"])
        self.assertEqual("publisher_vs_stored", hold["stage"])

    def test_red_stage_still_produces_red_hold(self):
        """A red stage produces a red hold, not an amber one."""
        result = {"stages": {
            "publisher_vs_stored": {"status": "red",
                                    "counts": {"mismatched": 5, "missing": 0, "extra": 0}},
            "stored_vs_chart": {"status": "green"},
            "freshness": {"status": "green"},
            "scrape_validity": {"status": "green"},
        }}
        hold = fp.hold_decision(result, "id1", None, T.NOW)
        self.assertIsNotNone(hold)
        self.assertEqual("red", hold["hold_level"])

    def test_non_lagging_amber_produces_no_hold(self):
        """An amber stage that is NOT merely-lagging (e.g. FantasyCalc movement) -> no hold."""
        result = {"stages": {
            "publisher_vs_stored": {"status": "amber",
                                    "counts": {"mismatched": 5, "missing": 0, "extra": 0,
                                               "unresolved_names": 0}},
            "stored_vs_chart": {"status": "green"},
            "freshness": {"status": "green"},
            "scrape_validity": {"status": "green"},
        }}
        hold = fp.hold_decision(result, "id1", None, T.NOW)
        self.assertIsNone(hold)

    def test_all_green_produces_no_hold(self):
        result = {"stages": {n: {"status": "green"} for n in fp.HOLD_STAGES}}
        self.assertIsNone(fp.hold_decision(result, "id1", None, T.NOW))


class StoredSaveNewerThanTheLiveChart(unittest.TestCase):
    """JEG-1194 (2026-10-28): the CBS week 8 save had no tight ends
    (scrape_validity red, "stored TE 10->0") while the live chart was the
    good week 7 one. The hold carried the live chart's identity, so the
    chain held the week 7 section and post-rebuild validate failed for every
    source for a day. A red about a newer stored save holds builds made from
    that save, never the live chart."""

    LIVE = "2026-10-22T00:35:32+00:00"     # the week 7 chart on the page
    NEWER = "2026-10-27T21:35:38+00:00"    # a build from the week 8 save

    @staticmethod
    def cbs_result(drop_side="stored", behind=True, extra_red=None):
        stages = {
            "publisher_vs_stored": {"status": "amber", "counts": {"mismatched": 0}},
            "stored_vs_chart": {"status": "amber", **({"behind": {"bake_id": "cbswk8", "week": 8}} if behind else {})},
            "freshness": {"status": "green"},
            "scrape_validity": {"status": "red", "summary": "player count dropped vs week 6: stored TE 10->0",
                                "signals": {"count_drops": [{"side": drop_side, "position": "TE", "now": 0,
                                                             "prior_week": 10, "severity": "red"}],
                                            "rank_inversions": 0, "sentinel_failures": []}},
        }
        for name in extra_red or ():
            stages[name] = {"status": "red", "summary": name}
        return {"stages": stages}

    def hold(self, **kw):
        return fp.hold_decision(self.cbs_result(**kw), "cbswk8", None, T.NOW, measured_site=self.LIVE)

    def fx(self, fetched_at):
        fx = fixture(week_label="Week 7")
        for sec in ("cbs", "cbs_adjusted"):
            if sec in fx["sources"]:
                fx["sources"][sec]["source_provenance"] = {"snapshot_fetched_at": fetched_at}
        return fx

    def test_scope_constants_agree(self):
        self.assertEqual(fh.SCOPE_STORED_NEWER, fp.SCOPE_STORED_NEWER)

    def test_stored_side_red_on_a_newer_save_is_scoped(self):
        h = self.hold()
        self.assertEqual("red", h["hold_level"])
        self.assertEqual(fp.SCOPE_STORED_NEWER, h.get("scope"))

    def test_a_chart_side_drop_is_not_scoped(self):
        self.assertIsNone(self.hold(drop_side="chart").get("scope"))

    def test_no_newer_save_is_not_scoped(self):
        """The stored save is the chart's own: the red is about the live chart."""
        self.assertIsNone(self.hold(behind=False).get("scope"))

    def test_any_chart_side_red_is_not_scoped(self):
        self.assertIsNone(self.hold(extra_red=["stored_vs_chart"]).get("scope"))
        self.assertIsNone(self.hold(extra_red=["freshness"]).get("scope"))

    def test_publisher_vs_stored_red_on_a_newer_save_is_scoped(self):
        result = self.cbs_result()
        result["stages"]["scrape_validity"] = {"status": "green"}
        result["stages"]["publisher_vs_stored"] = {"status": "red", "counts": {"mismatched": 4}}
        h = fp.hold_decision(result, "cbswk8", None, T.NOW, measured_site=self.LIVE)
        self.assertEqual(fp.SCOPE_STORED_NEWER, h.get("scope"))

    def test_rank_inversions_are_chart_side(self):
        result = self.cbs_result()
        result["stages"]["scrape_validity"]["signals"]["rank_inversions"] = 3
        h = fp.hold_decision(result, "cbswk8", None, T.NOW, measured_site=self.LIVE)
        self.assertIsNone(h.get("scope"))

    def test_the_live_chart_section_is_not_held(self):
        """The failing case: the chain kept the live week 7 section (review
        hold on week 8), so its identity equals measured_site."""
        fx = self.fx(self.LIVE)
        fx["sources"]["cbs"]["validationHold"] = {"reason": "fidelity: scrape_validity", "root": "cbs",
                                                  "hold_level": "red"}
        out, report = fh.apply_fidelity_holds(fx, {"cbs": self.hold()}, 8)
        self.assertFalse(out["sources"]["cbs"].get("validationHold"),
                         "a bad newer save must not hold the good live chart")
        self.assertNotIn("cbs", report)

    def test_a_build_from_the_newer_save_is_held(self):
        """Negative test: a candidate built from the flagged save is held
        (before JEG-1194 the identity skip let it through unheld)."""
        out, report = fh.apply_fidelity_holds(self.fx(self.NEWER), {"cbs": self.hold()}, 8)
        self.assertEqual("fidelity: scrape_validity", out["sources"]["cbs"]["validationHold"]["reason"])
        self.assertIn("cbs", report)

    def test_a_candidate_without_provenance_is_held(self):
        out, _ = fh.apply_fidelity_holds(fixture(), {"cbs": self.hold()}, 8)
        self.assertTrue(out["sources"]["cbs"].get("validationHold"))

    def test_unscoped_holds_keep_the_jeg_799_match(self):
        h = self.hold(drop_side="chart")
        out, _ = fh.apply_fidelity_holds(self.fx(self.LIVE), {"cbs": h}, 8)
        self.assertTrue(out["sources"]["cbs"].get("validationHold"))
        out, _ = fh.apply_fidelity_holds(self.fx(self.NEWER), {"cbs": h}, 8)
        self.assertFalse(out["sources"]["cbs"].get("validationHold"))


if __name__ == "__main__":
    unittest.main()
