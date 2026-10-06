"""JEG-381: the CBS ROS pre-load verifier must reject legs that differ from
the published fixture (wrong scoring slice, wrong vintage, missing players).

The 2026-10-04 ad-hoc load wrote the standard-scoring leg under the full-PPR
label; the negative cases below reproduce that class.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
import verify_cbsros_legs_vs_fixture as v  # noqa: E402

PUBLISHED = {"jahmyr gibbs": 70.0, "brock bowers": 23.1, "josh allen": 20.8}


def leg(values):
    return {"values": [{"player_norm": k, "value": x} for k, x in values.items()]}


class VerifyCbsrosLegsTest(unittest.TestCase):
    def test_matching_leg_passes(self):
        self.assertEqual([], v.compare(leg({"jahmyr gibbs": 70.0, "brock bowers": 23.07,
                                            "josh allen": 20.84}), PUBLISHED))

    def test_wrong_scoring_slice_is_rejected(self):
        # Standard-scoring values loaded under the full-PPR label (2026-10-04).
        probs = v.compare(leg({"jahmyr gibbs": 70.0, "brock bowers": 18.66,
                               "josh allen": 23.95}), PUBLISHED)
        self.assertTrue(any("differ from published" in p for p in probs))

    def test_missing_and_extra_players_are_rejected(self):
        probs = v.compare(leg({"jahmyr gibbs": 70.0, "brock bowers": 23.1,
                               "someone else": 5.0}), PUBLISHED)
        self.assertTrue(any("absent from leg" in p for p in probs))
        self.assertTrue(any("not published" in p for p in probs))


if __name__ == "__main__":
    unittest.main()
