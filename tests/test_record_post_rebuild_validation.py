"""A red post-rebuild validate must leave the chain status saying "failed".

JEG-509: runs 37944395121..37955914956 published a status with
success=false and failed=["post_rebuild_validation"] but
outcome="published_with_holds", the value the chain had written before
validate ran. Nothing was published, and an agent read the USA Today hold
as the cause.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import record_post_rebuild_validation as recorder  # noqa: E402

LOG = """FAIL: test_x (tests.test_two_tier_frontend.TestTwoTierPort.test_x)
AssertionError: False is not true
make: *** [Makefile:443: test-core] Error 1
"""


class RecordPostRebuildValidationTest(unittest.TestCase):
    def test_outcome_is_failed_even_when_the_chain_had_published_with_holds(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            src = repo / recorder.STATUS_PATHS[0]
            src.parent.mkdir(parents=True)
            src.write_text(json.dumps({
                "success": True, "failed": [], "outcome": "published_with_holds",
                "held": ["usatoday"], "hold_severity": "amber"}), encoding="utf-8")
            recorder.record(repo, LOG)
            for rel in recorder.STATUS_PATHS:
                status = json.loads((repo / rel).read_text(encoding="utf-8"))
                self.assertFalse(status["success"])
                self.assertEqual("failed", status["outcome"], rel)
                self.assertIn("post_rebuild_validation", status["failed"])
                # The per-source hold record is kept; it just is not the outcome.
                self.assertEqual(["usatoday"], status["held"])


if __name__ == "__main__":
    unittest.main()
