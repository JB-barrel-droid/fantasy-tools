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
    def test_dollar_rows_in_page_order_with_tiers(self):
        got = pull.parse_pianowski_page(yahoo_page(), "https://sports.yahoo.com/fantasy/article/a.html")
        self.assertEqual(got["pos"], "WR")
        self.assertEqual(got["vintage"], "2026-10-21")
        self.assertEqual(got["tiers"], 3)
        self.assertEqual([r["pos_rank"] for r in got["rows"][:3]], [1, 2, 3])
        self.assertEqual(got["rows"][2]["player_name"], "Player Number3")  # trailing asterisk dropped
        self.assertEqual(got["rows"][3]["player_name"], "Player Number4")  # leading asterisk dropped
        self.assertEqual(got["rows"][0]["source_value"], 50.0)
        self.assertEqual(got["rows"][0]["scoring"], "unstated")

    def test_other_article_is_ignored_and_short_list_fails(self):
        self.assertIsNone(pull.parse_pianowski_page(yahoo_page().replace("rest-of-season", "week 9"), "u"))
        with self.assertRaises(pull.PullError):
            pull.parse_pianowski_page(yahoo_page(n=10), "u")


class Snapshot(unittest.TestCase):
    def fetcher(self, pages):
        return lambda url: (200, pages[url]) if url in pages else (404, "")

    def test_newest_article_per_position_wins_and_ecr_link_is_followed(self):
        ros_url = "https://www.fantasypros.com/nfl/rankings/ros-half-point-ppr-overall.php"
        start = f'<a href="/nfl/rankings/ros-half-point-ppr-overall.php">x</a>{PAD}'
        newer = "https://sports.yahoo.com/fantasy/article/fantasy-football-rest-of-season-rankings-qb-tiers-1.html"
        author = f'<a href="{newer}">QB</a>{PAD}'
        words = {"quarterback": "Quarterback", "te": "TE", "rb": "RB", "wr": "WR"}
        pages = {pull.FP_START: start, ros_url: ecr_page(), pull.YAHOO_AUTHOR: author,
                 newer: yahoo_page("QB", 30, "2026-10-28T20:00:00Z")}
        for seed in pull.YAHOO_SEEDS:
            w = next(v for k, v in words.items() if f"rankings-{k}" in seed)
            pages[seed] = yahoo_page(w, 70, "2026-09-30T20:41:00Z")
        snap = pull.build_snapshot(list(pull.PULLERS), fetcher=self.fetcher(pages))
        qb = [p for p in snap["sources"]["yahoo_pianowski_ros"]["pages"] if p["pos"] == "QB"][0]
        self.assertEqual(qb["url"], newer)
        self.assertEqual(snap["sources"]["fantasypros_ros_ecr"]["pages"][0]["url"], ros_url)
        self.assertEqual({u["source"] for u in snap["unavailable"]},
                         {"espn_ros_article", "hayden_winks_ros", "usat_ros_overall"})

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
