"""JEG-242: copied-dashboard preview keeps numerical three-view parity.

The parent defect class: producers exist but nothing invokes them end to
end. The preview (pipelines/preview_vorp_views.py) is the last autonomous
integration item: it loads a REVIEWED candidate into a COPIED dashboard and
must prove, per view, that what the preview serves is numerically identical
to what the candidate carries.

Positive (must pass):
  - refresh (explicit test controls) -> preview builds the copied dashboard,
    and per-view display maps hold parity:
      indexed = native * 70 / provisional_maximum (one common all-source
      peak), re-derived independently; vorp/adj_values are the candidate maps
      verbatim; a genuine 0.0 native survives into every view map; absent
      keys stay absent; the granular source's Indexed view is unavailable
      WITH an explicit reason (never silent).
  - the node parity script (preview/check_preview_parity.js) agrees with the
    Python derivation on the same payload (two-language agreement).
  - Makefile names the preview target and this module is in test-unit.

Negative regressions (each must FAIL the broken state):
  - a tampered candidate (one adj value changed) is rejected by the review
    gate: the preview aborts nonzero and writes NO preview dir.
  - natives that no longer match the candidate's stored indexed map (a
    per-source-peaked or tampered native map) abort the preview.
  - an unknown source smuggled into the candidate aborts the preview.
"""

import io
import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
import sys  # noqa: E402

sys.path.insert(0, str(REPO / "pipelines"))

from preview_vorp_views import build_preview  # noqa: E402
from refresh_vorp_views import main as refresh_main  # noqa: E402

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

ZERO_KEY = "90007"  # a genuine 0.0 native in the published fixture


def _synthetic_values(seed_offset=0.0, zero_key=None):
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
    if zero_key is not None:
        values[zero_key][1] = 0.0
    return values


def _group_vorps_artifact():
    return {
        "teams": 12, "scoring": "half_ppr", "units": "raw_surplus_ppg",
        "roster": {
            "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1},
            "flex_count": 1, "flex_eligible": ["RB", "WR", "TE"],
            "bench_mix": {"QB": 12, "RB": 24, "WR": 24, "TE": 12},
        },
        "groups": [
            {"position": p, "role": r, "total_vorp": GROUP_TARGETS[(p, r)]}
            for p, r in [("QB", "starter"), ("QB", "bench"), ("RB", "starter"),
                         ("RB", "bench"), ("WR", "starter"), ("WR", "bench"),
                         ("TE", "starter"), ("TE", "bench")]
        ],
    }


def _granular_artifact(seed_offset=0.0):
    """Small granular (ppg-above-waiver) artifact for the espn source."""
    pool = {}
    key = 80001
    for i, (pos, vorp) in enumerate(
        [("QB", 40.0), ("QB", 12.0), ("RB", 90.0), ("RB", 25.0),
         ("WR", 80.0), ("WR", 30.0), ("TE", 20.0), ("TE", 5.0)]
    ):
        role = "starter" if i % 2 == 0 else "bench"
        pool[str(key)] = {"group": f"{pos}|{role}",
                          "imputed_vorp": vorp + seed_offset}
        key += 1
    values_bytes = json.dumps(pool, sort_keys=True).encode()
    manifest = {
        "schema": "granular-vorp-manifest-v1",
        "method": "ppg-above-waiver-v1",
        "output_sha256": __import__("hashlib").sha256(values_bytes).hexdigest(),
        "source_config": {
            "schema": "granular-roster-config-v1",
            "teams": 12,
            "scoring": "half_ppr",
            "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1},
            "flex_count": 1,
            "flex_eligible": ["RB", "WR", "TE"],
            "bench_mix": {"QB": 12, "RB": 24, "WR": 24, "TE": 12},
        },
    }
    return values_bytes, json.dumps(manifest, sort_keys=True).encode()


