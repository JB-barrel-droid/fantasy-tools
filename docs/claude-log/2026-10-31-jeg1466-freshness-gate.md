## 2026-10-31 - Freshness before promotion and merge / JEG-1466

Contract: REST-only, fail-closed freshness/check evidence before promotion or
merge. Add informational CI, merge-group groundwork and the short process rules.
Jeremy, 2026-10-31: "Ok, so set up best practices then" and "Ensure they're
rebased before promoting upward". Implemented as merge-main, never rebase or
force-push, as specified in this job. Disk floor for this job was explicitly
lowered to 3,670,016 KiB; the earlier blocked comment must not be reused.

### Verified (check named)

- Fake REST tests cover behind/merged-in/green/red/pending/API errors, moving
  heads/main, pagination, missing evidence, path skips, registry provenance,
  informational self-check exclusion and blocked promotion. The gate exits
  0/1/2 for pass/refusal/unavailable evidence and performs no retries.
- `python3 -m unittest tests.test_pr_freshness_gate tests.test_draft_ci_workflows
  tests.test_ci_speedup_workflows tests.test_waivers_mutation_offline_workflow
  tests.test_workflow_no_event_interpolation`: 66 tests passed before the final
  workflow lint correction. merge_group passes both ci_pr_gate phases without
  a PR lookup. Existing PR draft/head protections are preserved.
- Source inspection of #1255 (`c8ca2524`) found an attribution-only test registry:
  `docs/baseline-reds/registry.json`. It preserves failing command exit codes,
  so the gate does not turn whole red checks green. Read the registry from the
  observed main SHA only if present; #1255 was open at inspection.
- Repo-wide source search found no active existing PR promotion/merge executor.
  `pipelines/pr_promotion.py` supplies gated ready-for-review and merge-gate
  entry points; the latter never merges. Data-candidate promotion scripts and
  archived lane code are unrelated to PR promotion and were left unchanged.
- Final `actionlint` on all four changed workflows and `git diff --check`
  passed. After the lint correction, the 18 affected workflow guards passed
  (`WorkflowTest`, CI-speedup and event-interpolation guards).
- Actionlint initially found existing SC2155 in preview.yml's clock export,
  also present on origin/main. Split assignment/export without changing the
  value; this is the only preview edit beyond the merge_group trigger.
- Read JEG-1444 decision 13 and recorded the Oct 31 approval-window quote next
  to the Oct 29 standing OK. HANDOFF edits are confined to its header.

### Integration inventory outside this job's approved checkout

No files outside `/Users/botcomp/code/scratch/jeg1466/wt` were edited.
The bridge dispatch source under
`/Users/botcomp/Documents/Codex/2026-10-30/co/work/bridge/app/` has no dedicated
PR promotion or merge executor (searched current .mjs/.py/.sh sources, excluding
backups). It dispatches jobs; callers must require the gate at both boundaries.

- `/Users/botcomp/.config/banana/bin/merge-lock.sh` serializes Mac merge callers
  and prints the merge command. Add the gate to that instruction/caller's final
  boundary after merging/pushing main and green CI; holding its lock is not
  freshness evidence. One-line call (with the PR in `$2`):
  `python3 "$FANTASY_TOOLS_CHECKOUT/pipelines/pr_freshness_gate.py" "$2" || exit $?`
- Existing Mac promotion/merge prompt files below contain `gh pr ready`,
  `gh pr merge`, or the common merge preamble. Before **each** such operation,
  add this one-line call, substituting that prompt's PR number:
  `python3 "$FANTASY_TOOLS_CHECKOUT/pipelines/pr_freshness_gate.py" "$PR_NUMBER" || exit $?`
  `FANTASY_TOOLS_CHECKOUT` must name an approved, updated repo checkout with
  this gate; these files are outside the authorized worktree and remain untouched.

