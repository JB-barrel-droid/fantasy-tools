## 2026-10-27 - JEG-1170: shard validate's test-core across parallel preview jobs

Not written by Jeremy; a Ba-Nana run approved by him (JEG-1170). Stacked on PR #998 (JEG-1169).

Contract: cut the PR check `preview` from ~26 minutes to ~12-15 by running `make validate`'s
test-core as parallel matrix jobs, with nothing weaker (same lines, each once, browser required,
blocking).

### Changed

- Makefile: `validate` and `test-core` unchanged (pages.yml still runs `make validate`). New
  `validate-base` (validate minus test-core) and `test-core-shard-1`..`4`, together exactly
  test-core's recipe lines, balanced by the per-module times of preview run 40199508029
  (~7.5 minutes of tests each), test-core's order kept within each shard.
- preview.yml: `preview-build` (the old job, `make validate-base` in place of `make validate`;
  fidelity card, accuracy signals, manifest, artifact, rendered gate, PR comment unchanged),
  `preview-shard` (matrix 1-4, fail-fast false, 30 min: checkout at PR head, Python 3.12,
  Playwright cache, browser with RENDER_TESTS_REQUIRED=1, `make reference`, `make sync`,
  `make test-core-shard-N`), and `preview` (the check name), `needs` both, `if: always()`, fails
  unless both results are success. Timeouts: build 60, shard 30, aggregate 5.
- The PR comment now says "validate-base passed" (it posts before the shards finish).

### Tests

- New `tests/test_validate_shards.py` (in `test-unit-modules`): shard union == test-core (none
  missing, none twice, none shard-only), validate == validate-base + test-core, preview matrix ==
  Makefile shards; a mutation test per rule.
- `tests/test_preview_workflow_matches_pages.py`: compares pages' steps with `preview-build`
  (`make validate-base` stands for `make validate`); checks the shard job (commands, blocking,
  unconditional, fail-fast, RENDER_TESTS_REQUIRED) and the aggregate (needs, always(), result
  check, blocking). New mutation tests: shard job or aggregate removed, continue-on-error on the
  shard job / step / aggregate, full `make validate` back in preview-build, and others.
- `tests/test_ci_speedup_workflows.py`: timeouts checked per job (preview-build, preview-shard,
  preview).

### Verified (check named)

- `python3 -m unittest` tests.test_validate_shards, tests.test_preview_workflow_matches_pages,
  tests.test_ci_speedup_workflows, tests.test_deploy_gate_unconditional,
  tests.test_v2_render_runs_on_data_push, tests.test_workflow_no_event_interpolation,
  tests.test_retired_extras: OK. tests.test_render_sweep_shards: the same 4 failures as on the
  base commit (4 render modules in no render-sweep shard), not touched here.
- actionlint 1.7.12 on preview.yml: one SC2155 warning in the unchanged rendered-gate step, also
  present on the base commit; nothing in the new jobs.
- Local shard runs on the Mac (py3.12 venv, Playwright Chromium, RENDER_TESTS_REQUIRED=1), each in
  its own fresh git worktree, all four at once, `make reference sync` (13 s) then
  `make test-core-shard-N`: shard 1 (22 lines) pass in 718 s, shard 3 (24) pass in 403 s,
  shard 4 (23) pass in 343 s (tests.test_rank_guard passed), shard 2 (24) failed only at
  tests.test_v2_phone_fallback_font_render: "DejaVu Sans is not installed" (the Mac has no
  DejaVu; the Linux runner does, per the JEG-829 comment). The 9 lines after it, run one by one: OK.
  The Mac times are with four shards contending for 10 cores; shard 1 carries view_invariants.

### Claimed, not confirmed

- CI wall time of ~12-15 minutes: not measured; the shard jobs have not run on GitHub.
- The CI per-module times used for balancing come from one run; the Linux runner may differ.
- Branch protection: the required check is still named `preview`; not checked in repo settings.
