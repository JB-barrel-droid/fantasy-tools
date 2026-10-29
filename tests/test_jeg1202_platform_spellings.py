"""JEG-1202: offline coverage tests for ESPN, Sleeper and Yahoo player spellings.

Read-only audit of the shared resolver (pipelines/lib/canonical_players.py)
against platform spellings found in committed files. No network, no Supabase,
no canonical table or alias change. Expected player_keys come from the grounds
in docs/research/JEG-1202/build_matrix.py (gsis chain, exact canonical text,
exact id-linked Sleeper text, verified alias text, DST mascot), never from the
resolver under test.

    python3 -m unittest tests.test_jeg1202_platform_spellings
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "tests" / "fixtures" / "JEG-1202"
BUILD = ROOT / "docs" / "research" / "JEG-1202" / "build_matrix.py"

sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import canonical_players  # noqa: E402
import player_aliases  # noqa: E402


def _offline_guard(*_a, **_k):
    raise AssertionError("JEG-1202 tests must not read Supabase")


def _json_only_aliases(*_a, **_k):
    # The committed alias list only: what the real reader does with
    # PLAYER_ALIASES_SOURCE=json, without any network path.
    assert os.environ.get("PLAYER_ALIASES_SOURCE") == "json"
    return None


def _load_build():
    spec = importlib.util.spec_from_file_location("jeg1202_build_matrix", BUILD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PlatformSpellingCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved = (player_aliases.fetch_curated_rows, canonical_players._sbclient,
                      os.environ.get("PLAYER_ALIASES_SOURCE"))
        os.environ["PLAYER_ALIASES_SOURCE"] = "json"
        player_aliases.fetch_curated_rows = _json_only_aliases
        canonical_players._sbclient = _offline_guard
        player_aliases._reset_for_tests(None)
        cls.mod = _load_build()
        cls.canon = cls.mod.load_canonical()
        cls.reg = cls.mod.registry(cls.canon)
        cls.cases = json.loads((FX / "resolver_cases.json").read_text())["cases"]
        cls.obs = json.loads((FX / "platform_observations.json").read_text())["observations"]

    @classmethod
    def tearDownClass(cls):
        player_aliases.fetch_curated_rows, canonical_players._sbclient, env = cls._saved
        if env is None:
            os.environ.pop("PLAYER_ALIASES_SOURCE", None)
        else:
            os.environ["PLAYER_ALIASES_SOURCE"] = env
        player_aliases._reset_for_tests(None)

    def test_committed_outputs_match_a_fresh_build(self):
        drift = [str(p.relative_to(ROOT)) for p, txt in self.mod.render(*self.mod.build()).items()
                 if p.read_text(encoding="utf-8") != txt]
        self.assertEqual(drift, [], "rerun docs/research/JEG-1202/build_matrix.py")

    def test_every_observation_points_at_its_source_line(self):
        for o in self.obs:
            lines = (ROOT / o["file"]).read_text(encoding="utf-8").split("\n")
            self.assertEqual(lines[o["line"] - 1].rstrip("\r"), o["raw"], f"{o['file']}:{o['line']}")
            self.assertIn(o["spelling"], o["raw"], f"{o['file']}:{o['line']}")

    def test_grounded_expectations_never_come_from_the_resolver(self):
        allowed = {"exact_canonical", "sleeper_exact", "verified_alias", "dst_mascot",
                   "sleeper_idmap", "sleeper_gsis", "snapshot_collision", "snapshot_collision_position",
                   "idmap_gsis_not_in_players"}
        for c in self.cases:
            self.assertTrue(c["ground"], c)
            self.assertLessEqual(set(c["ground"]), allowed, c)

    def test_resolver_cases(self):
        for c in self.cases:
            with self.subTest(platform=c["platform"], spelling=c["spelling"], pos=c["pos"]):
                key, reason = canonical_players.resolve_with_reason(
                    c["spelling"], position=c["pos"], registry=self.reg)
                grounded = key == c["expect_key"] and (c["expect_key"] is not None or reason == c["expect_reason"])
                if c["status"] == "pass":
                    self.assertTrue(grounded, f"got {key} {reason}, expected {c['expect_key']} {c['expect_reason']}")
                else:
                    # A known gap may be fixed (grounded) or unchanged (pinned);
                    # anything else is new drift.
                    pinned = (key, reason) == (c["observed"]["player_key"], c["observed"]["reason"])
                    self.assertTrue(grounded or pinned, f"got {key} {reason}; pinned {c['observed']}")

    def test_every_required_category_has_a_passing_case(self):
        passing = {t for c in self.cases if c["status"] == "pass" for t in c["tags"]}
        for tag in ("punctuation", "suffix", "nickname", "collision", "unknown", "source_disagreement"):
            self.assertIn(tag, passing, tag)
        for plat in ("espn", "sleeper", "yahoo"):
            self.assertTrue(any(c["platform"] == plat and c["status"] == "pass" for c in self.cases), plat)

    def test_unknown_and_ambiguous_names_are_never_given_a_key(self):
        for c in self.cases:
            if c["expect_reason"] in ("unmatched", "ambiguous"):
                key, _ = canonical_players.resolve_with_reason(c["spelling"], position=c["pos"], registry=self.reg)
                self.assertIsNone(key, c)

    def test_missing_evidence_is_never_counted_as_coverage(self):
        import csv
        with (ROOT / "docs" / "research" / "JEG-1202" / "coverage_matrix.csv").open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        grounded_keys = {o["player_key"] for o in self.obs if o["ground_status"] == "grounded"}
        for r in rows:
            for plat in ("espn", "yahoo"):
                if r[f"{plat}_status"] == "missing":
                    self.assertEqual((r[f"{plat}_spelling"], r[f"{plat}_evidence"]), ("", ""), r["player_key"])
                else:
                    self.assertTrue(r[f"{plat}_evidence"] and r[f"{plat}_ground"], r["player_key"])
                    self.assertIn(int(r["player_key"]), grounded_keys)
            if r["sleeper_status"] == "missing":
                self.assertEqual((r["sleeper_spelling"], r["sleeper_ids"]), ("", ""), r["player_key"])
            else:
                self.assertTrue(r["sleeper_ids"] and r["sleeper_link"], r["player_key"])
        ungrounded = {(o["platform"], o["spelling"]) for o in self.obs if o["ground_status"] != "grounded"}
        for r in rows:
            for plat in ("espn", "yahoo"):
                for sp in filter(None, r[f"{plat}_spelling"].split(" | ")):
                    self.assertNotIn((plat, sp), ungrounded)


if __name__ == "__main__":
    unittest.main()
