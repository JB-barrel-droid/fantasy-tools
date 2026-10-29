"""ROS rankings feed (JEG-1198 option C): parsers, snapshot, saver, and isolation.

Isolation is the point of the ECR rule change (docs/pipeline-rules.md section 8):
expert consensus and analyst ROS rankings may be stored in public.ros_rankings, but no
value-building code reads that table, and the trade-value importer keeps its ECR hard
exclusion. Fixtures are synthetic pages in the shape the 2026-10-29 probe runs saw.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import pull_ros_rankings as pull  # noqa: E402
import save_ros_rankings as save  # noqa: E402

PAD = "<!-- " + "x" * pull.MIN_BODY + " -->"


def ecr_page(scoring="HALF", per_pos=None, ts=1793223616):
    per_pos = per_pos or {"QB": 32, "RB": 64, "WR": 84, "TE": 32}
    players, overall = [], 0
    for pos, n in per_pos.items():
        for i in range(1, n + 1):
            overall += 1
            players.append({"player_name": f"{pos} Player{i}", "player_team_id": "DET",
                            "player_position_id": pos, "rank_ecr": overall, "rank_min": "1",
                            "rank_max": "4", "rank_ave": "2.67", "rank_std": "0.94", "pos_rank": f"{pos}{i}"})
    players.append({"player_name": "Some Kicker", "player_position_id": "K", "pos_rank": "K1", "rank_ecr": 999})
    data = {"ranking_type_name": "ros", "scoring": scoring, "total_experts": 6,
            "last_updated_ts": ts, "players": players}
    return f"<html><script>var ecrData = {json.dumps(data)};\nvar sosData = {{}};</script>{PAD}</html>"


def yahoo_page(pos_word="WR", n=65, published="2026-10-21T21:01:24Z"):
    tiers = ["The Big Tickets", "Legitimate Building Blocks", "Bargain Bin"]
    body, k = [], 0
    for t in tiers:
        body.append(f"<h2>{t}</h2><ul>")
        for _ in range(n // len(tiers) + 1):
            if k >= n:
                break
            k += 1
            body.append(f'<li><a href="/x">${50 - k // 2} Player Number{k}</a>{"*" if k == 3 else ""}</li>'
                        if k != 4 else f'<li>${50 - k // 2} * Player Number{k}</li>')
        body.append("</ul>")
    return (f"<html><head><title>Fantasy Football rest-of-season rankings: {pos_word} Tiers - Yahoo Sports"
            f'</title><script>{{"datePublished":"{published}"}}</script></head><body>'
            f"{''.join(body)}{PAD}</body></html>")


def expert_table_page(experts=(("Pat Fitzmaurice (FantasyPros)", "pat-fitzmaurice", "10/27/2026"),)):
    rows = "".join(
        f'<tr><td><a href="/experts/{slug}.php">{name}</a> '
        f'<a href="/nfl/rankings/{slug}.php?type=ros&amp;scoring=HALF">View rankings for {name}</a></td>'
        f"<td>FantasyPros</td><td>#47</td><td>{when}</td></tr>" for name, slug, when in experts)
    return (f'<html><a href="/nfl/rankings/ros-half-point-ppr-overall.php">x</a>'
            f"<table>{rows}</table>{PAD}</html>")


EXPERT_WORDS = {"HALF": "Half PPR ", "PPR": "PPR ", "STD": ""}


def expert_page(code="HALF", per_pos=None, title=None, name="Pat Fitzmaurice (FantasyPros)"):
    per_pos = per_pos or {"QB": 24, "RB": 45, "WR": 55, "TE": 22, "K": 3}
    title = title or f"{name} | Fantasy Football {EXPERT_WORDS[code]}Rankings | 2026 Rest of Season"
    trs, rank = [], 0
    for pos, n in per_pos.items():
        for i in range(1, n + 1):
            rank += 1
            trs.append(f'<tr><td class="center">{rank}</td><td class="player-label">'
                       f'<a class="fp-player-link" fp-player-name="{pos} Player{i}">{pos} Player{i}</a></td>'
                       f'<td class="center">{pos}{i}</td><td class="center">DET</td></tr>')
    return f"<html><head><title>{title}</title></head><table>{''.join(trs)}</table>{PAD}</html>"


class EcrParser(unittest.TestCase):
    def test_rows_scoring_vintage_and_positions(self):
        got = pull.parse_ecr_page(ecr_page(), "https://www.fantasypros.com/nfl/rankings/ros-half-point-ppr-overall.php")
        self.assertEqual(got["scoring"], "half_ppr")
        self.assertEqual(got["vintage"], "2026-10-28")  # last_updated_ts in Chicago time
        self.assertEqual({r["pos"] for r in got["rows"]}, {"QB", "RB", "WR", "TE"})  # K dropped
        rb3 = next(r for r in got["rows"] if r["pos"] == "RB" and r["pos_rank"] == 3)
        self.assertEqual((rb3["rank_avg"], rb3["rank_std"], rb3["experts"]), (2.67, 0.94, 6))

    def test_not_ros_or_missing_json_fails_closed(self):
        with self.assertRaises(pull.PullError) as cm:
            pull.parse_ecr_page("<html>" + PAD, "u")
        self.assertEqual(cm.exception.code, "SOURCE_LAYOUT")
        with self.assertRaises(pull.PullError):
            pull.parse_ecr_page(ecr_page().replace('"ros"', '"weekly"'), "u")

    def test_truncated_position_fails_closed(self):
        with self.assertRaises(pull.PullError) as cm:
            pull.parse_ecr_page(ecr_page(per_pos={"QB": 5, "RB": 64, "WR": 84, "TE": 32}), "u")
        self.assertEqual(cm.exception.code, "SOURCE_TRUNCATED")


class YahooParser(unittest.TestCase):
    def test_dollar_rows_ranked_by_value_with_tiers(self):
        got = pull.parse_pianowski_page(yahoo_page(), "https://sports.yahoo.com/fantasy/article/a.html")
        self.assertEqual(got["pos"], "WR")
        self.assertEqual(got["vintage"], "2026-10-21")
        self.assertEqual(got["tiers"], 3)
        self.assertEqual([r["pos_rank"] for r in got["rows"][:4]], [1, 2.5, 2.5, 4.5])  # $50, $49, $49, $48, $48
        self.assertEqual(got["rows"][2]["player_name"], "Player Number3")  # trailing asterisk dropped
        self.assertEqual(got["rows"][3]["player_name"], "Player Number4")  # leading asterisk dropped
        self.assertEqual(got["rows"][0]["source_value"], 50.0)
        self.assertEqual(got["rows"][0]["scoring"], "unstated")

    def test_late_tier_is_ranked_by_value_not_page_order(self):
        injury = "<h3>Courtesy Injury Ranks</h3><ul><li>$60 Hurt Star</li></ul>"
        page = yahoo_page().replace("</body>", injury + "</body>")
        got = pull.parse_pianowski_page(page, "u")
        self.assertEqual(got["rows"][-1]["player_name"], "Hurt Star")  # last on the page
        self.assertEqual(got["rows"][-1]["pos_rank"], 1)  # first by value
        self.assertEqual(got["tiers"], 4)

    def test_value_ranks_share_ties(self):
        self.assertEqual(pull.value_ranks([5, 7, 7, 1]), [3, 1.5, 1.5, 4])

    def test_other_article_is_ignored_and_short_list_fails(self):
        self.assertIsNone(pull.parse_pianowski_page(yahoo_page().replace("rest-of-season", "week 9"), "u"))
        with self.assertRaises(pull.PullError):
            pull.parse_pianowski_page(yahoo_page(n=10), "u")


class ExpertLists(unittest.TestCase):
    """Each expert's own ROS list (Jeremy 2026-10-29: "multiple cuts of the fantasypros data")."""

    def test_expert_table_reads_name_link_and_updated_date(self):
        got = pull.expert_table(expert_table_page())
        self.assertEqual(got, [{"analyst": "Pat Fitzmaurice (FantasyPros)",
                                "path": "/nfl/rankings/pat-fitzmaurice.php", "vintage": "2026-10-27"}])

    def test_rows_are_ros_with_rank_position_and_one_expert(self):
        pg = pull.parse_expert_page(expert_page("PPR"), "u", "Pat Fitzmaurice (FantasyPros)", "2026-10-27", "PPR")
        self.assertEqual(pg["scoring"], "ppr")
        self.assertEqual({r["pos"] for r in pg["rows"]}, set(pull.POSITIONS))  # kickers dropped
        dst = expert_page("PPR").replace("</table>", '<tr><td class="center">300</td><td class="player-label">'
                                         '<a href="/x">Chicago Bears</a></td><td class="center">DST1</td>'
                                         '<td class="center">CHI</td></tr></table>')
        self.assertEqual(pull.parse_expert_page(dst, "u", "x", "2026-10-27", "PPR")["review_rows"], [])
        first = pg["rows"][0]
        self.assertEqual((first["pos"], first["pos_rank"], first["overall_rank"], first["experts"]), ("QB", 1, 1.0, 1))
        self.assertTrue(all(r["source"] == "fantasypros_expert_ros" and r["source_vintage"] == "2026-10-27"
                            for r in pg["rows"]))

    def test_weekly_or_wrong_scoring_page_is_refused(self):
        # Jeremy 2026-10-29: "do not blend weekly data with ROS data, ever"
        weekly = expert_page(title="Pat Fitzmaurice (FantasyPros) | Fantasy Football Half PPR Rankings | Week 9")
        with self.assertRaises(pull.PullError):
            pull.parse_expert_page(weekly, "u", "x", "2026-10-27", "HALF")
        with self.assertRaises(pull.PullError):  # a Half PPR page served for the PPR cut
            pull.parse_expert_page(expert_page("HALF"), "u", "x", "2026-10-27", "PPR")
        with self.assertRaises(pull.PullError):  # standard title check rejects a PPR page
            pull.parse_expert_page(expert_page("PPR"), "u", "x", "2026-10-27", "STD")
        with self.assertRaises(pull.PullError):  # last season's list
            pull.parse_expert_page(expert_page(title="X | Fantasy Football Half PPR Rankings | 2025 Rest of Season"),
                                   "u", "x", "2026-10-27", "HALF")

    def test_unavailable_list_has_no_rows_and_empty_page_fails(self):
        none = (f"<html><head><title>X | Fantasy Football PPR Rankings | 2026 Rest of Season</title></head>"
                f"<p>Rankings are not available for this expert.</p>{PAD}</html>")
        self.assertEqual(pull.parse_expert_page(none, "u", "x", "2026-10-27", "PPR")["rows"], [])
        with self.assertRaises(pull.PullError):
            pull.parse_expert_page(none.replace("not available", "coming"), "u", "x", "2026-10-27", "PPR")

    def test_short_or_missing_lists_go_to_review_not_failure(self):
        base = "https://www.fantasypros.com/nfl/rankings/pat-fitzmaurice.php?type=ros&scoring="
        pages = {pull.FP_START: expert_table_page(), base + "HALF": expert_page("HALF"),
                 base + "PPR": expert_page("PPR", per_pos={"QB": 5, "RB": 5, "WR": 5, "TE": 5})}
        fetcher = lambda url: (200, pages[url]) if url in pages else (404, "")
        got = pull.pull_experts(fetcher)
        self.assertEqual([p["scoring"] for p in got["pages"]], ["half_ppr"])
        self.assertEqual({r["scoring"] for r in got["review_rows"]}, {"ppr", "standard"})


