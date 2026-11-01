"""JEG-1128: DDF tiers follow roster seats, not the sign of the value (VP-7.3).

docs/methodology.md VP-7.3 ranks a position by blended DDF Value and gives
the first S*_p players the starter tier and the next up to N*_p the bench
tier; everyone below is waiver, and a DDF Value of exactly 0 is waiver
wherever it ranks. Jeremy kept this (logged pick A, 2026-10-28) over "tier
follows positive value" (option B), so two cases are expected and pinned here:

- Positive-valued waiver: a player ranked below N*_p keeps a small positive
  DDF Value (one publisher rosters him, the blend does not) and is waiver.
- Zero inside the seats: a player ranked within N*_p with a DDF Value of 0 is
  waiver, not bench.

The worked example (tests/fixtures/value_pipeline_worked_example.json) has
neither, so this test builds both from it without touching the projections
(the seats are allocated from projected points, so they stay RB 2/3 and
TE 3/4): chart c1 rosters RB Golf above RB Foxtrot, and TE Victor's chart
values are set to TE Whiskey's (or removed), which puts him at the waiver line.
All three implementations run the same input: the engine
(app/trade-value-chart/assets/value-model.js, headless under node), the
Python reference (pipelines/value_reference.py) and the spec reference
(pipelines/spec_reference). They must agree on every tier.

Discrimination: under option B, RB Golf would be bench; with the zero clause
removed, TE Victor would be bench. Either fails test_cases_get_waiver.

Skips the engine part when node is missing, unless RENDER_TESTS_REQUIRED=1.
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipelines"))

from tests import _render_env  # noqa: E402
from tests import test_value_reference_worked_example as pyref  # noqa: E402
from spec_reference import worked_example as specref  # noqa: E402

VALUE_MODEL = ROOT / "app" / "trade-value-chart" / "assets" / "value-model.js"
DRIVER = ROOT / "tests" / "value_pipeline_driver.js"

RB_GOLF, TE_VICTOR, TE_WHISKEY = "204", "404", "405"


def seat_fixture() -> dict:
    """The worked example with one positive-valued waiver (RB Golf) and one zero inside the seats (TE Victor)."""
    fx = copy.deepcopy(pyref.load())
    for key, src in fx["inputs"].items():
        if src["family"] != "chart":
            continue
        values = src["values"]
        if TE_WHISKEY in values:
            values[TE_VICTOR] = values[TE_WHISKEY]
        else:
            values.pop(TE_VICTOR, None)
    fx["inputs"]["c1"]["values"][RB_GOLF] = 40
    return fx


def _ranked(rows: dict, pos: str, mean_ppg: dict) -> list[str]:
    """VP-7.3 order: DDF Value desc, then mean PPG desc (missing last), then key asc."""
    keys = [k for k, r in rows.items() if r["pos"] == pos and r["value"] is not None]
    return sorted(keys, key=lambda k: (-rows[k]["value"], mean_ppg.get(k) is None, -(mean_ppg.get(k) or 0.0), int(k)))


def python_reference(fx: dict) -> dict:
    out = pyref.run(fx)
    rows = {str(k): {"pos": fx["players"][str(k)]["pos"], "value": r["ddf"]["blended"]["value"], "tier": r["ddf_tier"]}
            for k, r in out["rows"].items()}
    return {"rows": rows, "slot_fill": out["slot_fill"], "mean_ppg": {str(k): v for k, v in out["mean_ppg"].items()}}


def spec_reference(fx: dict) -> dict:
    out = specref.run_fixture(fx)
    return {str(k): r["ddf_tier"] for k, r in out["rows"].items()}


def engine(fx: dict) -> dict:
    node = shutil.which("node")
    if node is None:
        if _render_env.required():
            raise AssertionError("node is required (RENDER_TESTS_REQUIRED=1) but not installed")
        raise unittest.SkipTest("node not installed")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "seat_fixture.json"
        path.write_text(json.dumps(fx), encoding="utf-8")
        proc = subprocess.run([node, str(DRIVER), str(VALUE_MODEL), str(path)],
                              capture_output=True, text=True, check=True)
    return {k: r["ddf_tier"] for k, r in json.loads(proc.stdout)["rows"].items()}


class TiersFollowSeats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = seat_fixture()
        cls.py = python_reference(cls.fx)

    def rank(self, key: str) -> int:
        pos = self.py["rows"][key]["pos"]
        return _ranked(self.py["rows"], pos, self.py["mean_ppg"]).index(key) + 1

    def test_seats_unchanged_by_the_edit(self):
        sf = self.py["slot_fill"]
        self.assertEqual((sf["RB"]["starters"], sf["RB"]["rostered"]), (2, 3))
        self.assertEqual((sf["TE"]["starters"], sf["TE"]["rostered"]), (3, 4))

    def test_cases_are_present(self):
        golf, victor = self.py["rows"][RB_GOLF], self.py["rows"][TE_VICTOR]
        # RB Golf: below the 3 RB seats with a positive DDF Value.
        self.assertEqual(self.rank(RB_GOLF), 4)
        self.assertGreater(golf["value"], 0)
        # TE Victor: inside the 4 TE seats with a DDF Value of 0.
        self.assertEqual(self.rank(TE_VICTOR), 4)
        self.assertEqual(victor["value"], 0)

    def test_cases_get_waiver(self):
        self.assertEqual(self.py["rows"][RB_GOLF]["tier"], "waiver")
        self.assertEqual(self.py["rows"][TE_VICTOR]["tier"], "waiver")

    def test_every_tier_is_the_seat_rule(self):
        sf = self.py["slot_fill"]
        for pos in ("QB", "RB", "WR", "TE"):
            for rank, key in enumerate(_ranked(self.py["rows"], pos, self.py["mean_ppg"]), start=1):
                v = self.py["rows"][key]["value"]
                want = ("waiver" if v == 0 else "starter" if rank <= sf[pos]["starters"]
                        else "bench" if rank <= sf[pos]["rostered"] else "waiver")
                self.assertEqual(self.py["rows"][key]["tier"], want, f"{pos} rank {rank} key {key}")

    def test_spec_reference_agrees(self):
        py = {k: r["tier"] for k, r in self.py["rows"].items()}
        self.assertEqual(spec_reference(self.fx), py)

    def test_engine_agrees(self):
        py = {k: r["tier"] for k, r in self.py["rows"].items()}
        self.assertEqual(engine(self.fx), py)


if __name__ == "__main__":
    unittest.main()
