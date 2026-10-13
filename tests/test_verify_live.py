"""verify_live.py markers must exist in the built dist (JEG-629).

A stale marker made the script exit 1 on a healthy site. These tests serve the
built dist/ through the script's fetch hook: a good build exits 0, a wrong build
tag exits 1, and a marker absent from dist is caught.
"""
import contextlib
import io
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import verify_live  # noqa: E402

DIST = ROOT / "dist"


def dist_fetch(path):
    f = DIST / (path or "index.html")
    return 200, f.read_text(encoding="utf-8", errors="replace")


def run(argv, fetch_fn=dist_fetch):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = verify_live.main(argv, fetch_fn)
    return code, out.getvalue()


@unittest.skipUnless((DIST / "index.html").exists(), "dist not built")
class VerifyLiveTest(unittest.TestCase):
    def tag(self):
        html = (DIST / "index.html").read_text(encoding="utf-8")
        return re.search(r'trade-chart-build" content="([^"]+)"', html).group(1)

    def test_every_marker_is_in_built_dist(self):
        code, out = run([self.tag()])
        self.assertNotIn("FAIL", out)
        self.assertEqual(code, 0)

    def test_wrong_build_tag_exits_1(self):
        code, out = run(["tv-00000000-0000-deadbeef"])
        self.assertEqual(code, 1)
        self.assertIn("FAIL: expected", out)

    def test_absent_marker_is_caught(self):
        def stripped(path):
            status, text = dist_fetch(path)
            return status, text.replace("quadraticCurveTo", "")
        code, out = run([self.tag()], stripped)
        self.assertEqual(code, 1)
        self.assertIn("missing curve smoothing", out)


if __name__ == "__main__":
    unittest.main()
