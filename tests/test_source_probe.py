"""Refresh cadence: cheap change probes, the ingest decision, and the wiring.

Every guard here is checked against a broken variant (the `*_is_caught` tests):
a decision rule that ignores max age, a fingerprint that hashes page chrome, a
vintage check with schema-qualified table names, and so on.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "ops" / "watchdog"))

import source_probe as sp  # noqa: E402
import check_source_vintage as csv_mod  # noqa: E402

WF = ROOT / ".github" / "workflows"
MIGRATION = ROOT / "supabase" / "migrations" / "source_probe_cadence_20261008.sql"
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
H = timedelta(hours=1)
DAILY = sp.Policy(max_age=20 * H)


def ago(delta):
    return (NOW - delta).isoformat()


def ok(fp):
    return {"ok": True, "fingerprint": fp}


FAILED = {"ok": False, "fingerprint": None, "error": "status=403"}


# --------------------------------------------------------------------------
# Decision rule
# --------------------------------------------------------------------------

# (name, state, probe, policy, expected action, expected reason prefix)
SCENARIOS = [
    ("first run", None, ok("A"), DAILY, "ingest", "first"),
    ("unchanged and fresh", {"acked_fp": "A", "acked_at": ago(2 * H)}, ok("A"), DAILY,
     "skip", "unchanged"),
    ("unchanged but past max age", {"acked_fp": "A", "acked_at": ago(21 * H)}, ok("A"), DAILY,
     "ingest", "max_age"),
    ("changed", {"acked_fp": "A", "acked_at": ago(2 * H)}, ok("B"), DAILY, "ingest", "changed"),
    ("changed, ingest for it in flight",
     {"acked_fp": "A", "acked_at": ago(2 * H), "dispatched_fp": "B",
      "dispatched_at": ago(10 * timedelta(minutes=1)), "attempts": 1},
     ok("B"), DAILY, "wait", "retry; ingest in flight"),
    ("changed, last ingest never acked -> retry",
     {"acked_fp": "A", "acked_at": ago(5 * H), "dispatched_fp": "B",
      "dispatched_at": ago(3 * H), "attempts": 1},
     ok("B"), DAILY, "ingest", "retry"),
    ("changed, ingest failed max_attempts times -> rest",
     {"acked_fp": "A", "acked_at": ago(10 * H), "dispatched_fp": "B",
      "dispatched_at": ago(3 * H), "attempts": 4},
     ok("B"), DAILY, "wait", "gave_up"),
    ("gave up, but a max age has passed since the last try",
     {"acked_fp": "A", "acked_at": ago(40 * H), "dispatched_fp": "B",
      "dispatched_at": ago(21 * H), "attempts": 4},
     ok("B"), DAILY, "ingest", "changed"),
    ("probe failed", {"acked_fp": "A", "acked_at": ago(2 * H)}, FAILED, DAILY,
     "ingest", "probe_failed"),
    ("probe failed, blind ingest in flight",
     {"acked_fp": "A", "acked_at": ago(2 * H), "dispatched_fp": sp.UNPROBED,
      "dispatched_at": ago(20 * timedelta(minutes=1)), "attempts": 1},
     FAILED, DAILY, "wait", "probe_failed; ingest in flight"),
    ("probe failed, blind ingest acknowledged -> max-age runs only",
     {"acked_fp": sp.UNPROBED, "acked_at": ago(3 * H), "dispatched_fp": sp.UNPROBED,
      "dispatched_at": ago(3 * H), "attempts": 0},
     FAILED, DAILY, "skip", "probe failing"),
    ("probe failed and blind ingest acknowledged long ago",
     {"acked_fp": sp.UNPROBED, "acked_at": ago(21 * H)}, FAILED, DAILY,
     "ingest", "probe_failed"),
    ("FantasyCalc change inside min_interval",
     {"acked_fp": "A", "acked_at": ago(2 * H)}, ok("B"), sp.POLICIES["fantasycalc"],
     "wait", "changed; inside min_interval"),
    ("FantasyCalc change after min_interval",
     {"acked_fp": "A", "acked_at": ago(7 * H)}, ok("B"), sp.POLICIES["fantasycalc"],
     "ingest", "changed"),
    ("FantasyCalc unchanged past max age",
     {"acked_fp": "A", "acked_at": ago(25 * H)}, ok("A"), sp.POLICIES["fantasycalc"],
     "ingest", "max_age"),
]


def scenario_failures(decide_fn):
    bad = []
    for name, state, probe, policy, action, reason in SCENARIOS:
        got = decide_fn(state, probe, NOW, policy)
        if got["action"] != action or not got["reason"].startswith(reason):
            bad.append((name, got))
    return bad


class DecideTest(unittest.TestCase):
    def test_scenarios(self):
        self.assertEqual(scenario_failures(sp.decide), [])

    def test_a_rule_that_ignores_max_age_is_caught(self):
        def broken(state, probe, now, policy):
            if probe.get("ok") and state and probe["fingerprint"] == state.get("acked_fp"):
                return {"action": "skip", "reason": "unchanged"}
            return sp.decide(state, probe, now, policy)
        names = [n for n, _ in scenario_failures(broken)]
        self.assertIn("unchanged but past max age", names)

    def test_a_rule_that_skips_when_the_probe_fails_is_caught(self):
        def broken(state, probe, now, policy):
            if not probe.get("ok"):
                return {"action": "skip", "reason": "unchanged"}
            return sp.decide(state, probe, now, policy)
        self.assertIn("probe failed", [n for n, _ in scenario_failures(broken)])

    def test_a_rule_that_never_retries_is_caught(self):
        def broken(state, probe, now, policy):
            got = sp.decide(state, probe, now, policy)
            return {"action": "wait", "reason": "x"} if got["reason"] == "retry" else got
        self.assertIn("changed, last ingest never acked -> retry",
                      [n for n, _ in scenario_failures(broken)])

    def test_a_rule_that_retries_forever_is_caught(self):
        def broken(state, probe, now, policy):
            return sp.decide(state, probe, now, sp.Policy(max_age=policy.max_age, max_attempts=10**6))
        self.assertIn("changed, ingest failed max_attempts times -> rest",
                      [n for n, _ in scenario_failures(broken)])

    def test_every_source_has_a_policy_and_an_ingest(self):
        self.assertEqual(set(sp.POLICIES), set(sp.INGEST))
        self.assertEqual(set(sp.POLICIES), set(sp.PROBES))
        self.assertEqual(set(sp.SOURCES), set(csv_mod.CHAIN_SOURCES))


class BookkeepingTest(unittest.TestCase):
    def test_dispatch_then_retry_counts_attempts_and_ack_resets(self):
        row = sp.apply_decision(None, "cbs", ok("B"), {"action": "ingest", "reason": "first"}, NOW)
        self.assertEqual((row["dispatched_fp"], row["attempts"]), ("B", 1))
        row = sp.apply_decision(row, "cbs", ok("B"), {"action": "ingest", "reason": "retry"},
                                NOW + 3 * H)
        self.assertEqual(row["attempts"], 2)
        row = sp.apply_ack(row, "cbs", "B", NOW + 4 * H)
        self.assertEqual((row["acked_fp"], row["attempts"]), ("B", 0))
        self.assertEqual(sp.decide(row, ok("B"), NOW + 5 * H, DAILY)["action"], "skip")

    def test_failed_probe_dispatch_is_recorded_as_unprobed(self):
        row = sp.apply_decision({"acked_fp": "A", "acked_at": ago(H)}, "espn", FAILED,
                                {"action": "ingest", "reason": "probe_failed"}, NOW)
        self.assertEqual(row["dispatched_fp"], sp.UNPROBED)
        self.assertIsNone(row.get("last_fp"))  # a failed probe never overwrites last_fp

    def test_chain_runs_only_for_new_content(self):
        self.assertTrue(sp.ack_changes_content("A", "B"))
        self.assertTrue(sp.ack_changes_content(None, "B"))
        self.assertFalse(sp.ack_changes_content("A", "A"))       # max-age re-run
        self.assertFalse(sp.ack_changes_content("A", sp.UNPROBED))  # blind run
        self.assertFalse(sp.ack_changes_content("A", ""))

    def test_probe_and_ack_write_disjoint_columns(self):
        # An ack landing during a probe run must survive the probe's write.
        self.assertFalse({"acked_fp", "acked_at"} & set(sp.PROBE_COLUMNS))
        self.assertFalse({"last_fp", "dispatched_fp", "dispatched_at"} & set(sp.ACK_COLUMNS))

    def test_file_store_keeps_an_ack_written_mid_probe(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            store = sp.FileStore(Path(d) / "state.json")
            stale = store.load().get("cbs")  # probe loads state (empty)
            store.save_row(sp.apply_ack(None, "cbs", "B", NOW), sp.ACK_COLUMNS)  # ack lands
            store.save_row(sp.apply_decision(stale, "cbs", ok("B"),
                                             {"action": "skip", "reason": "x"}, NOW),
                           sp.PROBE_COLUMNS)  # probe writes its (stale) row
            self.assertEqual(store.load()["cbs"]["acked_fp"], "B")


# --------------------------------------------------------------------------
# Fingerprints (fake fetch, no network)
# --------------------------------------------------------------------------

class FakeFetch:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def __call__(self, url, headers=None):
        self.calls.append((url, headers or {}))
        for key, val in self.pages.items():
            if key in url:
                if isinstance(val, sp.Resp):
                    return val
                return sp.Resp(200, {"ETag": 'W/"x"'}, val)
        return sp.Resp(404, {}, "")


def fc_body(values, order=None):
    rows = [{"player": {"id": i, "name": f"P{i}"}, "value": v} for i, v in values.items()]
    if order == "reverse":
        rows.reverse()
    return json.dumps(rows)


FC_VALUES = {i: 10000 - i for i in range(150)}


def article(tables, chrome="ad-1", modified="2026-10-06T16:31:34+00:00", title="Week 5 trade chart"):
    return (f"<html><title>{title}</title><script>{chrome}</script>"
            f'<script type="application/ld+json">{{"dateModified": "{modified}"}}</script>'
            f'<div class="TableBuilder"></div><table><tr><td>{tables}</td></tr></table></html>')


class FingerprintTest(unittest.TestCase):
    def fp(self, source, pages, week=5):
        return sp.run_probe(source, FakeFetch(pages), week)

    def test_fantasycalc_order_does_not_matter_values_do(self):
        a = self.fp("fantasycalc", {"fantasycalc": fc_body(FC_VALUES)})
        b = self.fp("fantasycalc", {"fantasycalc": fc_body(FC_VALUES, "reverse")})
        moved = {**FC_VALUES, 3: 9000}
        c = self.fp("fantasycalc", {"fantasycalc": fc_body(moved)})
        self.assertTrue(a["ok"], a)
        self.assertEqual(a["fingerprint"], b["fingerprint"])
        self.assertNotEqual(a["fingerprint"], c["fingerprint"])

    def test_fantasycalc_short_list_fails_the_probe(self):
        r = self.fp("fantasycalc", {"fantasycalc": fc_body({1: 5})})
        self.assertFalse(r["ok"])

    @staticmethod
    def article_probe(source, pages, week=5, found=None):
        """Probe with a stub discovery (the real one is the ingest's own,
        pull_<source>.discover_url, tested by the discovery lane)."""
        def discover(wk, fetch_fn):
            url = found or f"https://example.test/{source}-week-{wk}/"
            st, _ = fetch_fn(url)
            if st != 200:
                raise RuntimeError("not found")
            return url
        fn = sp.probe_cbs if source == "cbs" else sp.probe_fantasypros
        try:
            return {"ok": True, **fn(FakeFetch(pages), week, discover=discover)}
        except sp.ProbeError as e:
            return {"ok": False, "error": str(e)}

    def test_article_chrome_does_not_move_the_fingerprint_tables_do(self):
        base = self.article_probe("fantasypros", {"week-5": article("Bijan 70")})
        chrome = self.article_probe("fantasypros", {"week-5": article("Bijan 70", chrome="ad-2")})
        edited = self.article_probe("fantasypros", {"week-5": article("Bijan 68")})
        self.assertTrue(base["ok"], base)
        self.assertEqual(base["fingerprint"], chrome["fingerprint"])
        self.assertNotEqual(base["fingerprint"], edited["fingerprint"])

    def test_hashing_the_whole_page_is_caught(self):
        # Broken variant: a body hash moves on every request's ad markup.
        a, b = article("Bijan 70"), article("Bijan 70", chrome="ad-2")
        self.assertNotEqual(sp.digest(a), sp.digest(b))
        self.assertEqual(sp.tables_hash(a), sp.tables_hash(b))

    def test_a_new_week_article_moves_the_fingerprint(self):
        # Discovery returns last week's article until the new one is up; the
        # week is read from the page headline, not the slug.
        old = self.article_probe("cbs", {"cbs-week-4": article("x", title="Week 4 trade chart")},
                                 found="https://example.test/cbs-week-4/")
        new = self.article_probe("cbs", {"2026-week-5": article("y")},
                                 found="https://example.test/dave-richards-2026-week-5-trade-chart/")
        self.assertEqual((old["signals"]["week"], new["signals"]["week"]), (4, 5))
        self.assertNotEqual(old["fingerprint"], new["fingerprint"])

    def test_probes_use_the_ingests_own_discovery(self):
        # A probe that guessed slugs fingerprinted CBS Week 4 while Week 5 was
        # up under a new slug (2026-10-08). Without an injected discover, each
        # article probe must call its ingest module's discover_url.
        import types
        called = []

        def fake_module(name):
            def discover_url(wk, fetch_fn):
                called.append(name)
                fetch_fn("https://example.test/week-5/")
                return "https://example.test/week-5/"
            return types.SimpleNamespace(discover_url=discover_url,
                                         extract_page_headline=lambda page: None)
        saved = sp._watchdog_module
        sp._watchdog_module = fake_module
        try:
            pages = FakeFetch({"week-5": article("x")})
            sp.probe_cbs(pages, 5)
            sp.probe_fantasypros(pages, 5)
            sp.probe_usatoday(pages, 5, datetime(2026, 10, 8).date())
        finally:
            sp._watchdog_module = saved
        self.assertEqual(called, ["pull_cbs", "pull_fantasypros", "pull_usatoday"])
        self.assertFalse(hasattr(sp, "CBS_SLUG") or hasattr(sp, "FP_SLUG") or hasattr(sp, "USAT_SLUG"))

    def test_week_not_out_yet_falls_back_to_last_week(self):
        class NotOut(RuntimeError):
            quiet = True

        class Unreadable(RuntimeError):
            quiet = False

        def discover_for(exc):
            def discover(wk, fetch_fn):
                if wk == 5:
                    raise exc("week 5 not published")
                fetch_fn("https://example.test/week-4/")
                return "https://example.test/week-4/"
            return discover
        pages = FakeFetch({"week-4": article("x", title="Week 4 trade chart")})
        r = sp.probe_cbs(pages, 5, discover=discover_for(NotOut))
        self.assertEqual(r["signals"]["week"], 4)
        with self.assertRaises(sp.ProbeError):  # listing unreadable: a real failure
            sp.probe_cbs(pages, 5, discover=discover_for(Unreadable))

    def test_discovery_failure_is_a_failed_probe(self):
        self.assertFalse(self.article_probe("fantasypros", {})["ok"])

    def test_page_without_a_week_in_the_headline_is_not_accepted(self):
        r = self.article_probe("fantasypros", {"week-5": article("x", title="Trade chart")})
        self.assertFalse(r["ok"])

    def test_cbs_revision_moves_the_fingerprint_and_etag_alone_does_not(self):
        page = article("Zay Flowers 26")
        a = self.article_probe("cbs", {"week-5": page})
        b = self.article_probe("cbs", {"week-5": sp.Resp(200, {"ETag": 'W/"other"'}, page)})
        c = self.article_probe("cbs", {"week-5": article("Zay Flowers 27",
                                                         modified="2026-09-30T17:33:52+00:00")})
        self.assertEqual(a["fingerprint"], b["fingerprint"])
        self.assertNotEqual(a["fingerprint"], c["fingerprint"])

    def test_cbs_probe_and_ingest_read_www_not_the_cdn_mirror(self):
        # sportsfly.cbsistatic.com served a day-old Week-4 revision on 2026-10-08.
        import pull_cbs
        self.assertNotIn("sportsfly", pull_cbs.SLUG)
        f = FakeFetch({"week-5": article("x")})
        sp.probe_cbs(f, 5, discover=lambda wk, fetch_fn: (fetch_fn("https://example.test/week-5/"),
                                                         "https://example.test/week-5/")[1])
        self.assertEqual(f.calls[0][1].get("Accept-Encoding"), "identity")

    def test_usatoday_uses_sitemap_lastmod(self):
        url = "https://www.usatoday.com/story/x/fantasy-trade-value-charts-week-5-ros-rankings/1/"

        def sitemap(lastmod):
            return f"<urlset><url><loc>{url}</loc><lastmod>{lastmod}</lastmod></url></urlset>"

        def discover(wk, fetch_fn):  # stand-in for pull_usatoday.discover_url
            st, body = fetch_fn(sp.USAT_SITEMAP % (2026, 10))
            if st != 200 or url not in body:
                raise RuntimeError("no article")
            return url
        today = datetime(2026, 10, 8).date()
        a = sp.probe_usatoday(FakeFetch({"2026-10": sitemap("2026-10-06T21:36:56Z")}), 5, today, discover)
        b = sp.probe_usatoday(FakeFetch({"2026-10": sitemap("2026-10-07T09:00:00Z")}), 5, today, discover)
        self.assertEqual((a["signals"]["week"], a["signals"]["lastmod"]), (5, "2026-10-06T21:36:56Z"))
        self.assertNotEqual(a["fingerprint"], b["fingerprint"])
        with self.assertRaises(sp.ProbeError):
            sp.probe_usatoday(FakeFetch({}), 5, today, discover)

    def test_razzball_stamp_moves_the_fingerprint(self):
        def page(stamp):
            return f"<p>Updated: {stamp}</p><table><tr><td>Josh Allen 22.1</td></tr></table>"
        a = self.fp("razzball", {"razzball": page("2026-10-07 11:07:17 PM EST")})
        b = self.fp("razzball", {"razzball": page("2026-10-08 11:02:01 PM EST")})
        self.assertTrue(a["ok"], a)
        self.assertNotEqual(a["fingerprint"], b["fingerprint"])
        self.assertFalse(self.fp("razzball", {"razzball": "<table></table>"})["ok"])

    def test_espn_hashes_projection_blocks_only(self):
        def body(total, actual):
            return json.dumps({"players": [{"id": 1, "player": {"stats": [
                {"seasonId": 2026, "statSourceId": 1, "statSplitTypeId": 1,
                 "scoringPeriodId": 6, "appliedTotal": total},
                {"seasonId": 2026, "statSourceId": 0, "statSplitTypeId": 1,
                 "scoringPeriodId": 5, "appliedTotal": actual}]}}]})
        a = self.fp("espn", {"espn": body(14.2, 3.0)})
        b = self.fp("espn", {"espn": body(14.2, 9.0)})
        c = self.fp("espn", {"espn": body(15.0, 3.0)})
        self.assertEqual(a["fingerprint"], b["fingerprint"])
        self.assertNotEqual(a["fingerprint"], c["fingerprint"])

    def test_network_failure_is_a_failed_probe_not_a_crash(self):
        r = sp.run_probe("cbsros", lambda url, headers=None: sp.Resp(None, {}, "timeout"), 5)
        self.assertFalse(r["ok"])
        self.assertIn("cbsros", r["error"])


# --------------------------------------------------------------------------
# Wiring: workflows, migration, vintage check
# --------------------------------------------------------------------------

def step_block(text, name):
    m = re.search(rf"^(\s*)- name: {re.escape(name)}\s*$", text, re.M)
    if not m:
        return None
    rest = text[m.end():]
    nxt = re.search(rf"^{m.group(1)}- ", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


class WiringTest(unittest.TestCase):
    def test_each_ingest_takes_probe_fp_and_acknowledges_its_own_source(self):
        for source, (wf, inputs) in sp.INGEST.items():
            text = (WF / wf).read_text()
            self.assertRegex(text, r"\n      probe_fp:\n", wf)
            ack = step_block(text, "Acknowledge probe fingerprint")
            self.assertIsNotNone(ack, wf)
            self.assertIn("success()", ack)
            self.assertIn("github.event.inputs.probe_fp != ''", ack)
            want = "${{ matrix.source }}" if "source" in inputs else source
            self.assertIn(f"source_probe.py ack --supabase --source {want} ", ack, wf)
            chain = step_block(text, "Dispatch the rebuild chain on new content")
            self.assertIn("steps.ack.outputs.new_content == 'true'", chain, wf)
            self.assertIn("gh workflow run rebuild-chain.yml", chain, wf)
            self.assertRegex(text, r"\n  actions: write", wf)
            # The ack sits after the monitored-check step: an ack failure must
            # not be recorded as an ingest failure.
            rec = [m.start() for m in re.finditer(r"- name: Record (the )?monitored check", text)]
            self.assertTrue(rec and rec[-1] < text.index("- name: Acknowledge probe fingerprint"), wf)

    def test_dispatch_args_match_declared_inputs(self):
        for source, (wf, _inputs) in sp.INGEST.items():
            text = (WF / wf).read_text()
            argv = sp.dispatch_args(source, "fp1")
            self.assertEqual(argv[:3], ["workflow", "run", wf])
            for key in [a.split("=", 1)[0] for a in argv[3:] if a != "-f"]:
                self.assertRegex(text, rf"\n      {key}:\n", f"{wf} lacks input {key}")
            self.assertIn("probe_fp=fp1", argv)

    def test_fantasycalc_bake_is_per_pull_not_per_day(self):
        # A date-only bake_id lets a later same-day save overwrite the Tuesday
        # 12:00 UTC cut pull that week history selects.
        text = (WF / "fantasycalc-weekly-save.yml").read_text()
        self.assertIn('--bake-id "$bake"', text)
        self.assertIn("date -u +%Y-%m-%dt%H%M", text)

    def test_probe_workflow_is_pg_cron_owned_and_dispatches(self):
        text = (WF / "source-probe.yml").read_text()
        self.assertNotRegex(text, r"(?m)^\s*schedule:")
        self.assertIn("actions: write", text)
        self.assertIn("source_probe.py probe", text)

    def test_migration_schedules_every_source_and_retires_the_blind_timers(self):
        sql = MIGRATION.read_text()
        groups = re.findall(r"cron\.schedule\('(source-probe-[a-z-]+)', '([^']+)',\s*\$\$.*?"
                            r"\"sources\": \"([^\"]+)\"", sql, re.S)
        covered = {s for _, _, srcs in groups for s in srcs.split(",")}
        self.assertEqual(covered, set(sp.SOURCES))
        for job in ("trade-chart-ingest-live", "trigger-espn-sync-live", "trigger-cbsros-sync-live",
                    "trigger-cbsros-sync-retry", "razzball-sync-live", "rebuild-chain-live"):
            self.assertIn(f"'{job}'", sql.split("cron.unschedule")[1])
        unsched = sql.split("cron.unschedule")[1].split(");")[0]
        for kept in ("rebuild-chain-bake-live", "trigger-fantasycalc-weekly-save", "vintage-check-live"):
            self.assertNotIn(kept, unsched)
        # Projection probes reach 23:25 UTC so Monday changes land in week N.
        proj = dict((g[0], g[1]) for g in groups)["source-probe-projections"]
        self.assertEqual(proj, "25 3-23/4 * * *")

    def test_max_age_plus_slot_gap_keeps_a_daily_projection_save(self):
        # Projection slots are 4 h apart: max age + one slot must stay <= 24 h,
        # so every UTC day (Monday included) has a snapshot.
        for s in ("espn", "cbsros", "razzball"):
            self.assertLessEqual(sp.POLICIES[s].max_age + 4 * H, 24 * H, s)


class VintageCheckTest(unittest.TestCase):
    """The hourly vintage check read `public.<table>` through PostgREST, which
    404s; every run failed safe to changed=True and dispatched the chain."""

    ROWS = {
        "source_trade_values": [
            {"id": 1, "source": "fantasycalc", "variant": "as_published", "week": 4, "bake_id": "a",
             "created_at": "2026-10-05T15:00:00Z", "source_content_date": None},
            {"id": 2, "source": "fantasycalc", "variant": "as_published", "week": 5, "bake_id": "b",
             "created_at": "2026-10-06T14:20:00Z", "source_content_date": None},
            {"id": 3, "source": "fantasycalc", "variant": "as_published", "week": None,
             "bake_id": "z", "created_at": "2026-10-07T00:00:00Z", "source_content_date": None},
        ],
    }

    def fake_client(self, table, params):
        if "." in table:  # PostgREST: "public.x" is looked up as public."public.x"
            raise SystemExit(f"404 Could not find the table 'public.{table}'")
        rows = [r for r in self.ROWS[table] if f"source=eq.{r['source']}" in params]
        m = re.search(r"&week=eq\.(\d+)", params)
        if m:
            rows = [r for r in rows if r["week"] == int(m.group(1))]
        if "week=not.is.null" in params:
            rows = sorted((r for r in rows if r["week"] is not None), key=lambda r: -r["week"])[:1]
        return rows

    def setUp(self):
        self.saved = (csv_mod._get_supabase_rows, csv_mod._get_supabase_page, dict(csv_mod.SOURCE_TABLES))
        csv_mod._get_supabase_rows = self.fake_client
        csv_mod._get_supabase_page = self.fake_client

    def tearDown(self):
        csv_mod._get_supabase_rows, csv_mod._get_supabase_page = self.saved[:2]
        csv_mod.SOURCE_TABLES.clear()
        csv_mod.SOURCE_TABLES.update(self.saved[2])

    def test_reads_the_latest_week_server_side(self):
        self.assertEqual(csv_mod.get_current_vintage("fantasycalc"), "Week 5")

    def test_table_names_are_bare(self):
        self.assertFalse([t for t in csv_mod.SOURCE_TABLES.values() if "." in t])

    def test_schema_qualified_names_are_caught(self):
        csv_mod.SOURCE_TABLES["fantasycalc"] = "public.source_trade_values"  # the pre-fix state
        with self.assertRaises(SystemExit):
            csv_mod.get_current_vintage("fantasycalc")


if __name__ == "__main__":
    unittest.main()


class RevisionSaveTest(unittest.TestCase):
    """A probe-detected article revision must reach the database as a new bake;
    otherwise the ingest acknowledges a change it never saved."""

    def test_fantasypros_revision_is_saved_not_skipped(self):
        import pull_fantasypros as fp
        src = (ROOT / "ops" / "watchdog" / "pull_fantasypros.py").read_text()
        # The pre-fix rule: any saved row for the week skipped the save.
        self.assertNotIn('print("week %d already saved (%d rows); skipping"', src)
        rows = [
            {"player_key": 1, "native_value": 70.0, "bake_id": "old", "created_at": "2026-10-06T16:00:00Z"},
            {"player_key": 1, "native_value": 68.0, "bake_id": "new", "created_at": "2026-10-07T21:23:00Z"},
            {"player_key": 2, "native_value": 40.0, "bake_id": "new", "created_at": "2026-10-07T21:23:00Z"},
        ]
        saved = fp.values_of_latest_bake(rows)
        self.assertEqual(saved, {1: 68.0, 2: 40.0})
        self.assertIsNone(fp.content_diff(saved, {1: 68.0, 2: 40.0}))
        self.assertEqual(fp.content_diff(saved, {1: 69.0, 2: 40.0}), "0 added, 0 removed, 1 changed")
        self.assertEqual(fp.content_diff(saved, {1: 68.0}), "0 added, 1 removed, 0 changed")

    def test_comparing_against_an_older_bake_is_caught(self):
        import pull_fantasypros as fp
        rows = [
            {"player_key": 1, "native_value": 70.0, "bake_id": "old", "created_at": "2026-10-06T16:00:00Z"},
            {"player_key": 1, "native_value": 68.0, "bake_id": "new", "created_at": "2026-10-07T21:23:00Z"},
        ]
        oldest = {1: 70.0}  # broken variant: compare with the first bake
        self.assertIsNotNone(fp.content_diff(oldest, {1: 68.0}))
        self.assertIsNone(fp.content_diff(fp.values_of_latest_bake(rows), {1: 68.0}))

    def test_trade_chart_bakes_are_per_pull(self):
        import ingest_usatoday
        import pull_fantasypros as fp
        t1 = datetime(2026, 10, 7, 9, 35, tzinfo=timezone.utc)
        t2 = datetime(2026, 10, 7, 21, 35, tzinfo=timezone.utc)
        self.assertNotEqual(ingest_usatoday.bake_id_fn(5, {}, t1), ingest_usatoday.bake_id_fn(5, {}, t2))
        self.assertEqual(ingest_usatoday.bake_id_fn(5, {}, t1), "usatwk5_2026-10-07t0935_v1")
        self.assertNotEqual(fp.pull_bake_id(5, t1), fp.pull_bake_id(5, t2))
        self.assertTrue(fp.pull_bake_id(5, t1).startswith("fpwk5_2026-10-07t"))


class RowOrderTest(unittest.TestCase):
    def test_tied_rows_reordered_do_not_move_the_hash_values_do(self):
        # CBS rest-of-season pages reorder players tied on points between requests.
        a = "<table><tr><td>Davis Mills 11.4</td></tr><tr><td>Mac Jones 11.4</td></tr></table>"
        b = "<table><tr><td>Mac Jones 11.4</td></tr><tr><td>Davis Mills 11.4</td></tr></table>"
        c = "<table><tr><td>Mac Jones 11.6</td></tr><tr><td>Davis Mills 11.4</td></tr></table>"
        self.assertEqual(sp.tables_hash(a), sp.tables_hash(b))
        self.assertNotEqual(sp.tables_hash(a), sp.tables_hash(c))
        # Broken variant: an order-sensitive text hash reports a change.
        self.assertNotEqual(sp.digest(sp.tables_text(a)), sp.digest(sp.tables_text(b)))
