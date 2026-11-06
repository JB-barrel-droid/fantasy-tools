# Reviewed integration queue (JEG-1524)

Local candidate preparation tooling. This is an inactive core slice, not a live
GitHub queue or authority to merge. Last verified: 2026-11-05, local fixtures.

## Run

Use Python 3.12+ and Git 2.38+. Run from the repository root:

```
python3 scripts/integration_queue.py queue-snapshot.json --dry-run
python3 scripts/integration_queue.py queue-snapshot.json > queue-receipt.json
python3 -m unittest tests.test_integration_queue -v
```

The snapshot is trusted coordinator input, never a PR-supplied artifact. Example
(replace the illustrative SHA and URLs with independently verified evidence):

```json
{
  "base_ref": "refs/remotes/origin/main",
  "required_checks": ["preview"],
  "prs": [{
    "number": 123,
    "head": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "title": "Example feature (JEG-123)",
    "url": "https://github.com/OWNER/REPO/pull/123",
    "owner": "lane owner",
    "author_session": "writer-job-id",
    "review": {
      "head": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "result": "pass",
      "session": "different-review-job-id",
      "url": "https://github.com/OWNER/REPO/pull/123#pullrequestreview-ID"
    },
    "checks": {
      "preview": {
        "head": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "result": "success"
      }
    }
  }]
}
```

Order is the input array order. The coordinator supplies that durable FIFO order;
any urgent priority decision must be made before producing the snapshot. Set
`held: true` or `closed: true` to remove an item. Ineligible items are reported and
skipped. No tier field changes admission. Missing, failed, pending or stale checks
hold the item; a review must pass on the same head in a different session.

A non-dry run creates one squash commit with current base as its sole parent,
original tip author, other authors as coauthor trailers, PR URL, reviewed SHA and
review URL. It updates only `refs/heads/queue/pr-N`, using a compare-and-swap.
It validates that exact commit in a temporary clone inside this checkout with
`make validate`. Lane branches and trunk stay untouched. A per-checkout flock
rejects overlapping CLI runs; keep `.integration-queue.lock` local and untracked.
No background job or automatic retry exists. Dry-run only checks admission and
reports the first eligible candidate; it writes no objects/refs and does not
predict mergeability or claim validation.

Each attempt recomputes against the resolved base and runs validation anew.
Base movement during validation yields `invalidated`, exit 1. A subsequent run
requires a refreshed snapshot/base ref; lane rebases are unnecessary. A textual
merge conflict emits `returned_to_owner` with owner and Git conflict detail, then
allows the next eligible candidate to proceed. A validation failure stops that
run (exit 1); the coordinator must inspect it and return semantic failures to the
owner. Git cannot infer semantic conflicts. Receipts are stdout; preserve them in
the coordinator's durable store. Any validation receipt becomes stale after a
head/base/evidence change; it is never authorization to land.

## Remaining production integration

A trusted GitHub adapter must fetch current trunk and PR heads; independently
verify COMMENT-review receipts, risk/model capability and session independence;
reject unresolved change requests; query all configured required checks on the
exact head from trusted check producers; and obtain all existing specific merge
and deployment approvals. The input JSON alone is not a security boundary.
Refresh that evidence immediately before landing. Implement durable enqueue,
remove/hold, receipt and owner-notification state. Do not use cached snapshots to
land. Current tooling emits conflict returns but does not post notifications.

Implement one atomic expected-base landing path with head/evidence rechecks and
remote serialization. Land the validated squash object, not a newly computed
merge. A lost compare-and-swap must invalidate validation, never force-push or
retry blindly. Serialize generated-data publishers through this same owner.
Confirm and retire duplicate merge routes before activation. Add deployment
verification of the exact landed revision/build stamp and a durable failure hold
that blocks later landings until recovery. Neither remote landing, publisher
routing nor deploy verification is implemented by this local preparer.

## Human settings step — Jeremy only

Jeremy must inspect actual live owners/check context names and configure GitHub
rules/settings himself. Agents must not change these settings. Required target:

- Protect `main`: prohibit force pushes and deletion; restrict updates to the
  single queue integration identity, including existing automated publishers.
- Require the repository's complete CI context set on PR heads, including preview
  validation/render contracts; pin trusted emitting apps. Record the exact names
  in adapter configuration; `preview` above is illustrative, not a live inventory.
- Require a trusted queue validation status on the exact candidate commit from
  the queue identity. Preserve exact-head independent COMMENT-review policy via
  a trusted admission check; GitHub approval count alone cannot enforce session
  independence or this repository's COMMENT-review receipt policy.
- Do not require every lane to be up to date with main. Validate the candidate
  against current trunk instead. Enable squash history; disable alternate merge
  routes and administrative/ad hoc bypass paths. If a narrowly scoped queue app
  exception is necessary to publish its already validated squash object, limit it
  to that identity and require the adapter's equivalent gates before any write.
- Establish one remote concurrency owner for queue and accepted data publishers;
  retain Pages completion and deployment verification before releasing the next
  landing. No schedule, setting or publisher is activated by this PR.

Existing approval windows, high-risk specific yes and deploy approval rules still
apply. This tooling does not grant a bypass at any risk tier.
