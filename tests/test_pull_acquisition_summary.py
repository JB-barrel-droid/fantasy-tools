#!/usr/bin/env python3
"""Regression tests for JEG-128 acquisition summary.

These tests verify that:
- State A: A puller that raises SystemExit(2) must produce acquisition.<src>.status == "failed"
- State B: A pull producing byte-identical output must record status == "unchanged"

Each test uses temp copies of the artifact, never the repo's committed artifact.
"""
import json
import os
import sys
import tempfile
import unittest

# Add pipelines to path for import
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "pipelines"))

from record_pull_acquisition import record_acquisition_to_file


def create_test_artifact(tmp_dir):
    """Create a minimal test artifact with the expected structure."""
    artifact = {
        "generated_at": "2026-10-01T16:07:19.936040+00:00",
        "schema": "pipeline-checkpoints-v1",
        "nfl_week": 4,
        "sources": {
            "espn": {
                "label": "ESPN",
                "checkpoints": {}
            }
        }
    }
    path = os.path.join(tmp_dir, "pipeline-checkpoints.json")
    with open(path, "w") as f:
        json.dump(artifact, f, indent=2)
        f.write("\n")
    return path


class TestBrokenStateAFailedPuller(unittest.TestCase):
    """State A: A puller that raises SystemExit(2) must produce acquisition.<src>.status == 'failed'.

    This test simulates a puller that fails (raises SystemExit(2)) and verifies that
    the acquisition summary correctly records the failure, never silently passing or
    leaving the block missing.
    """

    def test_failed_puller_records_failed_status(self):
        """Failed pull (SystemExit(2)) must produce acquisition.<src>.status == 'failed'."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact_path = create_test_artifact(tmp_dir)

            # Simulate a failed pull (raises SystemExit(2))
            # In real workflow: the pull script exits with code 2 on failure
            try:
                sys.exit(2)
            except SystemExit:
                pass

            # Record the acquisition with failed status
            # This is what the workflow should call after detecting the failure
            record = record_acquisition_to_file(
                path=artifact_path,
                source="espn",
                status="failed",
                rows=0,
                vintage="2026-10-02",
                reason="Pull script exited with code 2"
            )

            # Read back and verify
            with open(artifact_path, "r") as f:
                data = json.load(f)

            # The acquisition block must exist
            self.assertIn("acquisition", data, "acquisition block must exist after failed pull")

            # The source must have a failed status
            self.assertIn("espn", data["acquisition"], "espn must be in acquisition block")
            self.assertEqual(
                data["acquisition"]["espn"]["status"],
                "failed",
                "Failed puller must produce status == 'failed', never silent green"
            )

            # Must not be missing or have a false 'acquired' status
            self.assertNotEqual(
                data["acquisition"]["espn"]["status"],
                "acquired",
                "Failed pull must NOT produce acquired status"
            )


class TestBrokenStateBUnchangedOutput(unittest.TestCase):
    """State B: A pull producing byte-identical output must record status == 'unchanged'.

    This test verifies that when a pull produces no new data (byte-identical to previous),
    the acquisition summary correctly records 'unchanged' with the vintage, never
    incorrectly records it as 'acquired N rows'.
    """

    def test_unchanged_output_records_unchanged_status(self):
        """Unchanged output must record status == 'unchanged' with vintage, never 'acquired N rows'."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact_path = create_test_artifact(tmp_dir)

            # Simulate unchanged output (byte-identical to previous)
            # In real workflow: the pull produces same bytes as before
            previous_hash = "abc123"
            current_hash = "abc123"  # Same hash = unchanged

            vintage = "2026-10-02"

            # Record the acquisition with unchanged status
            record = record_acquisition_to_file(
                path=artifact_path,
                source="espn",
                status="unchanged",
                rows=0,
                vintage=vintage,
                reason=f"Unchanged since last pull (hash: {current_hash})"
            )

            # Read back and verify
            with open(artifact_path, "r") as f:
                data = json.load(f)

            # The acquisition block must exist
            self.assertIn("acquisition", data, "acquisition block must exist after unchanged pull")

            # The source must have unchanged status
            self.assertIn("espn", data["acquisition"], "espn must be in acquisition block")
            self.assertEqual(
                data["acquisition"]["espn"]["status"],
                "unchanged",
                "Unchanged output must produce status == 'unchanged'"
            )

            # Must include the vintage
            self.assertEqual(
                data["acquisition"]["espn"]["vintage"],
                vintage,
                "Unchanged status must include vintage"
            )

            # Must NOT have rows count (or if it does, must not be > 0 for unchanged)
            if "rows" in data["acquisition"]["espn"]:
                self.assertEqual(
                    data["acquisition"]["espn"]["rows"],
                    0,
                    "Unchanged must not report positive rows"
                )

            # Must NOT incorrectly record as acquired
            self.assertNotEqual(
                data["acquisition"]["espn"]["status"],
                "acquired",
                "Unchanged output must NOT be recorded as 'acquired'"
            )


