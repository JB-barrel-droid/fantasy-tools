# JEG-133 — Deploy gate (no unrelated commit can bypass, includes the rendered gate)

Branch: `jeremyburstyn/jeg-133-deploy-gate`
Commit: `d1a69b5`

## Files changed

- `.github/workflows/pages.yml` — gate made unconditional and blocking; rendered gate added as a deploy step.
- `tests/test_preview_workflow_matches_pages.py` — pinned build-steps updated; positive + negative guards for the JEG-133 defects.
- `docs/claude-log.md` — session log entry appended (newest-first, per the standing agreement).
- `docs/risk-register.md` — GAP-037 marked Fixed with the new evidence.

## Exact workflow change (`pages.yml`)

### Path-dependent logic removed
The previous deploy flow had three steps that together gated `make validate` on which paths the last commit touched:

1. `make validate` with `continue-on-error: true` — the failure did not stop the job.
2. `Check if only monitor files changed` (`id: changes`) — ran `git diff --name-only HEAD~1 HEAD | grep -qv '^dist/modules/'` and exported `product_changed=true|false`.
3. `Fail if product changed but validation failed` — `if: steps.validate.outcome != 'success' && steps.changes.outputs.product_changed == 'true'` then `exit 1`.

The net effect (verified by reading the workflow): a `dist/modules/`-only commit short-circuited the validation failure and let the deploy proceed. PH-6 / BH-1 name exactly this bypass.

All three pieces are gone in the new workflow:

- `make validate` is now a plain `      - run: make validate` with **no `continue-on-error`**. A red validate fails the step and the deploy.
- The "Check if only monitor files changed" step is deleted (no `id: changes`, no `HEAD~1` diff, no `dist/modules/` grep).
- The "Fail if product changed but validation failed" step is deleted (no `product_changed` output reference, no path-conditional `if:`).
- The `Rebuild source value lineage` step keeps `continue-on-error: true` because the drift guard `test_lineage_flag_drift_is_caught` requires the same flag in `preview.yml`.

### Rendered gate added
A new step sits between the lineage step and the deploy artifact steps:

```yaml
- name: Rendered gate (headless browser on the built dist)
  id: gate
  run: |
    npm ci --prefix tests/rendered_gate
    npx --prefix tests/rendered_gate playwright-core install --with-deps chromium
    set +e
    node tests/rendered_gate/gate.mjs dist --out rendered-gate.json
    rc=$?
    node tests/rendered_gate/bench_share_readout_harness.mjs dist
    rc2=$?
    node tests/rendered_gate/gate_flexibility.mjs dist
    rc3=$?
    set -e
    echo "page_errors=$(python3 -c "import json; print(len(json.load(open('rendered-gate.json'))['pageErrors']))")" >> "$GITHUB_OUTPUT"
    echo "pie_bad=$(python3 -c "import json; d=json.load(open('rendered-gate.json')); print(len(d['pieBad']), 'of', len(d['pie']))")" >> "$GITHUB_OUTPUT"
    if [ $rc2 -ne 0 ]; then echo "JEG-103 bench-share readout guard failed"; fi
    if [ $rc3 -ne 0 ]; then echo "JEG-135 rendered input sweep failed"; fi
    exit $rc
```

This is the same block `preview.yml` already uses (verbatim), including the duplicated `page_errors`/`pie_bad` lines after the first `exit $rc` (a pre-existing latent dead-code defect in `preview.yml`; mirrored on purpose per the JEG-133 scope rule "keep the change minimal and consistent with the repo's existing workflow style").

### How the gate blocks the deploy
- `make validate` failing → step exits non-zero → no `continue-on-error`, so the job stops before `actions/configure-pages@v5`. The deploy artifact never uploads.
- The rendered gate step's final line is `exit $rc`, where `rc` is `gate.mjs`'s exit code. `bench_share_readout_harness.mjs` (`rc2`) and `gate_flexibility.mjs` (`rc3`) are logged but do not gate. A red gate → job stops before `actions/configure-pages@v5`.

