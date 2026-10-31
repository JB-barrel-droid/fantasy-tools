"""Guard: v2-render also runs when a data bake lands on main (JEG-1118).

b227f453 (an automated data rebuild) pushed Compare 70 px past the fold and
nothing ran v2-render on main until the next PR, about 7 hours later (JEG-1112).
Jeremy, 2026-10-26: "Run it on push to mains that affect the data".

Two things must hold together:
  1. v2-render-test.yml has `on: push: branches: [main]` with a `paths:` filter
     that covers the files the rebuild chain commits for the page, and it keeps
     its pull_request trigger. It stays read-only (cannot loop).
  2. JEG-1441 chain commits use the main-only App token, so GitHub fires the
     push workflow directly. The App binding must remain and an explicit
     dispatch must not duplicate the render run.

Parsing is plain text (PyYAML is not on the CI unit-test step). Every rule is
negative-tested against a mutated copy of the real files.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RENDER = (ROOT / ".github/workflows/v2-render-test.yml").read_text(encoding="utf-8")
CHAIN = (ROOT / ".github/workflows/rebuild-chain.yml").read_text(encoding="utf-8")

# Files the chain and bake commit that change what the page renders
# (git show --stat b227f453 / 9c15530f / 53155f2e; rebuild-chain.yml commit step).
REQUIRED_PATHS = ("data/fixtures/current/**", "data/ddf-two-tier/**")


def on_block(text):
    m = re.search(r"^on:\s*\n((?:[ \t]+.*\n|\s*\n)+)", text, re.M)
    return m.group(1) if m else ""


def push_trigger(text):
    """(branches, paths) of the `push:` trigger, or None when there is none."""
    block = on_block(text)
    m = re.search(r"^  push:\s*\n((?:    .*\n)+)", block, re.M)
    if not m:
        return None
    body = m.group(1)
    br = re.search(r"branches:\s*\[([^\]]*)\]", body)
    branches = [b.strip(" \"'") for b in br.group(1).split(",")] if br else []
    pm = re.search(r"paths:\s*\n((?:\s+-\s+.*\n)+)", body)
    paths = re.findall(r"-\s+[\"']?([^\"'\n]+?)[\"']?\s*$", pm.group(1), re.M) if pm else []
    return branches, paths


def problems(render, chain):
    out = []
    trig = push_trigger(render)
    if trig is None:
        out.append("v2-render-test.yml has no push trigger")
    else:
        branches, paths = trig
        if branches != ["main"]:
            out.append(f"push trigger must be branches: [main], got {branches}")
        for p in REQUIRED_PATHS:
            if p not in paths:
                out.append(f"push paths filter lacks {p}")
    if not re.search(r"^  pull_request:", on_block(render), re.M):
        out.append("pull_request trigger removed")
    if not re.search(r"^  workflow_dispatch:", on_block(render), re.M):
        out.append("workflow_dispatch trigger removed (manual rendering remains supported)")
    if not re.search(r"^permissions:\s*\n\s+contents:\s*read\s*$", render, re.M):
        out.append("v2-render must stay contents: read")
    if re.search(r"git (commit|push)|contents:\s*write", render):
        out.append("v2-render must not commit or push (loop risk)")
    if 'MAIN_WRITER_TOKEN: ${{ steps.main-writer.outputs.token }}' not in chain:
        out.append("rebuild-chain.yml must publish with the App token so push triggers run")
    if 'environment: main-writer' not in chain:
        out.append("rebuild-chain.yml App token must be gated by main-writer")
    if re.search(r"actions/workflows/v2-render-test\.yml/dispatches", chain):
        out.append("explicit v2-render dispatch would duplicate the App push trigger")
    return out


class V2RenderDataPushTest(unittest.TestCase):
    def test_real_files_pass(self):
        self.assertEqual(problems(RENDER, CHAIN), [])

    def test_removing_push_trigger_is_caught(self):
        broken = re.sub(r"  push:\n    branches: \[main\]\n    paths:\n(?:      - .*\n)+", "", RENDER)
        self.assertNotEqual(broken, RENDER)
        self.assertIn("v2-render-test.yml has no push trigger", problems(broken, CHAIN))

    def test_removing_data_path_is_caught(self):
        broken = RENDER.replace('      - "data/fixtures/current/**"\n', "")
        self.assertNotEqual(broken, RENDER)
        self.assertIn("push paths filter lacks data/fixtures/current/**", problems(broken, CHAIN))

    def test_removing_path_filter_is_caught(self):
        # The push trigger's filter, not the pull_request one (JEG-1169 docs-only skip).
        broken = re.sub(r"(  push:\n    branches: \[main\]\n)    paths:\n(?:      - .*\n)+", r"\1", RENDER, count=1)
        self.assertNotEqual(broken, RENDER)
        self.assertTrue(any("paths filter" in p for p in problems(broken, CHAIN)))

    def test_pull_request_trigger_kept(self):
        broken = RENDER.replace("  pull_request:\n", "", 1)
        self.assertIn("pull_request trigger removed", problems(broken, CHAIN))

    def test_committing_workflow_is_caught(self):
        broken = RENDER.replace("contents: read", "contents: write")
        self.assertTrue(problems(broken, CHAIN))

    def test_chain_app_token_is_required_for_push_cascade(self):
        broken = CHAIN.replace('MAIN_WRITER_TOKEN: ${{ steps.main-writer.outputs.token }}', '')
        self.assertNotEqual(broken, CHAIN)
        self.assertIn("rebuild-chain.yml must publish with the App token so push triggers run", problems(RENDER, broken))

    def test_chain_app_token_environment_cannot_be_removed(self):
        broken = CHAIN.replace('environment: main-writer', '')
        self.assertNotEqual(broken, CHAIN)
        self.assertIn("rebuild-chain.yml App token must be gated by main-writer", problems(RENDER, broken))

    def test_duplicate_explicit_render_dispatch_is_caught(self):
        broken = CHAIN + "\n# actions/workflows/v2-render-test.yml/dispatches\n"
        self.assertIn("explicit v2-render dispatch would duplicate the App push trigger", problems(RENDER, broken))


if __name__ == "__main__":
    unittest.main()