class ConsensusCuts(unittest.TestCase):
    def test_each_scoring_page_named_on_the_first_is_followed(self):
        half = "https://www.fantasypros.com/nfl/rankings/ros-half-point-ppr-overall.php"
        ppr = "https://www.fantasypros.com/nfl/rankings/ros-ppr-overall.php"
        std = "https://www.fantasypros.com/nfl/rankings/ros-overall.php"
        first = ecr_page("HALF").replace("</html>", '<a href="/nfl/rankings/ros-ppr-overall.php">PPR</a>'
                                                     '<a href="/nfl/rankings/ros-overall.php">STD</a></html>')
        pages = {pull.FP_START: f'<a href="/nfl/rankings/ros-half-point-ppr-overall.php">x</a>{PAD}',
                 half: first, ppr: ecr_page("PPR"), std: ecr_page("STD")}
        got = pull.pull_ecr(lambda url: (200, pages[url]) if url in pages else (404, ""))
        self.assertEqual(sorted(p["scoring"] for p in got["pages"]), ["half_ppr", "ppr", "standard"])
        self.assertEqual(len({r["analyst"] for r in got["rows"]}), 1)

    def test_two_pages_with_one_scoring_fail_closed(self):
        half = "https://www.fantasypros.com/nfl/rankings/ros-half-point-ppr-overall.php"
        ppr = "https://www.fantasypros.com/nfl/rankings/ros-ppr-overall.php"
        first = ecr_page("HALF").replace("</html>", '<a href="/nfl/rankings/ros-ppr-overall.php">PPR</a></html>')
        pages = {pull.FP_START: f'<a href="/nfl/rankings/ros-half-point-ppr-overall.php">x</a>{PAD}',
                 half: first, ppr: ecr_page("HALF")}
        with self.assertRaises(pull.PullError):
            pull.pull_ecr(lambda url: (200, pages[url]) if url in pages else (404, ""))


