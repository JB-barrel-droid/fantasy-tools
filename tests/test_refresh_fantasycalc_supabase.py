#!/usr/bin/env python3
"""Regression tests for JEG-294: dynamic match-path resolution in
pipelines/refresh_fantasycalc_supabase.py.

The drift workflow refreshes the snapshot and match_source_snapshot.py writes
each refresh to output/source-matches/fantasycalc/<YYYY-MM-DD>/; the refresh
script used to hardcode one date, so every future drift day failed at the
Re-import step. These tests pin the dynamic resolution.

Unit tier: tmp dirs only, no data/raw, no Supabase, no network. sbclient is
stubbed before import (the script only needs it inside main()).
"""
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parent.parent


def _load_module():
    """Import refresh_fantasycalc_supabase with sbclient stubbed out."""
    trap = MagicMock(name="sbclient")
    with patch.dict(sys.modules, {"sbclient": trap}):
        sys.path.insert(0, str(REPO / "pipelines"))
        try:
            mod = importlib.import_module("refresh_fantasycalc_supabase")
            return importlib.reload(mod)
        finally:
            sys.path.remove(str(REPO / "pipelines"))


def _write_match(repo: Path, date: str, rows=None):
    ddir = repo / "output" / "source-matches" / "fantasycalc" / date
    ddir.mkdir(parents=True, exist_ok=True)
    (ddir / "fantasycalc-mixed-12-matched.json").write_text(
        json.dumps({"matched_rows": rows if rows is not None else []}))
    return ddir


class TestResolveMatchPath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_picks_latest_dated_dir(self):
        repo = Path(tempfile.mkdtemp())
        for d in ("2026-09-30", "2026-10-01", "2026-10-03"):
            _write_match(repo, d)
        p = self.mod.resolve_match_path(repo)
        self.assertEqual(p.parent.name, "2026-10-03")
        self.assertTrue(p.name.startswith("fantasycalc-"))
        self.assertTrue(p.name.endswith("-matched.json"))

    def test_ignores_non_date_dirs(self):
        repo = Path(tempfile.mkdtemp())
        _write_match(repo, "2026-09-30")
        (repo / "output" / "source-matches" / "fantasycalc" / "zzz-newest").mkdir()
        p = self.mod.resolve_match_path(repo)
        self.assertEqual(p.parent.name, "2026-09-30")

    def test_skips_newest_dir_without_match_file(self):
        repo = Path(tempfile.mkdtemp())
        _write_match(repo, "2026-09-30")
        (repo / "output" / "source-matches" / "fantasycalc" / "2026-10-03").mkdir()
        p = self.mod.resolve_match_path(repo)
        self.assertEqual(p.parent.name, "2026-09-30")

    def test_override_wins(self):
        repo = Path(tempfile.mkdtemp())
        _write_match(repo, "2026-10-03")
        other = repo / "custom-match.json"
        other.write_text(json.dumps({"matched_rows": []}))
        p = self.mod.resolve_match_path(repo, override=str(other))
        self.assertEqual(p, other)

    def test_override_missing_fail_closed(self):
        repo = Path(tempfile.mkdtemp())
        with self.assertRaises(FileNotFoundError):
            self.mod.resolve_match_path(repo, override=str(repo / "nope.json"))

    def test_fail_closed_when_no_match_files(self):
        repo = Path(tempfile.mkdtemp())
        with self.assertRaises(FileNotFoundError):
            self.mod.resolve_match_path(repo)

    def test_no_hardcoded_snapshot_date_in_source(self):
        # The incident date must not appear anywhere in the script (JEG-294
        # acceptance: no hardcoded date strings in path construction).
        src = (REPO / "pipelines" / "refresh_fantasycalc_supabase.py").read_text()
        self.assertNotIn("2026-09-30", src)


class TestMainEndToEnd(unittest.TestCase):
    """main() against stubbed Supabase + tmp repo: proves the drift-triggered
    refresh completes end-to-end on the dynamically resolved match file."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_refresh_completes(self):
        mod = self.mod
        repo = Path(tempfile.mkdtemp())
        _write_match(repo, "2026-10-03", rows=[{
            "source_player_name": "Ja'Marr Chase",
            "scoring": "half_ppr",
            "pos": "WR",
            "player_key": "jamarr-chase",
        }])
        sdir = repo / "data" / "raw" / "sources" / "fantasycalc" / "week-4"
        sdir.mkdir(parents=True)
        (sdir / "snapshot.json").write_text(json.dumps({"rows": [{
            "player_name": "Ja'Marr Chase",
            "scoring": "half_ppr",
            "native_value": 8500.0,
        }]}))

        posted = []
        store = []  # stateful fake: post() writes, get_all() reads back

        def fake_get_all(table, query):
            if table == "players":
                return [{"player_key": "jamarr-chase",
                         "metadata": {"team": "CIN"}}]
            return list(store)  # no existing week-4 rows until posted

        def fake_post(table, batch):
            posted.extend(batch)
            store.extend(batch)
            return list(batch)

        mod.get_all = fake_get_all
        mod.post = fake_post
        mod.delete = MagicMock()
        old_repo = mod.REPO
        mod.REPO = repo
        try:
            rc = mod.main([])
        finally:
            mod.REPO = old_repo
        self.assertEqual(rc, 0)
        self.assertEqual(len(posted), 1)
        row = posted[0]
        self.assertEqual(row["source"], "fantasycalc")
        self.assertEqual(row["variant"], "as_published")
        self.assertEqual(row["value"], 8500.0)
        self.assertEqual(row["native_value"], 8500.0)
        self.assertEqual(row["team"], "CIN")
        self.assertEqual(row["player_key"], "jamarr-chase")


if __name__ == "__main__":
    unittest.main()
