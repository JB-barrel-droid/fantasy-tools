## 2026-11-06 - GitHub Actions and branch cleanup sweep (no ticket; repo hygiene)

Contract: at Jeremy's request ("Clean up my GitHub processes"), inventory
workflows, runs, branches and PRs, then carry out his choice "A. Hygiene sweep":
delete merged branches, disable orphaned workflows via a PSpice print, and
ticket the always-red workflows. No code, workflow or config file changed.

### Verified (check named)
- 154 non-main branches: 25 have a merged PR, 47 a closed-unmerged PR, 31 no PR
  and 51 an open PR (`git ls-remote --heads` joined to every PR head ref via
  `gh api repos/.../pulls?state=all`, paged explicitly).
- 20 of the 25 merged branches still sit at their merged PR's head SHA
  (`gh api pulls/<n> .head.sha` == `branches/<b> .commit.sha`). The other 5
  (banana/fix-main-bench-share, be/JEG-975, be/jeg-820, be/jeg-833,
  claude/divergence-evidence-audit) moved after merge and are kept.
- 11 registered workflows have no file on main. 5 are on open-PR branches
  (fast-gate #1260, pr-freshness #1262, release-batch #1303,
  versus-vegas-preview-tests #1294, jeg1209-preview #1096) and must stay
  enabled. 6 are orphaned (`gh api contents/.github/workflows/<f>?ref=<open
  ref>` for every open PR ref).
- Always red: `health-artifacts.yml` (every run since 2026-10-30; push to main
  fails 3x, then the served-artifact watch exits 2), `render-sweep.yml` (every
  run since 2026-10-29; 4 tests in 3 modules), `full-suite.yml` (7 of 8 nightly
  runs cancelled at the 120-minute timeout), `chain-run-feedback.yml` (its only
  run failed, printing `gh api` usage). Checked with job logs via `gh api
  actions/jobs/<id>/logs`.
- Run 37642358642 (Record site deploy, queued since 2026-10-07) cannot be
  cancelled: `cancel` and `force-cancel` both return HTTP 409 "not been queued
  yet". Only deleting the run record removes it, and that needs Jeremy's yes.
- Filed JEG-1546 (render sweep) and JEG-1547 (nightly suite timeout) in Backlog.
  Commented evidence on JEG-1522 (chain-run-feedback) and JEG-1523 (health
  artifacts), with marker `claude-gh-cleanup-2026-11-06`.

### Claimed, not confirmed
- The branch deletes and workflow disables are not done. This cloud session
  can push only to its own branch, and the API write path returns 403 through
  the proxy. A paste-ready PSpice print with SHA-pinned branch checks was
  handed to Jeremy.
- The health-artifacts push failures likely share a cause with JEG-1519 (bot
  rate limit) and should clear with the JEG-1523 cutover. Not reproduced.