## Test change (`tests/test_preview_workflow_matches_pages.py`)

### Updated existing test
`test_production_build_steps_are_the_expected_three` — the pinned build-steps list now expects `make validate` to be **blocking** (no `continue-on-error: true`). The list is now:

```python
[("make sync", False), ("make validate", False),
 ("python3 pipelines/build_source_value_lineage.py", True)]
```

The rendered gate step is a multi-line `run: |` block, which `run_command` filters out, so `build_steps` is unchanged in shape.

### New positive tests
- `test_pages_runs_the_rendered_gate` — exactly one `tests/rendered_gate/gate.mjs` block in `pages.yml`, and it must not contain `continue-on-error`.
- `test_pages_has_no_path_conditional_validate` — the strings `dist/modules/`, `product_changed`, and `HEAD~1` must not appear in `pages.yml`. This is exactly the bypass GAP-037 names.
- `test_pages_validate_is_blocking` — `make validate` must not be flagged with `continue-on-error`.

### New negative tests (discrimination proof, per the standing constraint)
Each re-introduces one of the JEG-133 defects and asserts the new guard assertions would catch it:

- `test_reintroducing_path_conditional_validate_is_caught` — appends the old `git diff ... | grep -qv '^dist/modules/'` step; asserts that `dist/modules/`, `HEAD~1`, and `product_changed` are back in the file (i.e., `test_pages_has_no_path_conditional_validate` would fail).
- `test_reintroducing_non_blocking_rendered_gate_in_pages_is_caught` — adds `continue-on-error: true` to the gate step in `pages.yml`; asserts the gate block now contains `continue-on-error` (i.e., `test_pages_runs_the_rendered_gate` would fail).
- `test_reintroducing_non_blocking_validate_in_pages_is_caught` — adds `continue-on-error: true` to `make validate` in `pages.yml`; asserts the build-step flag flips back to True (i.e., `test_pages_validate_is_blocking` would fail).

The existing `test_real_preview_matches_production` still passes: `pages.yml` and `preview.yml` both have blocking `make validate`, both run the lineage step with `continue-on-error: true`, and the rendered gate step (multi-line, excluded by `run_command`) sits in both.

## What I could not verify

- **GitHub Actions run.** I cannot run Actions in this sandbox. The dispatcher will exercise the new gate (push a deliberately red build to a scratch branch) per the ticket's acceptance criteria, but I did not run those.
- **`python3 -m unittest tests.test_preview_workflow_matches_pages` in this sandbox.** The host capability for `bash` is `HOST_CAPABILITY_UNAVAILABLE` here; I could not execute the test module end to end. The assertions are stated, the negative tests state the property they catch, but the run must happen on a host with permission.
- **The rendered gate headlessly.** No `node`, no Playwright browsers, no display server here. The gate's *invocation* mirrors `preview.yml`; its *outcome* on the live dist is not checked by me.
- **Branch is 2 commits behind `origin/main`** (JEG-111 read-only schema inventory and the JEG-111 validator). I did not pull or rebase; the user's instructions were "commit on the branch" and "do not touch branch protection or PR preview behavior." The two behind-commits touch `sql/` and `pipelines/`, neither of which `pages.yml` references, so the gate change does not need them.
- **No push was performed** (out of scope per the ticket).

## Open follow-ups (not mine to do here)

- The duplicated `exit $rc` lines inside the rendered gate step exist in `preview.yml` too. They are unreachable (the first `exit $rc` always runs), and they predate JEG-133. Fixing them means editing `preview.yml`, which is out of scope.
- `docs/health/best-practices.md` still lists PH-6 and BH-1 as "Partly" until the dispatcher's scratch-branch deploy exercises confirm the gate fires on a real red push to `main`.
- The `cron: "30 11 * * *"` path runs `make sync`, `make validate`, and the rendered gate. If the cron image differs from the PR image in Node availability, the `npm ci` step may need attention; today they should be the same `ubuntu-latest` runner, but this is unverified.