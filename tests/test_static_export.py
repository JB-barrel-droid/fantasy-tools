import json
import re
import subprocess
import unittest
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory

from pipelines import ingest_player_news


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "trade-value-chart"
FIXTURES = ROOT / "data" / "fixtures" / "current"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class StaticExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (APP / "index.html").read_text(encoding="utf-8")
        cls.players = load_json(FIXTURES / "players.json")
        cls.comparison = load_json(FIXTURES / "comparison-sources-data.json")
        cls.news = load_json(FIXTURES / "player-news.json")

    def test_inline_players_match_fixture(self):
        match = re.search(
            r"<script[^>]*id=[\"']players-data[\"'][^>]*>(.*?)</script>",
            self.index,
            re.S,
        )
        self.assertIsNotNone(match, "index.html must contain players-data")
        self.assertEqual(json.loads(match.group(1)), self.players)

    def test_reference_build_command_validates_finished_artifacts(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "reference-build-report.json"
            freshness = Path(tmp) / "reference-freshness.json"
            subprocess.run(
                [
                    "python3",
                    "pipelines/build_reference_data.py",
                    "--output",
                    str(output),
                    "--freshness-output",
                    str(freshness),
                    "--today",
                    "2026-09-20",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            report = load_json(output)
            self.assertEqual("ok", report["status"])
            self.assertEqual(596, report["players"]["player_count"])
            self.assertEqual(8, report["comparison"]["source_count"])
            self.assertIn("artifact_hashes", report)

    def test_expected_player_universe_and_identity(self):
        players = self.players["players"]
        self.assertEqual(596, len(players))
        by_name = {player["name"]: player for player in players}
        self.assertEqual(869, by_name["Josh Allen"]["player_key"])
        self.assertEqual("QB", by_name["Josh Allen"]["pos"])
        self.assertEqual("BUF", by_name["Josh Allen"]["team"])
        self.assertEqual(1, by_name["Josh Allen"]["preseason_ecr_rank"])
        self.assertEqual("experts_only", by_name["Josh Allen"]["pricing"])
        self.assertEqual(1.0, by_name["Josh Allen"]["ecr_share"]["ppr"])

    def test_known_player_values_are_preserved(self):
        by_name = {player["name"]: player for player in self.players["players"]}
        self.assertEqual(351.48, by_name["Josh Allen"]["ecr_ros"]["ppr"])
        self.assertEqual(351.48, by_name["Josh Allen"]["blend_ros"]["ppr"])
        self.assertEqual(386.51, by_name["Josh Allen"]["espn_ros"]["ppr"])
        self.assertEqual(325.87, by_name["Bijan Robinson"]["ecr_ros"]["ppr"])
        self.assertIsNone(by_name["Kyle Juszczyk"].get("pm_ros"))

    def test_comparison_sources_contract(self):
        expected_sources = {
            "usatoday",
            "fantasycalc",
            "fantasypros",
            "cbs",
            "espn",
            "fantasycalc_adjusted",
            "usatoday_adjusted",
            "fantasypros_adjusted",
        }
        self.assertEqual(expected_sources, set(self.comparison["sources"]))
        for source in expected_sources:
            self.assertEqual("live", self.comparison["source_validation"][source])
        self.assertEqual("stale", self.comparison["source_validation"]["ecr"])
        self.assertEqual("pending", self.comparison["source_validation"]["razzball"])

    def test_known_full_ppr_12_team_source_values(self):
        sources = self.comparison["sources"]

        def value(source, combo, player="josh allen"):
            combo_data = sources[source]["combos"][combo]
            values = combo_data.get("values") or combo_data.get("reindexed")
            return values[player]

        # The adjusted (bias-corrected) series are the dashboard's own product,
        # so they keep hard pins. Raw published charts do NOT: every promoted
        # raw source is re-anchored onto the ESPN leg, so its top value is the
        # anchor's, not its own. Pinning raw tops to pre-promotion numbers is
        # what made an earlier commit revert good fixture data to green the
        # suite -- assert the anchoring rule instead. See
        # test_promoted_raw_sources_share_the_espn_anchor below.
        expected = {
            ("espn", "full_12"): 17.2,
            ("fantasycalc_adjusted", "full_12_qb1"): 19.0,
            ("usatoday_adjusted", "full_12"): 21.2,
            ("fantasypros_adjusted", "full_12"): 18.1,
        }
        for key, expected_value in expected.items():
            self.assertEqual(expected_value, value(*key))

    def test_promoted_raw_sources_share_the_espn_anchor(self):
        """Promotion re-anchors each raw chart's scale onto the ESPN leg.

        Replaces the per-source magic numbers that rotted at every promotion:
        the invariant is that a promoted raw source tops out at the anchor.
        """
        sources = self.comparison["sources"]
        espn_combo = sources["espn"]["combos"]["full_12"]
        anchor_peak = max((espn_combo.get("values") or espn_combo.get("reindexed")).values())

        promoted = [
            key for key in ("usatoday", "fantasycalc", "fantasypros", "cbs")
            if sources[key].get("promoted_at")
        ]
        self.assertTrue(promoted, "no raw source is promoted; fixture lost its promotions")

        for key in promoted:
            combos = sources[key]["combos"]
            combo = combos.get("full_12") or combos.get("full_12_qb1")
            values = combo.get("values") or combo.get("reindexed")
            self.assertAlmostEqual(
                anchor_peak,
                max(values.values()),
                delta=0.3,
                msg=f"{key} is promoted but its peak does not sit on the ESPN anchor",
            )
            self.assertEqual(
                "espn_leg",
                sources[key].get("reindex_anchor"),
                msg=f"{key} is promoted without recording its reindex anchor",
            )

    def test_promoted_sources_still_disagree_below_the_anchor(self):
        """Anchoring pins the top of each curve, never the whole curve.

        The dashboard's entire claim is that the signal lives where independent
        sources disagree. If a re-anchor ever flattened the raw charts onto the
        ESPN curve, this fails -- the old peak pins could not have caught it.
        """
        sources = self.comparison["sources"]

        def series(key):
            combos = sources[key]["combos"]
            combo = combos.get("full_12") or combos.get("full_12_qb1")
            return combo.get("values") or combo.get("reindexed") or {}

        espn = series("espn")
        for key in ("usatoday", "fantasycalc", "fantasypros", "cbs"):
            other = series(key)
            shared = set(espn) & set(other)
            self.assertGreater(len(shared), 50, f"{key} shares too few players with ESPN to compare")
            identical = sum(1 for player in shared if abs(other[player] - espn[player]) < 0.05)
            self.assertLess(
                identical / len(shared),
                0.5,
                f"{key} tracks the ESPN curve on {identical}/{len(shared)} players -- "
                "re-anchoring collapsed it instead of only pinning its top",
            )

    def test_fixed_pie_totals_match_source_metadata(self):
        players = load_json(FIXTURES / "players.json")["players"]
        position_by_key = {player["player_key"]: player["pos"] for player in players}

        def combo_key(source, scoring):
            if source in {"fantasycalc", "fantasycalc_adjusted"}:
                return f"{scoring}_12_qb1"
            return f"{scoring}_12"

        combos = {
            "full": "full",
            "half": "half",
            "standard": "std",
        }
        tolerance = 2.0
        for source, source_data in self.comparison["sources"].items():
            for scoring, adjusted_scoring in combos.items():
                key = combo_key(source, adjusted_scoring if source.endswith("_adjusted") else scoring)
                combo = source_data["combos"].get(key)
                if combo is None:
                    continue
                values = combo.get("values") or combo.get("reindexed") or {}
                for pos, target_data in combo.get("index_total", {}).items():
                    target = target_data["target_total"]
                    total = 0
                    for source_id, value in values.items():
                        player_key = self.comparison["player_keys"].get(source_id)
                        if position_by_key.get(player_key) == pos and isinstance(value, (int, float)):
                            total += value
                    self.assertLessEqual(
                        abs(total - target),
                        tolerance,
                        f"{source} {key} {pos} total {total:.1f} should match fixed-pie target {target}",
                    )

    def test_espn_adjusted_values_track_peer_sources(self):
        players = load_json(FIXTURES / "players.json")["players"]
        by_name = {player["name"]: player for player in players}
        by_key = {player["player_key"]: player for player in players}
        position_order = ["QB", "RB", "WR", "TE"]
        roster = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "BENCH": 6}
        teams = 12
        bench_share = 0.15

        def player_rank(player):
            return player.get("preseason_ecr_rank") or 9999

        def combo_key(source):
            if source in {"fantasycalc", "fantasycalc_adjusted"}:
                return "full_12_qb1"
            return "full_12"

        def source_values(source):
            combo = self.comparison["sources"][source]["combos"][combo_key(source)]
            raw = combo.get("values") or combo.get("reindexed") or {}
            return {
                self.comparison["player_keys"][source_id]: value
                for source_id, value in raw.items()
                if isinstance(value, (int, float))
            }

        def roles_from_values(values):
            rows = sorted(
                [
                    (player_key, value, by_key[player_key])
                    for player_key, value in values.items()
                    if player_key in by_key and by_key[player_key]["pos"] in position_order and value > 0
                ],
                key=lambda row: (-row[1], player_rank(row[2]), row[2]["name"]),
            )
            roles = {}
            for pos in position_order:
                for player_key, _, _ in [row for row in rows if row[2]["pos"] == pos][: teams * roster[pos]]:
                    roles[player_key] = "starter"
            for player_key, _, player in [row for row in rows if row[2]["pos"] in {"RB", "WR", "TE"} and row[0] not in roles][: teams * roster["FLEX"]]:
                roles[player_key] = "starter"
            for player_key, _, _ in [row for row in rows if row[0] not in roles][: teams * roster["BENCH"]]:
                roles[player_key] = "bench"
            return roles

        def espn_projection_roles():
            rows = sorted(
                [
                    (player["player_key"], player.get("espn_ppg", {}).get("ppr"), player)
                    for player in players
                    if player["pos"] in position_order and isinstance(player.get("espn_ppg", {}).get("ppr"), (int, float))
                ],
                key=lambda row: (-row[1], player_rank(row[2]), row[2]["name"]),
            )
            roles = {}
            for pos in position_order:
                for player_key, _, _ in [row for row in rows if row[2]["pos"] == pos][: teams * roster[pos]]:
                    roles[player_key] = "starter"
            for player_key, _, player in [row for row in rows if row[2]["pos"] in {"RB", "WR", "TE"} and row[0] not in roles][: teams * roster["FLEX"]]:
                roles[player_key] = "starter"
            for player_key, _, _ in [row for row in rows if row[0] not in roles][: teams * roster["BENCH"]]:
                roles[player_key] = "bench"
            return roles

        fixed_pies = sorted(
            sum(item["target_total"] for item in source_data["combos"][combo_key(source)]["index_total"].values())
            for source, source_data in self.comparison["sources"].items()
            if combo_key(source) in source_data["combos"]
        )
        middle = len(fixed_pies) // 2
        target_total = fixed_pies[middle] if len(fixed_pies) % 2 else (fixed_pies[middle - 1] + fixed_pies[middle]) / 2

        def split_to_fixed_pie(values, roles):
            starter_total = sum(max(0, value) for player_key, value in values.items() if roles.get(player_key) == "starter")
            bench_total = sum(max(0, value) for player_key, value in values.items() if roles.get(player_key) == "bench")
            adjusted = {}
            for player_key, value in values.items():
                if roles.get(player_key) == "starter":
                    adjusted[player_key] = max(0, value) * (target_total * (1 - bench_share) / starter_total)
                elif roles.get(player_key) == "bench":
                    adjusted[player_key] = max(0, value) * (target_total * bench_share / bench_total)
                else:
                    adjusted[player_key] = 0
            return adjusted

        espn = split_to_fixed_pie(source_values("espn"), espn_projection_roles())
        peers = {
            source: split_to_fixed_pie(source_values(source), roles_from_values(source_values(source)))
            for source in ["fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted"]
        }

        for name in ["Josh Allen", "Jahmyr Gibbs", "Bijan Robinson", "Puka Nacua", "Ja'Marr Chase", "Trey McBride"]:
            player_key = by_name[name]["player_key"]
            peer_values = sorted(values[player_key] for values in peers.values())
            peer_median = peer_values[len(peer_values) // 2]
            self.assertLess(
                abs(espn[player_key] - peer_median) / peer_median,
                0.18,
                f"ESPN adjusted value for {name} should stay near the adjusted-source cluster",
            )

    def test_nulls_are_not_silently_zero_filled(self):
        by_name = {player["name"]: player for player in self.players["players"]}
        self.assertIsNone(by_name["Kyle Juszczyk"].get("pm_ros"))
        self.assertNotEqual(0, by_name["Kyle Juszczyk"].get("pm_ros"))
        text = (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        self.assertIn("return null", text)
        self.assertRegex(text, r"drawing\s*=\s*false")

    def test_roster_lines_are_two_transitions(self):
        text = (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        self.assertIn("Starter → Bench", text)
        self.assertIn("Bench → Waiver", text)
        self.assertIn("same fixed pie split", text)
        self.assertIn("fixedPieDiagnostics", text)
        self.assertIn("window.TradeValueCurveDiagnostics", text)

    def test_curve_defaults_are_grouped_and_include_raw_value_above_waivers(self):
        text = (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        html = (APP / "index.html").read_text(encoding="utf-8")
        self.assertIn("Bottom-up indexed", text)
        self.assertIn("Adjusted source projects", text)
        self.assertIn("Direct published charts", text)
        self.assertIn("Raw value above waivers", text)
        self.assertIn('DEFAULT_INDEXED_SOURCES = ["espn"]', text)
        self.assertIn("buildCbsAdjustedMap", text)
        self.assertIn("buildEspnIndexedMap", text)
        self.assertIn("buildEspnRows", text)
        self.assertIn("DEFAULT_BENCH_SHARE = 0.15", text)
        self.assertIn("setBenchShare", text)
        self.assertIn("buildPublishedSourceMap", text)
        self.assertIn("rawProjectionVorp", text)
        self.assertIn("Bench %", text)
        self.assertIn("espn_vorp", text)
        self.assertIn("visiblePlayersList", html)
        self.assertIn("curvePlayerSearch", html)
        self.assertIn("yslider", html)
        self.assertNotIn("Legacy projection comparison", html)
        self.assertIn('let position = "ALL"', text)
        self.assertIn('let lockOrder = "espn"', text)
        self.assertIn('sourceAvailable("fantasycalc_adjusted")', text)

    def test_dashboard_copy_does_not_surface_old_branding(self):
        html = (APP / "index.html").read_text(encoding="utf-8")
        assets = "\n".join(
            (APP / "assets" / name).read_text(encoding="utf-8")
            for name in ["curve-widget.js", "comparison-dashboard.js", "comparison-dashboard.css"]
        )
        self.assertIn("<title>Trade Value Dashboard</title>", html)
        self.assertNotIn("Data Driven Football", html)
        self.assertNotIn("legacy model", html.lower())
        self.assertNotIn('"key":"ddf"', html)
        self.assertNotIn("DDF", assets)
        self.assertNotIn("sourcePicker", assets)

    def test_source_compatibility_uses_selected_league_shape(self):
        curve = (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        comparison = (APP / "assets" / "comparison-dashboard.js").read_text(encoding="utf-8")
        self.assertIn("sourceComboExists", curve)
        self.assertIn('return `${score}_${teams}`', curve)
        self.assertIn("Not available for", comparison)
        self.assertIn('return `${score}_${state.teams}`', comparison)
        self.assertIn("activeReferenceWeek", comparison)
        self.assertIn("isWeekCurrent", comparison)
        self.assertIn("sourceAvailable", comparison)
        self.assertIn("sourceIsStale", comparison)
        self.assertIn("stale", comparison)

    def test_kdst_projection_path_is_available_without_preseason_rank(self):
        text = (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        players = load_json(FIXTURES / "players.json")["players"]
        specialists = [player for player in players if player.get("pos") in {"K", "DST"}]
        self.assertTrue(specialists)
        self.assertTrue(any(max((value for value in (player.get("ecr_ppg") or {}).values() if isinstance(value, (int, float))), default=0) > 0 for player in specialists))
        self.assertIn('"K", "K"', text)
        self.assertIn('"DST", "DST"', text)
        self.assertIn("K/DST projection artifact", text)

    def test_all_position_order_and_y_axis_use_visible_window(self):
        text = (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        self.assertIn('position === "ALL" && lockOrder === "preseason"', text)
        self.assertIn("selectedRankSourceKey", text)
        self.assertIn("every curve shares", text)
        self.assertIn("sharedPlayerAxis", text)
        self.assertIn("row.values[sourceKey]", text)
        self.assertIn("slice(Math.max(0, zoomLow - 1), Math.max(zoomLow, zoomHigh))", text)
        self.assertIn("syncYAxis", text)
        self.assertIn("yAxisAuto", text)

    def test_top_indexed_values_preserve_high_overall_scale(self):
        gibbs_values = []
        for source, source_data in self.comparison["sources"].items():
            combo = source_data["combos"].get("full_12") or source_data["combos"].get("full_12_qb1")
            if not combo:
                continue
            values = combo.get("values") or combo.get("reindexed") or {}
            value = values.get("jahmyr gibbs")
            if isinstance(value, (int, float)):
                gibbs_values.append(value)
        # Guards against an indexed scale collapsing toward zero. The ceiling
        # is set by the ESPN anchor every promoted source is reindexed onto,
        # so it must not be pinned above it -- the old `max >= 84` recorded a
        # pre-anchor FantasyCalc peak and failed the moment promotion worked.
        self.assertGreaterEqual(min(gibbs_values), 78)
        self.assertGreaterEqual(max(gibbs_values), 80)

    def test_player_table_supports_configurable_expandable_fields(self):
        text = (APP / "assets" / "comparison-dashboard.js").read_text(encoding="utf-8")
        self.assertIn('key:"latest_news"', text)
        self.assertIn("visibleColumns()", text)
        self.assertIn("setTableSort", text)
        self.assertIn("renderExpandedRow", text)
        self.assertIn("TradeValuePlayerNews", text)
        self.assertIn("buildEspnIndexedMap", text)
        self.assertIn("buildEspnVorpMap", text)
        self.assertIn("normalizeRosterShape", text)
        self.assertIn("buildEspnRows", text)
        self.assertIn("DEFAULT_BENCH_SHARE = 0.15", text)
        self.assertIn('key:"espn_role"', text)
        self.assertIn("ESPN raw value above waivers", text)

    def test_data_health_surfaces_player_news_pipeline(self):
        html = (APP / "index.html").read_text(encoding="utf-8")
        self.assertIn('fetch("assets/player-news.json")', html)
        self.assertIn("Player news pipeline", html)
        self.assertIn("review_queue_count", html)
        self.assertIn("review_suppression_counts", html)
        self.assertIn("news matches", html)
        self.assertIn("source_refresh_at", html)
        self.assertIn("latest_actionable_news_at", html)
        self.assertIn("injury_data_updated_at", html)
        self.assertIn('fetch("assets/reference-freshness.json")', html)
        self.assertIn("Reference freshness pipe", html)
        self.assertTrue((APP / "assets" / "reference-freshness.json").exists())

    def test_player_news_fixture_schema_supports_muse_review_layer(self):
        self.assertEqual("player-news-v2", self.news["meta"]["schema"])
        self.assertIsNotNone(self.news["meta"]["generated_at"])
        self.assertEqual(544, self.news["meta"]["matched_item_count"])
        self.assertEqual(16, self.news["meta"]["adjustment_count"])
        self.assertEqual(4, self.news["meta"]["checked_but_not_adjusted_count"])
        self.assertEqual(138, self.news["meta"]["review_queue_count"])
        self.assertEqual(147, self.news["meta"]["suppressed_review_count"])
        self.assertEqual({"already_reviewed": 89, "duplicate": 30, "low_signal": 28}, self.news["meta"]["review_suppression_counts"])
        self.assertIn("source_refresh_at", self.news["meta"])
        self.assertIn("latest_actionable_news_at", self.news["meta"])
        self.assertIn("injury_data_updated_at", self.news["meta"])
        self.assertGreaterEqual(len(self.news["news_by_player_key"]), 100)
        self.assertEqual(16, len(self.news["adjustments_by_player_key"]))
        self.assertEqual(4, len(self.news["checked_but_not_adjusted"]))
        self.assertIn("trade_values_published_at", self.news["meta"])
        adjustments = [entry for entries in self.news["adjustments_by_player_key"].values() for entry in entries]
        by_id = {entry["id"]: entry for entry in adjustments}
        self.assertTrue(by_id["aj-brown-high-ankle-ir-20260911"]["consumed"])
        self.assertFalse(by_id["zay-flowers-hamstring-20260918"]["consumed"])

    def test_player_news_matching_is_full_name_precision_first(self):
        players, by_name, _ = ingest_player_news.load_players()
        entry = {
            "title": "A.J. Brown limited in practice after high-ankle sprain",
            "summary": "Team says A.J. Brown is questionable for Sunday.",
            "source": "Team report",
        }
        tags = ingest_player_news.topic_tags(entry)
        player, reason, candidates = ingest_player_news.matched_player(entry, players, by_name)
        self.assertIsNone(reason)
        self.assertEqual(468, player.player_key)
        self.assertIn("injury", tags)
        self.assertIn("injury", ingest_player_news.topic_tags({"title": "Beat update on Josh Allen", "topics": ["injury"]}))
        self.assertEqual(set(), ingest_player_news.actionable_topic_tags({"title": "Beat update on Josh Allen", "topics": ["injury"]}, ["injury"]))
        self.assertEqual([468], [candidate.player_key for candidate in candidates])

        vague_entry = {"title": "Packers love the new-look passing game", "source": "Example"}
        player, reason, candidates = ingest_player_news.matched_player(vague_entry, players, by_name)
        self.assertIsNone(player)
        self.assertEqual("no_full_name_match", reason)
        self.assertEqual([], candidates)

    def test_muse_watchlist_loader_and_review_suppression(self):
        players, by_name, _ = ingest_player_news.load_players()
        with TemporaryDirectory() as directory:
            watchlist_path = Path(directory) / "watchlist.json"
            watchlist_path.write_text(json.dumps({"players": ["Ladd McConkey", "Josh Allen"]}), encoding="utf-8")
            watchlist = ingest_player_news.load_watchlist(watchlist_path, players, by_name, 10)
        self.assertEqual(["Ladd McConkey", "Josh Allen"], [player.name for player in watchlist])

        adjusted = {468: ingest_player_news.parse_datetime_object("2026-09-11")}
        checked = {}
        self.assertTrue(ingest_player_news.suppress_review_item(468, "2026-09-13T00:12:08Z", adjusted, checked))
        self.assertFalse(ingest_player_news.suppress_review_item(468, "2026-09-14T00:12:08Z", adjusted, checked))
        pruned, counts = ingest_player_news.prune_review_queue(
            [
                {"player_key": 468, "published_at": "2026-09-13T00:12:08Z", "headline": "A.J. Brown out", "matched_player_count": 1},
                {"player_key": 869, "published_at": "2026-09-14T00:12:08Z", "headline": "NFL Week 2 injury report: Josh Allen and others", "matched_player_count": 2},
                {"player_key": 869, "published_at": "2026-09-14T00:12:08Z", "headline": "Josh Allen injury update", "matched_player_count": 1},
                {"player_key": 869, "published_at": "2026-09-14T00:12:08Z", "headline": "Josh Allen injury update", "matched_player_count": 1},
            ],
            adjusted,
            checked,
        )
        self.assertEqual(1, len(pruned))
        self.assertEqual({"already_reviewed": 1, "low_signal": 1, "duplicate": 1}, counts)

    def test_late_week_injury_freshness_gate(self):
        passing = Namespace(
            require_fresh_injury_data=True,
            today="2026-09-20T12:00:00-05:00",
            timezone="America/Chicago",
            injury_data_updated_at="2026-09-18T18:30:00-05:00",
            injury_freshness_file=None,
        )
        ingest_player_news.assert_injury_data_fresh(passing)
        derived = Namespace(
            require_fresh_injury_data=True,
            today="2026-09-20T12:00:00-05:00",
            timezone="America/Chicago",
            injury_data_updated_at=None,
            injury_freshness_file=None,
        )
        self.assertEqual(
            "2026-09-18T23:30:00Z",
            ingest_player_news.assert_injury_data_fresh(
                derived,
                [{"fetched_at": "2026-09-18T18:30:00-05:00", "title": "Fresh injury sweep"}],
            ),
        )

        failing = Namespace(
            require_fresh_injury_data=True,
            today="2026-09-20T12:00:00-05:00",
            timezone="America/Chicago",
            injury_data_updated_at="2026-09-18T12:00:00-05:00",
            injury_freshness_file=None,
        )
        with self.assertRaises(SystemExit):
            ingest_player_news.assert_injury_data_fresh(failing)

    def test_default_qb_waiver_transition_is_zero_value_boundary(self):
        players = load_json(FIXTURES / "players.json")["players"]
        by_key = {
            player["player_key"]: player
            for player in players
            if player.get("pos") in {"QB", "RB", "WR", "TE"}
        }
        sources = self.comparison["sources"]
        source_keys = [
            "usatoday",
            "fantasycalc",
            "fantasypros",
            "cbs",
            "espn",
            "fantasycalc_adjusted",
            "usatoday_adjusted",
            "fantasypros_adjusted",
        ]

        def combo_key(source):
            return "full_12_qb1" if source in {"fantasycalc", "fantasycalc_adjusted"} else "full_12"

        source_maps = {}
        for source in source_keys:
            combo = sources[source]["combos"][combo_key(source)]
            values = combo.get("values") or combo.get("reindexed") or {}
            native = combo.get("native") or {}
            source_maps[source] = {}
            for source_id, value in values.items():
                if source in {"fantasypros", "fantasypros_adjusted"} and source_id not in native:
                    continue
                player_key = self.comparison["player_keys"].get(source_id)
                if player_key in by_key and isinstance(value, (int, float)):
                    source_maps[source][player_key] = max(0, value)

        all_keys = set().union(*[set(values) for values in source_maps.values()])
        rows = []
        for player_key in all_keys:
            player = by_key[player_key]
            if player["pos"] != "QB":
                continue
            rank = player.get("preseason_ecr_rank")
            row_values = {source: source_maps[source].get(player_key) for source in source_keys}
            rows.append((rank if isinstance(rank, int) else 9999, player["name"], row_values))
        rows.sort(key=lambda item: (item[0], item[1]))

        last_positive = 0
        for index, (_, _, values) in enumerate(rows, 1):
            max_value = max([value for value in values.values() if isinstance(value, (int, float))], default=0)
            if max_value > 0:
                last_positive = index

        self.assertEqual(33, last_positive)
        self.assertEqual(34, last_positive + 1)


if __name__ == "__main__":
    unittest.main()
