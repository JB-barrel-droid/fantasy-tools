#!/usr/bin/env python3
"""JEG-324 / JEG-380: consolidated_values rows carry the live NOT NULL columns.

Rebuild run 37641559947 (2026-10-07) failed at "Build consolidation layer":
HTTP 400 23502 on public.consolidated_values, because the builder never wrote
player_key, bake_uuid or source_generated_at (NOT NULL since the JEG-377/380
hardening). FakeTable below enforces the live constraints (NOT NULL, FK on
source and player_key, ck_combo_reindexed_cap); each guard is shown to fail on
the broken state it names.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

import build_consolidated_values as bcv  # noqa: E402

FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
NOT_NULL = ("player", "source", "season", "week", "scoring", "teams", "qb_variant", "view",
            "value", "detail_locator", "bake_id", "created_at", "player_key", "bake_uuid",
            "source_generated_at")


class DbError(Exception):
    pass


class FakeSb:
    """public.consolidated_values / bakes / source_config / players as the live
    database enforces them (2026-10-07)."""

    def __init__(self, sources, player_keys):
        self.sources = list(sources)
        self.players = [{"player_key": k} for k in player_keys]
        self.bakes, self.values, self.calls = [], [], []

    def get(self, table, params=""):
        self.calls.append(("get", table))
        if table == "source_config":
            return [{"source": s} for s in self.sources]
        if table == "bakes":
            return [b for b in self.bakes if f"source=eq.{b['source']}&" in params
                    and b["context"]["fixture_sha256"] in params]
        raise AssertionError(table)

    def get_all(self, table, params=""):
        assert table == "players", table
        return self.players

    def post(self, table, rows, params="", prefer=""):
        self.calls.append(("post", table))
        if table == "bakes":
            out = []
            for r in rows:
                if not r.get("source_generated_at"):
                    raise DbError("23502 bakes.source_generated_at")
                b = dict(r, bake_id=f"{len(self.bakes) + 1:08x}-0000-4000-8000-000000000000")
                self.bakes.append(b)
                out.append(b)
            return out
        assert table == "consolidated_values", table
        bake_ids = {b["bake_id"] for b in self.bakes}
        keys = {p["player_key"] for p in self.players}
        for r in rows:
            for col in NOT_NULL:
                if col == "created_at" and col not in r:
                    continue  # omitted -> DEFAULT now(); an explicit null is still rejected
                if r.get(col) is None:
                    raise DbError(f"23502 null value in column {col!r}")
            if r["source"] not in self.sources:
                raise DbError("23503 fk_consolidated_values_source")
            if r["bake_uuid"] not in bake_ids:
                raise DbError("23503 fk_consolidated_values_bake_uuid")
            if r["player_key"] not in keys:
                raise DbError("23503 consolidated_values_player_fk")
            if r["view"] == "combo_reindexed" and r["value"] > 70:
                raise DbError("23514 ck_combo_reindexed_cap")
        self.values.extend(rows)


def load_detail():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def writable_detail():
    """The real fixture. (Its adjusted sections exceed the cap; they are not
    table rows, decision consol-adjusted-001.)"""
    return load_detail()


def run_write(detail, sources=None, keys=None):
    rows, diag = bcv.build_rows(detail)
    assert not bcv.reconcile(rows, detail, diag["review_no_player_key"])
    sb = FakeSb(sources if sources is not None else sorted(detail["sources"]),
                keys if keys is not None else sorted(set(detail["player_keys"].values())))
    n = bcv.write_supabase(rows, detail, "sha-test", sb=sb)
    return sb, rows, n


class WriteFieldsTest(unittest.TestCase):
    def test_every_written_row_satisfies_the_live_constraints(self):
        sb, rows, n = run_write(writable_detail())
        core, _ = bcv.split_for_table(rows)
        self.assertEqual(n, len(core))
        self.assertEqual(len(sb.values), len(core))
        self.assertEqual(len(sb.bakes), len({r["source"] for r in core}))
        # one bake per source, and every row's bake belongs to its own source
        bake_src = {b["bake_id"]: b["source"] for b in sb.bakes}
        self.assertTrue(all(bake_src[r["bake_uuid"]] == r["source"] for r in sb.values))

    def test_broken_state_rows_without_the_fields_are_rejected(self):
        # The pre-fix writer posted build_rows() output as is.
        detail = writable_detail()
        rows, _ = bcv.build_rows(detail)
        sb = FakeSb(sorted(detail["sources"]), sorted(set(detail["player_keys"].values())))
        broken = [{k: v for k, v in r.items() if k != "player_key"} for r in rows[:5]]
        with self.assertRaisesRegex(DbError, "23502"):
            sb.post("consolidated_values", broken)

    def test_rerun_of_the_same_fixture_reuses_its_bakes(self):
        detail = writable_detail()
        rows, _ = bcv.build_rows(detail)
        sb = FakeSb(sorted(detail["sources"]), sorted(set(detail["player_keys"].values())))
        bcv.write_supabase(rows, detail, "sha-test", sb=sb)
        bcv.write_supabase(rows, detail, "sha-test", sb=sb)
        core, _ = bcv.split_for_table(rows)
        self.assertEqual(len(sb.bakes), len({r["source"] for r in core}))

    def test_player_key_is_the_fixtures_own_key(self):
        detail = load_detail()
        rows, diag = bcv.build_rows(detail)
        self.assertEqual(diag["review_no_player_key"], [])
        self.assertTrue(all(r["player_key"] == detail["player_keys"][r["player"]] for r in rows))

    def test_player_without_a_key_goes_to_review_not_to_the_table(self):
        detail = load_detail()
        name = "aaron jones"
        del detail["player_keys"][name]
        rows, diag = bcv.build_rows(detail)
        self.assertFalse(any(r["player"] == name for r in rows))
        self.assertTrue(diag["review_no_player_key"])
        self.assertTrue(all(name in loc for loc in diag["review_no_player_key"]))
        self.assertEqual(bcv.reconcile(rows, detail, diag["review_no_player_key"]), [])
        # the completeness check still fires when the review list is not passed
        self.assertTrue(bcv.reconcile(rows, detail))


class SourceGeneratedAtTest(unittest.TestCase):
    def test_content_vintage_per_source(self):
        d = load_detail()["sources"]
        got = {s: bcv.source_generated_at_for(s, d[s]) for s in d}
        # The section's own vintage date, as an instant (2026-10-08: was a
        # hand pin of 2026-10-02 that went red on the next CBS ROS refresh).
        self.assertEqual(got["cbsros"], (f"{d['cbsros']['vintage'][:10]}T00:00:00+00:00", "vintage"))
        self.assertEqual(got["espn"][1], "espn_snapshot")
        self.assertEqual(got["fantasypros"][1], "source_provenance.content_vintage")
        self.assertEqual(got["usatoday_adjusted"][1], "lineage.raw_vintage")
        # "Week 5" is not an instant: the acquisition time is used
        self.assertEqual(got["fantasycalc"][1], "fetched_at")
        self.assertTrue(all(v[0] for v in got.values()), got)

    def test_missing_vintage_fails_closed_before_any_write(self):
        detail = writable_detail()
        for k in ("content_vintage", "fetched_at", "source_provenance", "lineage", "vintage",
                  "espn_snapshot"):
            detail["sources"]["cbs"].pop(k, None)
        rows, _ = bcv.build_rows(detail)
        sb = FakeSb(sorted(detail["sources"]), sorted(set(detail["player_keys"].values())))
        with self.assertRaisesRegex(SystemExit, "no content vintage"):
            bcv.write_supabase(rows, detail, "sha-test", sb=sb)
        self.assertEqual([c for c in sb.calls if c[0] == "post"], [])


class PreflightTest(unittest.TestCase):
    def test_over_cap_core_value_is_refused_whole_before_any_write(self):
        # The 70 cap still holds for core sources: one over-cap cbs value
        # refuses the whole write before anything lands (no partial 23514).
        detail = load_detail()
        combo = detail["sources"]["cbs"]["combos"]["full_12"]["reindexed"]
        combo["aaron jones"] = 75.0
        rows, _ = bcv.build_rows(detail)
        sb = FakeSb(sorted(detail["sources"]), sorted(set(detail["player_keys"].values())))
        with self.assertRaises(SystemExit) as cm:
            bcv.write_supabase(rows, detail, "sha-test", sb=sb)
        self.assertIn("1 combo_reindexed value(s) > 70", str(cm.exception))
        self.assertIn("ck_combo_reindexed_cap", str(cm.exception))
        self.assertEqual([c for c in sb.calls if c[0] == "post"], [], "wrote before failing")


class AdjustedExcludedTest(unittest.TestCase):
    """Decision consol-adjusted-001 (Jeremy 2026-10-07): *_adjusted sections are
    not written to public.consolidated_values, explicitly and with a log line."""

    def test_current_fixture_writes_core_sources_only_and_logs_the_skip(self):
        # 2026-10-07: 15 adjusted combo values exceed 70; the write must go
        # through anyway because adjusted sources are not table rows.
        import contextlib
        import io
        detail = load_detail()
        rows, _ = bcv.build_rows(detail)
        sb = FakeSb(sorted(detail["sources"]), sorted(set(detail["player_keys"].values())))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            n = bcv.write_supabase(rows, detail, "sha-test", sb=sb)
        written = {r["source"] for r in sb.values}
        self.assertFalse([s for s in written if s.endswith("_adjusted")], written)
        adjusted = {}
        for r in rows:
            if r["source"].endswith("_adjusted"):
                adjusted[r["source"]] = adjusted.get(r["source"], 0) + 1
        self.assertEqual(n, len(rows) - sum(adjusted.values()))
        self.assertEqual(set(adjusted), {"cbs_adjusted", "fantasycalc_adjusted",
                                         "fantasypros_adjusted", "usatoday_adjusted"})
        for src, cnt in adjusted.items():
            self.assertIn(f"skipped {src}: {cnt} rows not written to consolidated_values", out.getvalue())
        self.assertFalse([b for b in sb.bakes if b["source"].endswith("_adjusted")])

    def test_adjusted_rows_stay_in_the_served_export(self):
        # The chart/export side is unchanged: build_rows still emits them.
        rows, _ = bcv.build_rows(load_detail())
        self.assertTrue(any(r["source"] == "usatoday_adjusted" for r in rows))


class SourceConfigTest(unittest.TestCase):
    def test_source_missing_from_source_config_is_refused(self):
        detail = writable_detail()
        with self.assertRaisesRegex(SystemExit, r"source_config.*\['cbs'\]"):
            run_write(detail, sources=[s for s in detail["sources"] if s != "cbs"])

    def test_unknown_player_key_is_refused(self):
        detail = writable_detail()
        rows, _ = bcv.build_rows(detail)
        keys = sorted({r["player_key"] for r in rows})[1:]
        with self.assertRaisesRegex(SystemExit, "not in public.players"):
            run_write(detail, keys=keys)

    def test_attach_refuses_a_missing_field(self):
        rows, _ = bcv.build_rows(writable_detail())
        with self.assertRaisesRegex(SystemExit, "bake_uuid"):
            bcv.attach_write_fields(rows[:3], {}, {r["source"]: "2026-10-01T00:00:00+00:00" for r in rows},
                                    "2026-10-07T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
