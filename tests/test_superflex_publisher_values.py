"""Publisher superflex / 2-QB values (GAP-SUPERFLEX-PUBLISHER-VALUES, Jeremy 2026-10-08).

The publishers that state their own superflex values -- FantasyCalc
(numQbs=2, every position), the CBS "2QB" QB column, the USA Today "SFLEX"
QB column and the FantasyPros "2QB Value" QB column -- are saved as
qb_slots = 2 rows and reach the fixture as `native_superflex` on the 12-team
combo, which the engine overlays on the 1-QB natives when the roster has a
superflex slot (curve-widget.js savedPublishedNative).

Each check names the defect it catches and is run against that broken state:

1. Importer: qb_slots = 2 rows never join the 1-QB snapshot (a QB would
   appear twice, or as a NULL-value review row) and ride along as
   `superflex_rows` from the same week and bake only. Broken state: the
   importer before this change (no qb_slots split).
2. Chain: the superflex rows survive match -> reference -> section ->
   reindex -> promote as `native_superflex`, and the 1-QB natives are
   byte-identical with or without them. Broken states: each stage dropping
   them.
3. Promotion: a new publication without superflex values removes the old
   week's `native_superflex` (never an older column beside this week's 1-QB
   values), and invalid superflex values are dropped. Broken state: the
   merge before this change.
4. Savers / parsers: each publisher's superflex column is read (never the
   6-TD / TEP column), qb_slots = 2, `native_value` = the published number,
   and the shared isotonic reindex passes them through instead of failing
   closed. Broken state: the reindex before this change.
5. Same-week ingest guard: a QB's 1-QB and 2-QB values are different keys.
   Broken state: (player_key, scoring) keys, where a changed 1-QB value hid
   behind the unchanged 2-QB value and the write was skipped.
6. Readers that count or date the 1-QB rows (import health, source vintage)
   read qb_slots = 1 only.
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "ops" / "watchdog"))

import build_comparison_source_section as section_mod  # noqa: E402
import build_source_reference as reference_mod  # noqa: E402
import check_source_vintage as vintage_mod  # noqa: E402
import import_supabase_references as importer  # noqa: E402
import ingest_common  # noqa: E402
import match_source_snapshot as match_mod  # noqa: E402
import promote_comparison_section as promote_mod  # noqa: E402
import pull_fantasypros  # noqa: E402
import reindex_comparison_section as reindex_mod  # noqa: E402
import save_usatoday_references as usat  # noqa: E402
import verify_import_health as health_mod  # noqa: E402

FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"


# ---------------------------------------------------------------- 1. importer
def db_row(key, value, *, qb_slots=1, week=5, bake="fcwk5_b2", created="2026-10-08T10:00:00Z", **extra):
    row = {
        "source": "fantasycalc", "variant": "as_published", "player_key": key,
        "player_norm": f"p{key}", "position": "QB" if key == 869 else "RB",
        "scoring": "full", "league_teams": 12, "qb_slots": qb_slots, "season": 2026,
        "week": week, "value": value if qb_slots == 1 else None,
        "native_value": value, "source_content_date": None,
        "pulled_at": "2026-10-08T10:00:00Z", "bake_id": bake, "created_at": created,
    }
    row.update(extra)
    return row


TABLE = [
    db_row(869, 5000),
    db_row(2227, 10624),
    db_row(869, 10904, qb_slots=2),
    db_row(2227, 10379, qb_slots=2),
    # An older bake of the same week: its superflex value must not be read.
    db_row(869, 9000, qb_slots=2, bake="fcwk5_b1", created="2026-10-07T10:00:00Z"),
]


def import_snapshot(rows, source="fantasycalc"):
    saved = (importer.fetch_supabase_rows, importer.fetch_player_names)
    importer.fetch_supabase_rows = lambda table, params: [dict(r) for r in rows]
    importer.fetch_player_names = lambda keys: {869: "Josh Allen", 2227: "Jahmyr Gibbs"}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            result = importer.import_source(source, output_dir=Path(tmp))
            return json.loads(result["snapshot_path"].read_text(encoding="utf-8"))
    finally:
        importer.fetch_supabase_rows, importer.fetch_player_names = saved


def importer_problems(rows=TABLE, source="fantasycalc"):
    snapshot = import_snapshot(rows, source)
    problems = []
    one_qb = sorted((r["source_player_id"], r["value"]) for r in snapshot["rows"])
    if one_qb != [(869, 5000.0), (2227, 10624.0)]:
        problems.append(f"1-QB snapshot rows {one_qb}, want Allen 5000 and Gibbs 10624 once each")
    if snapshot["review_rows"]:
        problems.append(f"superflex rows in the 1-QB review: {snapshot['review_rows'][:2]}")
    superflex = sorted((r["source_player_id"], r["value"]) for r in snapshot.get("superflex_rows", []))
    if superflex != [(869, 10904.0), (2227, 10379.0)]:
        problems.append(f"superflex_rows {superflex}, want this bake's Allen 10904 / Gibbs 10379")
    return problems


def cbs_rows():
    def cbs(key, value, qb_slots=1, scoring="ppr"):
        return {"source": "cbs", "variant": "as_published", "player_key": key,
                "player_norm": f"p{key}", "position": "QB", "scoring": scoring,
                "league_teams": 12, "qb_slots": qb_slots, "season": 2026, "week": 4,
                "value": value, "native_value": value, "source_content_date": None,
                "pulled_at": "2026-10-01T10:00:00Z", "bake_id": None}
    return [cbs(869, 23), cbs(2227, 50), cbs(869, 50, qb_slots=2)]


class ImporterSplit(unittest.TestCase):
    def test_superflex_rows_are_carried_apart(self):
        self.assertEqual(importer_problems(), [])

    def test_cbs_two_qb_rows_never_join_the_one_qb_snapshot(self):
        snapshot = import_snapshot(cbs_rows(), "cbs")
        self.assertEqual(sorted(r["value"] for r in snapshot["rows"]), [23.0, 50.0])
        self.assertEqual([(r["source_player_id"], r["value"]) for r in snapshot["superflex_rows"]],
                         [(869, 50.0)])

    def test_no_superflex_rows_keeps_the_snapshot_shape(self):
        """Byte identity for every source that saves no superflex rows."""
        snapshot = import_snapshot([r for r in TABLE if r["qb_slots"] == 1])
        self.assertNotIn("superflex_rows", snapshot)
        self.assertNotIn("superflex_review_rows", snapshot)

    def test_guard_catches_the_unsplit_importer(self):
        saved = importer.split_qb_slots
        importer.split_qb_slots = lambda rows: (rows, [])  # origin/main: no split
        try:
            fc = importer_problems()
            # CBS: the 2QB value would sit beside the 1QB-4 value for Allen.
            cbs = import_snapshot(cbs_rows(), "cbs")
        finally:
            importer.split_qb_slots = saved
        print(f"\n[superflex importer negative] {len(fc)} problems, e.g. {fc[:1]}")
        self.assertGreater(len(fc), 0)
        self.assertEqual(sorted(r["value"] for r in cbs["rows"]), [23.0, 50.0, 50.0])


# ---------------------------------------------------------------- 2. chain
def snapshot_doc():
    def row(name, pos, value):
        return {"player_name": name, "pos": pos, "team": None, "scoring": "ppr", "teams": 12,
                "value": value, "native_value": value, "source_player_id": 1}
    return {
        "schema": "trade-value-source-snapshot-v1", "source": "fantasycalc",
        "fetched_at": "2026-10-08T00:00:00Z", "source_url": None,
        "default_scoring": None, "default_teams": 12,
        "rows": [row("Josh Allen", "QB", 5000.0), row("Jahmyr Gibbs", "RB", 10624.0)],
        "superflex_rows": [{**row("Josh Allen", "QB", 10904.0), "qb_slots": 2},
                           {**row("Jahmyr Gibbs", "RB", 10379.0), "qb_slots": 2}],
        "superflex_review_rows": [],
    }


STAGE_KEYS = {
    "match": ("superflex_matched_rows",),
    "reference": ("superflex_rows",),
}


def run_chain(snapshot, broken_stage=None):
    """snapshot -> match -> reference -> section -> reindex -> promoted combo."""
    def drop(stage, doc):
        if stage == broken_stage:
            for key in STAGE_KEYS.get(stage, ()):
                doc.pop(key, None)
            for combo in (doc.get("combos") or {}).values():
                combo.pop("native_superflex", None)
        return doc

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "snapshot.json").write_text(json.dumps(snapshot))
        matched = drop("match", match_mod.match_snapshot(tmp / "snapshot.json", PLAYERS, use_sleeper=False))
        (tmp / "matched.json").write_text(json.dumps(matched))
        reference = drop("reference", reference_mod.build_references(tmp / "matched.json")[0])
        (tmp / "reference.json").write_text(json.dumps(reference))
        section = drop("section", section_mod.build_section(
            [tmp / "reference.json"], FIXTURE, section_key=None, meta={}))
        (tmp / "section.json").write_text(json.dumps(section))
        reindexed, _review = reindex_mod.reindex_section(str(tmp / "section.json"))
        reindexed = drop("reindex", reindexed)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    combo = copy.deepcopy(fixture["sources"]["fantasycalc"]["combos"]["full_12_qb1"])
    cand = reindexed["combos"]["full_12_qb1"]
    if broken_stage == "promote":
        cand = {k: v for k, v in cand.items() if k != "native_superflex"}
    promote_mod._merge_promoted_combo(combo, cand)
    return section, combo


def chain_problems(broken_stage=None):
    problems = []
    _section, combo = run_chain(snapshot_doc(), broken_stage)
    want = {"josh allen": 10904.0, "jahmyr gibbs": 10379.0}
    if combo.get("native_superflex") != want:
        problems.append(f"promoted native_superflex {combo.get('native_superflex')}, want {want}")
    if combo["native"] != {"jahmyr gibbs": 10624.0, "josh allen": 5000.0}:
        problems.append(f"1-QB natives moved: {combo['native']}")
    return problems


class ChainCarriesSuperflex(unittest.TestCase):
    def test_chain_writes_native_superflex_on_the_twelve_team_combo(self):
        self.assertEqual(chain_problems(), [])

    def test_one_qb_values_identical_with_or_without_superflex(self):
        plain = snapshot_doc()
        plain.pop("superflex_rows")
        plain.pop("superflex_review_rows")
        with_sf, _ = run_chain(snapshot_doc())
        without, _ = run_chain(plain)
        for name, combo in without["combos"].items():
            self.assertEqual(with_sf["combos"][name]["native"], combo["native"])
            self.assertEqual(with_sf["combos"][name]["player_keys"], combo["player_keys"])
            self.assertNotIn("native_superflex", combo)
        self.assertNotIn("superflex_review_rows", without)

    def test_guard_catches_each_stage_dropping_superflex(self):
        for stage in ("match", "reference", "section", "reindex", "promote"):
            problems = chain_problems(broken_stage=stage)
            print(f"\n[superflex chain negative] {stage}: {len(problems)} problems")
            self.assertGreater(len(problems), 0, f"{stage} dropping superflex was NOT caught")


# ---------------------------------------------------------------- 3. promotion
def merge_before_change(new_combo, cand_combo):
    """promote_comparison_section._merge_promoted_combo on origin/main."""
    new_combo["native"] = dict(cand_combo["native"])
    new_combo["reindexed"] = dict(cand_combo["reindexed"])
    new_combo["fit"] = copy.deepcopy(cand_combo["fit"])
    new_combo["n"] = sum(cand_combo["n"].values())
    new_combo["index_total"] = copy.deepcopy(cand_combo["index_total"])
    if "translation" in cand_combo:
        new_combo["translation"] = copy.deepcopy(cand_combo["translation"])


def stale_superflex_problems(merge):
    old = {"native": {"josh allen": 1.0}, "native_superflex": {"josh allen": 99.0}}
    cand = {"native": {"josh allen": 2.0}, "reindexed": {"josh allen": 3.0},
            "fit": {}, "n": {"QB": 1}, "index_total": {}}
    merge(old, cand)
    return [f"last week's native_superflex kept: {old['native_superflex']}"] if "native_superflex" in old else []


class PromotionMerge(unittest.TestCase):
    def test_new_publication_without_superflex_removes_the_old(self):
        self.assertEqual(stale_superflex_problems(promote_mod._merge_promoted_combo), [])

    def test_guard_catches_the_merge_before_change(self):
        self.assertGreater(len(stale_superflex_problems(merge_before_change)), 0)

    def test_exclusion_gate_drops_invalid_superflex_values(self):
        section = {"combos": {"full_12_qb1": {
            "native": {"josh allen": 5000.0}, "player_keys": {"josh allen": 869},
            "native_superflex": {"josh allen": 10904.0, "jahmyr gibbs": -1.0, "nobody": 3.0}}}}
        gated, hidden = promote_mod.apply_exclusion_gate(section, {"jahmyr gibbs": 2227})
        self.assertEqual(gated["combos"]["full_12_qb1"]["native_superflex"], {"josh allen": 10904.0})
        self.assertEqual(hidden, 0)  # the count describes the 1-QB rows


# ---------------------------------------------------------------- 4. savers / parsers
USAT_PAYLOAD = {"tables": [
    {"title": "Quarterback trade value chart", "headers": ["RK", "Player", "1QB", "6-TD", "SFLEX"],
     "rows": [["1", "Josh Allen", "36", "42", "69"], ["2", "Lamar Jackson", "30", "33", "--"]]},
    {"title": "Running back trade value chart", "headers": ["RK", "Player", "STD", "Half", "PPR"],
     "rows": [["1", "Jahmyr Gibbs", "70", "72", "75"]]},
]}

FP_HTML = (
    "<h2>Quarterback Fantasy Football Trade Value Chart</h2><table>"
    "<tr><td>Name</td><td>Team</td><td>Value</td><td>Change</td><td>2QB Value</td><td>2QB Change</td></tr>"
    "<tr><td>Josh Allen</td><td>BUF</td><td>29.1</td><td>0</td><td>69.5</td><td>0</td></tr></table>"
    "<h2>Tight End Fantasy Football Trade Value Chart</h2><table>"
    "<tr><td>Name</td><td>Team</td><td>Value</td><td>Change</td><td>TEP Value</td><td>TEP Change</td></tr>"
    "<tr><td>Brock Bowers</td><td>LV</td><td>28.0</td><td>0</td><td>33.1</td><td>0</td></tr></table>"
)


class PublisherColumns(unittest.TestCase):
    def test_usa_today_sflex_column_qb_only(self):
        self.assertEqual(usat.parse_superflex(USAT_PAYLOAD), [("Josh Allen", "QB", 69.0)])
        no_column = copy.deepcopy(USAT_PAYLOAD)
        no_column["tables"][0]["headers"][4] = "OTHER"
        self.assertEqual(usat.parse_superflex(no_column), [])

    def test_fantasypros_two_qb_value_never_tep(self):
        self.assertEqual(pull_fantasypros.parse_superflex(FP_HTML), {("Josh Allen", "BUF"): 69.5})
        self.assertEqual(pull_fantasypros.parse_superflex(FP_HTML.replace("2QB Value", "Other")), {})

    def test_reindex_passes_superflex_rows_through(self):
        """Broken state: build_reindex_candidate fails closed on qb_slots != 1,
        so before this change any saver handing it a superflex row aborted."""
        sf = {"source": "usatoday", "variant": "as_published", "player_key": 869,
              "player_norm": "josh allen", "scoring": "full", "league_teams": 12,
              "qb_slots": 2, "season": 2026, "week": 5, "position": "QB",
              "value": 69.0, "native_value": 69.0}
        with self.assertRaises(SystemExit):
            usat.build_reindex_candidate([sf], "b")  # the fail-closed contract stays
        clean, _fx = _usat_fixture_rows()
        final, review = usat.apply_reindex(clean + [sf], [], "b")
        self.assertEqual(review, [])
        passed = [r for r in final if r["qb_slots"] == 2]
        self.assertEqual(passed, [{**sf, "value": None}])
        self.assertEqual(len(final), len(clean) + 1)


def _usat_fixture_rows():
    from tests.test_cbs_usatoday_recurring import UsatodayReindexTest
    return UsatodayReindexTest._fixture_rows()


# ---------------------------------------------------------------- 5. ingest guard
def guard_skips_changed_week(key_fn):
    """DB: Allen 1-QB 36 + 2-QB 69. New pull: Allen 1-QB 40, 2-QB 69 (a real
    1-QB revision). Returns True when the guard would skip the write."""
    def content(rows):
        out = {}
        for r in rows:
            out[key_fn(r)] = float(r["native_value"])
        return out
    existing = content([{"player_key": 869, "scoring": "full", "qb_slots": 1, "native_value": 36},
                        {"player_key": 869, "scoring": "full", "qb_slots": 2, "native_value": 69}])
    new = content([{"player_key": 869, "scoring": "full", "qb_slots": 1, "native_value": 40},
                   {"player_key": 869, "scoring": "full", "qb_slots": 2, "native_value": 69}])
    return set(new) == set(existing) and all(abs(existing[k] - new[k]) <= 1e-9 for k in new)


class IngestGuardKeys(unittest.TestCase):
    def test_one_qb_revision_is_written(self):
        self.assertFalse(guard_skips_changed_week(ingest_common.grain_key))

    def test_guard_catches_scoring_only_keys(self):
        self.assertTrue(guard_skips_changed_week(lambda r: (int(r["player_key"]), str(r["scoring"]))))

    def test_db_read_selects_qb_slots(self):
        seen = []
        db = ingest_common.Db(count_fn=lambda t, p: 0,
                              rows_fn=lambda t, p: seen.append(p) or [
                                  {"player_key": 869, "scoring": "full", "native_value": 36},
                                  {"player_key": 869, "scoring": "full", "qb_slots": 2, "native_value": 69}])
        got = db.grain_native_values("source_trade_values", "usatoday", "as_published", 2026, 5)
        self.assertIn("qb_slots", seen[0])
        self.assertEqual(got, {(869, "full"): 36.0, (869, "full", 2): 69.0})


# ---------------------------------------------------------------- 6. readers
class OneQbReaders(unittest.TestCase):
    def test_import_health_counts_one_qb_rows(self):
        for source in ("fantasycalc", "usatoday", "fantasypros", "cbs"):
            self.assertIn("qb_slots=eq.1", health_mod.SOURCE_CONFIGS[source]["params"], source)

    def test_source_vintage_reads_one_qb_rows(self):
        seen = []
        saved = vintage_mod._get_supabase_rows, vintage_mod._get_supabase_page
        vintage_mod._get_supabase_rows = lambda table, params: seen.append(params) or [
            {"week": 5, "bake_id": None, "source_content_date": None, "created_at": "x"}]
        # The latest-week lookup (refresh-cadence) is a second read; it must
        # carry the 1-QB filter too.
        vintage_mod._get_supabase_page = lambda table, params: seen.append(params) or [{"week": 5}]
        try:
            for source in ("fantasycalc", "cbs"):
                try:
                    vintage_mod.get_current_vintage(source)
                except SystemExit:
                    pass
        finally:
            vintage_mod._get_supabase_rows, vintage_mod._get_supabase_page = saved
        self.assertTrue(seen and all("qb_slots=eq.1" in p for p in seen), seen)


# ---------------------------------------------------------------- 7. engine
# The page with a fixture that carries native_superflex: with the superflex
# slot it plots exactly the Python reference derivation over the overlaid
# natives (tests/test_published_league_settings_engine.expected_derived with
# superflex), and without the slot it is unchanged. Broken state: a widget
# that ignores native_superflex (the overlay line removed).
APP = ROOT / "app" / "trade-value-chart"
OVERLAY_LINE = ('    if (native.size && ValueModel.superflexCount(rosterShape)) '
                'take(savedPublishedRow(key, "native_superflex"));\n')
PAGE_SOURCES = ("fantasycalc", "cbs", "fantasypros", "usatoday")
SET_AND_READ = """([n, keys]) => { const c = window.TradeValueCurveControls;
  c.setScoring('ppr'); c.setTeams(12); c.setRosterSpot('SUPERFLEX', n);
  const maps = window.TradeValueCurveHarness.sourceMaps();
  const d = window.TradeValueCurveDiagnostics || {};
  const out = {fixedPie: d.fixedPieIndexed, derivation: d.publishedDerivation, maps: {}};
  keys.forEach(k => { out.maps[k] = Object.fromEntries([...(maps.get(k) || new Map()).entries()]); });
  return out; }"""


def injected_fixture():
    """The current fixture plus publisher-style superflex values on two charts:
    FantasyCalc (every position, QBs x2.2 / others x0.85, like its numQbs=2
    list) and CBS (QBs only, like its 2QB column)."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    players = {p["player_key"]: p.get("pos") for p in json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]}
    pk = fixture["player_keys"]
    for source, combo_key, qb_only in (("fantasycalc", "full_12_qb1", False), ("cbs", "full_12", True)):
        combo = fixture["sources"][source]["combos"][combo_key]
        sf = {}
        for slug, value in combo["native"].items():
            pos = players.get(pk.get(slug))
            if value is None or (qb_only and pos != "QB"):
                continue
            sf[slug] = round(float(value) * (2.2 if pos == "QB" else 0.85), 1)
        combo["native_superflex"] = sf
    return fixture