- `/Users/botcomp/.config/banana/prompts/check-960.md`
- `/Users/botcomp/.config/banana/prompts/fix-bench-share-r2.md`
- `/Users/botcomp/.config/banana/prompts/fix-bench-share.md`
- `/Users/botcomp/.config/banana/prompts/fix-main-r3.md`
- `/Users/botcomp/.config/banana/prompts/jeg1156-fallback-r2.md`
- `/Users/botcomp/.config/banana/prompts/jeg1156-fallback.md`
- `/Users/botcomp/.config/banana/prompts/merge-920.md`
- `/Users/botcomp/.config/banana/prompts/merge-920rs.md`
- `/Users/botcomp/.config/banana/prompts/merge-921.md`
- `/Users/botcomp/.config/banana/prompts/merge-921r2.md`
- `/Users/botcomp/.config/banana/prompts/merge-921rs.md`
- `/Users/botcomp/.config/banana/prompts/merge-925.md`
- `/Users/botcomp/.config/banana/prompts/merge-939-958-r2.md`
- `/Users/botcomp/.config/banana/prompts/merge-939-958-r3.md`
- `/Users/botcomp/.config/banana/prompts/merge-939-958.md`
- `/Users/botcomp/.config/banana/prompts/merge-957.md`
- `/Users/botcomp/.config/banana/prompts/merge-959.md`
- `/Users/botcomp/.config/banana/prompts/merge-960.md`
- `/Users/botcomp/.config/banana/prompts/merge-962.md`
- `/Users/botcomp/.config/banana/prompts/merge-963.md`
- `/Users/botcomp/.config/banana/prompts/merge-963r2.md`
- `/Users/botcomp/.config/banana/prompts/merge-963r3.md`
- `/Users/botcomp/.config/banana/prompts/merge-963r4.md`
- `/Users/botcomp/.config/banana/prompts/merge-964.md`
- `/Users/botcomp/.config/banana/prompts/merge-964r2.md`
- `/Users/botcomp/.config/banana/prompts/merge-964r3.md`
- `/Users/botcomp/.config/banana/prompts/merge-964r4.md`
- `/Users/botcomp/.config/banana/prompts/merge-965.md`
- `/Users/botcomp/.config/banana/prompts/merge-965r2.md`
- `/Users/botcomp/.config/banana/prompts/merge-967.md`
- `/Users/botcomp/.config/banana/prompts/merge-967r2.md`
- `/Users/botcomp/.config/banana/prompts/merge-968.md`
- `/Users/botcomp/.config/banana/prompts/merge-968r2.md`
- `/Users/botcomp/.config/banana/prompts/merge-968rs.md`
- `/Users/botcomp/.config/banana/prompts/merge-969.md`
- `/Users/botcomp/.config/banana/prompts/merge-969r2.md`
- `/Users/botcomp/.config/banana/prompts/merge-969rs.md`
- `/Users/botcomp/.config/banana/prompts/merge-970.md`
- `/Users/botcomp/.config/banana/prompts/merge-970r2.md`
- `/Users/botcomp/.config/banana/prompts/merge-970rs.md`
- `/Users/botcomp/.config/banana/prompts/merge-972-971.md`
- `/Users/botcomp/.config/banana/prompts/merge-973.md`
- `/Users/botcomp/.config/banana/prompts/merge-974.md`
- `/Users/botcomp/.config/banana/prompts/merge-975.md`
- `/Users/botcomp/.config/banana/prompts/merge-976.md`
- `/Users/botcomp/.config/banana/prompts/merge-977.md`
- `/Users/botcomp/.config/banana/prompts/merge-978.md`
- `/Users/botcomp/.config/banana/prompts/merge-980.md`
- `/Users/botcomp/.config/banana/prompts/merge-981.md`
- `/Users/botcomp/.config/banana/prompts/merge-982.md`
- `/Users/botcomp/.config/banana/prompts/sq.md`
- `/Users/botcomp/.config/banana/prompts/wave4-preamble.md`

### Overlaps and remaining limits

- #1245: no direct file overlap; it edits `docs/README.md` and the cutover
  runbook/logs. It shares approval-window subject matter.
- #1250: direct overlap in `AGENTS.md`, `CLAUDE.md`, `HANDOFF.md`. Keep these
  small hunks when merging main; no edits to its cutover/model ownership rules.
- #1255: direct overlap in `.github/workflows/preview.yml` (trigger and clock
  export here, attribution wiring there); no registry or Makefile edits here.
- The informational workflow deliberately exits successfully after recording
  PASS/REFUSED, excludes only its exact running Actions check, and cannot
  authorize promotion. The CLI/promotion wrapper excludes nothing. Generic
  skipped checks require an explicit `skipped-by-path` producer receipt.
- Existing draft CI intentionally leaves required checks red. Under the requested
  all-head-checks rule those drafts cannot promote until that evidence is resolved;
  this change does not weaken draft CI or silently waive its reds.
- No repo settings changed. Merge-queue groundwork is unverified on a live queue
  (unavailable for this user-owned repo). No merge, deploy or auto-merge enabled.
- External call-site activation requires the owning operator to add the reported
  one-line calls. New in-repo entry points cannot intercept ad hoc `gh pr` calls.
- `make validate` intentionally not run, per the job instruction.

### Nov 1 continuation: strict policy and promotion

Jeremy's Nov 1 8:19 PM CT answer A keeps both exception flags disabled.
Merged main `5381de25` for promotion with a merge commit. Removed the entire
HANDOFF.md diff against main; handoff state goes on JEG-1466. The historical
option letters in the bot-only note are not Jeremy's current answer letters.
Installed missing local Playwright Chromium. Focused freshness/draft tests:
46 passed. Full validation and exact-head remote CI are recorded on the ticket.
No independent review performed by the author; no merge or deploy.