def _fixture(tmp: Path):
    values_dir = tmp / "values"
    values_dir.mkdir()
    (values_dir / "fantasycalc.json").write_text(
        json.dumps(_synthetic_values(zero_key=ZERO_KEY)))
    (values_dir / "usat.json").write_text(
        json.dumps(_synthetic_values(37.0, zero_key=ZERO_KEY)))
    granular_dir = tmp / "granular"
    granular_dir.mkdir()
    vals, manifest = _granular_artifact()
    (granular_dir / "espn.json").write_bytes(vals)
    (granular_dir / "espn.json.manifest.json").write_bytes(manifest)
    (tmp / "group_vorps.json").write_text(json.dumps(_group_vorps_artifact()))
    (tmp / "roster.json").write_text(json.dumps(ROSTER))
    (tmp / "controls.json").write_text(json.dumps(CONTROLS))
    args = [
        "--values-dir", str(values_dir),
        "--group-vorps", str(tmp / "group_vorps.json"),
        "--roster-config", str(tmp / "roster.json"),
        "--granular-dir", str(granular_dir),
        "--controls", str(tmp / "controls.json"),
        "--out-dir", str(tmp / "out"),
    ]
    return args, tmp / "out"


def _run_refresh(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = refresh_main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue() + err.getvalue()


def _run_preview(candidate, batch, out_dir):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = build_preview(Path(candidate), Path(batch), Path(out_dir))
    return code, out.getvalue() + err.getvalue()


class VorpViewsPreviewTests(unittest.TestCase):
    def test_preview_builds_copied_dashboard_with_three_view_parity(self):
        """Refresh -> reviewed candidate -> copied preview; per-view maps hold
        numerical parity (indexed = native*70/common peak; vorp/adj verbatim;
        genuine zero kept; absent stays absent; granular Indexed unavailable
        with reason)."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            argv, out = _fixture(tmp)
            code, log = _run_refresh(argv)
            self.assertEqual(code, 0, f"refresh failed:\n{log}")
            candidate, batch = out / "candidate.json", out / "work" / "batch.json"
            preview_dir = tmp / "preview"
            code, log = _run_preview(candidate, batch, preview_dir)
            self.assertEqual(code, 0, f"preview failed:\n{log}")

            dash = preview_dir / "preview-dashboard"
            self.assertTrue((dash / "index.html").is_file(),
                            "preview must be a copied dashboard")
            payload = json.loads(
                (dash / "assets" / "vorp-views-preview.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "vorp-views-preview-v1")
            self.assertTrue((preview_dir / "preview.manifest.json").is_file())

            cand = json.loads(candidate.read_text(encoding="utf-8"))
            peak = cand["provisional_maximum"]
            views = payload["views"]
            for src in ("fantasycalc", "usat"):
                for view in ("indexed", "vorp", "adj_values"):
                    self.assertEqual(
                        set(views[view][src]), set(cand["sources"][src][view]),
                        f"{src}.{view}: key-set drift vs candidate")
                for k, v in views["indexed"][src].items():
                    expected = payload["native_maps"][src][k] * 70.0 / peak
                    self.assertAlmostEqual(v, expected, delta=1e-9 * max(1.0, expected),
                                           msg=f"{src} indexed[{k}] not native*70/peak")
                for view in ("vorp", "adj_values"):
                    self.assertEqual(views[view][src], cand["sources"][src][view],
                                     f"{src}.{view}: not the candidate map verbatim")
                # Genuine zero survives in every view; a never-present key is absent.
                for view in ("indexed", "vorp", "adj_values"):
                    self.assertIn(ZERO_KEY, views[view][src],
                                  f"{src}.{view}: genuine zero dropped")
                    self.assertEqual(views[view][src][ZERO_KEY], 0.0)
                self.assertNotIn("1", views["vorp"][src])

            # Granular and derived AVG sources: Indexed unavailable WITH
            # explicit reason; VORP/Adjusted remain fully populated.
            for src in ("espn", "avg"):
                indexed = views["indexed"][src]
                self.assertIn("unavailable", indexed)
                self.assertGreater(len(indexed["unavailable"]), 10)
                self.assertIn(src, payload["exclusions"])
                self.assertTrue(views["vorp"][src])
                self.assertEqual(
                    set(views["vorp"][src]),
                    set(views["adj_values"][src]),
                )

            # Second-language agreement: node re-derives the same maps.
            node = subprocess.run(
                ["node", str(REPO / "preview" / "check_preview_parity.js"),
                 str(dash / "assets" / "vorp-views-preview.json")],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(node.returncode, 0,
                             f"node parity check failed:\n{node.stdout}\n{node.stderr}")

    def test_tampered_candidate_rejected_no_preview_written(self):
        """One changed adj value fails the review gate; the preview aborts
        nonzero and writes no preview dir."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            argv, out = _fixture(tmp)
            code, log = _run_refresh(argv)
            self.assertEqual(code, 0, f"refresh failed:\n{log}")
            cand = json.loads((out / "candidate.json").read_text(encoding="utf-8"))
            src = "fantasycalc"
            k = next(iter(cand["sources"][src]["adj_values"]))
            cand["sources"][src]["adj_values"][k] += 1.0
            tampered = tmp / "tampered.json"
            tampered.write_text(json.dumps(cand))
            preview_dir = tmp / "preview"
            code, log = _run_preview(tampered, out / "work" / "batch.json", preview_dir)
            self.assertNotEqual(code, 0, "tampered candidate must abort the preview")
            self.assertFalse(preview_dir.exists(),
                             "no preview dir may exist after a gate failure")

    def test_mismatched_natives_rejected(self):
        """Batch natives that no longer match the candidate's stored indexed
        map (per-source-peaked or tampered natives) abort the preview."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            argv, out = _fixture(tmp)
            code, log = _run_refresh(argv)
            self.assertEqual(code, 0, f"refresh failed:\n{log}")
            batch = json.loads((out / "work" / "batch.json").read_text(encoding="utf-8"))
            src = "fantasycalc"
            entry = batch["sources"][src]
            vals_path = out / "work" / entry["values"]
            pool = json.loads(vals_path.read_text(encoding="utf-8"))
            k = next(iter(pool))
            pool[k]["native"] = pool[k]["native"] * 1.5  # legacy per-source-peak signature
            vals_path.write_text(json.dumps(pool, sort_keys=True))
            meta = json.loads((out / "work" / entry["manifest"]).read_text(encoding="utf-8"))
            meta["output_sha256"] = __import__("hashlib").sha256(
                vals_path.read_bytes()).hexdigest()
            (out / "work" / entry["manifest"]).write_text(json.dumps(meta, sort_keys=True))
            preview_dir = tmp / "preview"
            code, log = _run_preview(out / "candidate.json", out / "work" / "batch.json",
                                     preview_dir)
            self.assertNotEqual(code, 0, "mismatched natives must abort the preview")

    def test_unknown_source_rejected(self):
        """A source outside SOURCE_KINDS smuggled into the candidate aborts."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            argv, out = _fixture(tmp)
            code, log = _run_refresh(argv)
            self.assertEqual(code, 0, f"refresh failed:\n{log}")
            cand = json.loads((out / "candidate.json").read_text(encoding="utf-8"))
            other = "fantasycalc"
            cand["sources"]["bogus"] = cand["sources"][other]
            tampered = tmp / "bogus.json"
            tampered.write_text(json.dumps(cand))
            code, log = _run_preview(tampered, out / "work" / "batch.json", tmp / "preview")
            self.assertNotEqual(code, 0, "unknown source must abort the preview")

    def test_makefile_names_preview_and_registers_tests(self):
        """The preview target exists and this module is a required check, so a
        future unwired state fails the gate instead of skipping it."""
        makefile = (REPO / "Makefile").read_text(encoding="utf-8")
        self.assertIn("preview-vorp-views:", makefile)
        self.assertIn("tests.test_vorp_views_preview", makefile)


if __name__ == "__main__":
    unittest.main()
