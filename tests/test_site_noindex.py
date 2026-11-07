"""JEG-1567: every HTML file `make sync` publishes carries the noindex meta.

Unit tests cover the injector and that SITE_NOINDEX is the only switch. The
built-tree test runs against dist/ when `make sync` has been run (CI runs it
before the tests; locally it skips unless dist/values.html, which only sync writes, exists).
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import site_noindex as sn  # noqa: E402

DIST = ROOT / "dist"
PAGE = '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>T</title></head><body>x</body></html>'


class InjectorTest(unittest.TestCase):
    def test_adds_once_after_charset_and_is_idempotent(self):
        out = sn.noindex_html(PAGE)
        self.assertEqual(1, out.count(sn.ROBOTS))
        self.assertEqual(out, sn.noindex_html(out))
        self.assertEqual(PAGE, out.replace(sn.ROBOTS, ""))   # nothing else changed

    def test_existing_noindex_kept(self):
        page = PAGE.replace("<title>", '<meta name="robots" content="noindex"><title>')
        self.assertEqual(page, sn.noindex_html(page))

    def test_indexable_robots_meta_replaced(self):
        page = PAGE.replace("<title>", '<meta name="robots" content="index, follow"><title>')
        out = sn.noindex_html(page)
        self.assertEqual(1, len(re.findall(r'name="robots"', out)))
        self.assertIn("noindex", out)

    def test_header_tag_is_not_a_head_and_reversed_attrs_are_found(self):
        out = sn.noindex_html('<header></header><head><meta charset="utf-8"></head>')
        self.assertTrue(out.startswith("<header></header><head>" + sn.ROBOTS))
        page = PAGE.replace("<title>", '<meta content="noindex" name="robots"><title>')
        self.assertEqual(page, sn.noindex_html(page))

    def test_no_head_fails_loudly(self):
        with self.assertRaises(ValueError):
            sn.noindex_html("<html><body>x</body></html>")

    def test_constant_is_the_only_switch(self):
        with tempfile.TemporaryDirectory() as d:
            dist = Path(d)
            (dist / "sub").mkdir()
            for rel in ("a.html", "sub/b.html"):
                (dist / rel).write_text(PAGE, encoding="utf-8")
            (dist / "c.md").write_text("# not html", encoding="utf-8")
            original = sn.SITE_NOINDEX
            try:
                sn.SITE_NOINDEX = False
                self.assertEqual([], sn.apply_site_noindex(dist))
                self.assertNotIn("robots", (dist / "a.html").read_text())
                sn.SITE_NOINDEX = True
                self.assertEqual(["a.html", "sub/b.html"], sn.apply_site_noindex(dist))
            finally:
                sn.SITE_NOINDEX = original
            for rel in ("a.html", "sub/b.html"):
                self.assertIn(sn.ROBOTS, (dist / rel).read_text())
            self.assertEqual("# not html", (dist / "c.md").read_text())

    def test_sync_calls_it_and_nothing_else_sets_it(self):
        sync = (ROOT / "pipelines" / "sync_dashboard_artifacts.py").read_text()
        self.assertIn("apply_site_noindex(DIST)", sync)
        self.assertNotIn("SITE_NOINDEX =", sync)
        self.assertGreater(sync.index("apply_site_noindex(DIST)"), sync.index("build_values_explainer(["))
        hits = [p.name for p in (ROOT / "pipelines").glob("*.py")
                if "SITE_NOINDEX =" in p.read_text() and p.name != "site_noindex.py"]
        self.assertEqual([], hits)


@unittest.skipUnless(DIST.joinpath("values.html").exists(), "dist/ not built (run make sync)")
class BuiltSiteTest(unittest.TestCase):
    def test_every_published_html_is_noindex(self):
        self.assertTrue(sn.SITE_NOINDEX)
        pages = sorted(DIST.rglob("*.html"))
        self.assertGreater(len(pages), 10)
        missing = [str(p.relative_to(DIST)) for p in pages
                   if not re.search(r'<meta\s+name="robots"[^>]*noindex', p.read_text(encoding="utf-8"))]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
