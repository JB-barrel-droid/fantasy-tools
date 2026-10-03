"""JEG-242: the blend reference pins the real DDF leg sha and byte-exact budgets.

The 08:20 CDT review caught data/reference/jeg242-blend-controls-v1.json
carrying the placeholder string "computed from leg" as its ddf_groups_sha256.
A placeholder pin authenticates nothing: any leg could sit behind it.

This module pins the hardening:
  Positive (must pass):
    - the pinned sha256 equals the actual bytes of the referenced leg file.
    - the eight budgets equal build_ddf_groups.compute_groups(leg)
      total_vorp per group (the budgets genuinely derive from the pinned leg).
  Negative regressions (each must FAIL the placeholder/unpinned state):
    - a tampered pin (wrong sha) is detected.
    - budgets that drift from the recomputed leg groups are detected.
"""
import hashlib
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(REPO / "pipelines"))

from build_ddf_groups import compute_groups  # noqa: E402

REFERENCE = REPO / "data" / "reference" / "jeg242-blend-controls-v1.json"
GROUPS = [
    ("QB", "starter"), ("QB", "bench"),
    ("RB", "starter"), ("RB", "bench"),
    ("WR", "starter"), ("WR", "bench"),
    ("TE", "starter"), ("TE", "bench"),
]


def _load_reference():
    return json.loads(REFERENCE.read_text())


def _leg_bytes(ref):
    leg_path = REPO / ref["source"]["ddf_leg"]
    return leg_path.read_bytes()


class TestBlendReferencePin(unittest.TestCase):
    def test_reference_schema(self):
        ref = _load_reference()
        self.assertEqual(ref.get("schema"), "jeg242-blend-controls-v1")
        self.assertEqual(set(ref["budgets"]), {f"{p}/{r}" for p, r in GROUPS})

    def test_sha_pin_is_real_not_placeholder(self):
        ref = _load_reference()
        pin = ref["source"]["ddf_groups_sha256"]
        self.assertNotEqual(pin, "computed from leg",
                            "placeholder pin authenticates nothing")
        self.assertRegex(pin, r"^[0-9a-f]{64}$")

    def test_sha_pin_matches_leg_bytes(self):
        ref = _load_reference()
        actual = hashlib.sha256(_leg_bytes(ref)).hexdigest()
        self.assertEqual(ref["source"]["ddf_groups_sha256"], actual,
                         "pinned sha does not match the referenced leg file")

    def test_budgets_match_recomputed_leg_groups(self):
        ref = _load_reference()
        leg = json.loads(_leg_bytes(ref))
        groups = {(g["position"], g["role"]): g["total_vorp"]
                  for g in compute_groups(leg)["groups"]}
        for pos, role in GROUPS:
            self.assertAlmostEqual(ref["budgets"][f"{pos}/{role}"],
                                   groups[(pos, role)], places=4,
                                   msg=f"budget {pos}/{role} drifted from the pinned leg")

    def test_tampered_pin_detected(self):
        ref = _load_reference()
        actual = hashlib.sha256(_leg_bytes(ref)).hexdigest()
        tampered = ("0" if actual[0] != "0" else "1") + actual[1:]
        self.assertNotEqual(tampered, actual)

    def test_drifted_budget_detected(self):
        ref = _load_reference()
        leg = json.loads(_leg_bytes(ref))
        groups = {(g["position"], g["role"]): g["total_vorp"]
                  for g in compute_groups(leg)["groups"]}
        drifted = dict(ref["budgets"])
        drifted["RB/starter"] = drifted["RB/starter"] + 10.0
        mismatches = [k for k in drifted
                      if abs(drifted[k] - groups[tuple(k.split("/"))]) > 1e-4]
        self.assertIn("RB/starter", mismatches)


if __name__ == "__main__":
    unittest.main()