def collect_overlay_page(fixture, widget_override=None):
    from tests.test_published_league_settings_render import _chromium_executable, _server
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc
    body = json.dumps(fixture)
    out = {}
    with _server() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable(playwright))
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route("**/assets/comparison-sources-data.json*", lambda route: route.fulfill(
                status=200, content_type="application/json", body=body))
            if widget_override is not None:
                page.route("**/assets/curve-widget.js*", lambda route: route.fulfill(
                    status=200, content_type="text/javascript", body=widget_override))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueCurveHarness && window.TradeValueCurveDiagnostics",
                                   timeout=20000)
            out["sf1"] = page.evaluate(SET_AND_READ, [1, list(PAGE_SOURCES) + ["espn"]])
            out["sf0"] = page.evaluate(SET_AND_READ, [0, list(PAGE_SOURCES)])
            out["errors"] = errors
        finally:
            browser.close()
    return out


def overlay_problems(widget_override=None):
    from unittest import mock
    from functools import partial
    from pipelines.vorp_translation import unified
    from tests.test_published_league_settings_engine import (
        browser_inputs, browser_players)

    fixture = injected_fixture()
    got = collect_overlay_page(fixture, widget_override)
    plain = collect_overlay_page(json.loads(FIXTURE.read_text(encoding="utf-8")))
    problems = [f"page error: {e[:200]}" for e in got["errors"]]
    pos_of = browser_players()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fixture.json"
        path.write_text(json.dumps(fixture))
        loader = partial(unified.load_native_values, fixture_path=path)
        with mock.patch.object(unified, "load_native_values", loader):
            # JEG-508 (VP-6.4): Indexed = the overlaid natives times ONE
            # factor against blended DDF Value (no longer the ESPN anchor):
            # value / overlay native is one constant over the listed players.
            for source in PAGE_SOURCES:
                values = {int(k): v for k, v in got["sf1"]["maps"][source].items()}
                native, _saved, _ = browser_inputs(fixture, pos_of, source, "ppr", superflex=True)
                native = {k: v for k, v in native if v > 0}
                missing = sorted(set(native) - set(values))
                if missing:
                    problems.append(f"superflex {source}: listed players not plotted {missing[:5]}")
                ratios = [values[k] / v for k, v in native.items() if k in values]
                if not ratios or max(ratios) - min(ratios) > 1e-9 * max(ratios):
                    problems.append(f"superflex {source}: Indexed is not one factor on the overlaid natives")
    for source in PAGE_SOURCES:
        if got["sf0"]["maps"][source] != plain["sf0"]["maps"][source]:
            problems.append(f"{source}: values moved without a superflex slot")
    for source in ("fantasycalc", "cbs"):
        if got["sf1"]["maps"][source] == plain["sf1"]["maps"][source]:
            problems.append(f"{source}: publisher superflex values not used (same as derived)")
        note = ((got["sf1"]["derivation"] or {}).get(source) or {}).get("superflex")
        if note != "publisher superflex values":
            problems.append(f"{source}: derivation note {note!r}")
    if got["sf1"]["fixedPie"] is not True:
        problems.append(f"fixedPieIndexed {got['sf1']['fixedPie']} with publisher superflex values")
    return problems


class EngineOverlay(unittest.TestCase):
    def test_page_plots_publisher_superflex_values(self):
        problems = overlay_problems()
        self.assertEqual(problems, [], "\n".join(problems[:20]))

    def test_guard_catches_a_widget_ignoring_native_superflex(self):
        widget = (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        self.assertIn(OVERLAY_LINE, widget)
        problems = overlay_problems(widget.replace(OVERLAY_LINE, ""))
        print(f"\n[superflex overlay negative] {len(problems)} problems, e.g. {problems[:1]}")
        self.assertGreater(len(problems), 0)


if __name__ == "__main__":
    unittest.main()
