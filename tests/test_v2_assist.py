"""JEG-1026: the built page carries the ChatGPT / Claude footer as static HTML, loads the state codec and the assist code in
order, and the connect guide it links is published. No browser needed (the render test is test_v2_assist_render.py).

Fails on origin/main: shell.html has no footer, build_v2_page loads neither script, build_llm_surfaces publishes no guide.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import build_llm_surfaces  # noqa: E402
import build_v2_page  # noqa: E402

INDEX = """<!doctype html><html><head><title>Old</title></head><body>
<script src="assets/value-model.js?v=x" defer></script>
<script src="assets/comparison-dashboard.js?v=x" defer></script>
</body></html>"""
SHELL = (ROOT / "app" / "v2" / "shell.html").read_text(encoding="utf-8")
POST = {"slug": "p", "title": "A post", "date": "2026-10-01", "summary": "s", "body_html": "<p>b</p>", "html": "<p>b</p>"}
LINE = 'Using ChatGPT or Claude? <a class="v2-link" href="' + build_v2_page.CONNECT_URL + '">Connect the tool</a>'


class AssistBuildTest(unittest.TestCase):
    def test_footer_line_is_static_html_in_both_pages(self):
        for at_root in (False, True):
            html = build_v2_page.build_v2_html(INDEX, SHELL, at_root=at_root, posts=[])
            self.assertIn(LINE, html, f"at_root={at_root}")
            self.assertNotIn("__CONNECT_URL__", html)
        # The built page embeds shell.html verbatim (tests/test_v2_contract_render.py), so the link is written out in the shell.
        self.assertIn(LINE, SHELL)

    def test_footer_is_after_the_research_tab_so_it_ends_every_tab(self):
        html = build_v2_page.build_v2_html(INDEX, SHELL, posts=[])
        self.assertGreater(html.index('id="v2Assist"'), html.index('id="v2Audit"'))
        composed = build_v2_page.compose_shell(SHELL, [])
        self.assertLess(composed.index('id="v2Research"'), composed.index('id="v2Assist"'))

    def test_codec_and_assist_load_before_the_page(self):
        html = build_v2_page.build_v2_html(INDEX, SHELL, posts=[])
        state, assist, page = (html.index(f'<script src="v2/{name}"') for name in ("ddf-state.js", "ddf-assist.js", "v2.js"))
        self.assertLess(state, assist)
        self.assertLess(assist, page)
        self.assertIn("ddf-assist.js", Path(build_v2_page.__file__).read_text(encoding="utf-8"))

    def test_the_connect_guide_the_footer_links_is_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_llm_surfaces.build(Path(tmp), "https://example.test/", "https://example.test/mcp")
            guide = (Path(tmp) / "connect" / "index.html").read_text(encoding="utf-8")
        self.assertTrue(build_v2_page.CONNECT_URL.endswith("/connect/"))
        self.assertIn("<title>Use Data Driven Football in Claude and ChatGPT</title>", guide)
        self.assertIn("Connect", guide)
        self.assertIn("<code>get_values</code>", guide)


if __name__ == "__main__":
    unittest.main()
