"""Standalone JEG-1420 reader: no site build, shell, roster or live sources.

The HTML fixture reads #1239's unchanged contract golden. Source variants are
produced and validated by the real offline builder, not invented UI payloads.
Run: CHROMIUM_PATH=/path/to/headless/chromium RENDER_TESTS_REQUIRED=1
     python3 -m unittest tests.test_waiver_board_view_render
"""
from __future__ import annotations

import functools
import http.server
import json
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app/v2/waiver-board-view.js"
FIXTURE = "/tests/fixtures/waiver_board_view/standalone.html"
GOLDEN = ROOT / "tests/fixtures/waiver_board/expected_half_ppr_12.json"
# Saved outputs built and replay-validated on corrected adapter head a7047158.
# Reading these needs no adapter import, producer change or site build.
SWAP_BOARDS = ROOT / "tests/fixtures/waiver_board_view/swaps_0_2.json"
sys.path.insert(0, str(ROOT / "pipelines"))
import build_waiver_board as builder  # noqa: E402
from lib.waiver_board import validate  # noqa: E402


def variant(kind):
    weekly = json.loads((ROOT / "tests/fixtures/weekly_inputs_producer/expected_wk8.json").read_text())
    values = json.loads((ROOT / "tests/fixtures/waiver_board/values_half_ppr_12.json").read_text())
    if kind == "stale":
        weekly["legs"]["experts.espn_weekly"].update(content_week=6, freshness="stale", label="stale")
    elif kind == "previous-season":
        values["season"] = 2025
    elif kind == "modeled":
        values["label"] = "modeled"
    elif kind == "one-week-behind":
        values["content_week"], values["prior"]["week"] = 7, 6
    elif kind == "unknown":
        weekly["legs"]["experts.espn_weekly"].update(content_week=None, freshness="unknown", label="modeled")
    board = builder.build_board(weekly, values, values["setting"], "2026-10-30T12:00:00Z")
    assert validate(board) == [], validate(board)
    return board