class Snapshot(unittest.TestCase):
    def fetcher(self, pages):
        return lambda url: (200, pages[url]) if url in pages else (404, "")

    def test_newest_article_per_position_wins_and_ecr_link_is_followed(self):
        ros_url = "https://www.fantasypros.com/nfl/rankings/ros-half-point-ppr-overall.php"
        start = expert_table_page()
        base = "https://www.fantasypros.com/nfl/rankings/pat-fitzmaurice.php?type=ros&scoring="
        newer = "https://sports.yahoo.com/fantasy/article/fantasy-football-rest-of-season-rankings-qb-tiers-1.html"
        author = f'<a href="{newer}">QB</a>{PAD}'
        words = {"quarterback": "Quarterback", "te": "TE", "rb": "RB", "wr": "WR"}
        pages = {pull.FP_START: start, ros_url: ecr_page(), pull.YAHOO_AUTHOR: author,
                 newer: yahoo_page("QB", 30, "2026-10-28T20:00:00Z")}
        for code in pull.FP_SCORING:
            pages[base + code] = expert_page(code)
        for seed in pull.YAHOO_SEEDS:
            w = next(v for k, v in words.items() if f"rankings-{k}" in seed)
            pages[seed] = yahoo_page(w, 70, "2026-09-30T20:41:00Z")
        snap = pull.build_snapshot(list(pull.PULLERS), fetcher=self.fetcher(pages))
        qb = [p for p in snap["sources"]["yahoo_pianowski_ros"]["pages"] if p["pos"] == "QB"][0]
        self.assertEqual(qb["url"], newer)
        self.assertEqual(snap["sources"]["fantasypros_ros_ecr"]["pages"][0]["url"], ros_url)
        self.assertEqual(snap["sources"]["fantasypros_expert_ros"]["row_count"], 3 * (24 + 45 + 55 + 22))
        self.assertEqual({u["source"] for u in snap["unavailable"]},
                         {"espn_ros_article", "hayden_winks_ros", "usat_ros_overall", "fantasylife_ros",
                          "footballguys_ros", "rotoballer_ros", "rsj_ros_article"})

    def test_blocked_source_fails_the_run_unless_partial(self):
        pages = {pull.FP_START: "<html></html>"}  # tiny body = blocked
        with self.assertRaises(pull.PullError) as cm:
            pull.build_snapshot(["fantasypros_ros_ecr"], fetcher=self.fetcher(pages))
        self.assertEqual(cm.exception.code, "SOURCE_BLOCKED")


