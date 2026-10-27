"""Guard: the CI speed-up settings stay in place (JEG-1169).

  - every workflow that installs Playwright browsers caches ~/.cache/ms-playwright
    with a key carrying the pinned Playwright version, and that version matches
    the python pin and tests/rendered_gate/package.json (both share one build);
  - Chromium is installed once per job: no `playwright-core install` after the
    python `playwright install`;
  - every preview job has a timeout (default is 6 hours) and v2-render has room for a
    slow browser install;
  - the docs-only skip on pull requests never skips a tests-only PR and keeps
    the docs the build reads.

Plain-text parsing on purpose (PyYAML is not on the CI runner). Each rule is
negative-tested against a mutated copy of the real file.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
BROWSER_WORKFLOWS = ("preview.yml", "pages.yml", "v2-render-test.yml", "full-suite.yml")
PR_FILTERED = ("preview.yml", "v2-render-test.yml")
BUILD_DOCS = ("docs/methodology.md", "docs/math-review-agenda.md", "docs/use-ddf-in-claude-chatgpt.md", "app/llm/**")
NPM_VERSION = json.loads((ROOT / "tests/rendered_gate/package.json").read_text(encoding="utf-8"))["dependencies"]["playwright-core"]


def read(name):
    return (WF / name).read_text(encoding="utf-8")


def browser_problems(name, text):
    out = []
    pins = set(re.findall(r"pip install --quiet playwright==([0-9.]+)", text))
    if len(pins) != 1:
        out.append(f"{name}: expected one python playwright pin, found {sorted(pins)}")
        return out
    pin = pins.pop()
    if pin != NPM_VERSION:
        out.append(f"{name}: python playwright {pin} != playwright-core {NPM_VERSION} (one browser build)")
    m = re.search(r"uses: actions/cache@v\d+\n\s+with:\n\s+path: ~/\.cache/ms-playwright\n\s+key: (.+)$", text, re.M)
    if not m:
        out.append(f"{name}: no actions/cache step for ~/.cache/ms-playwright")
    elif pin not in m.group(1):
        out.append(f"{name}: cache key {m.group(1)} does not carry playwright {pin}")
    elif text.index("~/.cache/ms-playwright") > text.index("playwright install"):
        out.append(f"{name}: the cache step must come before the browser install")
    if re.search(r"^\s+npx [^\n#]*playwright-core install", text, re.M):
        out.append(f"{name}: Chromium installed twice (playwright-core install after the python install)")
    return out


def job_timeout(text, job):
    m = re.search(rf"^  {re.escape(job)}:\n((?:    .*\n)+)", text, re.M)
    t = re.search(r"^    timeout-minutes: (\d+)$", m.group(1), re.M) if m else None
    return int(t.group(1)) if t else None


def pr_paths(text):
    m = re.search(r"^  pull_request:\n((?:    .*\n)+)", text, re.M)
    if not m:
        return None
    p = re.search(r"^    paths:\n((?:      - .*\n)+)", m.group(1), re.M)
    return re.findall(r"-\s+[\"']?([^\"'\n]+?)[\"']?\s*$", p.group(1), re.M) if p else []


def matches(pattern, path):
    rx = re.escape(pattern).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.fullmatch(rx, path) is not None


def triggers(patterns, path):
    """GitHub `paths` semantics: last matching pattern wins, `!` excludes."""
    hit = False
    for p in patterns:
        neg = p.startswith("!")
        if matches(p[1:] if neg else p, path):
            hit = not neg
    return hit


def filter_problems(name, text):
    out = []
    if re.search(r"^    paths-ignore:", text, re.M):
        out.append(f"{name}: use `paths` with ! patterns, not paths-ignore")
    pats = pr_paths(text)
    if pats is None:
        return [f"{name}: no pull_request trigger"]
    if not pats:
        return out
    for path in ("tests/test_example.py", "pipelines/x.py", ".github/workflows/preview.yml",
                 "app/llm/skill/SKILL.md", "Makefile"):
        if not triggers(pats, path):
            out.append(f"{name}: a PR changing only {path} would skip the check")
    for path in BUILD_DOCS:
        probe = path.replace("**", "skill/SKILL.md")
        if not triggers(pats, probe):
            out.append(f"{name}: {probe} feeds the build but a PR changing it would skip the check")
    for path in ("README.md", "docs/claude-log/x.md", "docs/runbook.txt"):
        if triggers(pats, path):
            out.append(f"{name}: a docs-only PR ({path}) still runs the check")
    return out


class CiSpeedupTest(unittest.TestCase):
    def test_real_workflows_cache_and_install_once(self):
        for name in BROWSER_WORKFLOWS:
            self.assertEqual([], browser_problems(name, read(name)))

    def test_real_timeouts(self):
        # JEG-1170: preview-build carries the ~45-minute budget; each test-core shard
        # and the aggregate `preview` check have their own, shorter one.
        self.assertTrue(45 < (job_timeout(read("preview.yml"), "preview-build") or 0) <= 90)
        self.assertTrue(15 < (job_timeout(read("preview.yml"), "preview-shard") or 0) <= 45)
        self.assertIsNotNone(job_timeout(read("preview.yml"), "preview"))
        self.assertGreaterEqual(job_timeout(read("v2-render-test.yml"), "v2-render") or 0, 25)

    def test_real_docs_only_filter(self):
        for name in PR_FILTERED:
            self.assertEqual([], filter_problems(name, read(name)))

    def test_pages_has_no_path_filter(self):
        self.assertIsNone(re.search(r"paths", read("pages.yml")))

    def test_missing_cache_is_caught(self):
        text = read("preview.yml").replace("path: ~/.cache/ms-playwright", "path: ~/.cache/other")
        self.assertTrue(any("no actions/cache" in p for p in browser_problems("preview.yml", text)))

    def test_stale_cache_key_is_caught(self):
        text = read("pages.yml").replace("ms-playwright-${{ runner.os }}-1.49.1", "ms-playwright-${{ runner.os }}-1.48.0")
        self.assertTrue(any("does not carry" in p for p in browser_problems("pages.yml", text)))

    def test_second_install_is_caught(self):
        text = read("pages.yml").replace("npm ci --prefix tests/rendered_gate\n",
                                         "npm ci --prefix tests/rendered_gate\n"
                                         "          npx --prefix tests/rendered_gate playwright-core install --with-deps chromium\n", 1)
        self.assertTrue(any("installed twice" in p for p in browser_problems("pages.yml", text)))

    def test_version_drift_is_caught(self):
        text = read("v2-render-test.yml").replace("playwright==1.49.1", "playwright==1.50.0")
        self.assertTrue(any("one browser build" in p for p in browser_problems("v2-render-test.yml", text)))

    def test_missing_preview_timeout_is_caught(self):
        for job, minutes in (("preview-build", 60), ("preview-shard", 30), ("preview", 5)):
            text = re.sub(rf"    timeout-minutes: {minutes}\n", "", read("preview.yml"))
            self.assertIsNone(job_timeout(text, job), job)

    def test_filter_skipping_tests_is_caught(self):
        text = read("preview.yml").replace('      - "!docs/**"\n', '      - "!docs/**"\n      - "!tests/**"\n', 1)
        self.assertTrue(any("tests/test_example.py" in p for p in filter_problems("preview.yml", text)))

    def test_filter_dropping_build_docs_is_caught(self):
        text = read("v2-render-test.yml").replace('      - "docs/methodology.md"\n', "", 1)
        self.assertTrue(any("docs/methodology.md" in p for p in filter_problems("v2-render-test.yml", text)))

    def test_matcher_semantics(self):
        self.assertTrue(matches("**/*.md", "README.md"))
        self.assertTrue(matches("**/*.md", "a/b/c.md"))
        self.assertTrue(matches("docs/**", "docs/a/b.txt"))
        self.assertFalse(matches("docs/**", "app/docs/x"))


if __name__ == "__main__":
    unittest.main()