def swap_board(kind="available"):
    return json.loads(SWAP_BOARDS.read_text())["cases"][kind]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class WaiverBoardViewRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise _render_env.unavailable(str(exc))
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(
                executable_path=_render_env.chromium_executable(cls.playwright),
                args=_render_env.HERMETIC_ARGS,
            )
        except Exception as exc:
            cls.playwright.stop()
            raise _render_env.unavailable(str(exc))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1366, "height": 900})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("console", lambda message: self.errors.append(message.text) if message.type == "error" else None)
        self.page.on("requestfailed", lambda request: self.errors.append(f"{request.url}: {request.failure}"))
        self.page.on("response", lambda response: self.errors.append(f"HTTP {response.status}: {response.url}") if response.status >= 400 else None)
        self.page.goto(self.base + FIXTURE)
        self.page.wait_for_selector(".wb-player")
        self.page.wait_for_load_state("networkidle")

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def field(self, key, name):
        return self.page.locator(f'.wb-player[data-player-key="{key}"] [data-field="{name}"]')

    def order(self):
        return self.page.locator(".wb-player").evaluate_all("rows => rows.map(row => Number(row.dataset.playerKey))")

    def open_sources(self):
        if not self.page.locator(".wb-sources").evaluate("el => el.open"):
            self.page.locator(".wb-sources > summary").click()

    def test_desktop_and_mobile_layout_semantics_and_gray_week(self):
        for width in (1366, 650, 390, 320):
            with self.subTest(width=width):
                self.page.set_viewport_size({"width": width, "height": 900})
                self.page.evaluate("() => renderBoard(fixtureBoard)")
                self.assertEqual(self.page.get_by_role("heading", name="Week 8 waiver board").count(), 1)
                self.assertEqual(self.page.get_by_role("table").count(), 1)
                self.assertEqual(self.page.locator(".wb-player").count(), 9)
                self.assertEqual(self.page.evaluate("document.documentElement.scrollWidth > innerWidth"), False)
                self.assertGreater(self.page.locator("caption").bounding_box()["width"], width * 0.7)
                self.assertLess(self.page.locator("caption").bounding_box()["height"], 90)
                self.assertEqual(self.page.get_by_role("columnheader", name="This week", exact=True).count(), 1)
                self.assertNotEqual(self.field(101, "points").evaluate("el => getComputedStyle(el).backgroundColor"), self.field(101, "ddf_value").evaluate("el => getComputedStyle(el).backgroundColor"))
                if width < 651:
                    self.assertTrue(self.page.locator('.wb-player[data-player-key="101"] .wb-week-label').is_visible())
                # Every disclosure target remains usable when expanded on a phone.
                self.assertEqual(self.page.locator(".wb-sources").evaluate("el => el.open"), width > 650)
                self.open_sources()
                self.assertEqual(self.page.locator(".wb-source").count(), 9)
                self.assertEqual(self.page.evaluate("document.documentElement.scrollWidth > innerWidth"), False)
                self.assertTrue(self.page.locator("summary:visible").evaluate_all("items => items.every(el => el.getBoundingClientRect().height >= 44)"))
                self.assertTrue(self.page.locator(".wb-missing > summary:visible").evaluate_all("""items => items.every(el => {
                    const range = document.createRange(); range.selectNodeContents(el);
                    return range.getClientRects().length === 1;
                })"""), "Availability words must fit without a trailing letter on another line")
                self.page.locator(".wb-sources > summary").click()
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.screenshot(path="/tmp/jeg-1420-mobile.png", full_page=True)

    def test_zero_missing_negative_and_prior_change_remain_distinct(self):
        self.assertEqual(self.field(102, "ddf_value").locator(".wb-field-value").inner_text(), "0")
        self.assertEqual(self.field(102, "points").locator(".wb-field-value").inner_text(), "0")
        self.assertEqual(self.field(104, "change").locator(".wb-field-value").inner_text(), "0")
        self.assertEqual(self.field(101, "change").locator(".wb-field-value").inner_text(), "+4.25")
        self.assertEqual(self.field(110, "change").locator(".wb-field-value").inner_text(), "-0.5")
        for key, field, reason in ((102, "change", "no DDF Value in week 7"), (105, "ddf_value", "not priced by DDF Value at this setting"), (104, "points", "conflicting duplicate rows at the same snapshot")):
            cell = self.field(key, field)
            self.assertEqual(cell.locator(".wb-field-value").count(), 0)
            cell.locator("summary").click()
            self.assertEqual(cell.locator("p").inner_text(), reason)
        self.assertEqual(self.field(106, "bye_week").locator(".wb-field-value").inner_text(), "This week (8)")
        self.assertEqual(self.field(101, "status").locator(".wb-field-value").inner_text(), "Active")
        self.field(101, "status").locator(".wb-status-notes > summary").click()
        self.assertIn("Questionable", self.field(101, "status").inner_text())
        self.assertIn("Limited", self.field(101, "status").inner_text())

    def test_weekly_points_status_and_byes_never_change_order_or_values(self):
        expected = [104, 101, 110, 103, 106, 102, 105, 108, 109]
        self.assertEqual(self.order(), expected)
        before = self.page.locator('td:not(.wb-week) .wb-field-value').all_text_contents()
        self.page.evaluate("""() => {
            const board = structuredClone(fixtureBoard);
            board.players.reverse();
            board.players.forEach((row, i) => {
                row.this_week.points = i * 10000;
                row.this_week.status = 'Out';
                row.this_week.bye_week = 8;
                row.this_week.on_bye = true;
            });
            renderBoard(board);
        }""")
        self.assertEqual(self.order(), expected)
        self.assertEqual(self.page.locator('td:not(.wb-week) .wb-field-value').all_text_contents(), before)
        self.assertEqual(self.page.locator('thead button, thead a, thead [tabindex]').count(), 0)

    def test_contract_unavailable_sections_swaps_and_unresolved_are_literal(self):
        board = json.loads(GOLDEN.read_text())
        for state in ("sections", "swaps"):
            self.assertEqual(self.page.locator(f".wb-{state} p").inner_text(), board[state]["missing_reason"])
        self.page.locator(".wb-unresolved > summary").click()
        self.assertEqual(self.page.locator(".wb-unresolved li").all_text_contents(), [f"{row['name']}: {row['unresolved_reason']}" for row in board["unresolved"]])
        self.assertEqual(self.page.get_by_text("ADD", exact=True).count(), 0)

    def test_source_disabled_reason_is_keyboard_accessible(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.evaluate("() => renderBoard(fixtureBoard)")
        self.page.locator(".wb-sources > summary").focus()
        self.page.keyboard.press("Enter")
        source = self.page.locator('[data-source="vegas"]')
        source.locator("summary").focus()
        self.page.keyboard.press("Enter")
        self.assertTrue(source.locator(".wb-disabled-reason").is_visible())
        self.assertEqual(source.locator(".wb-disabled-reason").inner_text(), "no Vegas producer yet (JEG-1195 slice S3)")
        self.assertIn("wb-disabled", source.get_attribute("class"))
        self.page.keyboard.press("Space")
        self.assertFalse(source.locator(".wb-disabled-reason").is_visible())

    def test_labels_freshness_and_disabled_fields_match_real_contract_variants(self):
        for kind, key, label, freshness in (("stale", "points", "stale", "stale"), ("previous-season", "values", "previous-season", "stale"), ("modeled", "values", "modeled", "current"), ("one-week-behind", "values", "published", "one week behind"), ("unknown", "points", "modeled", "unknown")):
            with self.subTest(kind=kind):
                board = variant(kind)
                self.page.evaluate("board => renderBoard(board)", board)
                self.open_sources()
                source = self.page.locator(f'[data-source="{key}"]')
                self.assertEqual(source.get_attribute("data-label"), label)
                self.assertIn(freshness, source.locator("summary").inner_text())
                if not board["sources"][key]["enabled"]:
                    source.locator("summary").click()
                    self.assertEqual(source.locator(".wb-disabled-reason").inner_text(), board["sources"][key]["disabled_reason"])
                    field = "points" if key == "points" else "ddf_value"
                    self.assertEqual(self.page.locator(f'[data-field="{field}"] .wb-field-value').count(), 0)
                    self.field(101, field).locator("summary").click()
                    self.assertEqual(self.field(101, field).locator("p").inner_text(), board["sources"][key]["disabled_reason"])

    def test_settings_callback_and_read_only_setting(self):
        self.page.get_by_role("button", name="Edit league settings:").click()
        self.assertEqual(self.page.evaluate("lastSettings"), {"scoring": "half_ppr", "teams": 12, "superflex": 0})
        for scoring, label in (("standard", "Standard"), ("ppr", "PPR")):
            self.page.evaluate("""scoring => {
                const board = structuredClone(fixtureBoard);
                board.setting = {scoring, teams: 10, superflex: 1};
                TradeValueWaiverBoardView.render(document.getElementById('board'), board);
            }""", scoring)
            self.assertEqual(self.page.locator(".wb-settings").inner_text(), f"{label} · 10 teams · Superflex")
            self.assertEqual(self.page.get_by_role("button").count(), 0)

    def test_unsupported_or_incomplete_version_clears_old_rows_then_supported_patch_renders(self):
        self.page.evaluate("() => renderBoard(null)")
        self.assertEqual(self.page.get_by_role("alert").count(), 1)
        self.assertEqual(self.page.locator(".wb-player").count(), 0)
        for version in ("0.2.0", "1.0.0", "0.10.0", "0.1.0-extra"):
            self.page.evaluate("version => renderBoard({...fixtureBoard, schema_version: version})", version)
            self.assertEqual(self.page.get_by_role("alert").count(), 1)
            self.assertEqual(self.page.locator(".wb-player").count(), 0)
        self.page.evaluate("() => renderBoard({...fixtureBoard, schema_version: '0.1.9'})")
        self.assertEqual(self.page.locator(".wb-player").count(), 9)

    def test_empty_board_and_untrusted_text(self):
        board = json.loads(GOLDEN.read_text())
        board["players"] = []
        self.page.evaluate("board => renderBoard(board)", board)
        self.assertTrue(self.page.get_by_text("No players in this board.").is_visible())
        board = json.loads(GOLDEN.read_text())
        board["players"][0]["name"] = '<img src=x onerror="window.injected=true">'
        board["swaps"]["missing_reason"] = "<script>window.injected=true</script>"
        self.page.evaluate("board => renderBoard(board)", board)
        self.assertEqual(self.page.locator(".ddf-waiver-board img, .ddf-waiver-board script").count(), 0)
        self.assertEqual(self.page.evaluate("window.injected === true"), False)
        self.assertEqual(self.page.locator(".wb-swaps p").inner_text(), board["swaps"]["missing_reason"])

    def test_repeated_renders_preserve_input_and_have_one_settings_listener(self):
        self.page.evaluate("""() => {
            window.beforeBoard = JSON.stringify(fixtureBoard);
            window.settingsCalls = 0;
            for (let i = 0; i < 3; i++) TradeValueWaiverBoardView.render(document.getElementById('board'), fixtureBoard, {onSettings: () => settingsCalls++});
        }""")
        self.page.get_by_role("button", name="Edit league settings:").click()
        self.assertEqual(self.page.evaluate("settingsCalls"), 1)
        self.assertTrue(self.page.evaluate("JSON.stringify(fixtureBoard) === beforeBoard"))
        self.assertEqual(self.page.locator(".ddf-waiver-board").count(), 1)

    def test_repeated_settings_selection_preserves_host_navigation_and_filter(self):
        boards = [json.loads(GOLDEN.read_text()), variant("stale"), variant("previous-season")]
        empty = json.loads(GOLDEN.read_text())
        empty["players"], empty["unresolved"] = [], []
        self.assertEqual(validate(empty), [])
        boards.extend([empty, json.loads(GOLDEN.read_text())])
        self.page.evaluate("""() => {
            history.replaceState({tab: 'waivers', filter: 'WR'}, '', '#waivers?position=WR');
            localStorage.setItem('waiver-host-filter', 'WR');
            const input = document.createElement('input'); input.id = 'host-filter'; input.value = 'WR';
            document.body.prepend(input);
            window.selections = [];
        }""")
        for board in boards:
            self.page.evaluate("""board => {
                window.selectedBoard = board;
                TradeValueWaiverBoardView.render(document.getElementById('board'), board, {
                    onSettings: setting => { selections.push({...setting}); setting.teams = 99; }
                });
            }""", board)
            self.page.get_by_role("button", name="Edit league settings:").click()
            self.assertEqual(self.page.evaluate("location.hash"), "#waivers?position=WR")
            self.assertEqual(self.page.evaluate("history.state"), {"tab": "waivers", "filter": "WR"})
            self.assertEqual(self.page.locator("#host-filter").input_value(), "WR")
            self.assertEqual(self.page.evaluate("localStorage.getItem('waiver-host-filter')"), "WR")
            self.assertIn("12 teams", self.page.locator(".wb-settings").inner_text())
            self.assertEqual(self.page.evaluate("selectedBoard.setting"), board["setting"])
            self.assertEqual(self.page.locator(".ddf-waiver-board").count(), 1)
        self.assertEqual(self.page.evaluate("selections"), [board["setting"] for board in boards])
        self.assertEqual(self.order(), [104, 101, 110, 103, 106, 102, 105, 108, 109])

    def test_source_provenance_and_points_leg_match_stored_artifact(self):
        board = json.loads(GOLDEN.read_text())
        self.open_sources()
        for key, source in board["sources"].items():
            item = self.page.locator(f'[data-source="{key}"]')
            item.locator("summary").click()
            provenance = " · ".join(str(value) for value in (
                source["source"], source["content_season"],
                None if source["content_week"] is None else f"week {source['content_week']}",
                source["content_vintage"],
            ) if value is not None)
            if provenance:
                self.assertEqual(item.locator("p").first.inner_text(), provenance)
        self.assertEqual(self.field(101, "points").locator(".wb-points-source").get_attribute("title"), board["points_leg"])
        # v0.1 supplies provider identifiers, not publisher URLs to guess.
        self.assertEqual(self.page.locator(".ddf-waiver-board a").count(), 0)

    def test_0_2_swaps_display_supplied_order_names_gain_and_policy(self):
        board = swap_board("two_moves")
        self.page.evaluate("board => renderBoard(board)", board)
        self.assertEqual(self.page.locator(".wb-swap").evaluate_all("items => items.map(el => [Number(el.dataset.add), Number(el.dataset.drop)])"), [[112, 111], [110, 106]])
        self.assertEqual(self.page.locator(".wb-swap-add dd > span").all_text_contents(), ["Arriving RB", "Gus Golf"])
        self.assertEqual(self.page.locator(".wb-swap-drop dd > span").all_text_contents(), ["Bench TE", "Fay Foxtrot"])
        self.assertEqual(self.page.locator(".wb-swap-gain dd").all_text_contents(), ["+10", "+5.75"])
        self.assertEqual(self.page.locator(".wb-swap-policy").inner_text(), "DDF Value gain ≥ 1")
        self.assertEqual(self.page.locator(".wb-sections p").inner_text(), board["sections"]["missing_reason"])
        self.assertEqual(self.page.locator(".wb-swap-list").get_by_role("listitem").count(), 2)
        self.assertEqual(self.page.locator(".wb-unresolved li").count(), 3)
        self.assertEqual(self.field(102, "points").locator(".wb-field-value").inner_text(), "0")

    def test_0_2_standalone_fixture_urls_and_unknown_selection(self):
        for kind in ("two_moves", "open_slot", "empty", "disabled_values", "unknown_roster", "unresolved_wire"):
            with self.subTest(kind=kind):
                self.page.goto(self.base + FIXTURE + "?swaps=" + kind)
                self.page.wait_for_selector(".wb-swaps")
                self.page.wait_for_load_state("networkidle")
                self.assertEqual(self.page.evaluate("fixtureBoard"), swap_board(kind))
                self.assertEqual(self.page.locator(".wb-swap").count(), len(swap_board(kind)["swaps"]["rows"]))
        self.page.goto(self.base + FIXTURE + "?swaps=unknown")
        self.page.get_by_role("alert").wait_for()
        self.assertEqual(self.page.get_by_role("alert").inner_text(), "Unknown swap fixture")
        self.assertEqual(self.page.locator(".wb-player, .wb-swap").count(), 0)
        self.page.goto(self.base + FIXTURE)
        self.page.wait_for_selector(".wb-player")
        self.assertEqual(self.page.evaluate("fixtureBoard.schema_version"), "0.1.0")

    def test_0_2_open_slot_empty_and_unresolved_wire_are_distinct(self):
        for kind in ("open_slot", "empty", "unresolved_wire"):
            with self.subTest(kind=kind):
                board = swap_board(kind)
                self.page.evaluate("board => renderBoard(board)", board)
                self.assertEqual(self.page.locator(".wb-swap").count(), len(board["swaps"]["rows"]))
                if kind == "open_slot":
                    self.assertEqual(self.page.locator(".wb-swap-drop dd").inner_text(), "Open roster slot")
                    self.assertEqual(self.page.locator(".wb-swap-gain dd").inner_text(), "+9")
                elif kind == "empty":
                    self.assertEqual(self.page.locator(".wb-swaps-empty").inner_text(), "No swaps in this board.")
                    self.assertEqual(self.page.locator(".wb-swap-policy").inner_text(), "DDF Value gain ≥ 100")
                    board["swaps"]["request"]["gain_policy"]["comparison"] = "gt"
                    self.page.evaluate("board => renderBoard(board)", board)
                    self.assertEqual(self.page.locator(".wb-swap-policy").inner_text(), "DDF Value gain > 100")
                else:
                    self.page.locator(".wb-unresolved-wire > summary").focus()
                    self.page.keyboard.press("Enter")
                    self.assertEqual(self.page.locator(".wb-unresolved-wire li").inner_text(), "Player key 999")
                    self.assertTrue(self.page.locator(".wb-unresolved-wire li").is_visible())

    def test_0_2_unavailable_reasons_replace_old_swaps_without_guessing(self):
        for kind in ("disabled_values", "unknown_roster"):
            with self.subTest(kind=kind):
                self.page.evaluate("board => renderBoard(board)", swap_board())
                self.assertEqual(self.page.locator(".wb-swap").count(), 1)
                board = swap_board(kind)
                self.page.evaluate("board => renderBoard(board)", board)
                self.assertEqual(self.page.locator(".wb-swaps p").inner_text(), board["swaps"]["missing_reason"])
                self.assertEqual(self.page.locator(".wb-swap, .wb-swap-policy").count(), 0)
                self.assertEqual(self.page.locator(".wb-sections p").inner_text(), board["sections"]["missing_reason"])
                if kind == "disabled_values":
                    self.assertEqual(self.page.locator('[data-field="ddf_value"] .wb-field-value').count(), 0)

    def test_0_2_missing_invalid_and_unsupported_artifacts_clear_old_swaps(self):
        mutations = (
            "delete board.swaps", "delete board.swaps.request", "delete board.swaps.request.gain_policy",
            "board.swaps.request.gain_policy.minimum = null", "board.swaps.request.gain_policy.comparison = 'default'",
            "board.swaps.request.setting.teams = 10", "delete board.swaps.rows[0].gain",
            "board.swaps.rows[0].add = 999", "board.swaps.rows[0].drop = 999",
            "board.swaps.unresolved_wire_keys = null", "board.swaps.available = false",
            "board.schema_version = '0.3.0'", "board.schema_version = '0.20.0'",
            "board.sections.available = true", "delete board.sources.values",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                board = swap_board()
                self.page.evaluate("board => renderBoard(board)", board)
                self.assertEqual(self.page.locator(".wb-swap").count(), 1)
                self.page.evaluate(f"board => {{ {mutation}; renderBoard(board); }}", board)
                self.assertEqual(self.page.get_by_role("alert").count(), 1)
                self.assertEqual(self.page.locator(".wb-swap, .wb-player").count(), 0)
        board = swap_board()
        board["schema_version"] = "0.2.9"
        self.page.evaluate("board => renderBoard(board)", board)
        self.assertEqual(self.page.locator(".wb-swap").count(), 1)

    def test_0_1_and_0_2_repeated_selection_phone_layout_and_safe_text(self):
        original = json.loads(GOLDEN.read_text())
        populated = swap_board("two_moves")
        self.page.evaluate("window.selectionCount = 0")
        for width in (1366, 650, 390, 320):
            for board in (populated, original, swap_board("unknown_roster"), populated):
                self.page.set_viewport_size({"width": width, "height": 900})
                self.page.evaluate("""board => {
                    window.selectionBoard = board; window.selectionBefore = JSON.stringify(board);
                    TradeValueWaiverBoardView.render(document.getElementById('board'), board, {onSettings: () => selectionCount++});
                }""", board)
                before = self.page.evaluate("selectionCount")
                self.page.get_by_role("button", name="Edit league settings:").click()
                self.assertEqual(self.page.evaluate("selectionCount"), before + 1)
                self.assertTrue(self.page.evaluate("JSON.stringify(selectionBoard) === selectionBefore"))
                self.assertEqual(self.page.locator(".ddf-waiver-board").count(), 1)
                self.assertFalse(self.page.evaluate("document.documentElement.scrollWidth > innerWidth"))
                self.assertEqual(self.page.locator(".wb-swap").count(), len(board["swaps"].get("rows", [])))
        hostile = swap_board()
        next(row for row in hostile["players"] if row["player_key"] == 110)["name"] = '<img src=x onerror="window.injected=true">'
        self.page.evaluate("board => renderBoard(board)", hostile)
        self.assertEqual(self.page.locator(".wb-swap-add dd > span").inner_text(), '<img src=x onerror="window.injected=true">')
        self.assertEqual(self.page.locator(".wb-swaps img, .wb-swaps script").count(), 0)
        self.assertFalse(self.page.evaluate("window.injected === true"))

    def test_checks_reject_zero_fill_and_weekly_sort_mutations(self):
        code = JS.read_text()
        mutations = (
            ("const value = data[key];", "const value = data[key] == null ? 0 : data[key];", "missing"),
            ("const av = a.value.ddf_value, bv = b.value.ddf_value;", "const av = a.this_week.points, bv = b.this_week.points;", "sort"),
        )
        for old, new, kind in mutations:
            self.assertIn(old, code)
            self.page.add_script_tag(content=code.replace(old, new, 1))
            self.page.evaluate("() => renderBoard(fixtureBoard)")
            if kind == "missing":
                self.assertEqual(self.field(105, "ddf_value").locator(".wb-field-value").count(), 1)
            else:
                self.assertNotEqual(self.order(), [104, 101, 110, 103, 106, 102, 105, 108, 109])
        self.page.add_script_tag(content=code)
        self.page.evaluate("() => renderBoard(fixtureBoard)")


class WaiverBoardOrdering(unittest.TestCase):
    def test_node_copy_order_zero_missing_and_input_immutability(self):
        script = """
          const assert = require('node:assert/strict');
          const {orderedPlayers} = require(process.argv[1]);
          const rows = [
            {player_key: 1, value: {ddf_value: null}},
            {player_key: 8, value: {ddf_value: 0}},
            {player_key: 4, value: {ddf_value: -2}},
            {player_key: 3, value: {ddf_value: 6}},
            {player_key: 2, value: {ddf_value: 6}}
          ];
          const before = JSON.stringify(rows);
          assert.deepEqual(orderedPlayers(rows).map(r => r.player_key), [2,3,8,4,1]);
          assert.equal(JSON.stringify(rows), before);
        """
        subprocess.run(["node", "-e", script, str(JS)], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
