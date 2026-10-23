## 2026-10-23 - JEG-916 follow-up: red v2 render modules on main (13 of 70 red, triaged)

- Scope: every `tests/test_*v2*render*.py` (70 files) run ALONE, RENDER_TESTS_REQUIRED=1, one at a time, detached to a log
  (a broad run gets killed with exit 144). First pass on origin/main 4dcc9170 (python3.9, Playwright 1.58); 13 red plus
  `test_v2_panels_render` killed by my 400 s timeout. Reruns after fast-forwarding to f887ae75; final reruns of the edited
  files under the CI pin (py3.12, Playwright 1.49.1, the JEG-916 sweep venv).
- Verified, per module (class, cause, action):
  - audit: STALE mutation anchor. JEG-913 (#832) made the route table `viewFor(base)`; the "route removed" patch looked for
    `hashBase() === ...`. Anchor re-pointed; the guard test now passes (all 5 mutations caught).
  - research: same JEG-913 anchor (`remove_route`). Re-pointed; green, 4 mutations caught.
  - manifesto: same JEG-913 change, the landing mutation anchored on the old ternary. Re-pointed to
    `const currentView = () => viewFor(hashBase()) || "targets";`; green, 5 mutations caught.
  - nav_320: STALE after JEG-852 (#809): seven tabs, not six. Count pinned to 7; one row pinned from 360 px; at 320 px at most
    two rows (the seven-tab 320 px wrap is already allowed by test_v2_phone_nav_overflow_render, JEG-818). The guard also went
    vacuous: the "Audit" label now has two redundant sources (`data-short="Audit"` from #809 and the JEG-873 rule below
    360 px), so removing only the rule changes nothing. New guard removes both and requires the 320 px label error, and
    asserts that removing just the attribute stays green (proves the redundancy it relies on). Decision for Jeremy below.
  - source_count: STALE premise after JEG-804 (#814, Jeremy 2026-10-22 "Out of DDF Value"): DDF Value is the three projections,
    so the pinned CBS hold (a chart) never reaches the blend and "a held source in the engine pool" cannot be true. Razzball is
    held in this test's own copy (`pin_holds_in_dist(dist, extra_held=("razzball",))`, new optional arg in tests/_holds.py,
    default behaviour unchanged). Green with all its broken-build mutations caught.
  - ddf_versions: STALE after JEG-804: the blend tab has no "Trade charts" group. Now requires Projections == espn, cbsros,
    razzball and no chart group. Proof: with the expected projection set shortened the test fails.
  - held_chip: STALE after JEG-804: the blend tab has no chart rows or chips (held CBS chips are on Chart lines only). Chip
    rules now run on Chart lines; the blend tab must list Projections and contain no chart label or chip. New test feeds the
    checker a blend tab with a chart row/chip (red and amber) and requires an error; the unmodified page must be clean.
  - customize_cleanup D2 and D4: STALE after JEG-804 (held DDF input must be a projection; the blend tab has no FantasyCalc).
    Razzball held in the test's copy; D4 unticks ESPN. Their guard tests pass. D3 stays RED, see JEG-930.
  - plain_copy: the "intro count hard-coded" mutation had gone vacuous (fixture compares 4 charts when CBS is not held, and
    the mutation hard-coded 4). Now hard-codes 7. All other mutations caught. One mutation, "projections disagree back",
    stays RED: since JEG-804 DDF Value equals DDF Projections, so the "DDF Projections say ... while DDF Value calls it"
    reason branch in trade.js is unreachable and no page state can show the mutation. Not weakened; see decisions.
  - targets: STALE copy. JEG-888 (#828) made the intro "We check 3 trade charts" (pinned fixture: CBS held, three compared);
    the pin said "four publishers' trade charts". Re-pointed; green. Proof: the pre-change test with the old pin is the red run.
- Not fixed, ticketed or already ticketed:
  - circular_banner: JEG-921 (existing, Backlog): banner no longer fires after JEG-804.
  - waterfall: still red on current main under both Playwright versions (verdict ends at 782.7, fold 768; #839 measured
    763.9): new JEG-932.
  - customize_cleanup D3 and the "DDF Value: charts only" blank-after-blend-edit defect: new JEG-930 (0 of 734 rows).
- Environment only: phone_fallback_font (DejaVu Sans not installed on this Mac; RuntimeError by design under
  RENDER_TESTS_REQUIRED=1); panels (killed at 400 s and 900 s while other agents' tests were running, green in 439 s alone
  under the 1.49.1 venv, 2 passed, 22 subtests).
- Churn: tests regenerate dist/ and app/trade-value-chart/; restored before commit, only test and doc files staged.
- Not verified: the wide-fallback-font test (needs DejaVu); full `make validate`; the other (non-v2) render modules.
