#!/usr/bin/env python3
"""Tests for JEG-132 R5b -- the input-lineage mismatch checker.

Regression-guard states per the brief:

    A. derived section with NO `lineage` block              -> exit non-zero
    B. adjusted section claims raw_vintage Week 3, current raw is Week 4
                                                              -> exit non-zero
    C. CBS ROS case: leg rebuilt from Week 4 raw, section lineage claims Week 3
                                                              -> exit non-zero
    D. lineage.raw_content_sha256 does not match the recomputed sha
                                                              -> exit non-zero

Each test must FAIL on the base commit (no checker, no blocks) and PASS after
the checker is implemented. Sandbox blocks test execution: py_compile only.

CLI surface contract:
  - python3 pipelines/check_input_lineage.py [--fixture PATH]
  - writes output/input-lineage.json with shape
    {"generated_at": str, "mismatches": [{section, reason, claimed?, actual?}],
     "checked": int}
  - exit 0 = pass, exit 1 = at least one named mismatch (never silent)
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPELINES = ROOT / "pipelines"
LIB = PIPELINES / "lib"

# Make lib importable regardless of how the test is invoked.
for p in (str(PIPELINES), str(LIB)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.lineage_block import (  # noqa: E402
    compute_raw_sha,
    collect_fixture_section_triples,
    collect_leg_triples,
    resolve_raw_vintage,
    build_lineage_block,
)


POSITIONS = ("QB", "RB", "WR", "TE")


def _make_players(n_per_pos: int = 4):
    players = []
    fkeys: dict = {}
    key_to_pos: dict = {}
    slug_to_pos: dict = {}
    for i, pos in enumerate(POSITIONS):
        for j in range(n_per_pos):
            key = 9000 + i * 100 + j
            slug = f"player {pos.lower()}{j}"
            players.append({"name": f"Player {pos}{j}", "pos": pos, "player_key": key})
            fkeys[slug] = key
            key_to_pos[key] = pos
            slug_to_pos[slug] = pos
    return players, fkeys, key_to_pos, slug_to_pos


def _make_raw_fixture_section(*, fkeys, slug_to_pos, base_value: float = 50.0,
                              vintage: str = "Week 4",
                              built_at: str = "2026-10-02T00:00:00Z",
                              content_vintage: str | None = None) -> dict:
    """Raw fixture section shaped like one entry of sources{}."""
    combos = {}
    for combo in ("full_12", "half_12", "standard_12"):
        native = {slug: base_value + i * 0.1 for i, slug in enumerate(fkeys)}
        reindexed = {slug: round(v / 10.0, 1) for slug, v in native.items()}
        index_total = {}
        for pos in POSITIONS:
            pos_slugs = [s for s in fkeys if slug_to_pos.get(s) == pos]
            target = round(sum(reindexed[s] for s in pos_slugs), 1)
            index_total[pos] = {"target_total": target, "n_priced": len(pos_slugs)}
        combos[combo] = {
            "native": native,
            "reindexed": reindexed,
            "player_keys": dict(fkeys),
            "n": len(fkeys),
            "index_total": index_total,
        }
    section = {
        "name": "Synthetic raw source",
        "kind": "test fixture raw",
        "fetched_at": "2026-10-02T00:00:00Z",
        "combos": combos,
        "vintage": vintage,
        "built_at": built_at,
    }
    if content_vintage is not None:
        section["content_vintage"] = content_vintage
    return section


def _write_fixture_with_raw_and_adjusted(
    tmp: Path, *,
    raw_content_vintage: str = "Week 4",
    raw_built_at: str = "2026-10-02T00:00:00Z",
    adj_lineage: dict | None = None,
    include_lineage_on_raw: bool = False,
    raw_section_factory=None,
) -> tuple[Path, dict]:
    """Write a temp fixture with raw fantasycalc/usatoday/fantasypros/cbs and
    matching _adjusted sections (with optional lineage blocks).

    Returns (fixture_path, players_list). The fixture is shaped like the
    real one so the checker's existing raw/derived mapping works.
    """
    players, fkeys, _, slug_to_pos = _make_players(n_per_pos=4)
    fixture = {
        "built_at": "2026-09-30T00:00:00Z",
        "sources": {},
        "player_keys": fkeys,
    }
    for src in ("fantasycalc", "usatoday", "fantasypros", "cbs"):
        section = (raw_section_factory(src) if raw_section_factory
                   else _make_raw_fixture_section(
                       fkeys=fkeys, slug_to_pos=slug_to_pos,
                       base_value=50.0, vintage="Week 3",
                       built_at="2026-09-30T00:00:00Z",
                       content_vintage=raw_content_vintage,
                   ))
        # raw sections must NOT have a lineage block; optional override for
        # negative tests that assert raw-also-has-lineage is harmless (raw
        # sections are skipped by the verifier; only derived are checked).
        if include_lineage_on_raw:
            section["lineage"] = {"raw_vintage": "x", "raw_content_sha256": "x",
                                  "raw_built_at": "x", "vintage_source": "x"}
        section["name"] = f"Raw {src}"
        fixture["sources"][src] = section
    # NOTE: no espn/cbsros/razzball sections here. In the live fixture those
    # keys are DERIVED (R5a stamps lineage on them), so the checker treats any
    # such key as derived and a lineage-less one is a mismatch. The derived
    # sections under test here are the _adjusted ones; leg-derived sections
    # are covered by the dedicated leg tests below.
    fx_path = tmp / "comparison-sources-data.json"
    fx_path.write_text(json.dumps(fixture))
    # Now stamp _adjusted sections. Default: stamp lineage matching the raw.
    fixture = json.loads(fx_path.read_text())
    if adj_lineage is None:
        # Default: build lineage that DOES match the current raw.
        for src in ("fantasycalc", "usatoday", "fantasypros", "cbs"):
            raw = fixture["sources"][src]
            triples = collect_fixture_section_triples(raw)
            lineage = build_lineage_block(
                triples=triples,
                raw_vintage=resolve_raw_vintage(
                    content_vintage=raw.get("content_vintage"),
                    espn_snapshot=raw.get("espn_snapshot"),
                    vintage=raw.get("vintage"),
                    fetched_at=raw.get("fetched_at"),
                )[0],
                raw_built_at=raw.get("built_at"),
                vintage_source="content_vintage",
            )
            adj = {
                "name": f"{src} adjusted",
                "kind": "test adjusted",
                "combos": {combo: {"reindexed": dict(raw["combos"][combo]["reindexed"])}
                           for combo in raw["combos"]},
                "lineage": lineage,
            }
            fixture["sources"][f"{src}_adjusted"] = adj
    else:
        # Caller-supplied lineage override: stamp the same (possibly stale) lineage
        # on every _adjusted section so the test can focus on a single field.
        for src in ("fantasycalc", "usatoday", "fantasypros", "cbs"):
            raw = fixture["sources"][src]
            adj = {
                "name": f"{src} adjusted",
                "kind": "test adjusted",
                "combos": {combo: {"reindexed": dict(raw["combos"][combo]["reindexed"])}
                           for combo in raw["combos"]},
                "lineage": copy.deepcopy(adj_lineage),
            }
            fixture["sources"][f"{src}_adjusted"] = adj
    fx_path.write_text(json.dumps(fixture))
    return fx_path, players


def _write_ddf_leg(leg_dir: Path, *, bake_id: str, snapshot_date: str,
                   content_vintage: str | None = None, n_rows: int = 6) -> Path:
    """Write a minimal DDF leg file shaped like the CBS-ROS leg."""
    values = [{
        "player_norm": f"player {i}",
        "player_key": 7000 + i,
        "value": round(20.0 + i * 0.5, 2),
        "ppg": round(5.0 + i * 0.1, 3),
    } for i in range(n_rows)]
    leg = {
        "bake_id": bake_id,
        "generated_at": "2026-10-02T12:00:00Z",
        "fetched_at": "2026-10-02T11:55:00Z",
        "values": values,
        "inputs": {
            "scoring": "ppr",
            "teams": 12,
            "cbsros_snapshot_date": snapshot_date,
        },
    }
    if content_vintage is not None:
        leg["inputs"]["content_vintage"] = content_vintage
    leg_dir.mkdir(parents=True, exist_ok=True)
    leg_path = leg_dir / "ddf_leg_cbsros.json"
    leg_path.write_text(json.dumps(leg))
    return leg_path


def _run_checker(fixture_path: Path, *, output_path: Path | None = None,
                 leg_dir: Path | None = None,
                 candidates_dir: Path | None = None,
                 repo_root: Path | None = None) -> tuple[int, str, str, dict | None]:
    """Invoke the checker as a subprocess and return (rc, stdout, stderr, artifact).

    The checker resolves the fixture + leg dirs + output at import-time via
    module-level constants. We patch them through env-symlink: point a temp
    repo at LEG_DIR / fixture / output via paths captured by main().
    """
    if repo_root is None:
        repo_root = ROOT
    # If the caller wants isolated LEG_DIR / output paths, we need the checker
    # to use them. The simplest way is to point REPO at a temp root via
    # monkey-patched module constants.
    import check_input_lineage as cil
    saved_leg = cil.LEG_DIR
    saved_default_fixture = cil.DEFAULT_FIXTURE
    saved_default_output = cil.DEFAULT_OUTPUT
    saved_candidates = cil.CANDIDATES_DIR
    saved_root = cil.ROOT
    try:
        cil.ROOT = repo_root
        cil.DEFAULT_FIXTURE = fixture_path
        cil.DEFAULT_OUTPUT = output_path or (repo_root / "output" / "input-lineage.json")
        cil.LEG_DIR = leg_dir or (repo_root / "data" / "ddf-two-tier")
        cil.CANDIDATES_DIR = candidates_dir or (repo_root / "output" / "comparison-candidates")
        cmd = [sys.executable, str(PIPELINES / "check_input_lineage.py"),
               "--fixture", str(fixture_path),
               "--output", str(output_path or (repo_root / "output" / "input-lineage.json"))]
        # The checker runs in a subprocess: module-constant monkey-patches do
        # NOT propagate, so pass the dirs as CLI args.
        if leg_dir is not None:
            cmd += ["--leg-dir", str(leg_dir)]
        if candidates_dir is not None:
            cmd += ["--candidates-dir", str(candidates_dir)]
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, env={**os.environ, "PYTHONPATH":
                f"{PIPELINES}:{LIB}"},
        )
    finally:
        cil.LEG_DIR = saved_leg
        cil.DEFAULT_FIXTURE = saved_default_fixture
        cil.DEFAULT_OUTPUT = saved_default_output
        cil.CANDIDATES_DIR = saved_candidates
        cil.ROOT = saved_root
    artifact = None
    if (output_path or (repo_root / "output" / "input-lineage.json")).exists():
        try:
            artifact = json.loads((output_path or (repo_root / "output" / "input-lineage.json"))
                                  .read_text())
        except (OSError, ValueError):
            artifact = None
    return result.returncode, result.stdout, result.stderr, artifact


class TestCheckerModule(unittest.TestCase):
    """Module-shape: the checker writes input-lineage.json in the exact shape."""

    def test_script_runs_and_writes_artifact_on_minimal_passing_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            out_path = tmp / "out.json"
            fx_path, _ = _write_fixture_with_raw_and_adjusted(tmp)
            rc, stdout, stderr, artifact = _run_checker(
                fx_path, output_path=out_path,
                leg_dir=tmp / "no-legs",
                candidates_dir=tmp / "no-candidates",
                repo_root=tmp,
            )
            self.assertEqual(rc, 0,
                             f"passing fixture must exit 0; stderr={stderr}; "
                             f"artifact={artifact}")
            self.assertIsNotNone(artifact, "checker must write artifact")
            for key in ("generated_at", "mismatches", "checked"):
                self.assertIn(key, artifact,
                              f"artifact must carry key {key!r}")
            self.assertIsInstance(artifact["mismatches"], list)
            self.assertIsInstance(artifact["checked"], int)

    def test_artifact_shape_exact_keys(self):
        """The monitor surface must have EXACTLY these top-level keys."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            out_path = tmp / "out.json"
            fx_path, _ = _write_fixture_with_raw_and_adjusted(tmp)
            rc, _, _, artifact = _run_checker(
                fx_path, output_path=out_path,
                leg_dir=tmp / "no-legs", candidates_dir=tmp / "no-candidates",
                repo_root=tmp,
            )
            self.assertEqual(rc, 0)
            self.assertEqual(set(artifact.keys()),
                             {"generated_at", "mismatches", "checked"},
                             "Artifact shape must be exactly the R5b contract.")


