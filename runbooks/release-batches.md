# Enforced release preflight (JEG-1484)

Jeremy, November 3: “Just implement all your recommendations. Keep moving.”
“If you need to do it in batches, you need to set up structure that enforces that.”
Where older instructions offer a separate serial member merge, use this batch
path. Monitoring and no-merge refresh jobs report state; the authorized release
owner owns registration, integration, merge and acceptance. Existing independent
review, approval, provider and value-math gates still apply.

## What actually enforces what

`pipelines/release_batch.py` is a read-only executable preflight. The registry
`.github/release-batches.json` on fetched main owns each member exclusively.
The PR `batch-ownership` check rejects reserved member PRs and validates registry
transitions using main's code. The merge runbook requires the same preflight
immediately before each merge; it freezes individual merges during an active
batch, rejects stale main/member/integration heads and missing CI/review evidence,
and blocks progression without publication/live acceptance. These commands do
not merge, deploy, schedule, cancel or retry anything.

No GitHub ruleset/settings change is included. A PR check is not automatically a
required branch-protection check; an operator bypassing the runbook or an outside
API merge is not prevented by repository code. Existing external merge agents
must invoke this preflight before their merge call. In particular, do not claim
that an unchanged saved monitoring/merge automation has been rewired by this PR.
Do not run an ordinary merge loop alongside a batch: that abandoned train #1196.

## Reserve, assemble and verify one release

1. Reconcile owners and changed files. Use 1..7 compatible PRs of one risk.
   High-risk/value-math work ships alone; value changes still need Jeremy's
   named approval with before/after values. Keep independent product coding
   moving on unrelated branches. No source PR is merged separately.
2. Create the integration draft PR, then propose a **registry-only PR** adding
   one `active` entry. Keep all older entries. Example shape, with real values:

   ```json
   {"id":"release-20261104-am","state":"active","owner":"release-session-id",
    "integration_pr":1305,"members":[
      {"pr":1304,"head":"<40-character-member-SHA>","risk":"review-standard","owner":"member-session-id"}
    ]}
   ```

   Members must already have current-head CI and review evidence. Registry
   transition review and CI remain required. Before the authorized registry
   merge run `python3 pipelines/release_batch.py --pr <registry-PR> --main <current-main-SHA>`.
   No next reservation may replace, abandon or silently rewrite the active one.
   Unexpected heads/conflicts require release-owner resolution, not retries or
   merging members independently. Main must contain the reservation before
   claiming exclusive ownership is active.
3. Use the existing [main-write switch](main-write-pause.md) for the approved
   release window; `pipelines/main_write_switch.py` supports the short scoped
   pause. Drain older-code writers and verify summaries. This PR leaves the
   switch off. A pause limits automated writes; it does not lock human merges.
4. From exact current main, merge the pinned member commits normally onto the
   integration branch. Never rebase or force-push. Add
   `.github/release-batch.json` **on the integration branch**:

   ```json
   {"batch_id":"release-20261104-am","main_sha":"<40-character-current-main-SHA>",
    "members":[{"pr":1304,"head":"<40-character-member-SHA>","risk":"review-standard","owner":"member-session-id"}]}
   ```

   Copy membership exactly from the main registry. The manifest pins main and
   source heads; the preflight's mandatory `--head` pins the resulting combined
   commit without a self-referential SHA in that commit. All members and main
   must be ancestors of the combined head. Bring a changed main in normally,
   update the manifest and get new exact-head CI/delta review.
5. Get the combined PR's actual full preview and v2-render workflows green.
   Preflight requires the build, all five core shards, all three render lanes,
   aggregate checks and the nonexpired `preview-dist-<combined-head>` artifact.
   It also rejects other failed/pending check runs. A draft deferral, skipped
   gate, manual substitute, old-head review or expired artifact does not count.
6. Independent reviewers attach a GitHub review on each exact source head and
   the exact combined head, with this machine-readable receipt in its body:

   ```text
   <!-- release-review {"head":"<40-character-SHA>","result":"pass","reviewer_session":"independent-session-id","provider":"claude","model":"opus","capability":"high-risk"} -->
   ```

   Use the actual provider/model and capability selected under AGENTS. The
   combined reviewer must differ from the integration and every source owner.
   This attestation supports sessions sharing a GitHub login; the receipt is
   evidence of declared session independence, not proof of a separate human
   identity. A later changes-requested review blocks preflight. Existing exact
   head review receipts can be annotated with this marker without repeating
   the review; an author cannot issue their own independent receipt.
7. After named release approval and all existing gates, run:

   ```bash
   python3 pipelines/release_batch.py --batch release-20261104-am --main <main-SHA> --head <combined-SHA>
   ```

   Save its output. Merge only the integration PR on that head immediately
   afterward, using the merge API's expected-head guard and current-main check.
   If either head changes, stop and regenerate evidence. The preflight does
   not provide an atomic compare-and-merge transaction. Publish once through
   the existing full Pages workflow. Do not add a second publication route.

## Accept before the next batch

Wait for successful Pages publication of the integration merge SHA and a later
successful existing `live-page-synthetic.yml` run. Its `live-page-synthetic-results`
artifact must explicitly pass, have no problems/page errors, include successful
page probes and name that exact live build tag. A previous-build acceptance is
insufficient. No workflow dispatch/deployment is performed by preflight.

Propose a registry-only PR changing that same entry to `accepted`, preserving
its membership and owner, with:

```json
"acceptance":{"published_sha":"<integration-merge-SHA>","publication_run":123,"live_run":124}
```

Preflight verifies those actual GitHub runs, every Pages gate, the merged PR,
and the downloaded live artifact. Run `--pr <receipt-PR> --main <current-main-SHA>`
before its authorized merge. The latest acceptance is reverified before the
next reservation and batch. An unavailable/expired live artifact blocks; obtain
fresh acceptance on the exact publication or preserve approved durable evidence
through a separately reviewed extension, never silently remove the gate.
Restore the existing pause and verify normal publication resumes.

## Status-only Pages runs

Every main push still creates a visible workflow. The classifier reads the full
Git range from the last successful **actual Pages deployment** to the event SHA,
not `HEAD~1` or just `event.before`. It checks both ancestor ranges and exact
JSON status filenames. A missing anchor/history/API response, force push,
malformed or deleted record, empty range, application/data/workflow or unknown
file takes the complete build, five shards, browser gate and publication path.
Manual/daily dispatch always takes that full path. The served health pair
`source-import-health.json` / `pipeline-checkpoints.json` also keeps the full
path: `health_artifacts_watch.py --await-published` requires their actual live
arrival. Exempting those files would break that existing fail-closed contract.

A verified status-only run uploads a classification receipt and summary, with
no build, shard, browser install or Pages artifact/publication. The deploy
monitor records no new `site_deploy` success for this no-publication result.
Producer workflow artifacts, committed main records, monitor observations and
alerts continue. **Live status JSON retains the previous published data** until
the next actual full publication (including the existing daily manual dispatch).
This deliberately trades live dashboard freshness for fewer rebuilds; the run
summary exposes that limit. Do not present the dashboard as freshly published
because a status-only workflow succeeded. Fresh holds that need rebaking remain
owned by the producer's existing chain dispatch; this classifier never suppresses
that workflow. A status-only classification cannot become a publication anchor.
