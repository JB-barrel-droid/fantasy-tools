## 2026-10-22 - JEG-572: repo hygiene pass

Origin heads now: main plus 5 branches. 4 have open PRs (#578, #666, #726, #731), left alone. be/chain-amber (PR #714 merged) is the only deletable one; SHA recorded in docs/branch-delete-restore-2026-10-22.txt before deletion.

Worktrees under ~/code/wt/ (be-616, fe-477, sources-saver) are registered in ~/code/fantasy-tools/.git, which this task must not modify, so none were removed. upd-fix is an empty directory.

Verified: git merge-base --is-ancestor per branch and gh pr list --head per branch. Not verified: whether the three ~/code/wt checkouts are clean.
