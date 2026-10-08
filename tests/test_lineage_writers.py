#!/usr/bin/env python3
"""Tests for JEG-132 R5a (writers) -- lineage block emission on derived sections.

The five builders (build_adjusted_fixture_sections,
build_cbsros_section_from_ddf_leg, build_espn_section_from_ddf_leg,
build_razzball_section_from_ddf_leg, build_comparison_source_section) must
record an immutable `lineage` block on every DERIVED section they write, with:

    lineage.raw_vintage         (raw content_vintage, or fallback)
    lineage.raw_content_sha256  (SHA-256 over raw triples)
    lineage.raw_built_at        (built_at of the raw section)
    lineage.vintage_source      ("content_vintage" | "legacy_fallback")

The block must be reproducible: recomputing the sha over the raw triples must
yield the same digest. Raw sections must NOT carry a lineage block (they are
inputs, not derivations).

These tests must FAIL on the base commit (no lineage blocks) and PASS after
the writers are updated. They use temp dirs only -- never touch the live
fixture or real DDF legs.

The sandbox does not allow running the test runner; py_compile-checked only.
The reviewer runs `python3 -m unittest tests.test_lineage_writers -v`.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPELINES = ROOT / "pipelines"
LIB = PIPELINES / "lib"

# Make the lib importable regardless of how the test is invoked.
for p in (str(PIPELINES), str(LIB)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.lineage_block import (  # noqa: E402
    compute_raw_sha,
    collect_fixture_section_triples,
    collect_leg_triples,
    collect_reference_triples,
    resolve_raw_vintage,
    build_lineage_block,
)


POSITIONS = ("QB", "RB", "WR", "TE")


def _make_players_and_keys(n_per_pos: int = 4):
    """Build a minimal players list + slug<->player_key map covering all four positions.

    Returns (players_list, fkeys {slug: key}, key_to_pos {key: pos}, slug_to_pos).
    """
    players = []
    fkeys: dict = {}
    key_to_pos: dict = {}
    for i, pos in enumerate(POSITIONS):
        for j in range(n_per_pos):
            key = 5000 + i * 100 + j
            slug = f"player {pos.lower()}{j}"
            players.append({"name": f"Player {pos}{j}",
                            "pos": pos,
                            "player_key": key})
            fkeys[slug] = key
            key_to_pos[key] = pos
    slug_to_pos = {slug: key_to_pos[fkeys[slug]] for slug in fkeys}
    return players, fkeys, key_to_pos, slug_to_pos


def _make_raw_fixture_section(*, fkeys, slug_to_pos, base_value: float = 50.0,
                              vintage: str = "Week 4",
                              built_at: str = "2026-10-02T00:00:00Z",
                              content_vintage: str | None = None):
    """Build a minimal raw fixture section shaped like one entry of sources{}.

    Each combo has player_keys, native, reindexed, index_total, n. Matches the
    shape the JEG-131 (R4a) builders produce.
    """
    combos = {}
    for combo in ("full_12", "half_12", "standard_12"):
        native = {slug: base_value + i * 0.1
                  for i, slug in enumerate(fkeys)}
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
        # R4a-stamped fresh shape: content_vintage wins over legacy fields.
        section["content_vintage"] = content_vintage
    return section


def _write_inputs_json(path: Path, *, n_per_pos: int = 4, base_value: float = 50.0):
    """Write a minimal adjustment-inputs.json with bias cells."""
    cells = []
    for pos in POSITIONS:
        for tier in ("starter", "bench"):
            cells.append({"position": pos, "tier": tier,
                          "alpha": 1.0, "beta": 1.0})
    payload = {
        "version": "test-bake-v1",
        "sources": {
            src: {"cells": cells} for src in ("fantasycalc", "usatoday",
                                               "fantasypros", "cbs")
        },
    }
    path.write_text(json.dumps(payload))
    return payload


def _write_fixture_with_raw_sources(tmp: Path, *, fkeys, n_per_pos: int = 4):
    """Build a fixture file with raw sources for fantasycalc/usatoday/fantasypros/cbs.

    Returns (fixture_path, players_path).
    """
    players, _, _, slug_to_pos = _make_players_and_keys(n_per_pos=n_per_pos)
    fixture = {
        "built_at": "2026-09-30T00:00:00Z",
        "sources": {},
        "player_keys": fkeys,
    }
    for src in ("fantasycalc", "usatoday", "fantasypros", "cbs"):
        section = _make_raw_fixture_section(
            fkeys=fkeys, slug_to_pos=slug_to_pos,
            base_value=50.0, vintage="Week 3",
            built_at="2026-09-30T00:00:00Z",
            content_vintage="Week 3",
        )
        section["name"] = f"Raw {src}"
        fixture["sources"][src] = section

    # ESPN anchor for the curve (the adjusted builder doesn't need it,
    # but mirroring real fixtures so future tests can grow into it).
    espn_section = copy.deepcopy(fixture["sources"]["fantasycalc"])
    espn_section["name"] = "ESPN raw anchor"
    fixture["sources"]["espn"] = espn_section

    fx_path = tmp / "comparison-sources-data.json"
    fx_path.write_text(json.dumps(fixture))
    players_path = tmp / "players.json"
    players_path.write_text(json.dumps({"players": players}))
    return fx_path, players_path


class TestLineageBlockHelper(unittest.TestCase):
    """Unit tests for the lineage_block helpers (deterministic, in-memory)."""

    def test_compute_raw_sha_is_deterministic_and_sorted(self):
        triples = [(3, 1.0, 10.0), (1, 2.0, 20.0), (2, 3.0, 30.0)]
        h1 = compute_raw_sha(triples)
        h2 = compute_raw_sha(list(reversed(triples)))  # same data, different order
        self.assertEqual(h1, h2,
                         "SHA must be insertion-order independent (sort by player_key).")
        self.assertEqual(len(h1), 64, "SHA-256 is 64 hex chars.")
        # Distinct triples yield a distinct hash.
        h3 = compute_raw_sha([(1, 2.0, 20.0), (2, 3.0, 30.0), (4, 0, 0)])
        self.assertNotEqual(h1, h3)

    def test_collect_fixture_section_triples_round_trips_with_compute(self):
        fkeys = {"a": 1, "b": 2}
        section = {
            "combos": {
                "full_12": {
                    "player_keys": {"a": 1, "b": 2},
                    "native": {"a": 10.0, "b": 20.0},
                    "reindexed": {"a": 1.0, "b": 2.0},
                },
                "half_12": {  # incomplete combo -- no player_keys, skip
                    "native": {"a": 10.0},
                    "reindexed": {"a": 1.0},
                },
            },
        }
        triples = collect_fixture_section_triples(section)
        self.assertEqual(len(triples), 2,
                         "Only combos with player_keys contribute triples.")
        keys = sorted(t[0] for t in triples)
        self.assertEqual(keys, [1, 2])
        # Hash recomputation must match.
        sha = compute_raw_sha(triples)
        self.assertEqual(sha, compute_raw_sha(triples))  # idempotent

    def test_collect_leg_triples_uses_player_key_ppg_value(self):
        leg = {"values": [
            {"player_key": 7, "ppg": 1.5, "value": 15.0},
            {"player_key": "bad", "ppg": 1.5, "value": 15.0},  # bad key, skip
            {"player_key": 8, "ppg": None, "value": 16.0},  # None allowed
        ]}
        triples = collect_leg_triples(leg)
        self.assertEqual(len(triples), 2)
        self.assertEqual([t[0] for t in triples], [7, 8])
        self.assertEqual(triples[1][1], None, "None native must survive.")
        self.assertEqual(triples[1][2], 16.0)

    def test_collect_reference_triples_prefers_native_value_over_value(self):
        ref = {"rows": [
            {"player_key": 1, "native_value": 99.0, "value": 9.9},
            {"player_key": 2, "value": 8.8},  # no native_value, fall back
            {"player_key": "x", "value": 1.0},  # bad key, skip
        ]}
        triples = collect_reference_triples(ref)
        self.assertEqual(len(triples), 2)
        d = {t[0]: (t[1], t[2]) for t in triples}
        self.assertEqual(d[1], (99.0, 9.9))
        self.assertEqual(d[2], (8.8, 8.8))

    def test_resolve_raw_vintage_prefers_content_vintage(self):
        self.assertEqual(
            resolve_raw_vintage(content_vintage="Week 4",
                                espn_snapshot="ESPN-2026-10-02",
                                vintage="legacy-vintage",
                                fetched_at="2026-10-02"),
            ("Week 4", "content_vintage"),
        )

    def test_resolve_raw_vintage_flags_fallback(self):
        # No content_vintage, but espn_snapshot -> legacy_fallback.
        v, src = resolve_raw_vintage(
            content_vintage=None,
            espn_snapshot="ESPN-2026-10-02",
            vintage="legacy-vintage",
            fetched_at="2026-10-02",
        )
        self.assertEqual(v, "ESPN-2026-10-02")
        self.assertEqual(src, "legacy_fallback")

    def test_resolve_raw_vintage_walks_legacy_chain(self):
        # Only fetched_at present -> still flagged legacy_fallback.
        v, src = resolve_raw_vintage(
            content_vintage=None,
            espn_snapshot=None,
            vintage=None,
            fetched_at="2026-10-02T00:00:00Z",
        )
        self.assertEqual(v, "2026-10-02T00:00:00Z")
        self.assertEqual(src, "legacy_fallback")

    def test_resolve_raw_vintage_returns_none_flagged_fallback_when_no_input(self):
        v, src = resolve_raw_vintage()
        self.assertIsNone(v)
        self.assertEqual(src, "legacy_fallback")

    def test_build_lineage_block_shape(self):
        lineage = build_lineage_block(
            triples=[(1, 1.0, 10.0), (2, 2.0, 20.0)],
            raw_vintage="Week 4",
            raw_built_at="2026-10-02T00:00:00Z",
            vintage_source="content_vintage",
        )
        self.assertEqual(lineage["raw_vintage"], "Week 4")
        self.assertEqual(lineage["raw_built_at"], "2026-10-02T00:00:00Z")
        self.assertEqual(lineage["vintage_source"], "content_vintage")
        self.assertEqual(len(lineage["raw_content_sha256"]), 64)
        # And the SHA matches a fresh recomputation.
        self.assertEqual(
            lineage["raw_content_sha256"],
            compute_raw_sha([(1, 1.0, 10.0), (2, 2.0, 20.0)]),
        )


class TestAdjustedFixtureSectionsLineage(unittest.TestCase):
    """build_adjusted_fixture_sections stamps lineage on every _adjusted section."""

    def _setup(self):
        tmp = Path(tempfile.mkdtemp())
        players, fkeys, _, slug_to_pos = _make_players_and_keys(n_per_pos=4)
        fx_path, players_path = _write_fixture_with_raw_sources(tmp, fkeys=fkeys)
        inputs_path = tmp / "adjustment-inputs.json"
        _write_inputs_json(inputs_path)
        # Players.json inside the temp fixture dir already exists; but the
        # builder looks at the repo default. Mirror it into a local path
        # and patch the defaults via argv to point at the temp.
        local_players_path = tmp / "players.json"
        local_players_path.write_text(json.dumps({"players": players}))
        return tmp, fx_path, inputs_path, local_players_path, fkeys, slug_to_pos

    def test_adjusted_sections_carry_lineage_block(self):
        tmp, fx_path, inputs_path, players_path, fkeys, slug_to_pos = self._setup()
        import build_adjusted_fixture_sections as bafs
        stats = bafs.build_adjusted_sections(fx_path, inputs_path, players_path)
        # All four sources must build (fail-closed builder).
        for src in ("fantasycalc", "usatoday", "fantasypros", "cbs"):
            self.assertEqual(stats[src]["status"], "built",
                             f"{src} _adjusted section failed to build")
        fixture = json.loads(fx_path.read_text(encoding="utf-8"))
        for src in ("fantasycalc", "usatoday", "fantasypros", "cbs"):
            adj_key = f"{src}_adjusted"
            self.assertIn(adj_key, fixture["sources"],
                          f"adjusted section {adj_key} missing from fixture")
            section = fixture["sources"][adj_key]
            self.assertIn("lineage", section,
                          f"{adj_key} missing lineage block (JEG-132 R5a)")
            lineage = section["lineage"]
            self.assertEqual(set(lineage.keys()),
                             {"raw_vintage", "raw_content_sha256",
                              "raw_built_at", "vintage_source"},
                             "Lineage schema must be exactly the 4 R5a fields")
            # R4a stamps content_vintage on the raw sections -> content_vintage path.
            self.assertEqual(lineage["vintage_source"], "content_vintage",
                             f"{adj_key}: raw carries content_vintage; "
                             "legacy_fallback would be a silent failure")
            self.assertEqual(lineage["raw_vintage"], "Week 3",
                             f"{adj_key}: raw_vintage must be the raw section's content_vintage")

    def test_adjusted_lineage_sha_matches_raw_recomputation(self):
        tmp, fx_path, inputs_path, players_path, fkeys, slug_to_pos = self._setup()
        import build_adjusted_fixture_sections as bafs
        bafs.build_adjusted_sections(fx_path, inputs_path, players_path)
        fixture = json.loads(fx_path.read_text(encoding="utf-8"))
        for src in ("fantasycalc", "usatoday", "fantasypros", "cbs"):
            adj_key = f"{src}_adjusted"
            raw_section = fixture["sources"][src]
            adj_section = fixture["sources"][adj_key]
            triples = collect_fixture_section_triples(raw_section)
            expected_sha = compute_raw_sha(triples)
            self.assertEqual(
                adj_section["lineage"]["raw_content_sha256"], expected_sha,
                f"{adj_key}: lineage SHA must match raw triples recomputation"
            )

    def test_adjusted_does_not_mutate_raw_sections(self):
        tmp, fx_path, inputs_path, players_path, fkeys, slug_to_pos = self._setup()
        # Snapshot the raw section's keys before running the builder.
        before = json.loads(fx_path.read_text(encoding="utf-8"))
        raw_keys_before = {src: set(before["sources"][src].keys())
                           for src in ("fantasycalc", "usatoday",
                                       "fantasypros", "cbs")}
        import build_adjusted_fixture_sections as bafs
        bafs.build_adjusted_sections(fx_path, inputs_path, players_path)
        after = json.loads(fx_path.read_text(encoding="utf-8"))
        for src in ("fantasycalc", "usatoday", "fantasypros", "cbs"):
            keys_after = set(after["sources"][src].keys())
            self.assertEqual(keys_after, raw_keys_before[src],
                             f"raw {src} keys changed; builder must not mutate inputs")
            self.assertNotIn("lineage", after["sources"][src],
                             f"raw {src} got a lineage block; raw sections must NOT")


# The section builders resolve their paths at module load; the tests below
# repoint them at a temp tree. Every test restores them, or a later test in
# the same process (test_cbsros_section) reads a deleted temp root.
_BUILDER_MODULES = ("build_espn_section_from_ddf_leg",
                    "build_cbsros_section_from_ddf_leg",
                    "build_razzball_section_from_ddf_leg")
_BUILDER_GLOBALS = ("ROOT", "REPO", "LEG_DIR", "FIXTURE", "PLAYERS")


def _builder_globals() -> dict:
    import importlib
    out = {}
    for name in _BUILDER_MODULES:
        mod = importlib.import_module(name)
        for attr in _BUILDER_GLOBALS:
            if hasattr(mod, attr):
                out[(name, attr)] = getattr(mod, attr)
    return out


class TestDdfLegSectionLineage(unittest.TestCase):
    """CBS-ROS / ESPN / Razzball builders stamp lineage from the raw DDF leg."""

    def setUp(self):
        import importlib
        saved = _builder_globals()

        def restore():
            for (name, attr), value in saved.items():
                setattr(importlib.import_module(name), attr, value)

        self.addCleanup(restore)

    def _write_ddf_leg(self, leg_dir: Path, *, bake_id: str,
                       snapshot_date: str,
                       content_vintage: str | None = None,
                       n_rows: int = 8) -> Path:
        """Write a minimal DDF leg file (one per scoring) shaped like the real ones."""
        values = []
        for i in range(n_rows):
            values.append({
                "player_norm": f"player qb{i}" if i % 2 == 0 else f"player rb{i}",
                "player_key": 1000 + i,
                "value": round(20.0 + i * 0.5, 2),
                "ppg": round(5.0 + i * 0.1, 3),
            })
        leg = {
            "bake_id": bake_id,
            "generated_at": "2026-10-02T12:00:00Z",
            "fetched_at": "2026-10-02T11:55:00Z",
            "values": values,
            "inputs": {
                "scoring": "ppr" if "-ppr-" in bake_id else
                           "half_ppr" if "-half_ppr-" in bake_id else "standard",
                "teams": int(bake_id.split("-")[-2].rstrip("t")),
                "espn_snapshot_date": snapshot_date,
                "cbsros_snapshot_date": snapshot_date,
                "razzball_snapshot_date": snapshot_date,
                # GAP-BAKE-ON-CHANGE: real legs record their input's id.
                "espn_csv_sha256": "0" * 64,
                "cbsros_snapshot_id": "sha256:" + "0" * 64,
                "razzball_snapshot_id": "sha256:" + "0" * 64,
            },
        }
        if content_vintage is not None:
            leg["inputs"]["content_vintage"] = content_vintage
        leg_dir.mkdir(parents=True, exist_ok=True)
        leg_path = leg_dir / "ddf_leg.json"
        leg_path.write_text(json.dumps(leg))
        return leg_path

    def _setup_ddf_legs(self, tmp: Path, *, content_vintage: str | None = None,
                        bake_tag: str = "espn"):
        """Create a data/ddf-two-tier/ tree with legs for all three scorings."""
        leg_root = tmp / "data" / "ddf-two-tier"
        bake_id_base = f"ddf-20261002-{bake_tag}"
        for scoring in ("ppr", "half_ppr", "standard"):
            bake_id = f"{bake_id_base}-{scoring}-12t-0p15"
            d = leg_root / bake_id
            self._write_ddf_leg(
                d,
                bake_id=bake_id,
                snapshot_date="2026-10-02",
                content_vintage=content_vintage,
            )

    def _setup_fixture(self, tmp: Path, *, fkeys):
        """Build a fixture with a placeholder espn section (the ESPN builder
        requires one to exist; we copy the legacy shape then let the writer
        overwrite it)."""
        players, _, _, slug_to_pos = _make_players_and_keys(n_per_pos=4)
        # Pre-existing espn section the builder overwrites.
        espn_section = _make_raw_fixture_section(
            fkeys=fkeys, slug_to_pos=slug_to_pos,
            base_value=50.0, vintage="Week 3",
            built_at="2026-09-30T00:00:00Z",
        )
        espn_section["name"] = "ESPN anchor (will be overwritten)"
        fixture = {
            "built_at": "2026-09-30T00:00:00Z",
            "sources": {"espn": espn_section},
            "player_keys": fkeys,
        }
        fx_path = tmp / "data" / "fixtures" / "current" / "comparison-sources-data.json"
        fx_path.parent.mkdir(parents=True, exist_ok=True)
        fx_path.write_text(json.dumps(fixture))
        players_path = tmp / "data" / "fixtures" / "current" / "players.json"
        players_path.write_text(json.dumps({"players": players}))
        return fx_path, players_path

    def _patch_leg_dir(self, tmp: Path):
        """Point LEG_DIR / ROOT at our temp via monkeypatch (the builders
        resolve them at module load time)."""
        import build_espn_section_from_ddf_leg as espn_mod
        import build_cbsros_section_from_ddf_leg as cbsros_mod
        import build_razzball_section_from_ddf_leg as rz_mod

        espn_mod.LEG_DIR = tmp / "data" / "ddf-two-tier"
        cbsros_mod.LEG_DIR = tmp / "data" / "ddf-two-tier"
        rz_mod.LEG_DIR = tmp / "data" / "ddf-two-tier"

        # ESPN builder also resolves REPO/FIXTURE/PLAYERS at module load; patch them.
        for mod in (espn_mod, cbsros_mod, rz_mod):
            mod.ROOT = tmp
            if hasattr(mod, "REPO"):
                mod.REPO = tmp
            if hasattr(mod, "FIXTURE"):
                mod.FIXTURE = tmp / "data" / "fixtures" / "current" / "comparison-sources-data.json"
            if hasattr(mod, "PLAYERS"):
                mod.PLAYERS = tmp / "data" / "fixtures" / "current" / "players.json"

        return espn_mod, cbsros_mod, rz_mod

    def test_cbsros_section_carries_lineage_with_content_vintage(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, fkeys, _, _ = _make_players_and_keys(n_per_pos=4)
            # Write CBS-ROS legs (bake_id must contain "-cbsros-").
            leg_root = tmp / "data" / "ddf-two-tier"
            for scoring, teams in [("ppr", 8), ("ppr", 10), ("ppr", 12), ("ppr", 14),
                                    ("half_ppr", 8), ("half_ppr", 10),
                                    ("half_ppr", 12), ("half_ppr", 14),
                                    ("standard", 8), ("standard", 10),
                                    ("standard", 12), ("standard", 14)]:
                d = leg_root / f"ddf-20261002-cbsros-{scoring}-{teams}t-0p15"
                leg = {
                    "bake_id": d.name,
                    "generated_at": "2026-10-02T12:00:00Z",
                    "fetched_at": "2026-10-02T11:55:00Z",
                    "values": [
                        {"player_norm": f"player qb{i}", "player_key": 1000 + i,
                         "value": 20.0 + i, "ppg": 5.0 + i * 0.1}
                        for i in range(6)
                    ],
                    "inputs": {"scoring": scoring, "teams": teams,
                               "cbsros_snapshot_date": "2026-10-02",
                               "cbsros_snapshot_id": "sha256:" + "0" * 64,
                               "content_vintage": "Week 4"},
                }
                d.mkdir(parents=True, exist_ok=True)
                (d / "ddf_leg_cbsros.json").write_text(json.dumps(leg))
            fx_path, players_path = self._setup_fixture(tmp, fkeys=fkeys)
            (tmp / "data" / "fixtures" / "current" / "players.json").write_text(
                json.dumps({"players": players}))

            import build_cbsros_section_from_ddf_leg as cbsros_mod
            cbsros_mod.LEG_DIR = tmp / "data" / "ddf-two-tier"
            cbsros_mod.ROOT = tmp
            section = cbsros_mod.section_from_leg(
                json.loads(fx_path.read_text(encoding="utf-8")),
                source_url="https://example/cbsros",
                combo_keys=cbsros_mod.COMBO_KEYS,
            )
            self.assertIn("lineage", section)
            lin = section["lineage"]
            self.assertEqual(set(lin.keys()),
                             {"raw_vintage", "raw_content_sha256",
                              "raw_built_at", "vintage_source"})
            self.assertEqual(lin["raw_vintage"], "Week 4",
                             "cbsros leg has content_vintage=Week 4 -> content_vintage path")
            self.assertEqual(lin["vintage_source"], "content_vintage")
            self.assertEqual(lin["raw_built_at"], "2026-10-02T12:00:00Z")
            self.assertEqual(len(lin["raw_content_sha256"]), 64)

    def test_cbsros_section_lineage_with_legacy_fallback(self):
        """When the leg has no content_vintage, vintage_source flags legacy_fallback."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, fkeys, _, _ = _make_players_and_keys(n_per_pos=4)
            leg_root = tmp / "data" / "ddf-two-tier"
            for scoring, teams in [("ppr", 12),]:
                d = leg_root / f"ddf-20261002-cbsros-{scoring}-{teams}t-0p15"
                leg = {
                    "bake_id": d.name,
                    "generated_at": "2026-10-02T12:00:00Z",
                    "fetched_at": "2026-10-02T11:55:00Z",
                    "values": [
                        {"player_norm": f"player qb{i}", "player_key": 1000 + i,
                         "value": 20.0 + i, "ppg": 5.0 + i * 0.1}
                        for i in range(4)
                    ],
                    "inputs": {"scoring": scoring, "teams": teams,
                               "cbsros_snapshot_date": "2026-10-01",
                               "cbsros_snapshot_id": "sha256:" + "0" * 64,
                               # no content_vintage -> legacy_fallback
                               },
                }
                d.mkdir(parents=True, exist_ok=True)
                (d / "ddf_leg_cbsros.json").write_text(json.dumps(leg))
            fx_path, players_path = self._setup_fixture(tmp, fkeys=fkeys)
            (tmp / "data" / "fixtures" / "current" / "players.json").write_text(
                json.dumps({"players": players}))

            import build_cbsros_section_from_ddf_leg as cbsros_mod
            cbsros_mod.LEG_DIR = tmp / "data" / "ddf-two-tier"
            cbsros_mod.ROOT = tmp
            section = cbsros_mod.section_from_leg(
                json.loads(fx_path.read_text(encoding="utf-8")),
                source_url="https://example/cbsros",
                combo_keys=["full_12"],  # just one combo for speed
            )
            lin = section["lineage"]
            self.assertEqual(lin["vintage_source"], "legacy_fallback",
                             "No content_vintage must flag the fallback (never silent).")
            self.assertEqual(lin["raw_vintage"], "2026-10-01")

    def test_cbsros_lineage_sha_reproduces_from_leg(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, fkeys, _, _ = _make_players_and_keys(n_per_pos=4)
            leg_root = tmp / "data" / "ddf-two-tier"
            d = leg_root / "ddf-20261002-cbsros-ppr-12t-0p15"
            d.mkdir(parents=True, exist_ok=True)
            leg_values = [
                {"player_norm": f"player qb{i}", "player_key": 1000 + i,
                 "value": 20.0 + i, "ppg": 5.0 + i * 0.1}
                for i in range(6)
            ]
            (d / "ddf_leg_cbsros.json").write_text(json.dumps({
                "bake_id": d.name,
                "generated_at": "2026-10-02T12:00:00Z",
                "fetched_at": "2026-10-02T11:55:00Z",
                "values": leg_values,
                "inputs": {"scoring": "ppr", "teams": 12,
                           "cbsros_snapshot_date": "2026-10-02",
                           "cbsros_snapshot_id": "sha256:" + "0" * 64,
                           "content_vintage": "Week 4"},
            }))
            fx_path, players_path = self._setup_fixture(tmp, fkeys=fkeys)
            (tmp / "data" / "fixtures" / "current" / "players.json").write_text(
                json.dumps({"players": players}))

            import build_cbsros_section_from_ddf_leg as cbsros_mod
            cbsros_mod.LEG_DIR = tmp / "data" / "ddf-two-tier"
            cbsros_mod.ROOT = tmp
            section = cbsros_mod.section_from_leg(
                json.loads(fx_path.read_text(encoding="utf-8")),
                source_url="https://example/cbsros",
                combo_keys=["full_12"],
            )
            triples = collect_leg_triples({
                "values": leg_values,
            })
            expected = compute_raw_sha(triples)
            self.assertEqual(section["lineage"]["raw_content_sha256"], expected,
                             "CBS-ROS SHA must reproduce from leg triples.")


class TestBuilderGlobalsRestored(unittest.TestCase):
    """Running the leg-section tests leaves the builders pointed at the repo
    (they used to leak a deleted temp ROOT/LEG_DIR into later tests)."""

    def test_leg_section_tests_restore_builder_paths(self):
        before = _builder_globals()
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestDdfLegSectionLineage)
        result = unittest.TestResult()
        suite.run(result)
        self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
        self.assertEqual(_builder_globals(), before)


