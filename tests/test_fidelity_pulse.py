"""Fidelity pulse (JEG-480): every stage turns its source red on a seeded fault.

Hermetic: synthetic publisher pages / API answers built from one table of
values, stored rows and a live chart built from the same table, a fake fetch
and a small canonical player registry. The baseline (publisher == stored ==
chart) must be green for every trade chart; then one fault is seeded per
stage and that source must turn red (or amber where the rule says so).
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import fidelity_pulse as fp  # noqa: E402

NOW = datetime(2026, 10, 8, 23, 0, tzinfo=timezone.utc)
SAVED = "2026-10-08T15:00:00+00:00"
IMPORTED = "2026-10-08T21:00:00Z"

PLAYERS = [
    {"player_key": 1, "full_name": "Josh Allen", "position": "QB", "active": True},
    {"player_key": 2, "full_name": "Jahmyr Gibbs", "position": "RB", "active": True},
    {"player_key": 3, "full_name": "Ja'Marr Chase", "position": "WR", "active": True},
    {"player_key": 4, "full_name": "Brock Bowers", "position": "TE", "active": True},
    {"player_key": 5, "full_name": "Kenneth Walker III", "position": "RB", "active": True},
    {"player_key": 6, "full_name": "Tyreek Hill", "position": "WR", "active": True},
]
UNIVERSE = {"josh allen": 1, "jahmyr gibbs": 2, "jamarr chase": 3, "brock bowers": 4, "kenneth walker iii": 5}

# key -> (publisher spelling, pos, {scoring: value}, superflex value or None)
CHART = {
    1: ("Josh Allen", "QB", {"std": 36, "half": 36, "full": 36}, 72),
    2: ("Jahmyr Gibbs", "RB", {"std": 72, "half": 74, "full": 77}, None),
    3: ("Ja'Marr Chase", "WR", {"std": 65, "half": 67, "full": 69}, None),
    4: ("Brock Bowers", "TE", {"std": 59, "half": 61, "full": 64}, None),
    5: ("Kenneth Walker", "RB", {"std": 69, "half": 71, "full": 73}, None),
}
CBS = {
    1: ("Josh Allen", "QB", {"std": 22, "half": 22, "full": 22}, 48),
    2: ("Jahmyr Gibbs", "RB", {"std": 51, "half": 52.5, "full": 54}, None),
    3: ("Ja'Marr Chase", "WR", {"std": 43, "half": 44.5, "full": 46}, None),
    4: ("Brock Bowers", "TE", {"std": 28, "half": 29.5, "full": 31}, None),
    5: ("Kenneth Walker III", "RB", {"std": 47, "half": 48.5, "full": 50}, None),
}
FP = {
    1: ("Josh Allen", "QB", {"std": 29.1, "half": 29.1, "full": 29.1}, 69.5),
    2: ("Jahmyr Gibbs", "RB", {"std": 75.1, "half": 75.1, "full": 75.1}, None),
    3: ("Ja’Marr Chase", "WR", {"std": 57.1, "half": 57.1, "full": 57.1}, None),
    4: ("Brock Bowers", "TE", {"std": 28.0, "half": 28.0, "full": 28.0}, None),
    5: ("Kenneth Walker III", "RB", {"std": 60.9, "half": 60.9, "full": 60.9}, None),
}


def fc_values():
    """FantasyCalc: every position has a 1-QB and a 2-QB value per scoring; 40 filler players
    so the list has a churn line and the column check has enough shared players."""
    out = {}
    base = {1: 6081, 2: 10567, 3: 9900, 4: 5200, 5: 8000}
    for k, b in base.items():
        name, pos = {1: ("Josh Allen", "QB"), 2: ("Jahmyr Gibbs", "RB"), 3: ("Ja'Marr Chase", "WR"),
                     4: ("Brock Bowers", "TE"), 5: ("Kenneth Walker III", "RB")}[k]
        out[k] = (name, pos, {"std": b - 10, "half": b, "full": b + 10},
                  {"std": b * 2 - 10 if pos == "QB" else b - 500, "half": b * 2 if pos == "QB" else b - 490,
                   "full": b * 2 + 10 if pos == "QB" else b - 480})
    return out


FILLER = [{"player_key": 100 + i, "full_name": f"Filler Player{i}", "position": "WR", "active": True} for i in range(40)]
FC = fc_values()
for i in range(40):
    FC[100 + i] = (f"Filler Player{i}", "WR", {"std": 1000 + 50 * i, "half": 1100 + 50 * i, "full": 1300 + 50 * i},
                   {"std": 900 + 40 * i, "half": 950 + 40 * i, "full": 1000 + 40 * i})

TABLES = {"usatoday": CHART, "cbs": CBS, "fantasypros": FP, "fantasycalc": FC}
URLS = {
    "usatoday": "https://www.usatoday.com/story/sports/fantasy/football/2026/10/06/fantasy-trade-value-charts-week-5-ros-rankings/92125556007/",
    "cbs": "https://www.cbssports.com/fantasy/football/news/dave-richards-2026-week-5-trade-chart/",
    "fantasypros": "https://www.fantasypros.com/2026/09/fantasy-football-trade-value-chart-week-5-2026/",
}
POS_WORD = {"QB": "quarterback", "RB": "running back", "WR": "wide receiver", "TE": "tight end"}


def fmt(v):
    return str(int(v)) if float(v).is_integer() else str(v)


def ld(modified="2026-10-06T21:36:46Z"):
    return f'<script type="application/ld+json">{{"datePublished":"2026-10-06T21:36:46Z","dateModified":"{modified}"}}</script>'


def usatoday_html(table, week=5, modified="2026-10-06T21:36:46Z"):
    parts = [f"<html><head><title>Fantasy football trade value charts: Week {week} (2026)</title>{ld(modified)}</head><body>"]
    for pos in ("QB", "RB", "WR", "TE"):
        head = ["RK", "Player", "1QB", "6/TD", "SFLEX"] if pos == "QB" else ["RK", "Player", "STD", "Half",
                                                                           "PPR" if pos == "RB" else "Full"]
        parts.append(f"<h2>Week {week} {POS_WORD[pos]} trade value chart</h2><table class=gnt_ar_b_tbl><tr>"
                     + "".join(f"<th>{h}</th>" for h in head) + "</tr>")
        for i, (name, p, vals, sf) in enumerate(v for v in table.values() if v[1] == pos):
            cells = [str(i + 1), name] + ([fmt(vals["std"]), "99", fmt(sf)] if pos == "QB"
                                          else [fmt(vals[s]) for s in ("std", "half", "full")])
            parts.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        parts.append("</table>")
    return "".join(parts) + "</body></html>"


def cbs_html(table, week=5, modified="2026-10-07T17:44:10+00:00"):
    parts = [f"<html><head><title>Dave Richard's Fantasy football trade value chart for Week {week} - CBS Sports</title>"
             f"{ld(modified)}</head><body><svg><title>ChevronDown</title></svg>"]
    for pos in ("QB", "RB", "WR", "TE"):
        head = ["Player", "tm", "1QB-4", "1QB-6", "2QB"] if pos == "QB" else ["Player", "tm", "non", "0.5", "PPR"]
        parts.append(f"<h3>{POS_WORD[pos].capitalize()} trade values</h3><table class=TableBuilder><tr>"
                     + "".join(f"<td>{h}</td>" for h in head) + "</tr>")
        for name, p, vals, sf in (v for v in table.values() if v[1] == pos):
            cells = [name, "XX"] + ([fmt(vals["std"]), "1", fmt(sf)] if pos == "QB"
                                    else [fmt(vals[s]) for s in ("std", "half", "full")])
            parts.append("<tr>" + "".join(f"<td><b>{c}</b></td>" for c in cells) + "</tr>")
        parts.append("</table>")
    return "".join(parts) + "</body></html>"


def fp_html(table, week=5, modified="2026-10-06T16:31:34+00:00"):
    parts = [f"<html><head><title>Fantasy Football Trade Value Chart: Week {week} (2026) - FantasyPros</title>"
             f"{ld(modified)}</head><body>"]
    for pos in ("QB", "RB", "WR", "TE"):
        head = (["Name", "Team", "Value", "Change", "2QB Value", "2QB Change", "Bye"] if pos == "QB"
                else ["Name", "Team", "Value", "Change", "Bye"])
        parts.append(f"<h2>{POS_WORD[pos].title()} Fantasy Football Trade Value Chart</h2><table><tr>"
                     + "".join(f"<td>{h}</td>" for h in head) + "</tr>")
        for name, p, vals, sf in (v for v in table.values() if v[1] == pos):
            cells = [name, "XX", fmt(vals["std"]), "0"] + ([fmt(sf), "0"] if pos == "QB" else []) + ["7"]
            parts.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        parts.append("</table>")
    return "".join(parts) + "</body></html>"


def fc_payload(table, scoring, qb):
    out = []
    for k, (name, pos, vals, sf) in table.items():
        v = vals[scoring] if qb == 1 else sf[scoring]
        out.append({"player": {"id": k, "name": name, "position": pos, "maybeTeam": "XX"}, "value": v})
    return sorted(out, key=lambda x: -x["value"])


def sitemap(entries, news=False):
    tag = "news:publication_date" if news else "lastmod"
    return ("<urlset>" + "".join(f"<url><loc>{u}</loc><{tag}>{d}</{tag}></url>" for u, d in entries)
            + "</urlset>")


class FakeFetch:
    def __init__(self, pages):
        self.pages = pages
        self.log = []

    def get(self, url, timeout=60, headers=None):
        self.log.append({"url": url})
        if url in self.pages:
            body = self.pages[url]
            return (200, body() if callable(body) else body, url)
        for prefix, body in self.pages.items():
            if url.startswith(prefix):
                return (200, body() if callable(body) else body, url)
        return (404, "", url)


STORED_SCORING = {"cbs": {"std": "standard", "half": "half_ppr", "full": "ppr"},
                  "default": {"std": "std", "half": "half", "full": "full"}}


def stored_rows(source, table, bake="bake_v1", created=SAVED, week=5, url=None):
    lab = STORED_SCORING.get(source, STORED_SCORING["default"])
    rows = []
    for k, (name, pos, vals, sf) in table.items():
        for s in ("std", "half", "full"):
            base = {"player_key": k, "player_norm": name.lower(), "position": pos, "scoring": lab[s], "week": week,
                    "bake_id": bake, "created_at": created, "pulled_at": created, "source_url": url}
            rows.append(dict(base, qb_slots=1, native_value=float(vals[s])))
            if sf is not None:
                rows.append(dict(base, qb_slots=2,
                                 native_value=float(sf[s] if isinstance(sf, dict) else sf)))
    return rows


class FakeStore:
    def __init__(self, rows_by_source):
        self.by = rows_by_source

    def latest_week(self, source):
        ws = [r["week"] for r in self.by.get(source, []) if r.get("qb_slots") in (None, 1)]
        return max(ws) if ws else None

    def rows(self, source, week):
        return [r for r in self.by.get(source, []) if r["week"] == week]

    def players(self):
        return PLAYERS + FILLER


def slug(name):
    import re
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", name.lower())).strip()


def chart_doc(tables, universe=None):
    universe = dict(universe or UNIVERSE)
    for i in range(40):
        universe[f"filler player{i}"] = 100 + i
    keyslug = {v: k for k, v in universe.items()}
    doc = {"built_at": IMPORTED, "player_keys": universe, "sources": {}}
    for src, table in tables.items():
        combos = {}
        for s, combo in fp.SITE_COMBO.items():
            name = combo + ("_qb1" if src == "fantasycalc" else "")
            native, sflex = {}, {}
            for k, (n, pos, vals, sf) in table.items():
                if k not in keyslug:
                    continue
                native[keyslug[k]] = float(vals[s])
                if sf is not None:
                    sflex[keyslug[k]] = float(sf[s] if isinstance(sf, dict) else sf)
            combos[name] = {"native": native, "native_superflex": sflex}
        doc["sources"][src] = {"source_provenance": {"week_designated": 5, "source_pulled_at": IMPORTED,
                                                     "source_url": URLS.get(src)},
                               "combos": combos}
    return doc


class Env:
    """One healthy world: publisher == stored == chart, nothing newer published."""

    def __init__(self):
        self.tables = copy.deepcopy(TABLES)
        self.stored = {s: stored_rows(s, t, url=URLS.get(s)) for s, t in self.tables.items()}
        self.chart = chart_doc(self.tables)
        self.pub = copy.deepcopy(TABLES)
        self.pages = {}
        self.usat_week_entries = [(URLS["usatoday"], "2026-10-06T21:36:46Z")]
        self.fp_news = [(URLS["fantasypros"].replace("/2026/09/", "/2026/10/"), "2026-10-06T16:27:55+00:00")]
        self.cbs_next = None
        self.report = None
        self.revised = {}
        self.page_week = {}

    def build_pages(self):
        p = {
            "https://www.gannett-cdn.com/sitemaps/USAT/web/web-sitemap-2026-10.xml": sitemap(self.usat_week_entries),
            "https://www.gannett-cdn.com/sitemaps/USAT/web/web-sitemap-2026-09.xml": sitemap([]),
            "https://www.fantasypros.com/sitemaps/articles-sitemap.php": sitemap(self.fp_news, news=True),
            URLS["usatoday"]: usatoday_html(self.pub["usatoday"], self.page_week.get("usatoday", 5),
                                            self.revised.get("usatoday", "2026-10-06T21:36:46Z")),
            URLS["cbs"]: cbs_html(self.pub["cbs"], self.page_week.get("cbs", 5),
                                  self.revised.get("cbs", "2026-10-07T17:44:10+00:00")),
            URLS["fantasypros"].replace("/2026/09/", "/2026/10/"): fp_html(
                self.pub["fantasypros"], 5, self.revised.get("fantasypros", "2026-10-06T16:31:34+00:00")),
            URLS["fantasypros"]: fp_html(self.pub["fantasypros"]),
        }
        for url, _ in self.usat_week_entries:  # every discovered USA Today article answers
            p.setdefault(url, usatoday_html(self.pub["usatoday"], 6 if "week-6" in url else 5))
        if self.cbs_next:
            p["https://www.cbssports.com/fantasy/football/news/dave-richards-2026-week-6-trade-chart/"] = self.cbs_next
        for s, ppr in fp.FC_PPR.items():
            for qb in (1, 2):
                p[fp.FC_API.format(qb=qb, ppr=ppr)] = json.dumps(fc_payload(self.pub["fantasycalc"], s, qb))
        return p

    def run(self, sources=fp.SOURCES):
        ident = fp.Identity.load(PLAYERS + FILLER)
        fetch = FakeFetch(self.build_pages())
        doc, div = fp.run(sources, fetch=fetch, store=FakeStore(self.stored), ident=ident, site_doc=self.chart,
                          site_error=None, report=self.report,
                          report_where="not yet available" if self.report is None else "test report", now=NOW)
        return {r["source"]: r for r in doc["sources"]}, doc, div


def st(result, source, stage=None):
    r = result[source]
    return r["stages"][stage]["status"] if stage else r["status"]


class BaselineGreen(unittest.TestCase):
    def test_all_trade_charts_green_on_consistent_data(self):
        res, doc, _ = Env().run()
        for s in fp.SOURCES:
            with self.subTest(source=s):
                self.assertEqual("green", st(res, s), json.dumps(res[s]["stages"], indent=1, default=str)[:3000])
                self.assertEqual("n/a", st(res, s, "reference_vs_engine"))
        self.assertEqual("green", doc["overall"])
        self.assertEqual(fp.SCHEMA, doc["schema"])

    def test_every_column_compared(self):
        res, _, _ = Env().run(["usatoday"])
        grains = res["usatoday"]["stages"]["publisher_vs_stored"]["grains"]
        self.assertEqual({"std|1", "half|1", "full|1", "std|2", "half|2", "full|2"}, set(grains))
        self.assertEqual(5 * 3 + 3, res["usatoday"]["stages"]["publisher_vs_stored"]["counts"]["compared"])


class Stage1PublisherVsStored(unittest.TestCase):
    def test_value_mismatch_red_for_each_trade_chart(self):
        for source, key, grain in (("usatoday", 2, "half"), ("cbs", 3, "full"), ("fantasypros", 4, "std")):
            with self.subTest(source=source):
                env = Env()
                name, pos, vals, sf = env.pub[source][key]
                env.pub[source][key] = (name, pos, dict(vals, **{grain: vals[grain] + 1}), sf)
                res, _, div = env.run([source])
                self.assertEqual("red", st(res, source, "publisher_vs_stored"))
                self.assertEqual("red", st(res, source))
                ex = res[source]["stages"]["publisher_vs_stored"]["examples"]
                self.assertEqual(key, ex[0]["player_key"])
                self.assertTrue(any(d["type"] == "value_mismatch" for d in div[source]))

    def test_superflex_column_mismatch_red(self):
        env = Env()
        name, pos, vals, sf = env.pub["usatoday"][1]
        env.pub["usatoday"][1] = (name, pos, vals, sf + 1)
        res, _, _ = env.run(["usatoday"])
        self.assertEqual("red", st(res, "usatoday", "publisher_vs_stored"))
        self.assertEqual(3, res["usatoday"]["stages"]["publisher_vs_stored"]["counts"]["mismatched"])

    def test_publisher_rounding_is_exact_not_a_tolerance(self):
        self.assertTrue(fp.equal_after_rounding("52.5", 52.5))
        self.assertTrue(fp.equal_after_rounding("36", 36.0))
        self.assertTrue(fp.equal_after_rounding("29.1", 29.1))
        self.assertFalse(fp.equal_after_rounding("36", 36.4))   # stored is not the printed number
        self.assertFalse(fp.equal_after_rounding("29.1", 29.0))

    def test_missing_and_extra_players_red(self):
        env = Env()
        del env.stored["cbs"][0:4]  # drop one stored player's rows
        res, _, _ = env.run(["cbs"])
        self.assertEqual("red", st(res, "cbs", "publisher_vs_stored"))
        env = Env()
        del env.pub["fantasypros"][3]  # stored player no longer on the page
        res, _, _ = env.run(["fantasypros"])
        self.assertEqual("red", st(res, "fantasypros", "publisher_vs_stored"))
        self.assertEqual(1, res["fantasypros"]["stages"]["publisher_vs_stored"]["counts"]["extra_in_stored"])

    def test_wrong_week_page_red(self):
        env = Env()
        env.page_week["cbs"] = 4
        res, _, _ = env.run(["cbs"])
        self.assertEqual("red", st(res, "cbs", "publisher_vs_stored"))
        self.assertIn("week", res["cbs"]["stages"]["publisher_vs_stored"]["summary"])

    def test_different_article_red_same_article_other_month_path_green(self):
        res, _, _ = Env().run(["fantasypros"])  # stored /2026/09/, discovered /2026/10/: one article
        self.assertEqual("green", st(res, "fantasypros", "publisher_vs_stored"))
        env = Env()
        env.usat_week_entries = [(URLS["usatoday"].replace("92125556007", "99999999999"), "2026-10-07T00:00:00Z")]
        res, _, _ = env.run(["usatoday"])
        self.assertEqual("red", st(res, "usatoday", "publisher_vs_stored"))
        self.assertIn("independent discovery", res["usatoday"]["stages"]["publisher_vs_stored"]["summary"])

    def test_revision_after_save_amber_in_grace_red_after(self):
        # (save time, page dateModified, expected): a revision after the save is amber for
        # GRACE_HOURS, red after; a mismatch with no later revision is plain red.
        for saved, modified, want in ((SAVED, "2026-10-08T20:00:00Z", "amber"),
                                      (SAVED, "2026-10-08T09:00:00Z", "red"),
                                      ("2026-10-07T00:00:00+00:00", "2026-10-07T06:00:00Z", "red")):
            with self.subTest(saved=saved, modified=modified):
                env = Env()
                env.stored["cbs"] = stored_rows("cbs", TABLES["cbs"], created=saved, url=URLS["cbs"])
                env.revised["cbs"] = modified
                name, pos, vals, sf = env.pub["cbs"][2]
                env.pub["cbs"][2] = (name, pos, dict(vals, std=vals["std"] + 1), sf)
                res, _, _ = env.run(["cbs"])
                self.assertEqual(want, st(res, "cbs", "publisher_vs_stored"))

    def test_player_outside_page_universe_amber_and_named(self):
        env = Env()
        env.pub["usatoday"][6] = ("Tyreek Hill", "WR", {"std": 15, "half": 15, "full": 15}, None)
        res, _, div = env.run(["usatoday"])
        s1 = res["usatoday"]["stages"]["publisher_vs_stored"]
        self.assertEqual("amber", s1["status"])
        self.assertEqual("Tyreek Hill", s1["outside_universe"][0]["name"])
        self.assertTrue(any(d["type"] == "outside_universe" for d in div["usatoday"]))

    def test_unreadable_publisher_is_unknown_not_green(self):
        env = Env()
        pages = env.build_pages()
        pages[URLS["cbs"]] = "<html><body>bot wall</body></html>"
        ident = fp.Identity.load(PLAYERS + FILLER)
        doc, _ = fp.run(["cbs"], fetch=FakeFetch(pages), store=FakeStore(env.stored), ident=ident,
                        site_doc=env.chart, site_error=None, report=None, report_where="n/a", now=NOW)
        r = doc["sources"][0]
        self.assertEqual("unknown", r["stages"]["publisher_vs_stored"]["status"])
        self.assertEqual("amber", r["status"])


class Stage1FantasyCalc(unittest.TestCase):
    def test_movement_since_save_is_amber(self):
        env = Env()
        for k in list(env.pub["fantasycalc"])[:10]:
            name, pos, vals, sf = env.pub["fantasycalc"][k]
            env.pub["fantasycalc"][k] = (name, pos, {s: v + 7 for s, v in vals.items()}, sf)
        res, _, _ = env.run(["fantasycalc"])
        self.assertEqual("amber", st(res, "fantasycalc", "publisher_vs_stored"))

    def test_systemic_difference_red(self):
        env = Env()
        for k, (name, pos, vals, sf) in list(env.pub["fantasycalc"].items()):
            env.pub["fantasycalc"][k] = (name, pos, {s: v * 2 for s, v in vals.items()}, sf)
        res, _, _ = env.run(["fantasycalc"])
        self.assertEqual("red", st(res, "fantasycalc", "publisher_vs_stored"))

    def test_column_swap_red(self):
        env = Env()
        # store the 2-QB list under 1-QB and vice versa for every player
        for r in env.stored["fantasycalc"]:
            r["qb_slots"] = 2 if r["qb_slots"] == 1 else 1
        res, _, _ = env.run(["fantasycalc"])
        s1 = res["fantasycalc"]["stages"]["publisher_vs_stored"]
        self.assertEqual("red", s1["status"])
        self.assertIn("column check", s1["summary"])

    def test_top_player_missing_red_bottom_churn_amber(self):
        env = Env()
        del env.pub["fantasycalc"][2]  # Gibbs, top of the list, gone from the live list
        res, _, _ = env.run(["fantasycalc"])
        self.assertEqual("red", st(res, "fantasycalc", "publisher_vs_stored"))
        env = Env()
        del env.pub["fantasycalc"][100]  # bottom of the list
        res, _, _ = env.run(["fantasycalc"])
        self.assertEqual("green", st(res, "fantasycalc", "publisher_vs_stored"))
        self.assertEqual(1, res["fantasycalc"]["stages"]["publisher_vs_stored"]["counts"]["list_churn"])


class Stage2StoredVsChart(unittest.TestCase):
    def test_chart_value_differs_from_stored_red(self):
        for source in fp.SOURCES:
            with self.subTest(source=source):
                env = Env()
                combo = "half_12_qb1" if source == "fantasycalc" else "half_12"
                env.chart["sources"][source]["combos"][combo]["native"]["jahmyr gibbs"] += 0.5
                res, _, div = env.run([source])
                self.assertEqual("red", st(res, source, "stored_vs_chart"))
                self.assertEqual("red", st(res, source))
                self.assertTrue(any(d["stage"] == "stored_vs_chart" for d in div[source]))

    def test_chart_superflex_value_differs_red(self):
        env = Env()
        env.chart["sources"]["cbs"]["combos"]["full_12"]["native_superflex"]["josh allen"] = 47.0
        res, _, _ = env.run(["cbs"])
        self.assertEqual("red", st(res, "cbs", "stored_vs_chart"))

    def test_player_missing_from_chart_red(self):
        env = Env()
        for c in env.chart["sources"]["usatoday"]["combos"].values():
            c["native"].pop("brock bowers")
        res, _, _ = env.run(["usatoday"])
        self.assertEqual("red", st(res, "usatoday", "stored_vs_chart"))

    def test_chart_reads_the_bake_it_was_built_from_and_flags_newer(self):
        env = Env()
        newer = stored_rows("cbs", TABLES["cbs"], bake="bake_v2", created="2026-10-08T22:00:00+00:00",
                            url=URLS["cbs"])
        for r in newer:
            if r["player_key"] == 2 and r["qb_slots"] == 1:
                r["native_value"] += 1
        env.stored["cbs"] += newer
        env.pub["cbs"][2] = (lambda n, p, v, s: (n, p, {k: x + 1 for k, x in v.items()}, s))(*env.pub["cbs"][2])
        res, _, _ = env.run(["cbs"])
        s2 = res["cbs"]["stages"]["stored_vs_chart"]
        self.assertEqual("bake_v1", s2["bake_id"])  # the chart was imported at 21:00, before bake_v2
        self.assertEqual("amber", s2["status"])
        self.assertEqual("bake_v2", s2["behind"]["bake_id"])
        self.assertEqual("green", st(res, "cbs", "publisher_vs_stored"))  # newest bake matches the page

    def test_stored_player_outside_universe_amber(self):
        env = Env()
        env.stored["cbs"] += stored_rows("cbs", {6: ("Tyreek Hill", "WR", {"std": 6, "half": 7, "full": 8}, None)},
                                         url=URLS["cbs"])
        env.pub["cbs"][6] = ("Tyreek Hill", "WR", {"std": 6, "half": 7, "full": 8}, None)
        res, _, _ = env.run(["cbs"])
        s2 = res["cbs"]["stages"]["stored_vs_chart"]
        self.assertEqual("amber", s2["status"])
        self.assertEqual(1, s2["counts"]["outside_universe"])

    def test_unreadable_chart_unknown(self):
        env = Env()
        ident = fp.Identity.load(PLAYERS + FILLER)
        doc, _ = fp.run(["cbs"], fetch=FakeFetch(env.build_pages()), store=FakeStore(env.stored), ident=ident,
                        site_doc=None, site_error="HTTP 404", report=None, report_where="n/a", now=NOW)
        self.assertEqual("unknown", doc["sources"][0]["stages"]["stored_vs_chart"]["status"])


class Stage3Freshness(unittest.TestCase):
    def test_newer_week_posted_red_after_grace_amber_inside(self):
        for published, want in (("2026-10-07T12:00:00Z", "red"), ("2026-10-08T20:00:00Z", "amber")):
            with self.subTest(published=published):
                env = Env()
                env.usat_week_entries.append((URLS["usatoday"].replace("week-5", "week-6").replace(
                    "92125556007", "92125556999"), published))
                res, _, _ = env.run(["usatoday"])
                self.assertEqual(want, st(res, "usatoday", "freshness"))
                self.assertEqual(want, st(res, "usatoday"))

    def test_cbs_and_fantasypros_newer_week(self):
        env = Env()
        env.cbs_next = cbs_html(CBS, week=6).replace("2026-10-06T21:36:46Z", "2026-10-06T00:00:00Z")
        res, _, _ = env.run(["cbs"])
        self.assertEqual("red", st(res, "cbs", "freshness"))
        env = Env()
        env.fp_news.append(("https://www.fantasypros.com/2026/10/fantasy-football-trade-value-chart-week-6-2026/",
                            "2026-10-08T22:00:00+00:00"))
        res, _, _ = env.run(["fantasypros"])
        self.assertEqual("amber", st(res, "fantasypros", "freshness"))

    def test_fantasycalc_new_content_week(self):
        env = Env()
        env.chart["sources"]["fantasycalc"]["source_provenance"]["week_designated"] = 4
        for r in env.stored["fantasycalc"]:
            r["week"] = 4
        res, _, _ = env.run(["fantasycalc"])
        self.assertEqual("red", st(res, "fantasycalc", "freshness"))  # week 5 opened 2026-10-06


class Stage4Reference(unittest.TestCase):
    def test_disagreement_red_absent_na(self):
        env = Env()
        env.report = {"generated_at": "2026-10-08T22:00:00Z", "values_compared": 10,
                      "sources": {"cbs": {"status": "disagree", "disagreeing_series": ["cbs"]},
                                  "usatoday": {"status": "agree"}},
                      "series": {"cbs": {"examples": [{"player_key": 2, "engine": 1.0, "reference": 1.2}]}}}
        res, _, _ = env.run(["cbs", "usatoday"])
        self.assertEqual("red", st(res, "cbs", "reference_vs_engine"))
        self.assertEqual("red", st(res, "cbs"))
        self.assertEqual("green", st(res, "usatoday", "reference_vs_engine"))
        res, _, _ = Env().run(["cbs"])
        self.assertEqual("n/a", st(res, "cbs", "reference_vs_engine"))
        self.assertEqual("green", st(res, "cbs"))


class Parsers(unittest.TestCase):
    def test_table_walk_reads_headings_and_skips_blank_cells(self):
        html = ("<h2>Quarterback trade values</h2><table><tr><td>Player</td><td>tm</td><td>1QB-4</td>"
                "<td>1QB-6</td><td>2QB</td></tr><tr><td>Joe Flacco</td><td>CLE</td><td>--</td><td>--</td>"
                "<td>3</td></tr></table>")
        rows, notes = fp.read_tables("cbs", fp.parse_page(html)[1])
        self.assertEqual(1, len(rows))
        self.assertEqual({"std|2": "3", "half|2": "3", "full|2": "3"}, rows[0].values)  # '--' never read as 0
        self.assertTrue(any("no table found" in n for n in notes))

    def test_first_title_wins(self):
        title, _ = fp.parse_page(cbs_html(CBS))
        self.assertIn("Week 5", title)

    def test_page_week_conflict(self):
        self.assertEqual((5, None), fp.page_week(URLS["usatoday"], "Week 5 trade values"))
        wk, problem = fp.page_week(URLS["usatoday"], "Week 4 trade values")
        self.assertIsNone(wk)
        self.assertIn("week 4", problem)

    def test_article_key_ignores_date_directories_only(self):
        a = "https://www.fantasypros.com/2026/09/fantasy-football-trade-value-chart-week-5-2026/"
        self.assertEqual(fp.article_key(a), fp.article_key(a.replace("/09/", "/10/")))
        self.assertNotEqual(fp.article_key(a), fp.article_key(a.replace("week-5", "week-6")))

    def test_history_rows(self):
        env = Env()
        env.chart["sources"]["cbs"]["combos"]["half_12"]["native"]["jahmyr gibbs"] += 0.5
        ident = fp.Identity.load(PLAYERS + FILLER)
        _, doc, div = env.run(["cbs"])
        runs, divs = fp.history_rows(doc, div, ident)
        self.assertEqual(1, len(runs))
        self.assertEqual("red", runs[0]["status"])
        self.assertEqual("fidelity_pulse", runs[0]["check_name"])
        self.assertEqual(doc["run_id"], runs[0]["pulse_id"])
        self.assertEqual(1, len(divs))
        self.assertEqual(("stored_vs_chart", "half|1", 2), (divs[0]["stage"], divs[0]["scoring_format"],
                                                            divs[0]["player_key"]))
        json.dumps(runs)  # serialisable for PostgREST


if __name__ == "__main__":
    unittest.main()