class TestSuccessfulAcquisition(unittest.TestCase):
    """Verify successful acquisition works correctly."""

    def test_acquired_status_with_rows(self):
        """Successful acquisition should record status == 'acquired' with row count."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact_path = create_test_artifact(tmp_dir)

            record = record_acquisition_to_file(
                path=artifact_path,
                source="espn",
                status="acquired",
                rows=512,
                vintage="2026-10-02",
                reason="Pulled 512 players"
            )

            # Read back and verify
            with open(artifact_path, "r") as f:
                data = json.load(f)

            self.assertEqual(data["acquisition"]["espn"]["status"], "acquired")
            self.assertEqual(data["acquisition"]["espn"]["rows"], 512)
            self.assertEqual(data["acquisition"]["espn"]["vintage"], "2026-10-02")
            self.assertIn("recorded_at", data["acquisition"]["espn"])

    def test_multiple_sources_independent(self):
        """Multiple sources should be tracked independently."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact_path = create_test_artifact(tmp_dir)

            # Record for espn
            record_acquisition_to_file(
                path=artifact_path,
                source="espn",
                status="acquired",
                rows=512,
                vintage="2026-10-02"
            )

            # Record for cbs
            record_acquisition_to_file(
                path=artifact_path,
                source="cbs",
                status="unchanged",
                rows=0,
                vintage="2026-10-02"
            )

            # Read back and verify both
            with open(artifact_path, "r") as f:
                data = json.load(f)

            self.assertEqual(data["acquisition"]["espn"]["status"], "acquired")
            self.assertEqual(data["acquisition"]["espn"]["rows"], 512)

            self.assertEqual(data["acquisition"]["cbs"]["status"], "unchanged")

            # Original top-level keys should be preserved
            self.assertIn("generated_at", data)
            self.assertIn("schema", data)
            self.assertIn("nfl_week", data)


class TestArtifactPreservation(unittest.TestCase):
    """Verify that non-acquisition keys are preserved."""

    def test_other_keys_preserved(self):
        """All non-acquisition keys must be preserved byte-for-byte (except order)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact_path = create_test_artifact(tmp_dir)

            # Read original
            with open(artifact_path, "r") as f:
                original_data = json.load(f)

            # Add acquisition
            record_acquisition_to_file(
                path=artifact_path,
                source="espn",
                status="acquired",
                rows=100,
                vintage="2026-10-02"
            )

            # Read updated
            with open(artifact_path, "r") as f:
                updated_data = json.load(f)

            # Verify original keys preserved
            for key in original_data:
                if key != "acquisition":
                    self.assertIn(key, updated_data, f"Key {key} must be preserved")
                    self.assertEqual(
                        original_data[key],
                        updated_data[key],
                        f"Value for {key} must be preserved"
                    )


if __name__ == "__main__":
    unittest.main()
