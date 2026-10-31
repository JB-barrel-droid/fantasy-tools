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
        # The Sleeper base is refreshed and committed by a workflow (JEG-366);
        # a refresh alone makes the matrix stale, not wrong. Say so instead of
        # failing the suite until someone reruns the build.
        built = json.loads((ROOT / "docs" / "research" / "JEG-1202" / "summary.json").read_text())
        base = json.loads((ROOT / self.mod.SLEEPER_BASE).read_text())["meta"]
        if built["sleeper_base_meta"].get("pulled_at") != base.get("pulled_at"):
            self.skipTest(f"Sleeper base refreshed since the matrix was built "
                          f"({built['sleeper_base_meta'].get('pulled_at')} -> {base.get('pulled_at')}); "
                          "rerun docs/research/JEG-1202/build_matrix.py")
        drift = [str(p.relative_to(ROOT)) for p, txt in self.mod.render(*self.mod.build()).items()
                 if p.read_text(encoding="utf-8") != txt]
        self.assertEqual(drift, [], "rerun docs/research/JEG-1202/build_matrix.py")

    def test_every_row_states_active_from_the_paired_snapshot(self):
        # JEG-1313: without saved active flags every row read as inactive and
        # namesakes looked ambiguous offline when the live registry would not.
        doc = json.loads((ROOT / self.mod.ACTIVE).read_text())
        raw = json.loads((ROOT / self.mod.SNAPSHOT).read_text())
        self.assertEqual(doc["identity_md5"], self.mod.identity_md5(raw))
        self.assertEqual(doc["row_count"], len(raw))
        self.assertTrue(all(isinstance(r.get("active"), bool) for r in self.canon.values()))
        self.assertEqual(sum(r["active"] for r in self.canon.values()), doc["active_count"])
        self.assertEqual(sum(e["active"] for e in self.reg.by_key.values()), doc["active_count"])

    def test_active_snapshot_is_refused_for_other_rows(self):
        raw = json.loads((ROOT / self.mod.SNAPSHOT).read_text())
        renamed = [dict(r) for r in raw]
        renamed[0]["full_name"] += " Jr."
        with self.assertRaises(SystemExit):
            self.mod.load_active(renamed)
        with self.assertRaises(SystemExit):
            self.mod.load_active(raw[:-1])

    def test_one_active_namesake_wins_without_a_position(self):
        # Grounded from the two snapshots only: of the rows whose name
        # normalizes to DeVonta Smith's, 764 is the one active row.
        norm = canonical_players.norm_player_name("DeVonta Smith")
        rows = [k for k, r in self.canon.items() if canonical_players.norm_player_name(r["full_name"]) == norm]
        self.assertGreater(len(rows), 1)
        self.assertEqual([k for k in rows if self.canon[k]["active"]], [764])
        self.assertEqual(canonical_players.resolve_with_reason("DeVonta Smith", registry=self.reg), (764, "ok"))

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