class Saver(unittest.TestCase):
    def setUp(self):
        self._fp = save.fetch_players
        save.fetch_players = lambda: [
            {"player_key": 1, "full_name": "QB Player1", "position": "QB", "active": True},
            {"player_key": 2, "full_name": "RB Player1", "position": "RB", "active": True},
        ]

    def tearDown(self):
        save.fetch_players = self._fp

    def test_resolves_through_the_canonical_resolver_and_reviews_misses(self):
        rows = pull.parse_ecr_page(ecr_page(), "u")["rows"]
        snap = {"schema": "ros-rankings-snapshot-v1", "rows": rows, "review_rows": []}
        clean, review = save.build_rows(snap)
        self.assertEqual(sorted(r["player_key"] for r in clean), [1, 2])
        self.assertTrue(all(r["season"] == 2026 for r in clean))
        self.assertGreater(len(review), 100)
        self.assertTrue(all(set(save.COLUMNS) <= set(r) for r in clean))

    def test_expert_lists_keep_one_row_per_analyst(self):
        rows = []
        for who in ("A (x)", "B (y)"):
            rows += pull.parse_expert_page(expert_page("HALF", name=who), "u", who, "2026-10-27", "HALF")["rows"]
        clean, _ = save.build_rows({"schema": "ros-rankings-snapshot-v1", "rows": rows, "review_rows": []})
        self.assertEqual(sorted(r["analyst"] for r in clean), ["A (x)", "A (x)", "B (y)", "B (y)"])
        self.assertIn("analyst", save.CONFLICT.split(","))

    def test_row_without_analyst_fails_closed(self):
        row = dict(pull.parse_ecr_page(ecr_page(), "u")["rows"][0], analyst="")
        with self.assertRaises(SystemExit):
            save.build_rows({"schema": "ros-rankings-snapshot-v1", "rows": [row]})

    def test_unknown_source_fails_closed(self):
        snap = {"schema": "ros-rankings-snapshot-v1",
                "rows": [{"source": "usat_ros_overall", "player_name": "x", "pos": "QB"}]}
        with self.assertRaises(SystemExit):
            save.build_rows(snap)


class Isolation(unittest.TestCase):
    """Rankings never reach published values (Jeremy 2026-10-29, option C)."""

    def test_only_the_feed_reads_or_writes_ros_rankings(self):
        allowed = {"pipelines/pull_ros_rankings.py", "pipelines/save_ros_rankings.py"}
        hits = []
        for base in ("pipelines", "supabase/functions", "app", "modules"):
            for p in (ROOT / base).rglob("*"):
                if p.suffix in {".py", ".ts", ".js", ".cjs", ".mjs", ".html", ".sql"} and p.is_file():
                    rel = p.relative_to(ROOT).as_posix()
                    if rel not in allowed and re.search(r"\bros_rankings\b", p.read_text(errors="ignore")):
                        hits.append(rel)
        self.assertEqual(hits, [])

    def test_trade_value_importer_keeps_the_ecr_exclusion(self):
        import import_supabase_references as imp
        self.assertIn("ecr", imp.HARD_EXCLUSIONS)
        self.assertTrue(imp.is_ecr_flavored("fantasypros_ros_ecr"))
        with self.assertRaises(SystemExit):
            imp.check_source("fantasypros_ros_ecr")


if __name__ == "__main__":
    unittest.main()
