## 2026-10-28 - GitHub review context cleanup

Contract: JEG-1211 — remove stale review noise while preserving current decisions,
holds, independent review evidence and deployment constraints.

### Verified (check named)
- GitHub PR inventory: 25 open PRs; no inline review threads returned.
- Rewrote 25 PR bodies to current briefs; closed superseded #966/#967.
- preview.yml already updates one marker comment; no workflow change needed.
- git diff --check passes; tests.test_doc_staleness passes (4 tests).
- Historical lane detail retained at pre-cleanup commit 032cee0 and git history.
- Detailed #1044 before/after measurements copied verbatim to linked evidence.

### Claimed, not confirmed
- This documentation change has not shipped to main.
- Existing PR CI, live source freshness and edge deployments were not rerun
  by this grooming; inherited results retain their source/date.
