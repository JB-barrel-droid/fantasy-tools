"""Structural regression guard for the DEFECT 2 lock-caption invariant.

DEFECT 2 (2026-09-30): after a forced lock reset (scoring or team-size change
made the locked source unavailable), ``syncContext()`` only ran inside
``rebuildDomain()`` — i.e. BEFORE the reset — so the "locked to ..." chart
caption kept the stale pre-reset lock label. The fix re-renders the caption
with the post-reset ``lockOrder`` by calling ``syncContext()`` at the end of
``setScoring()`` / ``setTeams()``, after the reset block.

This test pins that ordering directly on ``app/trade-value-chart/assets/
curve-widget.js``: within each function's body, the last ``syncContext()``
call must come AFTER the forced-reset block
(``lockOrder = defaultValueLock()`` + ``notifyLockRevert(...)``).

The guard is behavioral-in-spirit: it FAILS against a simulated broken state
(the trailing post-reset ``syncContext();`` removed), not just asserting the
current source. A real browser render check of the caption lives in
tests/test_lock_revert_notice_render.py.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIDGET = ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js"

# Function segments, in source order. setScoring's body ends where setTeams
# begins; setTeams' ends where setLockOrder begins.
_SEGMENTS = [
    ("setScoring", r"\n  function setScoring\(value, publish = true\) \{",
     r"\n  function setTeams\(value, publish = true\) \{", "scoring change"),
    ("setTeams", r"\n  function setTeams\(value, publish = true\) \{",
     r"\n  function setLockOrder\(value, publish = true\) \{", "team size change"),
]

_RESET = "lockOrder = defaultValueLock();"
_SYNC_RE = re.compile(r"\bsyncContext\(\)\s*;")
# The exact DEFECT 2 trailing call: the comment block plus the call.
_DEFECT2_BLOCK_RE = re.compile(
    r"    // DEFECT 2: syncContext\(\) only ran inside rebuildDomain\(\).*?\n"
    r"    syncContext\(\);\n",
    re.DOTALL,
)


def _segment(src, fname, start_re, end_re):
    start = re.search(start_re, src)
    end = re.search(end_re, src)
    if not start or not end:
        raise AssertionError(f"function boundaries for {fname} not found")
    return src[start.start():end.start()]


def caption_rerendered_after_reset(segment, reason):
    """True iff the segment re-renders the caption after a forced lock reset.

    Invariant chain: ``lockOrder = defaultValueLock();`` (the reset) is
    followed by ``notifyLockRevert(prevLock, "<reason>")`` (the QA-003 notice)
    and then a ``syncContext();`` call (the DEFECT 2 caption re-render).
    """
    reset_at = segment.find(_RESET)
    notify_at = segment.find(f'notifyLockRevert(prevLock, "{reason}");')
    sync_calls = [m.start() for m in _SYNC_RE.finditer(segment)]
    if reset_at < 0 or notify_at < 0 or not sync_calls:
        return False
    return sync_calls[-1] > notify_at > reset_at


class LockResetCaptionGuardTest(unittest.TestCase):
    def test_set_scoring_caption_rerendered_after_reset(self):
        src = WIDGET.read_text(encoding="utf-8")
        segment = _segment(src, "setScoring", *_SEGMENTS[0][1:3])
        self.assertTrue(
            caption_rerendered_after_reset(segment, _SEGMENTS[0][3]),
            "setScoring must call syncContext() after the forced lock reset",
        )

    def test_set_teams_caption_rerendered_after_reset(self):
        src = WIDGET.read_text(encoding="utf-8")
        segment = _segment(src, "setTeams", *_SEGMENTS[1][1:3])
        self.assertTrue(
            caption_rerendered_after_reset(segment, _SEGMENTS[1][3]),
            "setTeams must call syncContext() after the forced lock reset",
        )

    def test_guard_fails_against_simulated_broken_state(self):
        """Removing the DEFECT 2 post-reset calls must break the guard.

        This proves the guard discriminates the broken state: it is not
        merely asserting current behavior. The pre-fix code had syncContext()
        only inside rebuildDomain() (before the reset), which is exactly what
        this simulated state restores.
        """
        src = WIDGET.read_text(encoding="utf-8")
        broken, n = _DEFECT2_BLOCK_RE.subn("", src)
        self.assertGreater(n, 0, "simulated broken state must remove the DEFECT 2 call")
        self.assertNotEqual(broken, src)
        for fname, start_re, end_re, reason in _SEGMENTS:
            segment = _segment(broken, fname, start_re, end_re)
            self.assertFalse(
                caption_rerendered_after_reset(segment, reason),
                f"guard must fail on {fname} with the DEFECT 2 call removed",
            )


if __name__ == "__main__":
    unittest.main()
