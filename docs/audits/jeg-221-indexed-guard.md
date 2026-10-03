# JEG-221 Indexed selection guard regression

Base maina377b53; branchcodex/indexed-default-guard.

Reproduction: `python3 -m unittest tests.test_lock_revert_notice_render`
failed on scoring/team changes with defaultGroupedSources after JEG-210.
Indexed allows published trade-chart curves; the guard required legacy
ESPN/adjusted defaults. Two further selection errors mattered: init did not
bind view tabs before guarding, and12->8 treated selected but unavailable
USA Today as a viable publisher, blocking the FantasyCalc fallback.

The runtime now requires at least one available publisher, allows intentional
hiding of every available publisher, and fails unexplained empty selection or
missing publisher coverage. It initializes view tabs before guarding, selects
an available unhidden publisher on configuration change, and preserves user
hiding. Pending VORP/Adj tabs still rebuild the Indexed data behind the
placeholder; they cannot require unimplemented adjusted outputs. The legacy
default helper and its behavioral checks remain. No values or formulas changed.

Validation:

- `python3 -m unittest tests.test_curve_default_guard tests.test_lock_revert_notice_render tests.test_adjusted_curve_pause`:32 tests,exit0 on final patch. Rendered test now clicks pending VORP on initial load, changes scoring there, returns to Indexed and repeats the lock-reset flow.
- `node --check app/trade-value-chart/assets/curve-widget.js`, sync Python syntax and `git diff --check`:exit0.
- Playwright Chrome: initial PPR12 Indexed selects USA Today; Standard8 selects FantasyCalc; guardtrue; tab aria-selected states correct; no settings exception. Existing natural scale-disagreement ChartHealth errors remain visible and nonblocking.
- `make validate`: Indexed initialization/guard harness and lock-revert now pass. Later fails the current public-copy test on internal view ID literal"vorp" in VIEW_MODE_ORDER. This is a separate recorded false positive, not concealed as green.
- Removed main's sync-comment NUL byte because Python could not load the sync module; identical minimal repair already proposed in PR42. Generated source copies were produced with sync, not hand-edited.

Initial review examined an intermediate patch and incorrectly excused the
rendered repro failure. Codex rejected that recommendation and fixed the actual
workflow. Final independent review is recorded with the PR/Linear handoff.
Roman owns integration and production verification before Done.

Final independent Claude Code MCP rerun: all32 targeted tests passed
(7 guard,1 rendered lock-revert,24 pause checks). Codex independently ran the
same final patch with exit0. This confirms the local regression slice; it does
not approve integration or production deployment.
