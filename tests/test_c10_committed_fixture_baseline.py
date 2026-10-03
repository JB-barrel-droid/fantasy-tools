"""Regression: C10 rendered check must baseline against the COMMITTED fixture.

On 2026-10-03 ~11:07 CDT the checkpoint builder ran from the shared checkout
whose working-tree data/fixtures/current/comparison-sources-data.json carried
another lane's uncommitted change (1f555c50260b) while the live site served
bytes byte-identical to the committed fixture on origin/main (8ab9581df440).
The old code hashed the working tree, so every source's C10 went
"Production output WRONG" — a monitor false-red on healthy production.

committed_fixture_sha() prefers the origin/main blob so a dirty checkout can
never false-red C10 again. These tests prove the new semantics AND prove they
discriminate: test_old_logic_false_reds replicates the pre-fix working-tree
read inline and asserts it returns the dirty sha where the new helper returns
the committed one — the suite would have caught the bug.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINES = Path(__file__).resolve().parent.parent / "pipelines"
sys.path.insert(0, str(PIPELINES))

import build_pipeline_checkpoints as bpc  # noqa: E402

REL = "data/fixtures/current/comparison-sources-data.json"
COMMITTED = b'{"built_at": "2026-10-03T09:37:00", "sources": {}}'
DIRTY = b'{"built_at": "2026-10-03T09:37:00", "sources": {}, "wip": true}'


def _git(repo, *args):
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(["git", "-C", str(repo)] + list(args),
                          capture_output=True, env=env, timeout=30)


class CommittedFixtureShaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="c10base-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.fixture = self.repo / REL
        self.fixture.parent.mkdir(parents=True)
        self._real_repo = bpc.REPO

    def tearDown(self):
        bpc.REPO = self._real_repo
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _init_repo_with_commit(self, content):
        _git(self.repo, "init", "-q")
        self.fixture.write_bytes(content)
        _git(self.repo, "add", REL)
        _git(self.repo, "commit", "-qm", "fixture")

    def test_prefers_committed_over_dirty_working_tree(self):
        """The 2026-10-03 defect: working tree dirty, committed == served."""
        self._init_repo_with_commit(COMMITTED)
        # Another lane's uncommitted change lands in the working tree.
        self.fixture.write_bytes(DIRTY)
        bpc.REPO = self.repo

        got = bpc.committed_fixture_sha(self.fixture)

        committed_sha = hashlib.sha256(COMMITTED).hexdigest()[:12]
        dirty_sha = hashlib.sha256(DIRTY).hexdigest()[:12]
        self.assertNotEqual(committed_sha, dirty_sha)  # scenario is real
        self.assertEqual(got, committed_sha)

    def test_old_logic_false_reds(self):
        """Discrimination: the pre-fix working-tree read returns the dirty sha."""
        self._init_repo_with_commit(COMMITTED)
        self.fixture.write_bytes(DIRTY)

        # Pre-fix code, verbatim semantics:
        old_sha = hashlib.sha256(self.fixture.read_bytes()).hexdigest()[:12]
        dirty_sha = hashlib.sha256(DIRTY).hexdigest()[:12]
        committed_sha = hashlib.sha256(COMMITTED).hexdigest()[:12]

        self.assertEqual(old_sha, dirty_sha)
        self.assertNotEqual(old_sha, committed_sha)

    def test_origin_main_preferred_over_head(self):
        """Ref priority is deliberate: in the health cron the local HEAD is a
        pinned stale branch while origin/main is freshly fetched; in CI the
        chain commits a rebuilt fixture before pushing, so origin/main is the
        not-yet-deployed (i.e. currently served) state. Both want origin/main."""
        self._init_repo_with_commit(COMMITTED)
        _git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        # New local commit moves HEAD; origin/main stays at the old blob.
        self.fixture.write_bytes(b'{"new": true}')
        _git(self.repo, "add", REL)
        _git(self.repo, "commit", "-qm", "newer")
        bpc.REPO = self.repo

        got = bpc.committed_fixture_sha(self.fixture)
        self.assertEqual(got, hashlib.sha256(COMMITTED).hexdigest()[:12])

    def test_falls_back_to_working_tree_without_git(self):
        """Non-git environment: the working tree is the only baseline."""
        self.fixture.write_bytes(DIRTY)
        bpc.REPO = self.repo  # not a git repo here

        got = bpc.committed_fixture_sha(self.fixture)
        self.assertEqual(got, hashlib.sha256(DIRTY).hexdigest()[:12])

    def test_returns_none_when_missing_everywhere(self):
        """File neither committed nor on disk: None (C10 skips the check)."""
        self._init_repo_with_commit(b"{}")
        missing = self.repo / "data" / "fixtures" / "current" / "nope.json"
        bpc.REPO = self.repo

        self.assertIsNone(bpc.committed_fixture_sha(missing))


if __name__ == "__main__":
    unittest.main()
