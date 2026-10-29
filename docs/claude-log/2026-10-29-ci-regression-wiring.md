# Shared regression CI wiring, 2026-10-29

Owner: `be/ci-regression-wiring` from main 6be60d2e. Owned paths: Makefile,
`tests/test_render_sweep_shards.py`, `tests/test_render_sweep_coverage.py`,
HANDOFF and picks log. JEG-1264 comment c5acead4 says its #1110 owner changed
no Makefile/workflow hunk and owns only harness, fixture and test files. No
production workflow dispatch, schedule, Supabase, merge or deployment.

Current main already had four unwired render files: interactive trades release,
JEG-1263 simplified site, Compare rosters, and finder guardrails. The coverage
guard failed on all four. This branch lists each once in `test-render-extra`
and one of the three existing informational shards; the existing render sweep
workflow runs all three and remains outside required release CI. No expected
red is hidden and no green result is claimed. The parity parser now accepts
class-qualified unittest targets so one module's green and red classes can
be placed in different targets.

Minimal next wiring, only once each owning PR's files are present on the same
integration head:

1. #1110 / JEG-1264: add only verified green harness and mutation classes to
   `test-unit-modules`; continuity class and browser journey go to
   `test-render-extra` plus one shard. Keep actual context loss red and visible.
   Wait for its proposed split file and corrected baseline/mutation evidence.
   USO route/context must pass in a required release gate before claiming
   required-release success. Never add `KNOWN_RED` or skips.
2. #1114: once its resolver fixture and test land, add
   `tests.test_jeg1202_platform_spellings` to `test-unit-modules` after checking
   its claimed green baseline.
3. #1115: wire `Jeg1061LoggingContractTests.test_checker_catches_missing_and_misclassified_events`
   to unit. Put the recorded-before-hook handler check in informational sweep
   until the logging hook lands; its expected violations are not a functional
   pass.
4. #1080: keep the strict shared-link regressions visibly red in an
   informational job after its files land; its non-strict recorded state is
   audit evidence, not a fixed feature. Do not put it in a required gate yet.
5. #1109 history and #1111 edge drift: informational nightly only. #1109's
   existing `test-unit-modules` entry and #1111's proposed entry must be
   reconciled by this owner when those PRs land, without a second author on
   Makefile. Do not enable #1111's production cron workflow.

Local checks: `python3 -m unittest tests.test_render_sweep_shards
 tests.test_render_sweep_coverage` passes 12 tests. Full render baseline
for the four files is unverified; nightly will report failures honestly.
