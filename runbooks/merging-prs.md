# Merging a PR: the rules used on 2026-10-22

The merge checks the lead ran on every PR merged on 2026-10-22 (PRs #795 to #821), restated as a runbook. It adds to `heavy-suites-and-hot-files.md` (hot files, one engine PR at a time) and `AGENTS.md` "Merge protocol". Owner ticket: JEG-874.

## Before merging

JEG-1466, Jeremy, 2026-10-31: "Ok, so set up best practices then" and
"Ensure they're rebased before promoting upward". Merge `origin/main` into
the branch just before review and again just before merge; no rebase or
force-push. Push the branch normally, then require
`python3 pipelines/pr_freshness_gate.py <PR>` to pass (0 = fresh/green,
1 = refused, 2 = unavailable evidence; no retries). Use
`python3 -m pipelines.pr_promotion ready-for-review <PR>` for draft promotion
and `python3 -m pipelines.pr_promotion merge-gate <PR>` at the final merge
boundary. The informational workflow is a snapshot, never this authorization.
Generic skipped checks, pending checks and missing evidence fail closed;
`skipped` needs an explicit `skipped-by-path` receipt in the check output.
The #1255 registry is read only from main when present; it attributes known
test failures and never waives a red status. Draft-deferred red CI still
refuses promotion; resolve that evidence rather than bypassing the gate.

Skip re-review only if the merge leaves the PR's own diff unchanged: compare
`git diff <old-main> <reviewed-head> -- . <merge-only-exclusions> | git patch-id --stable`
with the corresponding new-main/new-head diff, excluding only explicitly
identified merge-only files. Record both heads, patch-ids and exclusions on
Linear before carrying the receipt forward; any code/rule/test delta needs
review. PRs stop editing `HANDOFF.md`; handoff notes go on the Linear ticket.

1. **The bot report matches the head.** The `preview.yml` run posts one "Preview build for `<sha>` (validate passed)" comment on the PR with the build tag, the dist manifest root, the artifact link and the rendered gate result. The `<sha>` must be the PR's current head (`gh pr view <n> --json headRefOid`). A report for an older head proves nothing about the commit you merge.
2. **`v2-render` is green** on the head (`gh pr checks <n>`; about 4 to 5 minutes).
3. **The PR is mergeable** (`gh pr view <n> --json mergeable`): no conflicts with `main`. If `UNKNOWN`, wait a minute and ask again.
4. **Read the preview run's `make validate` step result**, not only the check mark. The preview job runs `make validate` with `RENDER_TESTS_REQUIRED=1`; the bot comment says "validate passed" only when it did. When the job fails, open the run (`gh run view <run id> --log-failed | grep -n -E "FAIL|Error" | head`) and name the failing test on the ticket.
5. **Diff scope check for generated churn.** `gh pr view <n> --json files --jq '.files[].path'` must list only the files the PR claims. Regenerated `dist/`, `data/fixtures/current/`, `app/trade-value-chart/assets/*.json` or `players.json` in a front-end or docs PR mean `git add -A` ran after `make sync` or a render test; ask for them to be dropped unless the PR is a data refresh. (#806 carried `dist/assets/comparison-sources-data.json` and `dist/modules/comparison-sources-data.json` this way.)
6. **Stacked PRs merge in order.** A PR that "contains" another's commits (#795 stacked on #791) merges after its base, and its preview must have run on a head that includes the merged base. After the base merges, re-check that the stacked PR is still mergeable and its report still matches its head.
7. **Nav tab-count rule.** A PR that adds or removes a top-level tab must update every test that pins the tab list (`tests/test_v2_nav_render.py`, `test_v2_contract_render.py`, `test_v2_states_render.py`, the phone nav-width guards, `tests/rendered_gate/live.mjs` `V2_TABS` and `test_live_page_synthetic.py`) in the same PR, and the phone nav must still fit one row at 390 px (GL-13). Two tab PRs in flight at once (#808 Values auditing, #810 Writing) each had to merge `main` and re-run the nav tests before merging; #810 reverted #808's eight-tab compression once there were six tabs.

## Merge

- The Oct 29 standing OK ("merge anything you recommend once it is green")
  is limited by JEG-1444 decision 13: Jeremy, 2026-10-31, "One set of
  approvals at 6 am, one at 4 pm." Merge only in his 6 AM or 4 PM Central
  window, on his yes. Nothing sits on an auto-merge path. The gate passing
  does not authorize a merge or deploy.
- Squash-merge. Final PR of a ticket: title is the bare id ("JEG-850 ..."); earlier PRs say "(part of JEG-850)".
- Comment on the ticket: PR number, head sha, "bot report matched head", "v2-render green", what the lead checked and what is not yet verified (live site after deploy).
- Published output changed: wait for Deploy dashboard, then `runbooks/verify-live.md`.

## When the preview log is unreadable until the run ends

The preview job takes 54 to 67 minutes (completed runs on 2026-10-22: #815 54 min, #817 65 min, #809 67 min), and GitHub does not serve the step log while the job runs, so a `make validate` failure is invisible until the end. While waiting:

- Run the targeted suites for the diff locally with `RENDER_TESTS_REQUIRED=1` (one machine at a time: `heavy-suites-and-hot-files.md`), and the test modules the PR touched.
- Do not merge on `v2-render` alone: it runs only the v2 render modules, not `make validate`.
- If the run fails, the first useful line is usually the `FAIL:` or `ERROR:` line of the validate step: `gh run view <run id> --log-failed | grep -n -E "^.*(FAIL|ERROR):" | head`.
- A cancelled preview (a newer push on the same branch cancels the older run) is not a failure; wait for the run on the new head.
