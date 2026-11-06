"""JEG-1534: the /next/ preview build (pipelines/build_next_preview.py).

The preview must stay private (noindex), use the site icon, version its own
assets and data fetches with the build tag, never publish internal READMEs and
never write outside dist/next/.
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import build_next_preview as preview  # noqa: E402

TAG = "tv-20261106-1200-abcdef0"
PAGE = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<link rel="icon" href="data:,"><link rel="stylesheet" href="styles.css">'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=X">'
        '</head><body><a href="build.html">b</a><script src="site.js"></script>'
        '<script src="learn/render.js"></script></body></html>')
ROOT_ABSOLUTE = re.compile(r'(?:src|href)="/(?!/)')


class NextPreviewTest(unittest.TestCase):
    def test_page_is_noindex_once_with_site_icon(self):
        out = preview.preview_html(PAGE, TAG)
        self.assertEqual(1, out.count(preview.ROBOTS))
        self.assertLess(out.index('<meta charset="utf-8">'), out.index(preview.ROBOTS))
        self.assertIn(preview.ICON_SITE, out)
        self.assertNotIn(preview.ICON_BLANK, out)

    def test_rebuild_is_idempotent(self):
        once = preview.preview_html(PAGE, TAG)
        self.assertEqual(once, preview.preview_html(once, TAG))
        self.assertEqual(1, once.count("data-ddf-next-version"))

    def test_page_without_head_fails_loudly(self):
        with self.assertRaises(ValueError):
            preview.preview_html("<html><body>x</body></html>", TAG, "bare.html")
        out = preview.preview_html('<html><head lang="en"><title>t</title></head></html>', None)
        self.assertIn('<head lang="en">' + preview.ROBOTS, out)

    def test_only_own_assets_get_the_build_tag(self):
        out = preview.preview_html(PAGE, TAG)
        self.assertIn(f'href="styles.css?v={TAG}"', out)
        self.assertIn(f'src="site.js?v={TAG}"', out)
        self.assertIn(f'src="learn/render.js?v={TAG}"', out)
        self.assertIn('href="https://fonts.googleapis.com/css2?family=X"', out)
        self.assertIn('href="build.html"', out)

    def test_data_fetches_get_the_build_tag(self):
        out = preview.preview_html(PAGE, TAG)
        self.assertIn(f'<script data-ddf-next-version="{TAG}">', out)
        self.assertIn(f'"{TAG}"', out)
        self.assertLess(out.index(preview.ROBOTS), out.index("data-ddf-next-version"))
        self.assertLess(out.index("data-ddf-next-version"), out.index('src="site.js'))

    def test_build_writes_only_dist_next(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, dist = Path(tmp) / "src", Path(tmp) / "dist"
            (source / "learn").mkdir(parents=True)
            (source / "index.html").write_text(PAGE, encoding="utf-8")
            (source / "learn" / "posts.json").write_text("{}", encoding="utf-8")
            (source / "learn" / "README.md").write_text("internal", encoding="utf-8")
            (dist / "next").mkdir(parents=True)
            (dist / "next" / "stale.html").write_text("old", encoding="utf-8")
            (dist / "index.html").write_text("live", encoding="utf-8")
            preview.build(dist, TAG, source)
            self.assertEqual("live", (dist / "index.html").read_text(encoding="utf-8"))
            self.assertFalse((dist / "next" / "stale.html").exists())
            self.assertFalse((dist / "next" / "learn" / "README.md").exists())
            self.assertIn(preview.ROBOTS, (dist / "next" / "index.html").read_text(encoding="utf-8"))
            self.assertEqual("{}", (dist / "next" / "learn" / "posts.json").read_text(encoding="utf-8"))


@unittest.skipUnless(preview.SOURCE.is_dir(), "app/next not present")
class RealNextPagesTest(unittest.TestCase):
    """Walks the real app/next pages through the same build make sync runs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = preview.build(Path(self.tmp.name), TAG)
        self.pages = sorted(self.out.rglob("*.html"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_page_is_noindex_once_tagged_and_relative(self):
        self.assertGreaterEqual(len(self.pages), 16)
        for page in self.pages:
            name = str(page.relative_to(self.out))
            html = page.read_text(encoding="utf-8")
            with self.subTest(page=name):
                self.assertEqual(1, html.count(preview.ROBOTS))
                self.assertEqual(1, html.count(f'<script data-ddf-next-version="{TAG}">'))
                self.assertEqual([], ROOT_ABSOLUTE.findall(html))
                for ref in preview.LOCAL_ASSET.finditer(html):
                    self.fail(f"unversioned own asset {ref.group(2)}")
                self.assertEqual(html, preview.preview_html(html, TAG, name))

    def test_internal_readmes_are_not_published(self):
        self.assertEqual([], [str(p) for p in self.out.rglob("README.md")])


if __name__ == "__main__":
    unittest.main()
