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
The PR `batch-ownership` check validates exclusive reservations and registry
transitions using main's code. It reports a reserved member as owned, without
making that member's application CI unusable on synchronize; the ordinary merge
preflight still rejects it. The merge runbook requires the same preflight
immediately before each merge; it freezes individual merges during an active
batch, rejects stale main/member/integration heads and missing CI/review evidence,
and blocks progression without publication/live acceptance. These commands do
not merge, deploy, schedule, cancel or retry anything.

No GitHub ruleset/settings change is included. A PR check is not automatically a
required branch-protection check; an operator bypassing the runbook or an outside
API merge is not prevented by repository code. Existing external merge agents
must invoke this preflight before their merge call. The installation PR uses the
previous merge gates until main contains this registry/tool; its ownership job
explicitly reports that one bootstrap condition. In particular, do not claim
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
   Unexpected heads/conflicts require the recovery path below, not retries or
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

## Recover stale or failed members without deleting work

An ordinary member synchronize retains usable application CI. Reservation status
is a separate ownership fact, not an application failure. The existing build,
render, artifact and independent-review requirements are unchanged; stale pins
still fail full batch preflight.

For a corrected member, push its fix on its existing branch, obtain green
exact-head CI and its independent current-head review, then propose a registry-only
PR changing **only member head pins**. Batch id, owner, integration PR, member PRs,
risk and source owners must remain identical. Preflight verifies every corrected
current head's CI, artifacts and review before allowing that control transition.
Bring the new main and corrected members into the integration branch normally,
update its manifest, then obtain fresh combined CI and delta review. An old
combined head fails after the main registry correction; no old approval survives.

If the batch cannot proceed, propose a registry-only PR changing the active entry
to `withdrawn` with `"recovery":{"reason":"<why work is being deferred>"}`.
All ownership/membership/history remains. Preflight verifies the integration PR
is **not merged**. It never cancels runs, closes/deletes PRs or branches, deletes
artifacts, merges a failed member or fabricates publication/live acceptance.
Its member work can then enter a new reservation or the ordinary gated path.
A merged batch cannot withdraw: publication and exact-live acceptance remain
mandatory, even when a member is now stale or red. The latest actual accepted
release is still reverified before a following batch; withdrawn work is not a
release and does not replace that receipt.

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

The only additional control exemption is `.github/release-batches.json`.
For that file, the classifier walks every main first-parent commit since actual
publication and validates each registry transition with the same preflight
logic. Every transition commit must change only that one control file; mixed,
malformed, unverified, initial-install and missing-history cases use full gates.
An acceptance followed by the next reservation is validated as two transitions,
so the control commits themselves do not add two application publications per
batch. The combined application is published once. Existing pause-switch on/off,
manual/daily, health arrival and real data changes still use their full path and
can add deployments; this change does not claim exactly one total Pages run or
publication per window. It removes the two new registry-control publications and
coalesces N member application releases into one combined application release. Status-only
commits between transitions remain checked; no broad workflow exemption exists.
The Pages token adds only read access for Actions and PR acceptance evidence;
there is no GitHub settings or security configuration activation in this task.

A verified status/control-only run uploads a classification receipt and summary, with
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
