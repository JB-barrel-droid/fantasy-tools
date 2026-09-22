# Fixture transition proposal: retiring the baked `*_adjusted` sections

**Status:** decided — Option B (pause the stale adjusted curves), staged 2026-09-22. Jeremy: "pause the stale curves as you recommended."

## Current state (observed 2026-09-22)

The fixture `data/fixtures/current/comparison-sources-data.json` carries three
baked `*_adjusted` sections that bypass the repo pipeline:

| Section | Fit bake | Week | Provenance |
|---|---|---|---|
| `fantasycalc_adjusted` | `fitwk2_2026-09-17_v3` | 2 | bias correction per position × role cell vs the Monday methodology leg |
| `usatoday_adjusted` | `fitwk2_2026-09-17_v3` | 2 | same |
| `fantasypros_adjusted` | `fitwk2_2026-09-18_v1` | 2 | same |

`cbs_adjusted` is not in the fixture; the browser derives it live from
per-player ratios of the three baked adjusted sections against their raw refs.

All four Adjusted curves currently render with the dashboard's computed
`"stale · waiting Wk 3"` tag (active reference week is 3; every fit is week 2).

## Target (stage 1 architecture, already staged)

The fixture carries RAW sections only. All four adjusted curves render live in
the browser from fixture raw refs + the versioned adjustment-inputs asset
(`trade-value-adjustment-inputs-v1`). Stage 2 fills the cells (fit against the
DDF two-tier leg). With the stage-1 empty asset, rendering falls back exactly
to today's behavior (byte-identical, verified).

## The decision

Stage-2 inputs do not exist yet. Until they do, what should the dashboard show
for the Adjusted curves?

### Option A — keep the stale-flagged baked sections

Dashboard unchanged. The four Adjusted curves keep rendering from the week-2
bakes, labeled `"stale · waiting Wk 3"`.

- Pro: zero disruption; the staleness is honestly labeled.
- Con: keeps pipeline-bypassing data in the fixture and on screen; the stale
  flag is easy to miss; `cbs_adjusted` inherits stale inputs silently.

### Option B — pause the stale adjusted curves (recommended)

Per the never-publish-known-flaws rule: hide the three baked adjusted curves
and the `cbs_adjusted` derivation from the default view until stage-2 inputs
land — greyed out with a "waiting on fresh adjustment inputs" explanation,
the same treatment stale DDF values got on 2026-09-17. ESPN adjusted (live)
and the direct published charts stay.

- Pro: nothing stale or unvalidated on screen; matches the 2026-09-17
  precedent; when stage-2 inputs land, the curves return automatically via
  the live renderer — no re-bake, no fixture surgery.
- Con: the default view loses four of its five curves until stage 2; the
  chart is ESPN-led in the interim.

**Recommendation: B.** The dashboard already has the grey-with-explanation
pattern, and the live renderer makes the return trip free.

## Mechanics (after approval)

Pausing is a dashboard display change (default/available curve lists), not a
fixture deletion. Removing the baked sections from the fixture itself is a
separate, explicitly approved promotion-step change.
