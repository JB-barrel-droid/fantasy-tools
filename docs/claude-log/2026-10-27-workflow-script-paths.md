## 2026-10-27 - JEG-1160 workflow script paths guard

Contract: add a read-only CI guard that fails when a `.github/workflows/*.yml`
`run:` step invokes a repo-relative script (or `python -m pkg.mod` target) that
does not exist in the repo.

Authored by an OpenRouter `deepseek/deepseek-v4.1-flash` run (headless,
untrusted until a Claude review).

### Verified (check named)
- `python -m unittest tests.test_workflow_script_paths` passes (5 tests),
  parsing 33 workflows and 75 distinct repo-relative paths; no missing paths,
  so ALLOWLIST is empty.
- Mutation check: renaming `pipelines/nfl_week.py` to
  `pipelines/nfl_week_MISSING.py` in `fantasycalc-weekly-save.yml` makes
  `test_every_referenced_path_exists` fail naming that path and workflow;
  `git checkout --` reverts and the suite passes again.
- `ExtractorTest` pins the ignore rules (pip install, inline `-c`, heredocs,
  `${{ }}` paths, absolute paths, quoted grep/sed patterns) and the module
  mapping (`python -m unittest tests.x` -> `tests/test_x.py`).
- PyYAML is not importable on this runner, so the text parser is the path CI
  exercises; `_run_bodies` still prefers PyYAML when present.

### Claimed, not confirmed
- Behaviour under CI's Python (3.12) and under an environment where PyYAML is
  importable is asserted but was not run here.
- No missing paths were found on this worktree's `main`; a path genuinely
  missing on a future `main` still needs a manual ALLOWLIST entry.
