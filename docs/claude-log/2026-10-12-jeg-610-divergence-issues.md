## 2026-10-12 - JEG-610 divergence sub-issues

Contract: build the part of JEG-610 item 1 that needs no credentials (report to Linear sub-issue script plus workflow); leave the secret, exclude-source-week and projection thresholds open.

### Verified (check named)
- `python -m unittest tests.test_open_divergence_issues` (5 tests): only unresolved warn/investigate sources produce issues, body carries checklist and reasons, existing key is skipped, no token means no network call.
- Negative test: letting `reviewed` count as flagged made 2 of 5 tests fail; reverted.
- `open_divergence_issues.py --dry-run` on the current built report: 0 issues (FantasyPros is reviewed).

### Claimed, not confirmed
- The Linear GraphQL calls (`issue.children`, `issueCreate`) have not run against the live API; no token was available. First real run is the check.
- Workflow `divergence-issues.yml` has not run on GitHub.

### Needs Jeremy
- Add repository secret `LINEAR_API_KEY` (Linear personal API key) in GitHub Actions secrets. Never commit it. Until then the workflow only prints what it would open.

### Left open on JEG-610
- Item 2, exclude source-week resolution: touches blend inputs and value math, must pair with the Python reference.
- Item 3, projection baseline thresholds: needs a few weeks of reports.
