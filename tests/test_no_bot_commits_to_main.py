"""Guard: no workflow other than the allowed set commits to main.

After JEG-414 follow-up, health-artifacts.yml and source-vintage-check.yml
no longer commit to main. Only the workflows below are allowed to run `git
commit` + `git push` targeting main (the rebuild chain's fixture push,
bake-players, player-trace, and sleeper-identity):

  ALLOWED_COMMITTERS = {
      "rebuild-chain.yml",
      "bake-players.yml",
      "player-trace-rebuild.yml",
      "sleeper-identity-refresh.yml",
  }

Any other workflow file that contains both `git commit` and `git push` (or
`git push -f`/`git push --force`) is a violation. This test catches
accidental reversion of the JEG-414 change or new bot-commit workflows.

Negative test: re-introducing the commit step from health-artifacts.yml
(pre-fix) causes this test to fail.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = ROOT / ".github" / "workflows"

# Only these workflows may push commits to main.
ALLOWED_COMMITTERS = {
    "rebuild-chain.yml",        # fixture data push (the chain's output)
    "bake-players.yml",         # player-data bake
    "player-trace-rebuild.yml", # player-trace data
    "sleeper-identity-refresh.yml",  # identity layer
    "espn-supabase-sync.yml",   # commits pipelines/pull_espn_projections.py
                                 # (code updates, not ops artifacts)
}

_GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b")
_GIT_PUSH_RE = re.compile(r"\bgit\s+push\b")


def _non_comment_lines(text: str) -> str:
    """Return YAML text with pure-comment lines removed (avoids false positives
    from comments like '# no git commit or git push here')."""
    lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith("#"):
            lines.append(line)
    return "\n".join(lines)


def workflows_with_commit_and_push():
    """Return {filename} for every workflow that has both git commit and git push
    (ignoring comment-only lines)."""
    violators = set()
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        text = _non_comment_lines(path.read_text(encoding="utf-8"))
        if _GIT_COMMIT_RE.search(text) and _GIT_PUSH_RE.search(text):
            violators.add(path.name)
    return violators


class NoBotCommitsToMainTest(unittest.TestCase):
    def test_only_allowed_workflows_commit_and_push(self):
        """No workflow outside ALLOWED_COMMITTERS may git-commit + git-push."""
        violators = workflows_with_commit_and_push() - ALLOWED_COMMITTERS
        self.assertEqual(
            set(), violators,
            f"Workflow(s) outside the allowed set have git commit + push (will bot-commit to main): "
            f"{sorted(violators)}. "
            f"Move state to Supabase (public.ops_artifacts) or to a dedicated branch instead."
        )

    def test_allowed_workflows_still_commit_and_push(self):
        """Sanity: at least one allowed workflow still commits and pushes (guard is live)."""
        actual_committers = workflows_with_commit_and_push() & ALLOWED_COMMITTERS
        self.assertTrue(
            len(actual_committers) > 0,
            "No allowed workflow commits and pushes any more -- the guard is watching nothing. "
            "Update ALLOWED_COMMITTERS in this test if the last allowed committer was legitimately removed."
        )

    def test_health_artifacts_violation_is_caught(self):
        """Negative test: health-artifacts.yml with a git commit triggers the guard."""
        original = (WORKFLOWS_DIR / "health-artifacts.yml").read_text(encoding="utf-8")
        # Simulate the pre-fix state: add git commit + push lines.
        injected = original + (
            "\n      - name: _test_bad_commit\n"
            "        run: |\n"
            "          git commit -m 'Health artifacts (CI, JEG-414)'\n"
            "          git push origin main\n"
        )
        # Write to a temp path and re-evaluate.
        import tempfile, pathlib  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as td:
            tmp_dir = pathlib.Path(td)
            (tmp_dir / "health-artifacts.yml").write_text(injected, encoding="utf-8")
            # Copy one allowed file so the "at least one" check passes.
            for name in ALLOWED_COMMITTERS:
                src = WORKFLOWS_DIR / name
                if src.exists():
                    (tmp_dir / name).write_text(src.read_text(encoding="utf-8"))
                    break

            # Re-run the analysis on the tmp dir.
            violators = set()
            for path in sorted(pathlib.Path(td).glob("*.yml")):
                text = path.read_text(encoding="utf-8")
                if _GIT_COMMIT_RE.search(text) and _GIT_PUSH_RE.search(text):
                    violators.add(path.name)
            unapproved = violators - ALLOWED_COMMITTERS
            self.assertIn(
                "health-artifacts.yml", unapproved,
                "Pre-fix health-artifacts.yml with git commit+push was NOT caught by the guard"
            )

    def test_source_vintage_violation_is_caught(self):
        """Negative test: source-vintage-check.yml with a git commit triggers the guard."""
        original = (WORKFLOWS_DIR / "source-vintage-check.yml").read_text(encoding="utf-8")
        injected = original + (
            "\n      - name: _test_bad_commit\n"
            "        run: |\n"
            "          git commit -m 'JEG-205: record dispatched pipelines code hash'\n"
            "          git push origin main\n"
        )
        import tempfile, pathlib  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as td:
            tmp_dir = pathlib.Path(td)
            (tmp_dir / "source-vintage-check.yml").write_text(injected, encoding="utf-8")
            for name in ALLOWED_COMMITTERS:
                src = WORKFLOWS_DIR / name
                if src.exists():
                    (tmp_dir / name).write_text(src.read_text(encoding="utf-8"))
                    break
            violators = set()
            for path in sorted(pathlib.Path(td).glob("*.yml")):
                text = path.read_text(encoding="utf-8")
                if _GIT_COMMIT_RE.search(text) and _GIT_PUSH_RE.search(text):
                    violators.add(path.name)
            unapproved = violators - ALLOWED_COMMITTERS
            self.assertIn(
                "source-vintage-check.yml", unapproved,
                "Pre-fix source-vintage-check.yml with git commit+push was NOT caught by the guard"
            )


if __name__ == "__main__":
    unittest.main()
