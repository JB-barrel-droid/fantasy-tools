"""Fixture-driven tests for independent native FantasyCalc scope promotion."""
import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipelines"))
import pull_fantasycalc_full_feed as F

BASE_TIME = datetime(2026, 11, 5, 10, 30, tzinfo=timezone.utc)
PAYLOAD = [{"player": {"id": i, "name": f"Player {i}", "position": "WR", "team": "SEA"},
            "value": 10000 - i * 10} for i in range(200)]
TARGET = "numQbs=1&numTeams=12&ppr=0.5"


class FullFeedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name)
        # Exercise real files and atomic replacements without waiting for the
        # host filesystem to flush thousands of synthetic fixture archives.
        flush = patch.object(F.os, "fsync")
        flush.start()
        self.addCleanup(flush.stop)

    def acquire(self, fetch=lambda url: copy.deepcopy(PAYLOAD), hours=0, week=10):
        return F.acquire(self.cache, week=week, season=2026, fetch_fn=fetch,
                         now=BASE_TIME + timedelta(hours=hours))

    def target(self, observations):
        return next(o for o in observations if o["scoring"] == "half" and
                    o["league_variant"] == {"league_teams": 12, "qb_slots": 1})

    def changed_fetch(self, url):
        data = copy.deepcopy(PAYLOAD)
        if TARGET in url:
            data[100]["value"] *= 1.01
        return data

    def test_all_24_combos_baseline_unknown_and_hash_matches_promoted_input(self):
        urls = []
        observations = self.acquire(lambda url: (urls.append(url), copy.deepcopy(PAYLOAD))[1])
        self.assertEqual(24, len(set(urls)))
        self.assertEqual(24, len(list(self.cache.glob("fantasycalc_*.json"))))
        for obs in observations:
            self.assertEqual("baseline", obs["result"])
            self.assertIsNone(obs["last_observed_change_at"])
            self.assertEqual("content_vintage_unknown", obs["reason"])
            archive = json.loads(Path(obs["raw_snapshot_reference"]).read_text())
            self.assertEqual(obs["ingested_hash"], F.content_hash(archive["rows"]))
            self.assertIsNone(obs["served_hash"])

    def test_one_percent_outside_top25_propagates_only_its_combo(self):
        before = self.acquire()
        after = self.acquire(self.changed_fetch, hours=1)
        target = self.target(after)
        self.assertNotEqual(self.target(before)["normalized_content_hash"], target["normalized_content_hash"])
        self.assertEqual("changed", target["result"])
        self.assertEqual(1, sum(o["result"] == "changed" for o in after))
        bundle = json.loads((self.cache / "fantasycalc_half_12_qb1.json").read_text())
        row = next(r for r in bundle["rows"] if r["fantasycalc_id"] == "100")
        self.assertEqual(9090.0, row["value"])
        self.assertEqual(target["normalized_content_hash"], F.content_hash(bundle["rows"]))
        self.assertEqual(2, len(list((self.cache / "snapshots" / "fantasycalc_half_12_qb1").glob("*.json"))))

    def test_identical_and_row_reorder_keep_age_and_exact_24h_boundary(self):
        self.acquire()
        changed = self.target(self.acquire(self.changed_fetch, hours=1))
        def reordered(url):
            return list(reversed(self.changed_fetch(url)))
        at_floor = self.target(self.acquire(reordered, hours=25))
        self.assertEqual(changed["last_observed_change_at"], at_floor["last_observed_change_at"])
        self.assertEqual(86400, at_floor["content_age_seconds"])
        self.assertFalse(at_floor["stale"])
        old = self.target(self.acquire(reordered, hours=26))
        self.assertEqual("unchanged", old["result"])
        self.assertTrue(old["stale"])
        self.assertEqual("content_stale", old["reason"])
        self.assertNotEqual(changed["successful_fetch_at"], old["successful_fetch_at"])

    def test_missing_combo_preserves_prior_bundle_and_other_scopes_progress(self):
        self.acquire()
        path = self.cache / "fantasycalc_half_12_qb1.json"
        prior = path.read_bytes()
        def missing(url):
            if TARGET in url:
                raise OSError("fixture outage")
            data = copy.deepcopy(PAYLOAD)
            data[100]["value"] += 1
            return data
        after = self.acquire(missing, hours=1)
        self.assertEqual(prior, path.read_bytes())
        self.assertEqual("failed", self.target(after)["result"])
        self.assertEqual(23, sum(o["result"] == "changed" for o in after))
        self.assertEqual(self.target(after)["previous_hash"], self.target(after)["ingested_hash"])

    def test_bad_native_rows_fail_closed(self):
        self.acquire()
        path = self.cache / "fantasycalc_half_12_qb1.json"
        prior = path.read_bytes()
        for bad in (None, True, float("nan"), -1, "10"):
            def invalid(url):
                data = copy.deepcopy(PAYLOAD)
                if TARGET in url:
                    data[100]["value"] = bad
                return data
            with self.subTest(value=bad):
                self.assertEqual("failed", self.target(self.acquire(invalid, hours=1))["result"])
                self.assertEqual(prior, path.read_bytes())

    def test_malformed_player_fields_fail_closed_without_promotion(self):
        self.acquire()
        path = self.cache / "fantasycalc_half_12_qb1.json"
        prior = path.read_bytes()
        invalid_fields = {
            "id": ("", "  ", True, -1, 1.5, {}, []),
            "name": ({"name": "Player"}, [], 123, "", "  "),
            "position": ("PICK", "", {}, [], 123),
        }
        for field, values in invalid_fields.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    data = copy.deepcopy(PAYLOAD)
                    data[100]["player"][field] = value
                    with self.assertRaises(ValueError):
                        F.normalize(data)
                    obs = self.target(self.acquire(
                        lambda url: data if TARGET in url else copy.deepcopy(PAYLOAD), hours=1))
                    self.assertEqual("failed", obs["result"])
                    self.assertFalse(obs["complete"])
                    self.assertEqual(prior, path.read_bytes())
        for invalid in (None, [], {"player": None}, {"player": "bad"}):
            with self.subTest(row=invalid), self.assertRaises(ValueError):
                F.normalize(PAYLOAD[:-1] + [invalid])

    def test_malformed_prior_state_still_fetches_every_scope_and_retains_bundle(self):
        self.acquire()
        path = self.cache / "fantasycalc_half_12_qb1.json"
        valid = json.loads(path.read_text())
        malformed = ["{invalid JSON", "null", "[]", "{}"]
        for field, value in (("observation", None), ("observation", []),
                             ("rows", None), ("rows", {})):
            bundle = copy.deepcopy(valid)
            bundle[field] = value
            malformed.append(json.dumps(bundle))
        for field, value in (("last_observed_change_at", "invalid"),
                             ("last_observed_change_at", "2026-11-05T10:30:00"),
                             ("last_observed_change_at", {}),
                             ("successful_fetch_at", []),
                             ("normalized_content_hash", {})):
            bundle = copy.deepcopy(valid)
            bundle["observation"][field] = value
            malformed.append(json.dumps(bundle))
        for saved in malformed:
            with self.subTest(saved=saved[:100]):
                path.write_text(saved)
                prior = path.read_bytes()
                urls = []
                def fetched(url):
                    urls.append(url)
                    return copy.deepcopy(PAYLOAD)
                observations = self.acquire(fetched, hours=1)
                self.assertEqual(24, len(urls))
                self.assertEqual(24, len(set(urls)))
                self.assertEqual(24, len(observations))
                obs = self.target(observations)
                self.assertEqual("failed", obs["result"])
                self.assertFalse(obs["complete"])
                self.assertIn("prior_state_invalid", obs["error"])
                self.assertIsNone(obs["ingested_hash"])
                self.assertIsNone(obs["last_observed_change_at"])
                self.assertEqual(prior, path.read_bytes())
                self.assertEqual(23, sum(o["complete"] for o in observations))

    def test_duplicate_ids_and_partial_responses_fail_closed(self):
        for payload in (PAYLOAD[:40], PAYLOAD[:-1] + [PAYLOAD[0]]):
            with self.subTest(size=len(payload)):
                self.assertRaises(ValueError, F.normalize, payload)

    def test_normalizer_migration_is_unknown_not_vendor_change(self):
        self.acquire()
        self.acquire(self.changed_fetch, hours=1)
        with patch.object(F, "NORMALIZER_VERSION", "fantasycalc-native-v2"):
            obs = self.target(self.acquire(self.changed_fetch, hours=2))
        self.assertEqual("baseline", obs["result"])
        self.assertIsNone(obs["last_observed_change_at"])

    def test_week_rollover_is_unknown_not_vendor_change(self):
        self.acquire()
        obs = self.target(self.acquire(self.changed_fetch, hours=1, week=11))
        self.assertEqual("baseline", obs["result"])
        self.assertIsNone(obs["last_observed_change_at"])

    def test_failed_fetch_cannot_erase_stale_content_clock(self):
        self.acquire()
        self.acquire(self.changed_fetch, hours=1)
        def failed(url):
            raise OSError("offline")
        obs = self.target(self.acquire(failed, hours=26))
        self.assertTrue(obs["stale"])
        self.assertEqual(90000, obs["content_age_seconds"])
        self.assertEqual(F.stamp(BASE_TIME + timedelta(hours=1)), obs["successful_fetch_at"])

    def test_atomic_replace_failure_keeps_previous_bundle(self):
        self.acquire()
        path = self.cache / "fantasycalc_half_12_qb1.json"
        prior = path.read_bytes()
        real_replace = F.os.replace
        def broken(src, dest):
            if dest == path:
                raise OSError("fixture disk failure")
            real_replace(src, dest)
        with patch.object(F.os, "replace", side_effect=broken):
            obs = self.target(self.acquire(self.changed_fetch, hours=1))
        self.assertEqual("failed", obs["result"])
        self.assertEqual(prior, path.read_bytes())
        self.assertEqual(obs["previous_hash"], obs["ingested_hash"])


if __name__ == "__main__":
    unittest.main()
