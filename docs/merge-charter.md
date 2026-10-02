# Merge Charter (JEG-91)

This charter defines the pre-authorized auto-merge tiers for lane PRs. It is
the one-time approval that replaces per-PR taps for routine lane work.

Merge to `main` == Pages deploy, so this charter is also an auto-deploy
charter. The tier gates are the publish safety, not a human tap.

The machine-readable form lives in `lanes/plan.json` (`tier_definitions`,
`merge_queue`) and `lanes/merge_charter.py`. This document is the
human-readable contract; both must agree.

## Tiers

### Tier 0 — auto-merge, no human in the loop

**What may auto-merge:** tests, docs, monitor checks, process tooling under
`docs/`, `tests/`, `lanes/`, `tools/`, `ops/`, top-level `*.md`, and
`.github/workflows/*.yml`.

**What is forbidden in Tier 0:** anything under `app/`, `pipelines/`,
`modules/`, `supabase/`, `sql/`, `dist/`, `data/`, `verify_live.py`, or
`Makefile`. The path match must be unambiguous.

**Gates:**

- `make validate` green
- `verify_live.py` green
- Diff is mechanically checkable (no binary blobs, no large generated bundles)

**Reviewer:** none. **Jeremy is notified only on hold, never on merge.**

### Tier 1 — Roman merges hands-off

**What may auto-merge:** lane PRs in the Tier 1 file space (`app/`, `ops/`,
`lanes/`, `tools/`, `pipelines/`, `modules/`) that touch **no** methodology,
values, user-facing copy, publish surfaces, DDL, pricing math, or
fixed-pie/indexation logic.

**Gates:**

- Contract tests green
- Wiring verification green (`pipelines/verify_vorp_wiring.py` or equivalent)
- Evidence bundle attached (test output, `verify_live` output, rendered check)
- Different-lane review posted (Phase 2 wires this; JEG-92)

**Reviewer:** Roman. He re-reads the touched files, re-classifies the tier
on review (may upgrade to Tier 2), and merges hands-off when all gates pass.

### Tier 2 — Jeremy's tap

**Triggers (any one is enough):**

- PR touches `dist/`, `supabase/`, `sql/`, or `data/`
- PR touches methodology, values, user-facing copy, publish surfaces, DDL,
  pricing math, or the fixed-pie/indexation logic
- PR adds/removes a Tier 0 or Tier 1 forbidden path (charter amendment)

**Gates:**

- Jeremy explicitly approves the tap

**Boundary:** values, methodology, user-facing copy, destructive production
actions, outward-facing changes (except routine data refreshes through the
pipeline), and Tier 2 taps always stay with Jeremy. Routine data refreshes
(same methodology, fresh data through the pipeline to the published chart)
go hands-off.

## Merge Queue (JEG-96 scope addition)

Merges to `main` serialize. One PR at a time. Before each item merges:

1. Rebase onto the current `main` tip
2. Re-run `make validate`
3. Re-run `verify_live.py`
4. Re-classify the tier (the reviewer may upgrade)
5. Post the tier as a PR comment

Rationale: 5 of the 20 most recent Deploy dashboard runs on 2026-10-02 were
cancelled by newer pushes. WIP limits alone only reduce collision rate; a
serial queue with rebase-and-re-verify eliminates them.

Encoded in `lanes/merge_charter.py::MergeQueue`.

## Lane brief template — tier declaration

Lane briefs must declare an expected tier up front so lanes self-classify:

```text
PR: <title>
Branch: <owner:lane/jeg-NN-...>
Expected tier: 0 | 1 | 2
Files changed:
  <path>
  ...
Tiers 0/1 only: confirm no methodology, values, copy, publish, DDL, or
pricing-math surfaces touched.
Evidence bundle: <link or "attached">
```

Roman re-classifies on review and posts the actual tier as a comment.

## Failure modes (held with reason, Jeremy notified on Tier 2 only)

- Any gate fails -> the PR is held, the reason is posted as a comment.
- Tier 0 holds do not page Jeremy.
- Tier 1 holds go to Roman's queue.
- Tier 2 holds go to Jeremy's queue.

Fail-closed: nothing merges on a red gate.

## Out of scope today

- Claude lane adapter (`claude` CLI never verified working).
- ChatGPT lane adapter (codex account out of usage).
- Full API-key lane identity machinery. Lanes sign result files
  (`lanes/<lane>/<issue>-result.md`) and Roman verifies against the brief.
  Graduate to API keys only if the cheap version is ever gamed.

## Acceptance (JEG-91)

1. ~~`docs/merge-charter.md` committed with the three tiers and their exact
   gates.~~ Done in this commit.
2. Sweep cron implements tier routing; a Tier-0 pilot PR auto-merges
   end-to-end with the tier posted as a comment. (Pending: wires into the
   existing PR sweep cron definition.)
3. A Tier-2 pilot PR is held for Jeremy's tap with the reason stated.
   (Pending: sweep cron wires the reason-posting step.)
4. Jeremy approves the tier definitions (one-time decision replacing per-PR
   taps). (Pending — this document is the proposal.)