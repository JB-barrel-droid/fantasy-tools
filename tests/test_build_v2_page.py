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

    def test_missing_engine_script_fails_closed(self):
        broken = INDEX.replace('<script src="assets/value-model.js?v=x" defer></script>', "")
        with self.assertRaises(SystemExit):
            build_v2_page.build_v2_html(broken, "<div></div>")


if __name__ == "__main__":
    unittest.main()