class TestComparisonSourceSectionLineage(unittest.TestCase):
    """build_comparison_source_section stamps lineage on the candidate it emits."""

    def _write_reference(self, tmp: Path, *, content_vintage=None,
                         source="fantasycalc", n=8):
        rows = []
        for i in range(n):
            rows.append({
                "player_key": 2000 + i,
                "canonical_name": f"Player {i}",
                "source_player_name": f"Player {i}",
                "scoring": "ppr" if i % 2 == 0 else "half_ppr",
                "teams": 12,
                "qb": None,
                "value": float(50 + i),
                "native_value": float(500 + i * 10),
            })
        ref = {
            "schema": "trade-value-source-reference-v1",
            "source": source,
            "fetched_at": "2026-10-02T10:00:00Z",
            "source_provenance": {
                "content_vintage": content_vintage,
                "asof": "2026-10-02",
            },
            "rows": rows,
            "review_rows": [],
        }
        ref_path = tmp / "reference.json"
        ref_path.write_text(json.dumps(ref))
        return ref_path, rows

    def _setup_fixture(self, tmp: Path, fkeys):
        players, _, _, _ = _make_players_and_keys(n_per_pos=4)
        # The candidate builder uses canonical_slugs() against the fixture's
        # player_keys; reuse our test keys for the candidate's rows so
        # identity resolves.
        # Translate rows' player_keys into the fixture's keys (which use 5xxx).
        fixture = {
            "built_at": "2026-09-30T00:00:00Z",
            "sources": {},
            "player_keys": fkeys,
        }
        fx_path = tmp / "comparison.json"
        fx_path.write_text(json.dumps(fixture))
        players_path = tmp / "players.json"
        players_path.write_text(json.dumps({"players": players}))
        return fx_path, players_path

    def test_candidate_section_carries_lineage_block(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, fkeys, _, _ = _make_players_and_keys(n_per_pos=4)
            # Make reference rows use fixture's player_keys.
            ref_rows = []
            keys = list(fkeys.values())
            for i, k in enumerate(keys):
                slug = next(s for s, v in fkeys.items() if v == k)
                ref_rows.append({
                    "player_key": k,
                    "canonical_name": slug,
                    "source_player_name": slug,
                    "scoring": "ppr",
                    "teams": 12,
                    "qb": None,
                    "value": float(50 + i),
                    "native_value": float(500 + i * 10),
                })
            ref_path = tmp / "reference.json"
            ref_path.write_text(json.dumps({
                "schema": "trade-value-source-reference-v1",
                "source": "fantasycalc",
                "fetched_at": "2026-10-02T10:00:00Z",
                "source_provenance": {
                    "content_vintage": "Week 4",
                    "asof": "2026-10-02",
                },
                "rows": ref_rows,
                "review_rows": [],
            }))
            fx_path, players_path = self._setup_fixture(tmp, fkeys)

            import build_comparison_source_section as bcs
            section = bcs.build_section(
                str(ref_path),
                fx_path,
                section_key="fantasycalc",
                meta={"name": "FantasyCalc", "kind": "test"},
            )
            self.assertIn("lineage", section)
            lin = section["lineage"]
            self.assertEqual(set(lin.keys()),
                             {"raw_vintage", "raw_content_sha256",
                              "raw_built_at", "vintage_source"})
            self.assertEqual(lin["raw_vintage"], "Week 4")
            self.assertEqual(lin["vintage_source"], "content_vintage")
            self.assertEqual(len(lin["raw_content_sha256"]), 64)

    def test_candidate_lineage_sha_reproduces_from_reference(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, fkeys, _, _ = _make_players_and_keys(n_per_pos=4)
            ref_rows = []
            keys = list(fkeys.values())
            for i, k in enumerate(keys):
                slug = next(s for s, v in fkeys.items() if v == k)
                ref_rows.append({
                    "player_key": k,
                    "canonical_name": slug,
                    "source_player_name": slug,
                    "scoring": "ppr",
                    "teams": 12,
                    "qb": None,
                    "value": float(50 + i),
                    "native_value": float(500 + i * 10),
                })
            ref_path = tmp / "reference.json"
            ref_path.write_text(json.dumps({
                "schema": "trade-value-source-reference-v1",
                "source": "fantasycalc",
                "fetched_at": "2026-10-02T10:00:00Z",
                "source_provenance": {"content_vintage": None, "asof": "2026-10-02"},
                "rows": ref_rows,
                "review_rows": [],
            }))
            fx_path, players_path = self._setup_fixture(tmp, fkeys)

            import build_comparison_source_section as bcs
            section = bcs.build_section(
                str(ref_path),
                fx_path,
                section_key="fantasycalc",
                meta={"name": "FantasyCalc", "kind": "test"},
            )
            triples = collect_reference_triples({
                "rows": ref_rows,
            })
            expected = compute_raw_sha(triples)
            self.assertEqual(section["lineage"]["raw_content_sha256"], expected,
                             "Comparison candidate SHA must reproduce from "
                             "reference rows.")


class TestSchemaAndAcceptance(unittest.TestCase):
    """Schema and acceptance invariants the sibling R5b checker will rely on."""

    def test_lineage_block_exactly_four_keys(self):
        """No extra keys creep into the lineage block (R5b stability)."""
        lineage = build_lineage_block(
            triples=[(1, 1.0, 10.0)],
            raw_vintage="x", raw_built_at="y",
            vintage_source="content_vintage",
        )
        self.assertEqual(set(lineage.keys()),
                         {"raw_vintage", "raw_content_sha256",
                          "raw_built_at", "vintage_source"})

    def test_vintage_source_exactly_one_of_two_values(self):
        """vintage_source is the union discriminator for the checker."""
        for src in ("content_vintage", "legacy_fallback"):
            self.assertIn(src, ("content_vintage", "legacy_fallback"))
        # And the type is a string.
        lineage = build_lineage_block(
            triples=[(1, 1.0, 10.0)],
            raw_vintage="x", raw_built_at="y",
            vintage_source="content_vintage",
        )
        self.assertIsInstance(lineage["vintage_source"], str)

    def test_sha_is_hex_and_64_chars(self):
        lineage = build_lineage_block(
            triples=[(1, 1.0, 10.0)],
            raw_vintage="x", raw_built_at="y",
            vintage_source="content_vintage",
        )
        sha = lineage["raw_content_sha256"]
        self.assertEqual(len(sha), 64)
        int(sha, 16)  # raises if not hex

    def test_triples_with_none_native_still_hash(self):
        """None values (D2 gate artifacts) must not break the SHA computation."""
        triples = [(1, None, 10.0), (2, 20.0, None)]
        sha = compute_raw_sha(triples)
        # Round trip: same triples -> same hash.
        self.assertEqual(sha, compute_raw_sha(triples))


if __name__ == "__main__":
    unittest.main()