"""v2 page build: the new layout must wrap the existing engine, not replace it."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipelines"))
import build_v2_page  # noqa: E402

INDEX = """<!doctype html><html><head><title>Old</title></head><body>
<header class="topbar">old ui</header>
<script src="assets/value-model.js?v=x" defer></script>
<script src="assets/curve-widget.js?v=x" defer></script>
<script src="assets/comparison-dashboard.js?v=x" defer></script>
<script id="players-data" type="application/json">{}</script>
</body></html>"""


class BuildV2PageTest(unittest.TestCase):
    def test_engine_is_wrapped_offscreen_and_scripts_kept(self):
        html = build_v2_page.build_v2_html(INDEX, '<div id="v2App"></div>')
        self.assertIn('<base href="../">', html)
        self.assertIn('<body class="v2">', html)
        engine_open = html.index('id="legacyEngine"')
        old_ui = html.index('old ui')
        engine_close = html.index("</div>", old_ui)
        first_script = html.index('<script src="assets/value-model.js')
        # The old UI sits inside the off-screen engine container, and the
        # container closes before the engine scripts so they still load.
        self.assertLess(engine_open, old_ui)
        self.assertLess(engine_close, first_script)
        self.assertIn('id="players-data"', html)
        self.assertGreater(html.index('<script src="v2/v2.js"'), html.index('comparison-dashboard.js'))
        # The trade-targets helpers load before the view that uses them.
        self.assertGreater(html.index('<script src="v2/v2.js"'), html.index('<script src="v2/targets.js"'))
        self.assertGreater(html.index('<script src="v2/v2.js"'), html.index('<script src="v2/trade.js"'))
        # Values auditing (JEG-847): the registry loads before the two sub-tab files, and all before v2.js.
        core = html.index('<script src="v2/audit-core.js"')
        for name in ("audit-pie.js", "audit-source.js"):
            self.assertGreater(html.index(f'<script src="v2/{name}"'), core)
            self.assertLess(html.index(f'<script src="v2/{name}"'), html.index('<script src="v2/v2.js"'))
        self.assertIn('href="v2/audit-pie.css"', html)
        self.assertIn('href="v2/audit-source.css"', html)

    def test_design_flag_loads_in_head_before_paint(self):
        # JEG-1137: ?design=fieldnotes must set data-design before first paint, on both pages, after v2.css.
        for at_root in (False, True):
            html = build_v2_page.build_v2_html(INDEX, '<div id="v2App"></div>', at_root=at_root)
            tag = '<script src="v2/design-flag.js"></script>'
            self.assertEqual(html.count(tag), 1)
            self.assertLess(html.index(tag), html.index("</head>"))
            self.assertGreater(html.index(tag), html.index('href="v2/v2.css"'))
        flag_js = (build_v2_page.APP_V2 / "design-flag.js").read_text(encoding="utf-8")
        self.assertIn('get("design")', flag_js)
        self.assertIn('=== "fieldnotes"', flag_js)

    def test_research_nav_hidden_until_a_post_publishes(self):
        # JEG-1371 (Jeremy, 2026-10-29, audit decision 2: A): with no published post, neither the menu entry nor the
        # Writing sub-tab for Research is on the page, on /v2/ or at the root. One published post brings both back.
        shell = (build_v2_page.APP_V2 / "shell.html").read_text(encoding="utf-8")
        self.assertIn('data-key="writing/research"', shell)
        self.assertIn('data-writing="research"', shell)
        post = {"slug": "bench-share", "title": "Bench share", "summary": "How bench share was tested.",
                "date": "2026-11-01", "body": "<p>Body.</p>"}
        for at_root in (False, True):
            empty = build_v2_page.build_v2_html(INDEX, shell, at_root=at_root, posts=[])
            self.assertNotIn('data-key="writing/research"', empty)
            self.assertNotIn('data-writing="research"', empty)
            self.assertNotIn('<span class="v2-tab-full">Research</span>', empty)
            # The other Writing entries stay, and the Research page still builds so #writing/research resolves.
            self.assertIn('data-key="writing/how-values"', empty)
            self.assertIn('data-key="writing/manifesto"', empty)
            self.assertIn('data-writing="how-values"', empty)
            self.assertIn('id="v2Research"', empty)
            published = build_v2_page.build_v2_html(INDEX, shell, at_root=at_root, posts=[post])
            self.assertEqual(published.count('data-key="writing/research"'), 1)
            self.assertEqual(published.count('data-writing="research"'), 1)
            self.assertIn('href="#writing/research/bench-share"', published)

    def test_missing_engine_script_fails_closed(self):
        broken = INDEX.replace('<script src="assets/value-model.js?v=x" defer></script>', "")
        with self.assertRaises(SystemExit):
            build_v2_page.build_v2_html(broken, "<div></div>")


if __name__ == "__main__":
    unittest.main()
