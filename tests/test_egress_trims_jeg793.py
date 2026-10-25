"""JEG-793 egress trims must not change data, values or published output.

  A. gzip: the client asks for gzip, decodes it transparently, returns the
     same data, and the counter reports decoded and on-wire bytes.
  B. source-vintage-check: the narrow, newest-date-scoped reads derive the
     same vintage as the old whole-table select=* reads, from fewer rows.
  C. importer: the date-scoped reads for ESPN / CBS ROS / Razzball build the
     same snapshot and manifest as the unscoped reads, from fewer rows.

No network: a small in-memory PostgREST stand-in answers the queries.
"""
import gzip
import importlib.util
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT / "pipelines"
sys.path.insert(0, str(PIPELINES))
sys.path.insert(0, str(PIPELINES / "lib"))

import gh_sbclient as sb  # noqa: E402
import check_source_vintage as csv_  # noqa: E402


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, PIPELINES / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


importer = _load("import_supabase_references_jeg793", "import_supabase_references.py")


# --------------------------------------------------------------------------
# A. gzip
# --------------------------------------------------------------------------

class FakeHeaders(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


class FakeResp:
    def __init__(self, raw, encoding=None):
        self._raw = raw
        self.headers = FakeHeaders({"content-encoding": encoding} if encoding else {})

    def read(self):
        return self._raw


ENV = {"SUPABASE_URL": "https://example.invalid", "SUPABASE_SERVICE_KEY": "SECRETKEY"}
ROWS = [{"id": i, "name": f"player {i}", "value": i * 1.5} for i in range(300)]


class GzipTest(unittest.TestCase):
    def setUp(self):
        sb._BYTES.clear()
        sb._WIRE.clear()

    def _get(self, resp):
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["accept"] = req.get_header("Accept-encoding")
            return resp

        with mock.patch.dict(os.environ, ENV), \
                mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            out = sb.get("players", "?select=*")
        return out, seen

    def test_same_data_with_and_without_gzip(self):
        plain = json.dumps(ROWS).encode()
        zipped = gzip.compress(plain)
        out_plain, _ = self._get(FakeResp(plain))
        sb._BYTES.clear()
        sb._WIRE.clear()
        out_gz, seen = self._get(FakeResp(zipped, "gzip"))
        self.assertEqual(out_plain, ROWS)
        self.assertEqual(out_gz, out_plain)
        self.assertEqual(seen["accept"], "gzip")

    def test_counter_records_decoded_and_wire_bytes(self):
        plain = json.dumps(ROWS).encode()
        zipped = gzip.compress(plain)
        self.assertLess(len(zipped), len(plain))
        self._get(FakeResp(zipped, "gzip"))
        self.assertEqual(sb._BYTES[("GET", "players")], [1, len(plain)])
        self.assertEqual(sb._WIRE[("GET", "players")], len(zipped))
        line = sb.bytes_summary_lines()[0]
        self.assertIn(f"requests=1 bytes={len(plain)} wire={len(zipped)}", line)
        self.assertNotIn("SECRETKEY", line)

    def test_uncompressed_reply_still_works_and_wire_equals_bytes(self):
        plain = json.dumps(ROWS).encode()
        out, _ = self._get(FakeResp(plain))
        self.assertEqual(out, ROWS)
        self.assertEqual(sb._WIRE[("GET", "players")], len(plain))


# --------------------------------------------------------------------------
# In-memory PostgREST stand-in
# --------------------------------------------------------------------------

def query(tables, table, params):
    """Evaluate the PostgREST subset the trimmed readers use."""
    parts = [p for p in params.lstrip("?").split("&") if p]
    select, order, limit, filters = "*", None, None, []
    for p in parts:
        k, _, v = p.partition("=")
        if k == "select":
            select = v
        elif k == "order":
            order = v
        elif k == "limit":
            limit = int(v)
        elif k == "offset":
            continue
        else:
            filters.append((k, v))
    rows = list(tables[table])
    for k, v in filters:
        if k == "or":
            assert v == "(qb_slots.is.null,qb_slots.eq.1)", v
            rows = [r for r in rows if r.get("qb_slots") in (None, 1)]
        elif v == "not.is.null":
            rows = [r for r in rows if r.get(k) is not None]
        elif v.startswith("eq."):
            rows = [r for r in rows if str(r.get(k)) == v[3:]]
        else:
            raise AssertionError(f"unsupported filter {k}={v}")
    if order:
        col, _, direction = order.partition(".")
        nulls = [r for r in rows if r.get(col) is None]
        rest = sorted((r for r in rows if r.get(col) is not None),
                      key=lambda r: r[col], reverse=direction == "desc")
        rows = nulls + rest if direction == "desc" else rest + nulls  # PostgREST NULLS FIRST on desc
    if limit is not None:
        rows = rows[:limit]
    if select != "*":
        cols = select.split(",")
        rows = [{c: r.get(c) for c in cols if c in r} for r in rows]
    return rows


class Backend:
    """Counts rows returned so the trims can be shown to read less."""

    def __init__(self, tables):
        self.tables = tables
        self.rows_read = 0

    def __call__(self, table, params):
        out = query(self.tables, table, params)
        self.rows_read += len(out)
        return out


def stv(source, week, bake, created, n=3, qb_slots=1, content_date=None, value=100.0):
    return [{"source": source, "variant": "as_published", "qb_slots": qb_slots, "week": week,
             "bake_id": bake, "created_at": created, "source_content_date": content_date,
             "player_key": 1000 + i, "value": value + i, "position": "RB", "extra": "x" * 50}
            for i in range(n)]


def snap(date_col, date, week, pulled, n=3, **extra):
    return [{"player_key": 2000 + i, date_col: date, "week": week, "pulled_at": pulled,
             "created_at": pulled, "source_content_date": extra.get("content_date"),
             "player_norm": f"p{i}", "pos": "RB", "team": "BUF", "health": "",
             "games_reported": 16.0, "ros_standard": 10.0 + i, "ros_half_ppr": 11.0 + i,
             "ros_ppr": 12.0 + i, "gp": 8.0, "receptions": 3.0,
             "per_game_standard": 1.0 + i, "per_game_half_ppr": 1.5 + i, "per_game_ppr": 2.0 + i,
             "raw_stats": {"pg_rush_att": 6.5 + i}, "junk": "y" * 80} for i in range(n)]


TABLES = {
    "source_trade_values":
        stv("fantasycalc", 3, "b1", "2026-10-01T01:00:00Z")
        + stv("fantasycalc", 4, "b2", "2026-10-08T01:00:00Z")
        + stv("fantasycalc", 4, "b3", "2026-10-09T01:00:00Z")
        + stv("fantasycalc", 5, "b9", "2026-10-15T01:00:00Z", qb_slots=2)  # superflex never picks week
        + stv("usatoday", None, "u1", "2026-10-08T01:00:00Z", content_date="2026-10-07")
        + stv("usatoday", None, "u2", "2026-10-15T01:00:00Z", content_date="2026-10-14"),
    "cbs_trade_values": stv("cbs", 4, "c1", "2026-10-08T01:00:00Z") + stv("cbs", 5, "c2", "2026-10-15T01:00:00Z"),
    "espn_season_projections":
        snap("espn_snapshot_date", "2026-10-01", 4, "2026-10-01T00:00:00Z")
        + snap("espn_snapshot_date", "2026-10-08", 5, "2026-10-08T00:00:00Z", n=4),
    "cbs_ros_projections":
        snap("cbs_snapshot_date", "2026-10-01", 4, "2026-10-01T00:00:00Z", content_date="2026-10-01")
        + snap("cbs_snapshot_date", "2026-10-08", 5, "2026-10-08T00:00:00Z", n=4, content_date="2026-10-08")
        + snap("cbs_snapshot_date", None, 9, "2026-10-09T00:00:00Z", n=1),  # undated row never wins
    "razzball_projections":
        snap("razzball_snapshot_date", "2026-09-30", 4, "2026-09-30T00:00:00Z", content_date="2026-09-30")
        + snap("razzball_snapshot_date", "2026-10-08", 5, "2026-10-08T03:00:00Z", n=4, content_date="2026-10-08")
        + snap("razzball_snapshot_date", "2026-10-08", 5, "2026-10-08T19:00:00Z", n=3, content_date="2026-10-08"),
}


# --------------------------------------------------------------------------
# B. source-vintage-check
# --------------------------------------------------------------------------

def legacy_vintage(tables, source):
    """The pre-trim logic: whole-table select=* then the same selectors."""
    table = csv_.SOURCE_TABLES[source]
    rows = tables[table]
    if source in ("fantasycalc", "usatoday", "fantasypros", "cbs"):
        name = "cbs" if source == "cbs" else source
        rows = [r for r in rows if r["source"] == name and r["variant"] == "as_published"
                and r.get("qb_slots") == 1]
        top = sorted((r["week"] for r in rows if r["week"] is not None), reverse=True)
        if top:
            rows = [r for r in rows if r["week"] == top[0]]
        rows, _ = csv_._select_latest_week(rows)
        rows, _ = csv_._select_latest_bake(rows)
    else:
        key = {"espn": "espn_snapshot_date", "cbsros": "cbs_snapshot_date",
               "razzball": "razzball_snapshot_date"}[source]
        rows, _ = csv_._select_latest_snapshot_date(rows, date_key=key)
    return csv_._derive_db_vintage(rows, source)


class VintageCheckTest(unittest.TestCase):
    def run_new(self, tables, source):
        backend = Backend(tables)
        with mock.patch.object(csv_, "_get_supabase_rows",
                               side_effect=lambda t, p: backend(t, p)), \
                mock.patch.object(csv_, "_get_supabase_page",
                                  side_effect=lambda t, p: backend(t, p)):
            return csv_.get_current_vintage(source), backend.rows_read

    def test_same_vintage_as_legacy_for_every_source(self):
        for source in ("fantasycalc", "usatoday", "espn", "cbs", "cbsros", "razzball"):
            with self.subTest(source=source):
                got, _ = self.run_new(TABLES, source)
                self.assertEqual(got, legacy_vintage(TABLES, source))

    def test_reads_fewer_rows_than_whole_table(self):
        for source, table in (("espn", "espn_season_projections"),
                              ("cbsros", "cbs_ros_projections"),
                              ("razzball", "razzball_projections")):
            with self.subTest(source=source):
                _, read = self.run_new(TABLES, source)
                self.assertLess(read, len(TABLES[table]))

    def test_snapshot_reads_are_narrow_and_scoped(self):
        calls = []
        backend = Backend(TABLES)

        def spy(table, params):
            calls.append((table, params))
            return backend(table, params)

        with mock.patch.object(csv_, "_get_supabase_rows", side_effect=spy), \
                mock.patch.object(csv_, "_get_supabase_page", side_effect=spy):
            csv_.get_current_vintage("razzball")
        self.assertTrue(all("select=*" not in p for _, p in calls), calls)
        self.assertIn("razzball_snapshot_date=eq.2026-10-08", calls[-1][1])

    def test_undated_table_falls_back_to_week(self):
        tables = {"cbs_ros_projections": snap("cbs_snapshot_date", None, 7, "2026-10-01T00:00:00Z")}
        for r in tables["cbs_ros_projections"]:
            r["source_content_date"] = None
        got, _ = self.run_new(tables, "cbsros")
        self.assertEqual(got, "Week 7")
        self.assertEqual(got, legacy_vintage(tables, "cbsros"))

    def test_wrong_newest_date_is_detected(self):
        """Guard sanity: an off-by-one (second newest) date would differ."""
        tables = TABLES
        wrong = sorted({r["razzball_snapshot_date"] for r in tables["razzball_projections"]})[-2]
        with mock.patch.object(csv_, "_latest_date_param",
                               side_effect=lambda t, c: f"&{c}=eq.{wrong}"):
            got, _ = self.run_new(tables, "razzball")
        self.assertNotEqual(got, legacy_vintage(tables, "razzball"))


# --------------------------------------------------------------------------
# C. importer
# --------------------------------------------------------------------------

class ImporterScopeTest(unittest.TestCase):
    def build(self, builder, tables, scoped=True):
        backend = Backend(tables)
        patches = [
            mock.patch.object(importer, "fetch_supabase_rows", backend),
            mock.patch.object(importer, "fetch_player_names",
                              lambda keys: {k: f"Player {k}" for k in keys}),
            mock.patch.object(importer, "fetch_player_positions", lambda keys: {k: "RB" for k in keys}),
            mock.patch.object(importer, "fixture_pos_team", lambda: {}),
        ]
        if not scoped:
            patches.append(mock.patch.object(importer, "latest_date_param", lambda t, c: ""))
        for p in patches:
            p.start()
        try:
            out = getattr(importer, builder)()
        finally:
            for p in reversed(patches):
                p.stop()
        return out, backend.rows_read

    def test_scoped_equals_unscoped_and_reads_less(self):
        for builder, table in (("build_espn_snapshot", "espn_season_projections"),
                               ("build_cbsros_snapshot", "cbs_ros_projections"),
                               ("build_razzball_snapshot", "razzball_projections")):
            with self.subTest(builder=builder):
                new, new_read = self.build(builder, TABLES, scoped=True)
                old, old_read = self.build(builder, TABLES, scoped=False)
                # Filter note text names the scope, never the data; compare the
                # whole snapshot and manifest verbatim.
                self.assertEqual(json.dumps(new, sort_keys=True, default=str),
                                 json.dumps(old, sort_keys=True, default=str))
                self.assertLess(new_read, old_read)

    def test_off_by_one_date_scope_is_detected(self):
        dates = sorted({r["razzball_snapshot_date"] for r in TABLES["razzball_projections"]})
        wrong = dates[-2]
        backend = Backend(TABLES)
        new, _ = self.build("build_razzball_snapshot", TABLES, scoped=True)
        with mock.patch.object(importer, "latest_date_param",
                               lambda t, c: f"&{c}=eq.{wrong}"):
            broken, _ = self.build("build_razzball_snapshot", TABLES, scoped=True)
        self.assertNotEqual(json.dumps(new, sort_keys=True, default=str),
                            json.dumps(broken, sort_keys=True, default=str))

    def test_undated_table_keeps_unscoped_read(self):
        tables = {"cbs_ros_projections": [dict(r, cbs_snapshot_date=None)
                                          for r in TABLES["cbs_ros_projections"][:3]]}
        backend = Backend(tables)
        with mock.patch.object(importer, "fetch_supabase_rows", backend):
            self.assertEqual(importer.latest_date_param("cbs_ros_projections", "cbs_snapshot_date"), "")


if __name__ == "__main__":
    unittest.main()
