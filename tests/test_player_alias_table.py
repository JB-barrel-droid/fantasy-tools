"""JEG-438: alias list in Supabase, saver misses queued per source, nightly
reconcile, monitored open-name count.

Each rule has its negative: the state it names must act, the neighbouring
benign state must not.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import player_aliases  # noqa: E402
import identity_queue  # noqa: E402
import reconcile_player_identity as rec  # noqa: E402
import build_monitoring_summary as bms  # noqa: E402
import monitor_alerts as ma  # noqa: E402
from canonical_players import norm_player_name  # noqa: E402

MIGRATION = ROOT / "supabase" / "migrations" / "jeg438_alias_table_curated.sql"
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def table_rows_from_json():
    """What PostgREST returns for the curated rows once the migration ran."""
    return [{"source_player_name": e["alias"], "player_key": e["player_key"], "position": e["pos"],
             "players": {"full_name": e["full_name"]}} for e in player_aliases.json_entries()]


class MigrationSeedIsTheJsonList(unittest.TestCase):
    TUPLE = re.compile(r"\(\s*'((?:[^']|'')*)',\s*'((?:[^']|'')*)',\s*'([A-Z]+)',\s*(\d+),\s*'(?:[^']|'')*'\s*\)")

    def seed(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        return {(a.replace("''", "'"), n, p, int(k)) for a, n, p, k in self.TUPLE.findall(sql)}

    def test_seed_rows_equal_the_committed_json(self):
        want = {(e["alias"], norm_player_name(e["alias"]), e["pos"], e["player_key"])
                for e in player_aliases.json_entries()}
        self.assertEqual(self.seed(), want,
                         "supabase/migrations/jeg438_alias_table_curated.sql must seed exactly data/inputs/player_aliases.json")

    def test_the_comparison_catches_a_missing_entry(self):
        want = {(e["alias"], norm_player_name(e["alias"]), e["pos"], e["player_key"])
                for e in player_aliases.json_entries()}
        self.assertNotEqual(set(list(self.seed())[1:]), want)

    def test_migration_is_data_only_and_schedules_the_nightly_job(self):
        sql = re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8")).lower()
        self.assertNotRegex(sql, r"\b(create|alter|drop)\s+(table|index|view|function|policy)\b")
        self.assertIn("'player-identity-reconcile-nightly'", sql)
        self.assertIn("'player_identity_reconcile'", sql)
        self.assertIn("method", sql)
        self.assertIn("'curated'", sql)


class LoaderReadsTheTableWhenPresent(unittest.TestCase):
    def tearDown(self):
        player_aliases._reset_for_tests(None)

    def load_with(self, fetch):
        player_aliases._reset_for_tests(None)
        with mock.patch.object(player_aliases, "fetch_curated_rows", fetch):
            return player_aliases.load(), player_aliases.loaded_from()

    def test_curated_rows_are_read_and_give_the_same_index_as_the_json(self):
        from_table, origin = self.load_with(lambda: table_rows_from_json())
        self.assertEqual(origin, "supabase")
        self.assertEqual(from_table, player_aliases._index(player_aliases.json_entries()))

    def test_a_table_only_alias_is_seen(self):
        rows = table_rows_from_json() + [{"source_player_name": "Zebulon Quixotic", "player_key": 4214,
                                          "position": "QB", "players": {"full_name": "Mitchell Trubisky"}}]
        idx, origin = self.load_with(lambda: rows)
        self.assertEqual(origin, "supabase")
        self.assertEqual(idx[norm_player_name("Zebulon Quixotic")]["player_key"], 4214)

    def test_no_rows_no_credentials_or_a_failed_read_fall_back_to_the_json(self):
        json_idx = player_aliases._index(player_aliases.json_entries())
        for label, fetch in (("empty", lambda: []), ("not configured", lambda: None),
                             ("error", mock.Mock(side_effect=OSError("down")))):
            with self.subTest(label):
                idx, origin = self.load_with(fetch)
                self.assertEqual(origin, "json")
                self.assertEqual(idx, json_idx)

    def test_a_row_without_the_embedded_player_falls_back_whole(self):
        rows = table_rows_from_json()
        rows[0]["players"] = None
        _idx, origin = self.load_with(lambda: rows)
        self.assertEqual(origin, "json")

    def test_env_switch_and_missing_credentials_skip_the_network(self):
        with mock.patch.dict(os.environ, {"PLAYER_ALIASES_SOURCE": "json", "SUPABASE_URL": "https://x",
                                          "SUPABASE_SERVICE_KEY": "k"}), \
                mock.patch("urllib.request.urlopen") as op:
            self.assertIsNone(player_aliases._fetch_curated_rows())
            op.assert_not_called()
        env = {k: v for k, v in os.environ.items() if k not in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY")}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch("urllib.request.urlopen") as op:
            self.assertIsNone(player_aliases._fetch_curated_rows())
            op.assert_not_called()


class SaverMissesAreQueued(unittest.TestCase):
    REVIEW = [
        {"reason": "no_match", "player_name": "Jalen Nobody", "pos": "WR"},
        {"reason": "ambiguous", "player_name": "Same Name", "pos": "RB"},
        {"reason": "unresolved_name", "player": "Third Guy", "pos": "TE"},
        {"name": "Fourth Guy", "position": "QB", "detail": "no single canonical players-table identity; never guessed"},
        {"reason": "missing_or_non_numeric_value", "player": "Priced Guy"},       # a value problem
        {"name": "Fifth Guy", "detail": "missing name or non-numeric value; never guessed"},
        {"reason": "reindex: no anchor", "player_key": 12},
        {"reason": "no_match", "player_name": "Jalen Nobody", "pos": "WR"},       # duplicate
    ]

    def test_only_identity_misses_are_taken_once_each(self):
        got = {(m["name"], m["pos"], m["status"]) for m in identity_queue.identity_misses(self.REVIEW)}
        self.assertEqual(got, {("Jalen Nobody", "WR", "unmatched"), ("Same Name", "RB", "review"),
                               ("Third Guy", "TE", "unmatched"), ("Fourth Guy", "QB", "unmatched")})

    def test_new_names_insert_open_names_refresh_settled_names_stay(self):
        misses = identity_queue.identity_misses(self.REVIEW[:3])
        existing = [
            {"id": 7, "norm_name": "same name", "position": "RB", "status": "review", "seen_count": 2},
            {"id": 8, "norm_name": "third guy", "position": "TE", "status": "verified", "seen_count": 1},
        ]
        inserts, patches = identity_queue.plan("razzball", misses, existing, NOW.isoformat())
        self.assertEqual([r["source_player_name"] for r in inserts], ["Jalen Nobody"])
        self.assertEqual(inserts[0]["status"], "unmatched")
        self.assertNotIn("player_key", inserts[0])  # nothing here ever names a player
        self.assertEqual(patches, [(7, {"last_seen_at": NOW.isoformat(), "seen_count": 3})])

    def test_a_queue_failure_never_fails_the_save(self):
        lines = []
        with mock.patch.object(identity_queue, "get_rows", mock.Mock(side_effect=OSError("down"))):
            out = identity_queue.record_misses("razzball", self.REVIEW, log=lines.append)
        self.assertEqual(out["error"], 1)
        self.assertIn("WARNING", lines[-1])

    def test_record_writes_through_the_injected_client(self):
        posted, patched = [], []
        with mock.patch.object(identity_queue, "get_rows", lambda p: []), \
                mock.patch.object(identity_queue, "post_rows", posted.extend), \
                mock.patch.object(identity_queue, "patch_row", lambda i, b: patched.append(i)):
            out = identity_queue.record_misses("cbsros", self.REVIEW, now=NOW.isoformat(), log=lambda s: None)
        self.assertEqual(out["inserted"], 4)
        self.assertEqual({r["source"] for r in posted}, {"cbsros"})

    def test_every_saver_queues_its_misses(self):
        for saver, source in (("save_razzball_references", '"razzball"'), ("save_cbsros_references", '"cbsros"'),
                              ("save_espn_cbs_references", 'result["source"]'),
                              ("save_fantasycalc_references", '"fantasycalc"'),
                              ("save_usatoday_references", '"usatoday"')):
            with self.subTest(saver):
                text = (ROOT / "pipelines" / f"{saver}.py").read_text(encoding="utf-8")
                self.assertIn(f"identity_queue.record_misses({source}", text)


PLAYERS = [
    {"player_key": 4000, "full_name": "Jackson Meeks", "position": "WR", "active": False},
    {"player_key": 3247, "full_name": "Jaxon Smith-Njigba", "position": "WR", "active": True},
    {"player_key": 51, "full_name": "Same Name", "position": "RB", "active": True},
    {"player_key": 52, "full_name": "Same Name", "position": "RB", "active": True},
    {"player_key": 1268, "full_name": "Jalen Moreno-Cropper", "position": "WR", "active": False},
    {"player_key": 60, "full_name": "Tom Brady", "position": "QB", "active": False},
]


def open_row(i, name, pos, source="razzball", status="unmatched", seen=NOW):
    return {"id": i, "source": source, "source_player_name": name, "norm_name": norm_player_name(name),
            "position": pos, "status": status, "player_key": None, "candidate_keys": None,
            "method": "saver-miss", "last_seen_at": seen.isoformat()}


class NightlyReconcile(unittest.TestCase):
    def decide(self, name, pos):
        return rec.decide(open_row(1, name, pos), rec.build_index(PLAYERS))

    def test_unique_exact_name_is_verified_even_at_another_position(self):
        d = self.decide("Jackson Meeks", "TE")
        self.assertEqual((d["status"], d["player_key"], d["method"]), ("verified", 4000, "reconcile:exact"))

    def test_verified_alias_is_verified(self):
        d = self.decide("Jalen Cropper", "WR")
        self.assertEqual((d["status"], d["player_key"], d["method"]), ("verified", 1268, "reconcile:alias"))

    def test_two_active_namesakes_go_to_review_without_a_key(self):
        d = self.decide("Same Name", "RB")
        self.assertEqual((d["status"], d["player_key"], d["candidate_keys"]), ("review", None, [51, 52]))

    def test_a_close_spelling_is_only_a_provisional_proposal(self):
        d = self.decide("Jaxon Smith-Njigbaa", "WR")
        self.assertEqual((d["status"], d["player_key"], d["method"]), ("provisional", 3247, "reconcile:fuzzy"))
        self.assertGreaterEqual(d["confidence"], rec.FUZZY_FLOOR)

    def test_a_distant_name_stays_unmatched(self):
        d = self.decide("Zebulon Quixotic", "WR")
        self.assertEqual((d["status"], d["player_key"]), ("unmatched", None))

    def test_fuzzy_respects_position(self):
        self.assertEqual(self.decide("Jaxon Smith-Njigbaa", "QB")["status"], "unmatched")

    def test_report_counts_open_names_per_source_in_the_window(self):
        rows = [open_row(i, f"Zebulon Quixotic{chr(97 + i)}", "WR") for i in range(6)]
        rows.append(open_row(10, "Old Name", "WR", seen=NOW - timedelta(days=30)))
        rows.append(open_row(11, "Jackson Meeks", "TE", source="espn", status="review"))
        patches, report = rec.reconcile(rows, PLAYERS, NOW)
        self.assertEqual(report["open_by_source"]["razzball"]["open"], 6)
        self.assertNotIn("espn", report["open_by_source"])        # settled tonight
        self.assertEqual(report["sources_over_threshold"], {"razzball": 6})
        self.assertIn((11, "verified"), [(i, b["status"]) for i, b in patches])

    def test_dry_run_writes_nothing_and_write_records_the_check(self):
        rows = [open_row(1, "Jackson Meeks", "TE")]
        for write in (False, True):
            with self.subTest(write=write):
                patched, recorded = [], []
                with mock.patch.object(rec, "fetch_open", lambda: rows), \
                        mock.patch.object(rec, "fetch_players", lambda: PLAYERS), \
                        mock.patch.object(rec, "fetch_curated", lambda: []), \
                        mock.patch.object(rec, "patch_row", lambda i, b: patched.append(i)), \
                        mock.patch.object(rec, "record_check", lambda *a: recorded.append(a)), \
                        mock.patch("builtins.print"):
                    out = Path(os.environ.get("TMP", "/tmp")) / "player-identity-reconcile-test.json"
                    rc = rec.main(["--out", str(out)] + (["--write"] if write else []))
                self.assertEqual(rc, 0)
                self.assertEqual(patched, [1] if write else [])
                self.assertEqual(recorded, [(True, True, None)] if write else [])

    def test_curated_drift_is_reported(self):
        rows = [{"source_player_name": e["alias"], "player_key": e["player_key"]}
                for e in player_aliases.json_entries()]
        self.assertEqual(rec.curated_drift(rows)["only_in_json"], [])
        self.assertTrue(rec.curated_drift(rows[1:])["only_in_json"])


class OpenNamesAreMonitored(unittest.TestCase):
    def summary(self, n, read_error=None):
        rows = [open_row(i, f"Name{i} Person", "WR") for i in range(n)]
        fetch = (mock.Mock(side_effect=OSError("down")) if read_error else (lambda: rows))
        return bms.build(lambda: {"schema": bms.SCHEMA, "overall": "green", "generated_at": "x",
                                  "checks": [{"check_id": "c"}]}, now=NOW, fetch_identity=fetch)

    def test_over_threshold_alerts_per_source(self):
        snap = self.summary(identity_queue.OPEN_NAMES_ALERT + 1)
        keys = [a.key for a in ma.identity_unmatched_alerts(snap)]
        self.assertEqual(keys, ["identity-unmatched-razzball"])
        self.assertIn("identity-unmatched-razzball", [a.key for a in ma.evaluate(snap, {}, NOW)])

    def test_at_threshold_and_failed_reads_do_not_alert(self):
        self.assertEqual(ma.identity_unmatched_alerts(self.summary(identity_queue.OPEN_NAMES_ALERT)), [])
        snap = self.summary(3, read_error=True)
        self.assertIn("read_error", snap["identity"])
        self.assertEqual(ma.identity_unmatched_alerts(snap), [])

    def test_guard_catches_a_rule_without_the_threshold(self):
        snap = self.summary(1)
        snap["identity"]["alert_threshold"] = 0
        self.assertEqual(len(ma.identity_unmatched_alerts(snap)), 1)


if __name__ == "__main__":
    unittest.main()
