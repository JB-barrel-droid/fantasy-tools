"""JEG-242: review for shared-batch70-views-v1 candidate artifacts.

Builds a genuine candidate end-to-end through the real producers
(build_imputed_vorps -> build_reweighted_values) on synthetic publisher
values, then gates it with pipelines/review_batch70_views.py.

Positive: the real-producer candidate passes all gates, with and without
--batch hash admission.
Negative (each must fail the review):
  - tampered batch file (hash admission catches substitution)
  - missing manifest (the unwired path has no provenance)
  - artifact_status != candidate (promotion needs a different review)
  - legacy per-source 70 scaling (each source peaks at 70 independently;
    the old normalization destroys the common budget, so per-source sums
    diverge and conservation fails)
  - included-but-unexcluded unknown source
  - sidecar/artifact hash mismatch
  - granular empty indexed is the contract (no as-published natives);
    granular nonempty indexed fails (wrong-kind wiring); published empty
    indexed fails (wiring gap)
"""
import copy
import hashlib
import io
import json
import math
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

from build_imputed_vorps import main as impute_main  # noqa: E402
from build_reweighted_values import main as reweight_main  # noqa: E402
from review_batch70_views import GateFailure, check_views, main as review_main  # noqa: E402

ROSTER = {
    "schema": "option-c-publisher-roster-v1",
    "teams": 12,
    "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1},
    "flex_count": 1,
    "flex_eligible": ["RB", "WR", "TE"],
    "bench_total": 72,
    "scoring": "half_ppr",
}

GROUP_TARGETS = {
    ("QB", "starter"): 148.84, ("QB", "bench"): 26.27,
    ("RB", "starter"): 995.91, ("RB", "bench"): 175.75,
    ("WR", "starter"): 975.04, ("WR", "bench"): 172.07,
    ("TE", "starter"): 145.73, ("TE", "bench"): 23.38,
}

CONTROLS = {
    "QB/starter": 100.0, "QB/bench": 20.0,
    "RB/starter": 800.0, "RB/bench": 150.0,
    "WR/starter": 800.0, "WR/bench": 150.0,
    "TE/starter": 120.0, "TE/bench": 25.0,
}

EXCLUDED = {
    "cbs": "test exclusion (not built in fixture)",
    "fantasypros": "test exclusion (not built in fixture)",
    "espn": "test exclusion (granular leg not built in fixture)",
    "cbsros": "test exclusion (granular leg not built in fixture)",
    "razzball": "test exclusion (granular leg not built in fixture)",
}

SOURCES = ("fantasycalc", "usat")


def _synthetic_values(tmp: Path, seed_offset: float = 0.0) -> dict:
    """220 synthetic players in round-robin position order with strictly
    decreasing published values, so every (position, role) group ends up
    with a positive native pool under the 12-team complete roster."""
    counts = {"QB": 20, "RB": 70, "WR": 90, "TE": 40}
    queues = {pos: [f"{pos}-{i}" for i in range(n)] for pos, n in counts.items()}
    order = []
    while any(queues.values()):
        for pos in ("QB", "RB", "WR", "TE"):
            if queues[pos]:
                order.append((pos, queues[pos].pop(0)))
    values = {}
    key = 90001
    for rank, (pos, _tag) in enumerate(order):
        values[str(key)] = [pos, 1000.0 - rank * 0.5 + seed_offset]
        key += 1
    return values


def _group_vorps_artifact() -> dict:
    return {
        "teams": 12,
        "scoring": "half_ppr",
        "units": "raw_surplus_ppg",
        "roster": {
            "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1},
            "flex_count": 1,
            "flex_eligible": ["RB", "WR", "TE"],
            "bench_mix": {"QB": 12, "RB": 24, "WR": 24, "TE": 12},
        },
        "groups": [
            {"position": p, "role": r, "total_vorp": GROUP_TARGETS[(p, r)]}
            for p, r in [("QB", "starter"), ("QB", "bench"), ("RB", "starter"),
                         ("RB", "bench"), ("WR", "starter"), ("WR", "bench"),
                         ("TE", "starter"), ("TE", "bench")]
        ],
    }


