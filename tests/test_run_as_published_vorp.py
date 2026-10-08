"""JEG-242: run_as_published_vorp.py is real orchestration, not a scaffold.

The 08:20 CDT review caught the script as an honest scaffold: it validated
the reference config and printed, but never called build_imputed_vorps /
build_reweighted_values (TODO list in-file). This module pins the hardening:

  Positive (must pass):
    - the orchestrator resolves Jeremy's pinned reference, verifies the leg
      sha pin, rebuilds group VORPs from the pinned leg, extracts --controls
      mechanically from the reference budgets, and runs the reviewed
      refresh_vorp_views path end-to-end (impute -> reweight -> review ->
      versioned manifest + orchestrator provenance). Candidate-only.
    - the extracted controls are byte-identical to the reference budgets
      (no invented weights).
  Negative regressions (each must FAIL the scaffold/unwired state):
    - a reference with a tampered leg-sha pin aborts before any producer
      runs and writes no candidate.
    - a --group-vorps override whose totals disagree with the reference
      budgets aborts (imputation targets and reweight controls can never
      silently disagree).
    - the Makefile names this orchestration (run-as-published-vorp target).
"""
import hashlib
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(REPO / "pipelines"))

from run_as_published_vorp import main as orch_main  # noqa: E402

REFERENCE = REPO / "data" / "reference" / "jeg242-blend-controls-v1.json"

ROSTER = {
    "schema": "option-c-publisher-roster-v1",
    "teams": 12,
    "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1},
    "flex_count": 1,
    "flex_eligible": ["RB", "WR", "TE"],
    "bench_total": 72,
    "scoring": "half_ppr",
}


def _synthetic_values(seed_offset=0.0):
    counts = {"QB": 20, "RB": 70, "WR": 90, "TE": 40}
    queues = {pos: [f"{pos}-{i}" for i in range(n)] for pos, n in counts.items()}
    order = []
    while any(queues.values()):
        for pos in ("QB", "RB", "WR", "TE"):
            if queues[pos]:
                order.append((pos, queues[pos].pop(0)))
    values, key = {}, 90001
    for rank, (pos, _tag) in enumerate(order):
        values[str(key)] = [pos, 1000.0 - rank * 0.5 + seed_offset]
        key += 1
    return values


def _fixture(tmp: Path, reference: Path = REFERENCE):
    values_dir = tmp / "values"
    values_dir.mkdir()
    (values_dir / "fantasycalc.json").write_text(json.dumps(_synthetic_values()))
    (values_dir / "usat.json").write_text(json.dumps(_synthetic_values(37.0)))
    (tmp / "roster.json").write_text(json.dumps(ROSTER))
    return ["--values-dir", str(values_dir),
            "--roster-config", str(tmp / "roster.json"),
            "--out-dir", str(tmp / "out"),
            "--reference", str(reference)]


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = orch_main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue() + err.getvalue()


class TestRunAsPublishedVorp(unittest.TestCase):
    def test_orchestrates_end_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            code, log = _run(_fixture(tmp))
            self.assertEqual(code, 0, f"orchestration failed:\n{log}")
            out = tmp / "out"
            self.assertTrue((out / "candidate.json").is_file())
            self.assertTrue((out / "refresh-run.manifest.json").is_file())
            prov = json.loads((out / "orchestrator.json").read_text(encoding="utf-8"))
            self.assertEqual(prov["schema"], "jeg242-orchestration-v1")
            self.assertEqual(prov["group_vorps"]["mode"], "rebuilt_from_pinned_leg")
            # leg pin verified against actual bytes
            ref = json.loads(REFERENCE.read_text(encoding="utf-8"))
            leg_bytes = (REPO / ref["source"]["ddf_leg"]).read_bytes()
            self.assertEqual(prov["group_vorps"]["leg_sha256"],
                             hashlib.sha256(leg_bytes).hexdigest())
            cand = json.loads((out / "candidate.json").read_text(encoding="utf-8"))
            self.assertEqual(cand["schema"], "shared-batch70-views-v1")
            self.assertIn("fantasycalc", cand["sources"])

    def test_controls_extracted_verbatim_from_budgets(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            code, log = _run(_fixture(tmp))
            self.assertEqual(code, 0, f"orchestration failed:\n{log}")
            controls = json.loads((tmp / "out" / "work" / "controls.from_reference.json").read_text(encoding="utf-8"))
            ref = json.loads(REFERENCE.read_text(encoding="utf-8"))
            self.assertEqual(controls, ref["budgets"])

    def test_tampered_leg_pin_aborts_before_producers(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            bad_ref = tmp / "bad-reference.json"
            ref = json.loads(REFERENCE.read_text(encoding="utf-8"))
            pin = ref["source"]["ddf_groups_sha256"]
            ref["source"]["ddf_groups_sha256"] = ("0" if pin[0] != "0" else "1") + pin[1:]
            bad_ref.write_text(json.dumps(ref))
            code, log = _run(_fixture(tmp, reference=bad_ref))
            self.assertNotEqual(code, 0)
            self.assertIn("sha mismatch", log)
            self.assertFalse((tmp / "out" / "candidate.json").exists(),
                             "no candidate may be written after a pin failure")

    def test_mismatched_group_vorps_override_aborts(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            gv = tmp / "group_vorps.json"
            ref = json.loads(REFERENCE.read_text(encoding="utf-8"))
            groups = [{"position": p, "role": r, "total_vorp": ref["budgets"][f"{p}/{r}"] + 5.0}
                      for p, r in [("QB", "starter"), ("QB", "bench"), ("RB", "starter"),
                                   ("RB", "bench"), ("WR", "starter"), ("WR", "bench"),
                                   ("TE", "starter"), ("TE", "bench")]]
            gv.write_text(json.dumps({
                "teams": 12, "scoring": "half_ppr",
                "roster": {"slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1},
                           "flex_count": 1, "flex_eligible": ["RB", "WR", "TE"],
                           "bench_mix": {"QB": 10, "RB": 27, "WR": 33, "TE": 10}},
                "groups": groups}))
            argv = _fixture(tmp) + ["--group-vorps", str(gv)]
            code, log = _run(argv)
            self.assertNotEqual(code, 0)
            self.assertIn("disagrees with reference budget", log)

    def test_makefile_names_orchestration(self):
        text = (REPO / "Makefile").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^run-as-published-vorp:")

    def test_no_todo_scaffold_remains(self):
        src = (REPO / "pipelines" / "run_as_published_vorp.py").read_text(encoding="utf-8")
        self.assertNotIn("TODO", src)
        self.assertIn("refresh_views", src)


if __name__ == "__main__":
    unittest.main()