class TestStateA_MissingLineageBlock(unittest.TestCase):
    """State A: a derived section has NO `lineage` block."""

    def test_adjusted_section_without_lineage_is_named_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            fx_path, _ = _write_fixture_with_raw_and_adjusted(tmp)
            # Strip the lineage off `fantasycalc_adjusted` (and leave the
            # other three alone, so we can assert WHICH sections are named).
            fx = json.loads(fx_path.read_text())
            fx["sources"]["fantasycalc_adjusted"].pop("lineage", None)
            fx_path.write_text(json.dumps(fx))

            out_path = tmp / "out.json"
            rc, _, _, artifact = _run_checker(
                fx_path, output_path=out_path,
                leg_dir=tmp / "no-legs", candidates_dir=tmp / "no-candidates",
                repo_root=tmp,
            )
            self.assertNotEqual(rc, 0,
                                "missing lineage block must be a mismatch (exit 1)")
            names = {m["section"] for m in artifact["mismatches"]}
            self.assertIn("fantasycalc_adjusted", names,
                          "missing-lineage section must be named in mismatches")
            # The other three adjusted sections still carry lineage -> not in mismatch.
            self.assertNotIn("usatoday_adjusted", names)
            self.assertNotIn("fantasypros_adjusted", names)
            self.assertNotIn("cbs_adjusted", names)
            # The named mismatch cites the reason.
            m = next(m for m in artifact["mismatches"]
                     if m["section"] == "fantasycalc_adjusted")
            self.assertEqual(m["reason"], "missing_lineage_block")

    def test_cbsros_section_without_lineage_is_named_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            fx_path, _ = _write_fixture_with_raw_and_adjusted(tmp)
            fx = json.loads(fx_path.read_text())
            # Build a cbsros section (no lineage) and a fresh leg.
            fx["sources"]["cbsros"] = {
                "name": "CBS ROS", "kind": "model projections",
                "combos": {}, "lineage": None,
            }
            fx_path.write_text(json.dumps(fx))
            leg_root = tmp / "legs"
            _write_ddf_leg(leg_root / "ddf-20261002-cbsros-ppr-12t-0p15",
                           bake_id="ddf-20261002-cbsros-ppr-12t-0p15",
                           snapshot_date="2026-10-02",
                           content_vintage="Week 4")

            out_path = tmp / "out.json"
            rc, _, _, artifact = _run_checker(
                fx_path, output_path=out_path,
                leg_dir=leg_root, candidates_dir=tmp / "no-candidates",
                repo_root=tmp,
            )
            self.assertNotEqual(rc, 0)
            names = {m["section"] for m in artifact["mismatches"]}
            self.assertIn("cbsros", names,
                          "cbsros missing lineage must be named in mismatches")


