"""Homepage AI connection panel (JEG-1266): truthful setup and sharing states, the copy pack, and the live adapter.

The state checks live in tests/ai_connection_panel_harness.cjs (pure Node, no browser). Every guard is proven:
test_checks_fail_on_broken_builds copies the module, breaks one rule at a time, and requires the harness to name the check
that catches it. The copy checks below are the JEG-1223 / JEG-1252 acceptance checks 2, 3, 4, 8, 9 and 10, run over every
string the panel can show.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "v2"
SOURCE = APP / "ai-connection-panel.js"
HARNESS = ROOT / "tests" / "ai_connection_panel_harness.cjs"
COPY_PACK = ROOT / "docs" / "product" / "jeg-1223-ai-onboarding-copy.md"   # lands with PR #1078
# JEG-1130's launch copy rule (tests/test_launch_copy_guard.py) wins over the pack: storage copy says "on this device",
# never "in this browser". The pack at PR #1078 head 91b0328 still has the browser wording for this one line.
LAUNCH_COPY_RULE = {  # pack wording -> wording the launch rule allows (ai.link.local)
    "Your saved work stays in this browser. A link carries only what is in its address.":
        "Your saved work stays on this device. A link carries only what is in its address.",
}

REQUIRED = [
    "test_states_are_distinct", "test_never_claims_connected", "test_unknown_is_not_true", "test_connect_explained_once",
    "test_copy_actions", "test_copy_failure_shows_link", "test_copy_result_only_when_ready", "test_missing_league",
    "test_default_league_labelled", "test_fixture_labelled", "test_context_not_mutated", "test_live_adapter_unknown_before_attach",
    "test_live_adapter_reads_link", "test_live_adapter_guide_and_clipboard",
    # mount(): a copy result belongs to the view it was started on (JEG-1300)
    "test_copy_result_on_its_own_view", "test_late_copy_dropped_after_hashchange", "test_same_route_change_drops_copy",
    "test_newer_press_and_destroy_drop_copy",
]

# (what is broken, old text, new text, the check that must catch it)
MUTATIONS = [
    ("connection read from the context", 'connection: "unknown",', 'connection: c.connection || "unknown",', "test_never_claims_connected"),
    ("connected flag shown", 'heading: COPY["ai.h"], body: COPY["ai.body"],',
     'heading: COPY["ai.h"], body: c.connected ? "You\'re connected." : COPY["ai.body"],', "test_never_claims_connected"),
    ("unknown guide shown as available", 'if (cap === true) return {state: "available"', 'if (cap !== false) return {state: "available"',
     "test_unknown_is_not_true"),
    ("unknown link builder offered", 'if (caps.linkCodec !== true || !share)', 'if (!share)', "test_unknown_is_not_true"),
    ("clipboard off still tried", 'if (io.clipboard === false || typeof', 'if (typeof', "test_copy_actions"),
    ("failure reported as copied", 'return {status: "failed", url};\n    }', 'return {status: "copied", url};\n    }', "test_copy_actions"),
    ("failure hides the link", 'text: COPY["ai.err.copy"], url: copy.url}', 'text: COPY["ai.err.copy"], url: null}', "test_copy_failure_shows_link"),
    ("stale copy result kept", 'copy: share.state === "ready" ? copyState(copy) : copyState(null)', 'copy: copyState(copy)',
     "test_copy_result_only_when_ready"),
    ("missing league still shares", 'if (share.league !== "saved" && !work.length)', 'if (false)', "test_missing_league"),
    ("default settings called yours", 'share.league === "saved" ? "your league settings"', 'share.league ? "your league settings"',
     "test_default_league_labelled"),
    ("fixture label dropped", 'fixture: c.fixture ?', 'fixture: false ?', "test_fixture_labelled"),
    ("adapter assumes attached", '} catch (error) { return {codec: null, link: null}; }', '} catch (error) { return {codec: true, link: null}; }',
     "test_live_adapter_unknown_before_attach"),
    ("adapter assumes the guide", 'setupGuide: guide ? true : (doc && doc.readyState !== "loading" ? false : null)', 'setupGuide: true',
     "test_live_adapter_guide_and_clipboard"),
    ("adapter ignores insecure pages", ' && r.isSecureContext !== false', '', "test_live_adapter_guide_and_clipboard"),
    # JEG-1300: each guard on a late copy result, removed one at a time
    ("older press overwrites a newer one", 'if (destroyed || mine !== revision) return;', 'if (destroyed) return;',
     "test_newer_press_and_destroy_drop_copy"),
    ("hashchange keeps a running copy", 'const onHash = () => { clear(); };', 'const onHash = () => { live.textContent = ""; update(null); };',
     "test_late_copy_dropped_after_hashchange"),
    ("late copy ignores a same-route change", 'if (viewKey(now) !== key) { clear(); return; }', '',
     "test_same_route_change_drops_copy"),
    ("update() replays an old result", 'if (last && key !== lastKey)', 'if (false)', "test_same_route_change_drops_copy"),
    ("destroy() keeps a running copy", 'destroyed = true;\n      revision += 1;\n', '', "test_newer_press_and_destroy_drop_copy"),
]

FORBIDDEN = ["tested", "import", "sync", "automatic", "same numbers", "guarantee", "will accept", "perfect", "sleeper", "espn", "yahoo",
             "same view", "keep working", "picks up from there", "full round trip", "full trade analysis", "complete lineup",
             "works the same"]


def run_harness(modules_dir: Path) -> dict:
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", str(HARNESS), str(modules_dir)], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise AssertionError(f"harness crashed: {out.stderr[-1500:]}")
    return json.loads(out.stdout)


def panel_strings() -> dict:
    """Every COPY and UI string, read from the module through Node."""
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    script = f"const P = require({json.dumps(str(SOURCE))}); process.stdout.write(JSON.stringify({{copy: P.COPY, ui: P.UI, guide: P.GUIDE_URL}}));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


def pack_strings(text: str) -> dict:
    """String ID -> string from the copy pack's tables (`| `id` | string | ...`)."""
    found = {}
    for line in text.splitlines():
        m = re.match(r"\|\s*`(ai\.[a-z0-9.]+)`\s*\|(.*)$", line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        # Fallback/error rows put the string in the third column (ID | When | String).
        value = cells[1] if m.group(1).startswith("ai.err.") else cells[0]
        found[m.group(1)] = value
    return found


class AiConnectionPanelLogicTest(unittest.TestCase):
    def test_every_check_passes(self):
        result = run_harness(APP)
        self.assertEqual(sorted(result), sorted(REQUIRED), "harness checks and REQUIRED drifted")
        failed = {k: v for k, v in result.items() if v is not True}
        self.assertEqual(failed, {})

    def test_panel_never_writes_storage_or_calls_out(self):
        source = SOURCE.read_text(encoding="utf-8")
        for needle in ("localStorage", "sessionStorage", "indexedDB", "store.replace", "store.set", "store.update", "fetch(",
                       "XMLHttpRequest", "sendBeacon", "WebSocket"):
            self.assertNotIn(needle, source)

    def test_checks_fail_on_broken_builds(self):
        source = SOURCE.read_text(encoding="utf-8")
        for what, old, new, check in MUTATIONS:
            with self.subTest(what):
                self.assertEqual(source.count(old), 1, f"mutation anchor is stale or not unique: {old}")
                with tempfile.TemporaryDirectory() as tmp:
                    (Path(tmp) / "ai-connection-panel.js").write_text(source.replace(old, new), encoding="utf-8")
                    result = run_harness(Path(tmp))
                self.assertIsNot(result.get(check), True, f"{check} did not catch: {what}")


class AiConnectionPanelCopyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.strings = panel_strings()
        cls.all = list(cls.strings["copy"].values()) + list(cls.strings["ui"].values())

    def test_copy_is_the_pack_verbatim(self):
        # Runs once PR #1078's copy pack is on the branch; until then it is checked against the pack's own branch by hand
        # (docs/claude-log/2026-10-29-jeg-1266-ai-connection-panel.md).
        if not COPY_PACK.exists():
            self.skipTest("copy pack not on this branch yet (PR #1078)")
        pack = pack_strings(COPY_PACK.read_text(encoding="utf-8"))
        for key, value in self.strings["copy"].items():
            with self.subTest(key):
                self.assertIn(key, pack)
                want = pack[key].replace(" `<url>` (matches today's fallback, `v2.js` `Copy this link:`)", "")
                want = LAUNCH_COPY_RULE.get(want, want)
                self.assertEqual(value, want)

    def test_guide_link_is_the_footer_link(self):
        # Acceptance check 2: the same href as the footer's Connect the tool.
        shell = (APP / "shell.html").read_text(encoding="utf-8")
        self.assertIn(f'href="{self.strings["guide"]}">Connect the tool</a>', shell)

    def test_no_forbidden_claim(self):
        # Acceptance checks 3 and 8, plus the ticket's: no parity, complete-lineup or sync promise.
        for text in self.all:
            for word in FORBIDDEN:
                with self.subTest(word=word, text=text[:40]):
                    self.assertNotIn(word, text.lower())

    def test_free_and_no_account_only_next_to_ddf(self):
        # Acceptance check 9.
        for text in self.all:
            for sentence in re.split(r"(?<=[.?!])\s+", text):
                if re.search(r"\bfree\b|no (ddf )?account|sign-in", sentence, re.I):
                    with self.subTest(sentence=sentence):
                        self.assertRegex(sentence, r"Data Driven Football|DDF")

    def test_never_says_not_connected_as_fact(self):
        # Acceptance checks 4 and 10: no detected connection state either way.
        for text in self.all:
            with self.subTest(text=text[:40]):
                self.assertNotRegex(text, r"(?i)\b(isn't|is not|not) connected\b|\byou're connected\b|\byou are connected\b|✓")


if __name__ == "__main__":
    unittest.main()
