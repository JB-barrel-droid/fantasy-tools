"""JEG-1534: the /next/ preview build (pipelines/build_next_preview.py).

The preview must stay private (noindex), use the site icon, version its own
assets with the build tag, and never write outside dist/next/.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import build_next_preview as preview  # noqa: E402

PAGE = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<link rel="icon" href="data:,"><link rel="stylesheet" href="styles.css">'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=X">'
        '</head><body><a href="build.html">b</a><script src="site.js"></script>'
        '<script src="learn/render.js"></script></body></html>')


class NextPreviewTest(unittest.TestCase):
    def test_page_is_noindex_once_with_site_icon(self):
        out = preview.preview_html(PAGE, "tv-1")
        self.assertEqual(1, out.count(preview.ROBOTS))
        self.assertLess(out.index('<meta charset="utf-8">'), out.index(preview.ROBOTS))
        self.assertIn(preview.ICON_SITE, out)
        self.assertNotIn(preview.ICON_BLANK, out)
        self.assertEqual(out, preview.preview_html(out, None))

    def test_only_own_assets_get_the_build_tag(self):
        out = preview.preview_html(PAGE, "tv-1")
        self.assertIn('href="styles.css?v=tv-1"', out)
        self.assertIn('src="site.js?v=tv-1"', out)
        self.assertIn('src="learn/render.js?v=tv-1"', out)
        self.assertIn('href="https://fonts.googleapis.com/css2?family=X"', out)
        self.assertIn('href="build.html"', out)

    def test_build_writes_only_dist_next(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, dist = Path(tmp) / "src", Path(tmp) / "dist"
            (source / "learn").mkdir(parents=True)
            (source / "index.html").write_text(PAGE, encoding="utf-8")
            (source / "learn" / "posts.json").write_text("{}", encoding="utf-8")
            (dist / "next").mkdir(parents=True)
            (dist / "next" / "stale.html").write_text("old", encoding="utf-8")
            (dist / "index.html").write_text("live", encoding="utf-8")
            preview.build(dist, "tv-1", source)
            self.assertEqual("live", (dist / "index.html").read_text(encoding="utf-8"))
            self.assertFalse((dist / "next" / "stale.html").exists())
            self.assertIn(preview.ROBOTS, (dist / "next" / "index.html").read_text(encoding="utf-8"))
            self.assertEqual("{}", (dist / "next" / "learn" / "posts.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
