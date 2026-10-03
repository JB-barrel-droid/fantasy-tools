#!/usr/bin/env python3
"""JEG-242: backstop manifest hash must cover the exact bytes written.

Regression for the 6701d3a fix: pipelines/backstop_shallow_sources.py hashed
the JSON payload BEFORE appending the trailing newline while load_imputed()
verifies the manifest sha256 against the file's exact bytes (newline included),
so every generated artifact failed verification. The manifest now covers the
newline-terminated bytes.

Negative discrimination: a manifest built the pre-fix way (hash of the bytes
WITHOUT the trailing newline) must fail load_imputed with a hash mismatch.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from backstop_shallow_sources import consensus_group, main, load_imputed  # noqa: E402


def _source_fixture(tmpdir: Path, name: str, pool: dict) -> dict:
    values_text = json.dumps(pool, indent=2, sort_keys=True) + "\n"
    values_path = tmpdir / f"{name}.imputed.json"
    values_path.write_text(values_text, encoding="utf-8")
    manifest = {
        "schema": "option-c-imputation-manifest-v1",
        "publisher_roster": {
            "schema": "option-c-publisher-roster-v1",
            "teams": 12,
            "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1},
            "flex_count": 1,
            "flex_eligible": ["RB", "WR", "TE"],
            "bench_total": 72,
            "scoring": "half_ppr",
        },
        "output_sha256": hashlib.sha256(values_text.encode("utf-8")).hexdigest(),
    }
    manifest_path = tmpdir / f"{name}.imputed.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {"values": values_path.name, "manifest": manifest_path.name}


def _build_batch(tmpdir: Path) -> Path:
    fc_pool = {
        "pk_ja": {"group": "RB|starter", "imputed_vorp": 40.0, "native": 100.0},
        "pk_cd": {"group": "WR|starter", "imputed_vorp": 30.0, "native": 80.0},
        "pk_ef": {"group": "TE|bench", "imputed_vorp": 10.0, "native": 20.0},
    }
    usat_pool = {
        "pk_ja": {"group": "RB|starter", "imputed_vorp": 44.0, "native": 110.0},
        "pk_cd": {"group": "WR|starter", "imputed_vorp": 28.0, "native": 70.0},
    }
    # Third source so pk_ef (missing from usat) is avg-eligible (min_sources=2)
    fp_pool = {
        "pk_ja": {"group": "RB|starter", "imputed_vorp": 42.0, "native": 105.0},
        "pk_ef": {"group": "TE|bench", "imputed_vorp": 14.0, "native": 30.0},
    }
    batch = {
        "schema": "vorp-source-batch-v1",
        "sources": {
            "fantasycalc": _source_fixture(tmpdir, "fantasycalc", fc_pool),
            "usat": _source_fixture(tmpdir, "usat", usat_pool),
            "fantasypros": _source_fixture(tmpdir, "fantasypros", fp_pool),
        },
    }
    batch_path = tmpdir / "vorp-source-batch-v1.json"
    batch_path.write_text(json.dumps(batch, indent=2, sort_keys=True) + "\n")
    return batch_path


class TestBackstopHashRoundtrip(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.batch_path = _build_batch(self.tmpdir)
        # out-dir == batch parent (the writer's relative-path requirement)
        rc = main([
            "--batch", str(self.batch_path),
            "--out-dir", str(self.tmpdir),
            "--target-count", "3",
        ])
        self.assertEqual(rc, 0)
        self.aug = json.loads((self.tmpdir / "vorp-source-batch-augmented-v1.json").read_bytes())

    def tearDown(self):
        self._tmp.cleanup()

    def _entry_files(self, source: str):
        entry = self.aug["sources"][source]
        return (self.tmpdir / entry["values"]), (self.tmpdir / entry["manifest"])

    def test_avg_manifest_hash_matches_written_bytes(self):
        """6701d3a regression: avg manifest covers the newline-terminated bytes."""
        values_path, manifest_path = self._entry_files("avg")
        manifest = json.loads(manifest_path.read_bytes())
        self.assertEqual(manifest["output_sha256"],
                         hashlib.sha256(values_path.read_bytes()).hexdigest())
        # The exact verification path load_imputed uses must succeed.
        values, _ = load_imputed(self.tmpdir / "vorp-source-batch-augmented-v1.json", "avg")
        self.assertEqual(len(values), 3)

    def test_backstopped_manifest_hash_matches_written_bytes(self):
        values_path, manifest_path = self._entry_files("usat")
        manifest = json.loads(manifest_path.read_bytes())
        self.assertEqual(manifest["output_sha256"],
                         hashlib.sha256(values_path.read_bytes()).hexdigest())
        values, _ = load_imputed(self.tmpdir / "vorp-source-batch-augmented-v1.json", "usat")
        self.assertEqual(len(values), 3)
        self.assertEqual(values["pk_ef"]["backstopped_by"], "avg")
        self.assertAlmostEqual(values["pk_ef"]["imputed_vorp"], 12.0)

    def test_prefixed_manifest_without_newline_fails_verification(self):
        """Simulates the pre-fix writer: hashing bytes WITHOUT the trailing
        newline must fail load_imputed -- this is the broken state 6701d3a fixed."""
        values_path, _ = self._entry_files("avg")
        file_bytes = values_path.read_bytes()
        self.assertTrue(file_bytes.endswith(b"\n"))
        broken = {"output_sha256": hashlib.sha256(file_bytes[:-1]).hexdigest()}
        manifest_path = self.tmpdir / "avg.broken.manifest.json"
        manifest_path.write_text(json.dumps(broken))
        batch = json.loads(self.batch_path.read_bytes())
        batch["sources"]["avg_broken"] = {
            "values": values_path.name, "manifest": manifest_path.name,
        }
        broken_batch = self.tmpdir / "broken-batch.json"
        broken_batch.write_text(json.dumps(batch))
        with self.assertRaises(ValueError):
            load_imputed(broken_batch, "avg_broken")

    def test_tampered_bytes_fail_verification(self):
        values_path, _ = self._entry_files("avg")
        tampered = self.tmpdir / "avg.tampered.imputed.json"
        raw = values_path.read_bytes().replace(b"42.0", b"43.0")
        tampered.write_bytes(raw)
        batch = json.loads((self.tmpdir / "vorp-source-batch-augmented-v1.json").read_bytes())
        batch["sources"]["avg_tampered"] = {
            "values": tampered.name,
            "manifest": self.aug["sources"]["avg"]["manifest"],
        }
        tampered_batch = self.tmpdir / "tampered-batch.json"
        tampered_batch.write_text(json.dumps(batch))
        with self.assertRaises(ValueError):
            load_imputed(tampered_batch, "avg_tampered")

    def test_avg_values_are_cross_source_means(self):
        values, _ = load_imputed(self.tmpdir / "vorp-source-batch-augmented-v1.json", "avg")
        self.assertAlmostEqual(values["pk_ja"]["imputed_vorp"], 42.0)
        self.assertAlmostEqual(values["pk_cd"]["imputed_vorp"], 29.0)
        self.assertAlmostEqual(values["pk_ef"]["imputed_vorp"], 12.0)
        self.assertEqual(values["pk_ef"]["group"], "TE|bench")
        self.assertEqual(sorted(values["pk_ef"]["avg_sources"]), ["fantasycalc", "fantasypros"])
        self.assertEqual(values["pk_ja"]["group"], "RB|starter")
        self.assertEqual(sorted(values["pk_ja"]["avg_sources"]), ["fantasycalc", "fantasypros", "usat"])

    def test_shallow_source_backstopped_only_for_missing_players(self):
        values, manifest = load_imputed(self.tmpdir / "vorp-source-batch-augmented-v1.json", "usat")
        # Native usat rows are untouched
        self.assertNotIn("backstopped_by", values["pk_ja"])
        self.assertEqual(values["pk_ja"]["imputed_vorp"], 44.0)
        # Missing player filled from avg
        self.assertEqual(values["pk_ef"]["backstopped_by"], "avg")
        # Missing player filled from avg (mean of fc 10.0 and fp 14.0)
        self.assertEqual(values["pk_ef"]["imputed_vorp"], 12.0)
        self.assertEqual(values["pk_ef"]["backstop_n"], 2)
        self.assertEqual(values["pk_ef"]["backstop_group_assignment"],
                         "cross-source-positive-majority-vote-v1")
        self.assertEqual(manifest["backstop_target_count"], 3)
        self.assertEqual(
            manifest["backstop_target_policy"],
            "top-available-source-average-vorp-v1",
        )
        self.assertEqual(len(manifest["backstop_target_sha256"]), 64)

    def test_single_source_player_cannot_satisfy_min_sources_target(self):
        """Coverage is measured against the league cohort, not max publisher
        depth. A player seen by only one source is not avg-eligible; asking the
        avg pool to cover that larger cohort must fail closed."""
        batch = json.loads(self.batch_path.read_bytes())
        fc_path = self.tmpdir / batch["sources"]["fantasycalc"]["values"]
        fc = json.loads(fc_path.read_bytes())
        fc["pk_only_fc"] = {"group": "RB|bench", "imputed_vorp": 50.0, "native": 125.0}
        fc_text = json.dumps(fc, indent=2, sort_keys=True) + "\n"
        fc_path.write_text(fc_text)
        manifest_path = self.tmpdir / batch["sources"]["fantasycalc"]["manifest"]
        manifest = json.loads(manifest_path.read_bytes())
        manifest["output_sha256"] = hashlib.sha256(fc_text.encode("utf-8")).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        with self.assertRaises(ValueError):
            main([
                "--batch", str(self.batch_path),
                "--out-dir", str(self.tmpdir / "too-deep"),
                "--target-count", "4",
                "--min-sources", "2",
            ])

    def test_positive_average_cannot_be_labeled_cut(self):
        """A positive cross-source VORP row must stay in a funded group even
        when most contributing publishers classify the player as cut."""
        self.assertEqual(
            consensus_group([
                ("fantasycalc", 12.0, "RB|bench"),
                ("usat", 0.0, "RB|cut"),
                ("fantasypros", 0.0, "RB|cut"),
            ]),
            "RB|bench",
        )

    def test_backstop_uses_target_cohort_not_deepest_source_length(self):
        """A source can publish fewer rows than another publisher and still
        need no backstop if it covers the entire configured league cohort."""
        aug = json.loads((self.tmpdir / "vorp-source-batch-augmented-v1.json").read_bytes())
        report = aug["_backstop"]["backstopped_sources"]
        # fantasycalc has all 3 target players and is never backstopped merely
        # because some other source could publish a deeper list.
        self.assertNotIn("fantasycalc", report)
        self.assertEqual(aug["_backstop"]["target_count"], 3)
        self.assertEqual(
            aug["_backstop"]["target_selection_universe"],
            "all-published-union",
        )


if __name__ == "__main__":
    unittest.main()