class TestStateB_AdjustedVintageMismatch(unittest.TestCase):
    """State B: adjusted section claims raw_vintage Week 3, current raw is Week 4."""

    def test_adjusted_vintage_mismatch_is_named(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            # Raws are Week 4 (content_vintage=Week 4). Adjusted section's
            # lineage claims raw_vintage=Week 3 -> mismatch.
            stale_lineage = {
                "raw_vintage": "Week 3",  # stale
                "raw_content_sha256": "f" * 64,
                "raw_built_at": "2026-09-30T00:00:00Z",
                "vintage_source": "content_vintage",
            }
            fx_path, _ = _write_fixture_with_raw_and_adjusted(
                tmp, raw_content_vintage="Week 4",
                raw_built_at="2026-10-02T00:00:00Z",
                adj_lineage=stale_lineage,
            )
            out_path = tmp / "out.json"
            rc, _, _, artifact = _run_checker(
                fx_path, output_path=out_path,
                leg_dir=tmp / "no-legs", candidates_dir=tmp / "no-candidates",
                repo_root=tmp,
            )
            self.assertNotEqual(rc, 0, "stale raw_vintage must fail closed")
            names = {m["section"] for m in artifact["mismatches"]}
            self.assertTrue(
                any(n.endswith("_adjusted") for n in names),
                f"at least one _adjusted section must be named; got {names}",
            )
            # At least one of the four must name the raw_vintage mismatch.
            reasons = {(m["section"], m["reason"]) for m in artifact["mismatches"]}
            vintage_mismatches = [s for (s, r) in reasons
                                  if r == "lineage_raw_vintage_mismatch"]
            self.assertEqual(len(vintage_mismatches), 4,
                             f"all four adjusted sections must flag; got {vintage_mismatches}")


class TestStateC_CbsrosRealWorldCase(unittest.TestCase):
    """State C: the real CBS ROS lag incident. Leg is fresh (Week 4), but the
    section's lineage block still says Week 3."""

    def test_cbsros_section_claims_week3_leg_is_week4(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            fx_path, _ = _write_fixture_with_raw_and_adjusted(tmp)
            # Write a Week 4 CBS-ROS leg (freshest).
            leg_root = tmp / "legs"
            leg_path = _write_ddf_leg(
                leg_root / "ddf-20261002-cbsros-ppr-12t-0p15",
                bake_id="ddf-20261002-cbsros-ppr-12t-0p15",
                snapshot_date="2026-10-02",
                content_vintage="Week 4",
            )
            # Stamp the cbsros section with lineage that lies: claims Week 3.
            fx = json.loads(fx_path.read_text())
            leg_doc = json.loads(leg_path.read_text())
            triples = collect_leg_triples(leg_doc)
            correct_sha = compute_raw_sha(triples)
            fx["sources"]["cbsros"] = {
                "name": "CBS ROS", "kind": "model projections",
                "combos": {"full_12": {"values": {}, "native": {}, "n": 0}},
                "lineage": {
                    "raw_vintage": "Week 3",  # wrong!
                    "raw_content_sha256": correct_sha,  # sha matches real leg
                    "raw_built_at": leg_doc["generated_at"],
                    "vintage_source": "content_vintage",
                },
            }
            fx_path.write_text(json.dumps(fx))

            out_path = tmp / "out.json"
            rc, _, _, artifact = _run_checker(
                fx_path, output_path=out_path,
                leg_dir=leg_root, candidates_dir=tmp / "no-candidates",
                repo_root=tmp,
            )
            self.assertNotEqual(rc, 0, "CBS-ROS Week-3-vs-Week-4 lag must fail closed")
            cbsros_mismatches = [m for m in artifact["mismatches"]
                                 if m["section"] == "cbsros"]
            self.assertEqual(len(cbsros_mismatches), 1,
                             "exactly one CBS-ROS mismatch record expected")
            self.assertEqual(cbsros_mismatches[0]["reason"],
                             "lineage_raw_vintage_mismatch")
            self.assertEqual(cbsros_mismatches[0]["claimed"], "Week 3")
            self.assertEqual(cbsros_mismatches[0]["actual"], "Week 4")


class TestStateD_ShaMismatch(unittest.TestCase):
    """State D: lineage.raw_content_sha256 does not match the recomputed sha."""

    def test_adjusted_sha_mismatch_is_named(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            # Write a fixture where _adjusted sections carry the correct
            # raw_vintage / vintage_source but a deliberately wrong sha.
            players, fkeys, _, slug_to_pos = _make_players(n_per_pos=4)
            raw_section = _make_raw_fixture_section(
                fkeys=fkeys, slug_to_pos=slug_to_pos,
                base_value=50.0, vintage="Week 3",
                built_at="2026-09-30T00:00:00Z",
                content_vintage="Week 4",
            )
            # Build a known-correct lineage, then sabotage the sha only.
            triples = collect_fixture_section_triples(raw_section)
            good_sha = compute_raw_sha(triples)
            stale_lineage = {
                "raw_vintage": "Week 4",
                "raw_content_sha256": good_sha,  # start correct
                "raw_built_at": raw_section["built_at"],
                "vintage_source": "content_vintage",
            }
            fx_path, _ = _write_fixture_with_raw_and_adjusted(
                tmp, raw_content_vintage="Week 4",
                raw_built_at=raw_section["built_at"],
                adj_lineage=stale_lineage,
            )
            # Sabotage: overwrite every _adjusted section's sha to a wrong value.
            fx = json.loads(fx_path.read_text())
            for src in ("fantasycalc", "usatoday", "fantasypros", "cbs"):
                key = f"{src}_adjusted"
                fx["sources"][key]["lineage"]["raw_content_sha256"] = "0" * 64
            fx_path.write_text(json.dumps(fx))

            out_path = tmp / "out.json"
            rc, _, _, artifact = _run_checker(
                fx_path, output_path=out_path,
                leg_dir=tmp / "no-legs", candidates_dir=tmp / "no-candidates",
                repo_root=tmp,
            )
            self.assertNotEqual(rc, 0, "wrong sha must fail closed")
            sha_mismatches = [m for m in artifact["mismatches"]
                              if m["reason"] == "lineage_raw_content_sha256_mismatch"]
            self.assertEqual(len(sha_mismatches), 4,
                             f"all four adjusted sections must flag wrong sha; "
                             f"got {sha_mismatches}")
            # The claimed sha is the sabotaged one.
            for m in sha_mismatches:
                self.assertEqual(m["claimed"], "0" * 64)


class TestInvariants(unittest.TestCase):
    """Sanity invariants the R5b brief relies on."""

    def test_artifact_mismatches_have_required_keys(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            fx_path, _ = _write_fixture_with_raw_and_adjusted(tmp)
            fx = json.loads(fx_path.read_text())
            fx["sources"]["fantasycalc_adjusted"].pop("lineage", None)
            fx_path.write_text(json.dumps(fx))

            out_path = tmp / "out.json"
            rc, _, _, artifact = _run_checker(
                fx_path, output_path=out_path,
                leg_dir=tmp / "no-legs", candidates_dir=tmp / "no-candidates",
                repo_root=tmp,
            )
            self.assertNotEqual(rc, 0)
            for m in artifact["mismatches"]:
                self.assertIn("section", m, f"mismatch missing section: {m}")
                self.assertIn("reason", m, f"mismatch missing reason: {m}")

    def test_empty_fixture_with_no_derived_sections_passes(self):
        """If no derived sections exist, exit 0 and `checked` is 0."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, fkeys, _, slug_to_pos = _make_players(n_per_pos=2)
            fixture = {"built_at": "2026-10-02T00:00:00Z",
                       "sources": {}, "player_keys": fkeys}
            fx_path = tmp / "fixture.json"
            fx_path.write_text(json.dumps(fixture))

            out_path = tmp / "out.json"
            rc, _, _, artifact = _run_checker(
                fx_path, output_path=out_path,
                leg_dir=tmp / "no-legs", candidates_dir=tmp / "no-candidates",
                repo_root=tmp,
            )
            self.assertEqual(rc, 0)
            self.assertEqual(artifact["checked"], 0)
            self.assertEqual(artifact["mismatches"], [])


if __name__ == "__main__":
    unittest.main()