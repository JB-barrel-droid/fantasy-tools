"""Unit tests for pipelines/build_e2e_fidelity.py (JEG-77).

The builder imports check_freshness / check_fidelity from check_source_fidelity
without duplicating logic. These tests verify:
  - The builder calls the imported functions (no parallel logic).
  - The output JSON shape matches what the dashboard card expects.
  - Per-source status aggregation (worst-of-freshness-and-fidelity) is right.
  - Missing fixture fails closed.
  - A stale fixture correctly surfaces a freshness_stale failure.
  - A flipped fixture (native vs reindexed pairs out of order) surfaces a
    fidelity_flip failure.
All fixture-driven, no network, no Supabase, no live publisher hits.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_e2e_fidelity as builder  # noqa: E402
import check_source_fidelity as csf  # noqa: E402


def _now_minus(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _fixture_with(
    sources: dict | None = None,
    fetched_at: str | None = None,
    content_vintage: str = "Week 4",
    combos: dict | None = None,
) -> dict:
    """Helper: build a fixture matching check_source_fidelity's expectations.

    sources: dict of {src: {}}, fetched_at: ISO timestamp string applied to every
    provided source, combos: per-source fixture combos (otherwise empty).
    """
    sources = sources or {"fantasycalc": {}, "usatoday": {}, "fantasypros": {}, "cbs": {}}
    out = {"sources": {}}
    for src in sources:
        src_block: dict = {"content_vintage": content_vintage}
        if fetched_at is not None:
            src_block["fetched_at"] = fetched_at
        src_block["combos"] = combos or {}
        out["sources"][src] = src_block
    return out


class StatusAggregationTest(unittest.TestCase):
    """The per-source status must be the worst of freshness + fidelity."""

    def test_no_failures_yields_ok(self):
        # Fresh today → freshness OK; no fidelity pairs → no fidelity failures.
        fx = _fixture_with(fetched_at=_now_minus(0))
        # Drive with the temp fixture (the builder fail-closes on missing
        # fixture files, so no stray build() call belongs here).
        with tempfile.TemporaryDirectory() as td:
            fx_path = Path(td) / "fx.json"
            fx_path.write_text(json.dumps(fx))
            payload = builder.build(fx_path, 2.0)
        for src, s in payload["sources"].items():
            self.assertEqual(s["freshness"]["status"], "ok", src)
            self.assertEqual(s["fidelity"]["status"], "ok", src)
            self.assertEqual(s["status"], "ok", src)
            self.assertEqual(s["n_failures"], 0, src)
        self.assertEqual(payload["summary"]["status"], "ok")
        self.assertEqual(payload["summary"]["n_failures"], 0)

    def test_stale_yields_warn(self):
        # Fetched 5 days ago → freshness_stale → warn, no fidelity → status warn.
        fx = _fixture_with(fetched_at=_now_minus(5))
        with tempfile.TemporaryDirectory() as td:
            fx_path = Path(td) / "fx.json"
            fx_path.write_text(json.dumps(fx))
            payload = builder.build(fx_path, 2.0)
        for src, s in payload["sources"].items():
            self.assertEqual(s["freshness"]["status"], "warn", src)
            self.assertEqual(s["status"], "warn", src)
            self.assertGreater(s["n_failures"], 0, src)
        self.assertEqual(payload["summary"]["status"], "warn")

    def test_no_fetched_at_yields_unk(self):
        # No fetched_at → freshness_unknown → unk. Drives status to unk.
        fx = _fixture_with(fetched_at=None)
        with tempfile.TemporaryDirectory() as td:
            fx_path = Path(td) / "fx.json"
            fx_path.write_text(json.dumps(fx))
            payload = builder.build(fx_path, 2.0)
        for src, s in payload["sources"].items():
            self.assertEqual(s["freshness"]["status"], "unk", src)
            self.assertEqual(s["status"], "unk", src)
            self.assertEqual(s["n_failures"], 1, src)
        self.assertEqual(payload["summary"]["status"], "unk")

    def test_missing_source_in_fixture_yields_unk(self):
        # The fixture exists but is missing every source. Fail-closed: the
        # builder emits a freshness_unknown entry per missing source (never a
        # silent empty payload that would read as "all clean").
        fx = {"sources": {}}
        with tempfile.TemporaryDirectory() as td:
            fx_path = Path(td) / "fx.json"
            fx_path.write_text(json.dumps(fx))
            payload = builder.build(fx_path, 2.0)
        self.assertEqual(set(payload["sources"].keys()),
                         {"fantasycalc", "usatoday", "fantasypros", "cbs"})
        for src, s in payload["sources"].items():
            self.assertEqual(s["freshness"]["status"], "unk", src)
            self.assertEqual(s["status"], "unk", src)
            self.assertEqual(s["n_failures"], 1, src)
            self.assertEqual(s["freshness"]["failures"][0]["type"],
                             "freshness_unknown", src)
        self.assertEqual(payload["summary"]["n_failures"], 4)
        self.assertEqual(payload["summary"]["status"], "unk")


class ShapeContractTest(unittest.TestCase):
    """The dashboard card depends on this exact JSON shape."""

    def test_required_top_level_keys(self):
        fx = _fixture_with(fetched_at=_now_minus(0))
        with tempfile.TemporaryDirectory() as td:
            fx_path = Path(td) / "fx.json"
            fx_path.write_text(json.dumps(fx))
            payload = builder.build(fx_path, 2.0)
        for k in ("generated_at", "max_age_days", "sources", "summary"):
            self.assertIn(k, payload, f"payload missing top-level key {k!r}")
        self.assertIsInstance(payload["generated_at"], str)
        # generated_at must parse as ISO
        datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00"))
        for k in ("n_sources", "n_failures", "status"):
            self.assertIn(k, payload["summary"], f"summary missing key {k!r}")

    def test_source_keys_are_csf_sources(self):
        fx = _fixture_with()
        with tempfile.TemporaryDirectory() as td:
            fx_path = Path(td) / "fx.json"
            fx_path.write_text(json.dumps(fx))
            payload = builder.build(fx_path, 2.0)
        self.assertEqual(set(payload["sources"].keys()), set(csf.SOURCES))

    def test_per_source_shape(self):
        fx = _fixture_with(fetched_at=_now_minus(1.0))
        with tempfile.TemporaryDirectory() as td:
            fx_path = Path(td) / "fx.json"
            fx_path.write_text(json.dumps(fx))
            payload = builder.build(fx_path, 2.0)
        for src, s in payload["sources"].items():
            for k in ("label", "fetched_at", "content_vintage",
                      "freshness", "fidelity", "n_failures", "status"):
                self.assertIn(k, s, f"{src} missing key {k!r}")
            self.assertIn("status", s["freshness"])
            self.assertIn("failures", s["freshness"])
            self.assertIsInstance(s["freshness"]["failures"], list)
            self.assertIn("status", s["fidelity"])
            self.assertIn("failures", s["fidelity"])
            self.assertIsInstance(s["fidelity"]["failures"], list)


class FailClosedTest(unittest.TestCase):
    """The builder must refuse to fabricate a payload from a missing fixture."""

    def test_missing_fixture_raises(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "nope.json"
            with self.assertRaises(FileNotFoundError):
                builder.build(missing, 2.0)


class ImportsNotDuplicatesTest(unittest.TestCase):
    """The whole point of the JEG-77 contract: NO parallel logic."""

    def test_builder_uses_csf_functions(self):
        """build() must call csf.check_freshness and csf.check_fidelity,
        not reimplement them. We assert the builder module imports them
        by name, and that calling build() drives the same code path."""
        # Import-level check: the names are present in the builder's namespace.
        self.assertTrue(hasattr(builder, "csf"), "builder lost its csf import")
        self.assertIs(builder.csf, csf)

        # Functional check: drive a synthetic fidelity flip and verify the
        # builder surfaces it as a fidelity_flip failure. This is only
        # possible if the imported check_fidelity ran.
        flip_combo = "half_12"
        # Construct a combo whose native ordering matches the published pair
        # (JSN > Puka, JSN > Jefferson, Amon-Ra > Puka per usatoday) but whose
        # reindexed ordering swaps them — that's a fidelity flip.
        flip_combos = {
            flip_combo: {
                # Slug shape must match the real fixture's native keys
                # ("jaxon smithnjigba", not the spaced label form) — that is
                # what check_fidelity's FIDELITY_PAIRS fragments match via
                # find_slug. A spaced slug silently skips the pair.
                "native": {
                    "jaxon smithnjigba": 73.0,
                    "puka nacua": 62.0,
                    "justin jefferson": 50.0,
                    "amonra st brown": 67.0,
                },
                "reindexed": {
                    # Swap: lower players now higher in reindexed (flip).
                    "puka nacua": 73.0,
                    "jaxon smithnjigba": 62.0,
                    "justin jefferson": 67.0,
                    "amonra st brown": 50.0,
                },
            }
        }
        # _fixture_with applies the same per-source combos to every source,
        # so pass flip_combos directly (not wrapped per-source).
        fx = _fixture_with(
            fetched_at=_now_minus(0),
            combos=flip_combos,
        )
        with tempfile.TemporaryDirectory() as td:
            fx_path = Path(td) / "fx.json"
            fx_path.write_text(json.dumps(fx))
            payload = builder.build(fx_path, 2.0)
        usatoday = payload["sources"]["usatoday"]
        flip_failures = [f for f in usatoday["fidelity"]["failures"]
                         if f.get("type") == "fidelity_flip"]
        self.assertGreater(len(flip_failures), 0,
                           "expected at least one fidelity_flip failure for the "
                           "synthetic swap; builder did not run imported check_fidelity")
        self.assertEqual(usatoday["fidelity"]["status"], "bad")
        self.assertEqual(usatoday["status"], "bad")

    def test_no_local_reimplementation_of_check_functions(self):
        """Grep-style guard: the builder must not reimplement check_freshness
        or check_fidelity with its own copies of FIDELITY_PAIRS / parsing."""
        src = (ROOT / "pipelines" / "build_e2e_fidelity.py").read_text()
        # Forbidden local reimplementations.
        self.assertNotIn("FIDELITY_PAIRS", src,
                         "builder defines its own FIDELITY_PAIRS — should import")
        self.assertNotIn("def check_freshness(", src,
                         "builder defines its own check_freshness — should import")
        self.assertNotIn("def check_fidelity(", src,
                         "builder defines its own check_fidelity — should import")
        # Required wiring.
        self.assertIn("check_freshness", src,
                      "builder never calls check_freshness")
        self.assertIn("check_fidelity", src,
                      "builder never calls check_fidelity")


class WriteOutputTest(unittest.TestCase):
    """CLI: --out writes the JSON file."""

    def test_main_writes_out(self):
        fx = _fixture_with(fetched_at=_now_minus(0))
        with tempfile.TemporaryDirectory() as td:
            fx_path = Path(td) / "fx.json"
            fx_path.write_text(json.dumps(fx))
            out_path = Path(td) / "out.json"
            rc = builder.main([
                "--out", str(out_path),
                "--fixture", str(fx_path),
                "--max-age-days", "2.0",
            ])
            self.assertEqual(rc, 0)
            self.assertTrue(out_path.exists())
            written = json.loads(out_path.read_text())
            self.assertIn("generated_at", written)
            self.assertIn("sources", written)
            self.assertEqual(set(written["sources"].keys()), set(csf.SOURCES))


if __name__ == "__main__":
    unittest.main()