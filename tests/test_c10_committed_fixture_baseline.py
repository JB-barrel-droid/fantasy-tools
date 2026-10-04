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
        bpc._FIXTURE_REF_FETCHED_AT.pop(str(self.repo), None)
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

    def test_stale_ref_false_reds_pre_fix(self):
        """Discrimination for the 2026-10-03 ~21:07 CDT defect: the health
        runner's origin/main ref still pointed at 54eb76a's fixture while main
        had already moved to the chain's 1ccf84e0 rebuild. Reading
        origin/main WITHOUT a fetch baselines against the superseded fixture
        (pre-fix semantics) while the fixed helper fetches first and returns
        the fresh blob."""
        remote = self.tmp / "remote.git"
        _git(self.tmp, "init", "--bare", "-q", "remote.git")
        _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
        seed = self.tmp / "seed"
        _git(self.tmp, "clone", "-q", str(remote), "seed")
        (seed / REL).parent.mkdir(parents=True, exist_ok=True)
        (seed / REL).write_bytes(COMMITTED)
        _git(seed, "add", REL)
        _git(seed, "commit", "-qm", "v1")
        _git(seed, "push", "-q", "-u", "origin", "main")
        consumer = self.tmp / "consumer"
        _git(self.tmp, "clone", "-q", str(remote), "consumer")
        # Remote advances; the consumer has not fetched since v1.
        (seed / REL).write_bytes(DIRTY)
        _git(seed, "add", REL)
        _git(seed, "commit", "-qm", "v2")
        _git(seed, "push", "-q", "origin", "main")

        # Pre-fix semantics (verbatim): read origin/main with no fetch.
        stale = _git(consumer, "show", "origin/main:" + REL)
        stale_sha = hashlib.sha256(stale.stdout).hexdigest()[:12]
        self.assertEqual(stale_sha, hashlib.sha256(COMMITTED).hexdigest()[:12])
        self.assertNotEqual(stale_sha, hashlib.sha256(DIRTY).hexdigest()[:12])

        # Fixed helper fetches first and returns the fresh blob.
        bpc.REPO = consumer
        bpc._FIXTURE_REF_FETCHED_AT.pop(str(consumer), None)
        got = bpc.committed_fixture_sha(consumer / REL)
        self.assertEqual(got, hashlib.sha256(DIRTY).hexdigest()[:12])

    def test_mid_run_rebuild_is_picked_up(self):
        """2026-10-03 ~23:07 CDT defect: the health runner fetched origin/main
        at process start, the comparison chain committed a new fixture
        mid-run (752aa00), and C10 compared the served bytes against the
        superseded blob -- seven "Production output WRONG" false reds on
        healthy production. The refresh is time-based, so a baseline call
        after the refresh window re-fetches and sees the rebuilt fixture.

        Discrimination: with the fetch-once-per-process guard the second
        call returns the stale blob, so this test fails there.
        """
        NEWER = b'{"built_at": "2026-10-04T04:00:00", "sources": {}, "rebuilt": true}'
        remote = self.tmp / "remote.git"
        _git(self.tmp, "init", "--bare", "-q", "remote.git")
        _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
        seed = self.tmp / "seed"
        _git(self.tmp, "clone", "-q", str(remote), "seed")
        (seed / REL).parent.mkdir(parents=True, exist_ok=True)
        (seed / REL).write_bytes(COMMITTED)
        _git(seed, "add", REL)
        _git(seed, "commit", "-qm", "v1")
        _git(seed, "push", "-q", "-u", "origin", "main")
        consumer = self.tmp / "consumer"
        _git(self.tmp, "clone", "-q", str(remote), "consumer")
        bpc.REPO = consumer

        first = bpc.committed_fixture_sha(consumer / REL)
        self.assertEqual(first, hashlib.sha256(COMMITTED).hexdigest()[:12])

        # The chain rebuilds and pushes a new fixture AFTER our fetch.
        (seed / REL).write_bytes(NEWER)
        _git(seed, "add", REL)
        _git(seed, "commit", "-qm", "v2")
        _git(seed, "push", "-q", "origin", "main")

        # Sanity: the consumer's origin/main ref is now stale.
        stale = _git(consumer, "show", "origin/main:" + REL)
        self.assertEqual(
            hashlib.sha256(stale.stdout).hexdigest()[:12], first)

        # Minutes pass before C10 runs: expire the refresh window.
        bpc._FIXTURE_REF_FETCHED_AT[str(consumer)] = 0

        got = bpc.committed_fixture_sha(consumer / REL)
        self.assertEqual(got, hashlib.sha256(NEWER).hexdigest()[:12])

    def test_no_refetch_inside_window(self):
        """Inside the refresh window no refetch happens (the fetch cost is
        paid at most once per window, not per source). This pins the residual
        trade-off: a rebuild landing inside the ~90s window is still missed,
        which is why the window is short."""
        NEWER = b'{"built_at": "2026-10-04T04:00:00", "sources": {}, "rebuilt": true}'
        remote = self.tmp / "remote.git"
        _git(self.tmp, "init", "--bare", "-q", "remote.git")
        _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
        seed = self.tmp / "seed"
        _git(self.tmp, "clone", "-q", str(remote), "seed")
        (seed / REL).parent.mkdir(parents=True, exist_ok=True)
        (seed / REL).write_bytes(COMMITTED)
        _git(seed, "add", REL)
        _git(seed, "commit", "-qm", "v1")
        _git(seed, "push", "-q", "-u", "origin", "main")
        consumer = self.tmp / "consumer"
        _git(self.tmp, "clone", "-q", str(remote), "consumer")
        bpc.REPO = consumer

        first = bpc.committed_fixture_sha(consumer / REL)

        (seed / REL).write_bytes(NEWER)
        _git(seed, "add", REL)
        _git(seed, "commit", "-qm", "v2")
        _git(seed, "push", "-q", "origin", "main")

        # Window not expired: no refetch, stale blob returned by design.
        got = bpc.committed_fixture_sha(consumer / REL)
        self.assertEqual(got, first)
        self.assertNotEqual(got, hashlib.sha256(NEWER).hexdigest()[:12])

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