def _build_candidate(tmp: Path):
    """Run the real producers; return (candidate_path, batch_path)."""
    (tmp / "values_fc.json").write_text(json.dumps(_synthetic_values(tmp)))
    (tmp / "values_usat.json").write_text(json.dumps(_synthetic_values(tmp, 37.0)))
    (tmp / "group_vorps.json").write_text(json.dumps(_group_vorps_artifact()))
    (tmp / "roster.json").write_text(json.dumps(ROSTER))
    for src, vals in (("fantasycalc", "values_fc.json"), ("usat", "values_usat.json")):
        out = tmp / f"imputed_{src}.json"
        rc = impute_main(["--values", str(tmp / vals),
                          "--group-vorps", str(tmp / "group_vorps.json"),
                          "--roster-config", str(tmp / "roster.json"),
                          "--out", str(out)])
        assert rc == 0, f"imputation failed for {src}"
    batch = {
        "schema": "vorp-source-batch-v1",
        "configuration": ROSTER,
        "sources": {
            src: {"values": f"imputed_{src}.json",
                  "manifest": f"imputed_{src}.json.manifest.json"}
            for src in SOURCES
        },
        "excluded_sources": EXCLUDED,
    }
    batch_path = tmp / "batch.json"
    batch_path.write_text(json.dumps(batch, indent=2, sort_keys=True))
    (tmp / "controls.json").write_text(json.dumps(CONTROLS))
    candidate_path = tmp / "candidate.json"
    rc = reweight_main(["--batch", str(batch_path),
                        "--controls", str(tmp / "controls.json"),
                        "--out", str(candidate_path)])
    assert rc == 0, "reweight failed"
    return candidate_path, batch_path


def _run_review(*args) -> tuple[int, str]:
    buf_out, buf_err = io.StringIO(), io.StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        code = review_main([str(a) for a in args])
    return code, buf_out.getvalue() + buf_err.getvalue()


