"""The chain commits the DDF legs its sections were built from
(GAP-RAZZBALL-REFRESH-FOLLOWUPS (1)).

Defect: rebuild-chain.yml's commit step staged the fixture but never
data/ddf-two-tier, so after each new vintage the committed
ddf_leg_{espn,cbsros,razzball}.json lagged the published sections
(2026-10-08: cbsros section 2026-10-08 vs newest committed leg 2026-09-30),
and check_input_lineage reported every one of them as a mismatch. Two more
defects kept that checker red even with fresh legs: it looked for
ddf_leg_espn.json (the ESPN leg is ddf_leg.json), and it compared the
section's stamp with the newest leg of ANY combo while the writer stamps the
first combo's leg of the same run.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import check_input_lineage as cil  # noqa: E402
from build_ddf_two_tier_leg import write_leg_json  # noqa: E402
from lineage_block import build_lineage_block, collect_leg_triples, resolve_raw_vintage  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "rebuild-chain.yml"


def commit_branches() -> tuple[str, str]:
    text = WORKFLOW.read_text(encoding="utf-8")
    step = text[text.index("- name: Commit and push if changed"):]
    step = step[:step.index("git diff --cached --quiet")]
    ok = step[step.index('if [ "$CHAIN_OUTCOME" = "success" ]; then'):step.index("          else")]
    bad = step[step.index("          else"):]
    return ok, bad


class WorkflowStagesLegs(unittest.TestCase):
    def test_success_branch_stages_the_legs(self):
        ok, _ = commit_branches()
        self.assertRegex(ok, r"git add data/ddf-two-tier\b")

    def test_failure_branch_never_stages_legs(self):
        _, bad = commit_branches()
        self.assertNotIn("data/ddf-two-tier", re.sub(r"#.*", "", bad))


class UnchangedRebuildKeepsTheFile(unittest.TestCase):
    LEG = {"bake_id": "ddf-20261006-razzball-ppr-12t-0p15", "schema": "trade-value-ddf-leg-v1",
           "generated_at": "2026-10-07T00:00:00Z", "values": [{"player_key": 1, "value": 5.0}]}

    def test_same_content_new_timestamp_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ddf_leg_razzball.json"
            write_leg_json(p, dict(self.LEG))
            before = p.read_bytes()
            got = write_leg_json(p, dict(self.LEG, generated_at="2026-10-08T10:00:00Z"))
            self.assertEqual(p.read_bytes(), before)
            self.assertEqual(got["generated_at"], "2026-10-07T00:00:00Z")

    def test_changed_values_are_written(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ddf_leg_razzball.json"
            write_leg_json(p, dict(self.LEG))
            new = dict(self.LEG, generated_at="2026-10-08T10:00:00Z",
                       values=[{"player_key": 1, "value": 6.0}])
            got = write_leg_json(p, new)
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["values"][0]["value"], 6.0)
            self.assertEqual(got["generated_at"], "2026-10-08T10:00:00Z")


def make_leg(root: Path, source: str, filename: str, combo: str, generated_at: str,
             value: float, snap_field: str, vintage: str) -> dict:
    leg = {"bake_id": f"ddf-20261006-{source}-{combo}-0p15", "generated_at": generated_at,
           "values": [{"player_key": 1, "player_norm": "a b", "value": value, "ppg": value}],
           "inputs": {snap_field: vintage}}
    d = root / leg["bake_id"]
    d.mkdir(parents=True)
    (d / filename).write_text(json.dumps(leg))
    return leg


class LineageCheckerFollowsTheWriter(unittest.TestCase):
    def run_checker(self, source, filename, snap_field):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first = make_leg(root, source, filename, "ppr-8t", "2026-10-08T10:00:01Z", 5.0, snap_field, "2026-10-06")
            make_leg(root, source, filename, "ppr-12t", "2026-10-08T10:00:09Z", 7.0, snap_field, "2026-10-06")
            # Exactly what the section writer stamps: the first combo's leg.
            raw_vintage, vintage_source = resolve_raw_vintage(vintage="2026-10-06")
            lineage = build_lineage_block(triples=collect_leg_triples(first), raw_vintage=raw_vintage,
                                          raw_built_at=first["generated_at"], vintage_source=vintage_source)
            saved = cil.LEG_DIR
            cil.LEG_DIR = root
            try:
                mismatches: list = []
                cil.check_fixture_sections({"sources": {source: {"lineage": lineage}}}, mismatches)
            finally:
                cil.LEG_DIR = saved
            return [m for m in mismatches if m["section"] == source]

    def test_stamp_from_the_first_combo_leg_is_accepted(self):
        self.assertEqual(self.run_checker("razzball", "ddf_leg_razzball.json", "razzball_snapshot_date"), [])

    def test_espn_leg_filename_is_the_one_the_builder_writes(self):
        self.assertEqual(self.run_checker("espn", "ddf_leg.json", "espn_snapshot_date"), [])


if __name__ == "__main__":
    unittest.main()
