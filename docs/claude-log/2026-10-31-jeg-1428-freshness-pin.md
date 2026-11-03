## 2026-10-31 - JEG-1428 freshness pin

Contract: Re-pin the weekly-input freshness test to the live shared rule without changing either rule's behavior. Document freshness_for_weeks as authoritative for weekly-input artifacts.

### Verified (check named)
- On origin/main f58091a3, `python3 -m unittest tests.test_weekly_inputs_contract.RulesPinnedToRepoTest.test_freshness_rule_matches_check_reference_freshness`: Ran 1 test; FAILED (failures=1), obsolete literal assertion.
- After: same command, Ran 1 test; OK. `python3 -m unittest tests.test_weekly_inputs_contract`: Ran 36 tests; OK.
- Behavioral pin compares all 18 artifact weeks against all 18 served weeks plus unknown before the cutoff; separate test pins the intentional Thursday cutoff difference.
- In-memory mutation check with unittest.mock.patch: forcing either freshness_for_weeks or source_week_status to current makes the pin fail (both detected).
- `make validate`: FAILED during sync because Playwright chromium_headless_shell-1208 executable is missing. No retry. Generated tracked app/dist changes restored; untracked build artifacts remain locally and are excluded from commits.
- `git ls-remote origin refs/heads/main`: f58091a3909c3a53f1e9eae7fb413355efc1dead, matching worktree base. Initial fetch reported a concurrent origin/main ref update; no retry needed.

### Claimed, not confirmed
- Full validate and browser-dependent checks remain unconfirmed until the missing runtime is supplied. Independent review and CI remain for the lead; no merge or deploy performed.