class TestReviewBatch70Views(unittest.TestCase):
    def test_real_producer_candidate_passes_with_batch_admission(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            candidate, batch = _build_candidate(tmp)
            code, out = _run_review("--artifact", candidate, "--batch", batch)
            self.assertEqual(code, 0, f"review should pass:\n{out}")
            self.assertIn("REVIEW PASSED", out)
            self.assertIn("gate 8/8 batch admission: OK", out)

    def test_review_without_batch_skips_admission_but_passes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            candidate, _ = _build_candidate(tmp)
            code, out = _run_review("--artifact", candidate)
            self.assertEqual(code, 0, f"review should pass:\n{out}")
            self.assertIn("SKIPPED", out)

    def test_tampered_batch_fails_hash_admission(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            candidate, batch = _build_candidate(tmp)
            # Tamper: rewrite the batch with a modified exclusion reason.
            doc = json.loads(batch.read_text())
            doc["excluded_sources"]["cbs"] = "tampered"
            batch.write_text(json.dumps(doc, indent=2, sort_keys=True))
            code, out = _run_review("--artifact", candidate, "--batch", batch)
            self.assertEqual(code, 1, "tampered batch must fail hash admission")
            self.assertIn("batch_sha256", out)

    def test_missing_manifest_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            candidate, _ = _build_candidate(tmp)
            doc = json.loads(candidate.read_text())
            del doc["manifest"]
            bad = tmp / "no_manifest.json"
            bad.write_text(json.dumps(doc))
            code, out = _run_review("--artifact", bad)
            self.assertEqual(code, 1, "manifest-less artifact must fail")
            self.assertIn("manifest", out.lower())

    def test_non_candidate_status_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            candidate, _ = _build_candidate(tmp)
            doc = json.loads(candidate.read_text())
            doc["artifact_status"] = "reviewed"
            bad = tmp / "reviewed.json"
            bad.write_text(json.dumps(doc))
            code, out = _run_review("--artifact", bad)
            self.assertEqual(code, 1, "non-candidate status must fail this review")
            self.assertIn("candidate", out)

    def test_legacy_per_source_70_scaling_fails_conservation(self):
        """The old method scaled each source to peak 70 independently, which
        destroys the common budget. The review must reject that signature."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            candidate, _ = _build_candidate(tmp)
            doc = json.loads(candidate.read_text())
            for views in doc["sources"].values():
                adj = views["adj_values"]
                peak = max(adj.values())
                # Legacy signature: every source independently peaks at 70.
                views["adj_values"] = {k: v / peak * 70.0 for k, v in adj.items()}
            bad = tmp / "legacy_scaled.json"
            bad.write_text(json.dumps(doc))
            code, out = _run_review("--artifact", bad)
            self.assertEqual(code, 1, "legacy per-source 70 scaling must fail")
            self.assertIn("total_budget_per_source", out)

    def test_unexcluded_unknown_source_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            candidate, _ = _build_candidate(tmp)
            doc = json.loads(candidate.read_text())
            first = next(iter(doc["sources"].values()))
            doc["sources"]["mystery"] = copy.deepcopy(first)
            bad = tmp / "mystery.json"
            bad.write_text(json.dumps(doc))
            code, out = _run_review("--artifact", bad)
            self.assertEqual(code, 1, "unknown non-excluded source must fail")

    def test_sidecar_artifact_mismatch_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            candidate, batch = _build_candidate(tmp)
            # Rewrite one imputation artifact after the batch pinned it.
            target = tmp / "imputed_fantasycalc.json"
            doc = json.loads(target.read_text())
            first_key = next(iter(doc))
            doc[first_key]["imputed_vorp"] = doc[first_key]["imputed_vorp"] + 1.0
            target.write_text(json.dumps(doc, indent=2, sort_keys=True))
            code, out = _run_review("--artifact", candidate, "--batch", batch)
            self.assertEqual(code, 1, "substituted source artifact must fail")
            self.assertIn("hash", out.lower())

    def test_candidate_conserves_budget_and_peaks_at_70(self):
        """Independent re-derivation of the producer's two core invariants."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            candidate, _ = _build_candidate(tmp)
            doc = json.loads(candidate.read_text())
            scale = doc["total_budget_per_source"]
            for name, views in doc["sources"].items():
                total = math.fsum(views["adj_values"].values())
                self.assertTrue(
                    math.isclose(total, scale, rel_tol=1e-9, abs_tol=1e-9),
                    f"{name}: adj sum {total} != budget {scale}",
                )
            peak = max(v for views in doc["sources"].values()
                       for v in views["adj_values"].values())
            self.assertTrue(math.isclose(peak, 70.0, rel_tol=1e-9, abs_tol=1e-9),
                            f"global peak {peak} != 70")


    def test_granular_empty_indexed_is_the_contract(self):
        """Granular sources carry no as-published natives, so an EMPTY indexed
        map passes the view gate (vorp/adj keep identical key sets)."""
        doc = {
            "sources": {
                "espn": {
                    "indexed": {},
                    "vorp": {"90001": 40.0, "90002": 12.0},
                    "adj_values": {"90001": 70.0, "90002": 0.0},
                }
            }
        }
        maxima = check_views(doc, 70.0)
        self.assertIn("espn", maxima)

    def test_granular_nonempty_indexed_fails(self):
        """A granular source WITH an indexed map is wrong-kind wiring, not
        data: the gate must reject it (discrimination proven)."""
        doc = {
            "sources": {
                "espn": {
                    "indexed": {"90001": 9914.0},
                    "vorp": {"90001": 40.0, "90002": 12.0},
                    "adj_values": {"90001": 70.0, "90002": 0.0},
                }
            }
        }
        with self.assertRaises(GateFailure):
            check_views(doc, 70.0)

    def test_published_empty_indexed_fails(self):
        """A published source with an empty indexed map is a wiring gap, not
        a design choice: the gate must reject it."""
        doc = {
            "sources": {
                "fantasycalc": {
                    "indexed": {},
                    "vorp": {"90001": 40.0, "90002": 12.0},
                    "adj_values": {"90001": 70.0, "90002": 0.0},
                }
            }
        }
        with self.assertRaises(GateFailure):
            check_views(doc, 70.0)


if __name__ == "__main__":
    unittest.main()
