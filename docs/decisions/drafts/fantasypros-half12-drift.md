## draft-2026-10-02-fantasypros-half12-drift: FantasyPros half_12 drift — refresh or accept
- id: draft-2026-10-02-fantasypros-half12-drift
- created: 2026-10-02
- deadline: 2026-10-09
- category: native-drift
- silence-default: proceed
- outcome: pending
- outcome_date:
- recommendation: DRAFT: refresh the FantasyPros half_12 combo via the snapshot->match->reference->section pipeline, keep standard_12 and full_12 untouched unless their drift also trips the gate.

### Context

FantasyPros is the other as-published source whose native has
tripped a drift gate in this window. The FantasyPros half_12 combo
is the canonical 12-team half-PPR combo the comparison dashboard
leans on for cross-source cross-checks; full_12 and standard_12 are
priced alongside it but the standing lineage / scale-agreement
checks focus on half_12 because that is the combo that the
VORP-overlap scaling was calibrated against
(`proportional_scaling_vorp_overlap`).

Three pieces of standing context bound this draft:

- The reindex pipeline's "as-published indexing: proportional
  scaling" rule (2026-09-30): for sources with
  `value_provenance == "published"` (FantasyCalc, USA Today,
  FantasyPros, CBS) we use global proportional scaling rather than
  per-position quantile mapping, calibrated on the VORP>0 overlap
  set. That makes the *relative* shape of the half_12 chart
  load-bearing; an isolated half_12 refresh that disagrees with
  the full_12 / standard_12 siblings on cross-position rank is a
  real signal, not noise.
- The FantasyPros coverage regression flagged in GAP-007 (RB
  51<52, WR 72<74) — this is a separate parked item; if the
  half_12 refresh surfaces the same coverage regression, this
  draft and GAP-007 should be linked from the Outcome Note when
  the queue closes.
- The "two-failure rule" from the project's working agreements:
  the same approach failing twice is the stop signal. The half_12
  refresh's blast radius is wider than USA Today's (half_12 is the
  calibration anchor for the scaling step), so the retry cap
  matters more here.

### Problem

When FantasyPros half_12's `native` no longer matches the live
published chart, three options exist:

- Refresh half_12 only — leave full_12 / standard_12 on the
  existing snapshot. Cheap, but creates a cross-sibling
  disagreement inside the same source's combos that the next
  lineage check will flag.
- Refresh all three combos (half_12, full_12, standard_12). Most
  expensive; preserves cross-sibling consistency; risks a fresh
  fetch failing on two of the three and leaving a half-refreshed
  snapshot.
- Accept the snapshot, surface the drift visibly, queue the next
  refresh on the standing schedule. Cheapest; preserves snapshot
  identity; the lineage monitor stays red until the next cycle.
- (the defensive one) Hybrid: refresh half_12, accept siblings
  only if half_12's new values are within tolerance of full_12 /
  standard_12's existing cross-position shape; otherwise abort and
  queue the whole source for next-cycle refresh. Most defensive;
  cheapest when the drift is fetch-only; most complex to validate.

### Options

1. **Refresh half_12 only.** Targeted, cheap, but creates an
   internal cross-combo disagreement that the lineage section will
   surface as a different signal than the original drift.
2. **Refresh all three FantasyPros combos together.** Preserves
   cross-combo consistency inside FantasyPros; matches the
   proportional-scaling rationale; risks a partial refresh on
   fetch failure.
3. **Accept and surface drift visibly.** Cheapest; aligns with the
   "snapshot identity lives for one NFL week" model; monitor stays
   red until the next scheduled refresh.
4. **Hybrid: refresh half_12, accept siblings only if consistent.**
   Most defensive; cheapest when the drift is fetch-only; requires
   a cross-combo tolerance the project has not yet pinned.

### Recommendation

DRAFT: Option 4 (the hybrid). The half_12 refresh is the part that
actually moved; full_12 and standard_12 are sibling combos and
should only move when half_12's movement is consistent with them.
If the refresh fails or produces a half_12 that disagrees with the
existing cross-position shape of its siblings, accept and queue the
whole source for next-cycle refresh — do not half-refresh.

The exact tolerance for "consistent with the cross-position shape
of its siblings" is TBD: this draft follows the same 5%/20% gate
as the USA Today draft and the FantasyCalc drift checker. The
reviewer may want a tighter tolerance for FantasyPros because
half_12 is the VORP-overlap calibration anchor; mark that decision
explicit before queueing.

### Outcome Note

(Empty while `outcome: pending`.)