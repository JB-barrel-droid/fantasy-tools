"""JEG-793: gh_sbclient counts response bytes per (method, table)."""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipelines"))
import gh_sbclient as sb  # noqa: E402


class FakeResp:
    def __init__(self, raw):
        self._raw = raw

    def read(self):
        return self._raw


ENV = {"SUPABASE_URL": "https://example.invalid", "SUPABASE_SERVICE_KEY": "SECRETKEY"}
BODIES = [b'[{"id":1},{"id":2}]', b'[{"id":3}]', b'{"ok":true}']


class BytesCounterTest(unittest.TestCase):
    def setUp(self):
        sb._BYTES.clear()

    def _run(self, fn, bodies):
        it = iter(bodies)
        with mock.patch.dict(os.environ, ENV), \
                mock.patch("urllib.request.urlopen",
                           side_effect=lambda *a, **k: FakeResp(next(it))):
            fn()

    def test_counts_bytes_per_table_and_rpc(self):
        def calls():
            sb.get("players", "?select=*")
            sb.get("players", "?select=id")
            sb.rpc("promote", {"a": 1})
        self._run(calls, BODIES)
        self.assertEqual(sb._BYTES[("GET", "players")],
                         [2, len(BODIES[0]) + len(BODIES[1])])
        self.assertEqual(sb._BYTES[("POST", "rpc/promote")], [1, len(BODIES[2])])

    def test_summary_has_no_params_or_keys_and_is_gated(self):
        self._run(lambda: sb.get("players", "?select=*&name=eq.Secret"), BODIES[:1])
        size = len(BODIES[0])
        with mock.patch.dict(os.environ, {"SUPABASE_BYTES_LOG": "", "GITHUB_ACTIONS": ""}):
            buf = io.StringIO()
            with redirect_stderr(buf):
                sb._emit_bytes_summary()
            self.assertEqual(buf.getvalue(), "")
        with tempfile.NamedTemporaryFile("r+", suffix=".md") as step, \
                mock.patch.dict(os.environ, {"SUPABASE_BYTES_LOG": "1",
                                             "GITHUB_STEP_SUMMARY": step.name}):
            buf = io.StringIO()
            with redirect_stderr(buf):
                sb._emit_bytes_summary()
            out = buf.getvalue() + step.read()
        self.assertIn(f"GET players requests=1 bytes={size}", out)
        self.assertIn(f"| GET | players | 1 | {size} |", out)
        for leak in ("SECRETKEY", "Secret", "select"):
            self.assertNotIn(leak, out)


if __name__ == "__main__":
    unittest.main()
