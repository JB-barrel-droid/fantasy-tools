## draft-2026-10-02-prediction-markets-leg: surface the prediction-markets leg or not
- id: draft-2026-10-02-prediction-markets-leg
- created: 2026-10-02
- deadline: 2026-10-09
- category: leg-promotion
- silence-default: proceed
- outcome: pending
- outcome_date:
- recommendation: DRAFT: do not surface a prediction-markets leg in the comparison dashboard yet — the source-identity, lineage, and provenance questions are unresolved; queue this as a follow-up after those three are settled.

### Context

The project has a partial prediction-markets data feed wired in for
internal modeling (`pipelines/...` and `supabase` reference tables
carry rows tagged with prediction-markets provenance), but the leg
is not surfaced in the comparison dashboard. The comparison
dashboard today renders: ESPN (DDF methodology), CBS (published),
CbsRoz (DDF methodology from `public.cbs_ros_projections`), Razzball
(DDF methodology from `public.razzball_projections`), FantasyCalc
(published, 24 combos), FantasyPros (published, 3 combos), USA Today
(published, 3 combos). The four as-published sources all have a
published chart; the three DDF-methodology sources all have a
canonical identity map (Supabase `players` table) and a documented
provenance trail.

Prediction markets is not one of those. It has no published chart,
no canonical identity map against `players.json`, and no published
"native value" concept — its rows carry implied probabilities, not
trade-value points. Surfacing it would mean inventing a mapping
from implied probability to a synthetic trade value, which is the
class of data-error the project's "never guess, never invent names"
rule is meant to block.

This draft is the parked item for the next time someone asks "can
we get a prediction-markets line on the chart?"

### Problem

If the project adds a prediction-markets leg, three things have to
be settled first:

1. **Identity.** Which `player_key` does a prediction-market row
   map to? The `players` table is the identity authority. If the
   prediction-markets source names a player with a different
   spelling (e.g. "Jaxon Smith-Njigba" vs "Jaxon SmithNjigba" vs
   "JSN"), the project's standing rule is fail-closed — the row
   goes to `review_rows`, not the section. Without a canonical
   mapping the section is more `review_rows` than values.
3. **Provenance.** Is the prediction-markets number a "native" in
   the same sense FantasyCalc's API value is? The dashboard's
   "Value Provenance" column carries `"published"` vs
   DDF-methodology vs `"native"`. Prediction-markets sits
   somewhere in between — the number is real and market-priced,
   but it is not a trade-chart value. Surfacing it without a
   provenance label invites readers to compare it line-for-line
   with the other legs, which it cannot sustain.
4. **Lineage.** The lineage section
   (`build_source_value_lineage.py`) compares each leg's `native`
   against a live human-readable page. Prediction markets has no
   static live page; the "live" comparison would have to hit an
   API. Either the lineage section needs a new rule
   (live_api vs live_page), or this leg opts out of the lineage
   section. Either is a standing-contract change.

### Options

1. **Surface it now, label it `prediction-markets`, document the
   caveat in the dashboard.** Cheapest path to "yes there's a
   prediction-markets line on the chart." Risks: identity
   mismatches land in `review_rows` and look like data bugs;
   readers compare it line-for-line with the other legs; the
   lineage section shows N/A on this leg and the monitor stays
   red on a new row.
2. **Don't surface it; queue the three prerequisite decisions
   (identity, provenance, lineage) as separate entries.** Most
   conservative; aligns with the "never guess, never invent"
   rule; the prediction-markets leg appears in the dashboard
   only after the three prerequisites close.
3. **Surface a degraded form: show only the top-N
   prediction-markets probabilities, no comparison line.** A
   reader can see "yes, the project has prediction-market data"
   without the dashboard pretending it is a trade-value leg.
   Risks: no visual line on the chart, easy to miss; still needs
   identity and provenance labels.

### Recommendation

DRAFT: Option 2 — do not surface it. Queue the three prerequisite
decisions (identity, provenance, lineage) as separate entries with
their own deadlines. Each prerequisite is a methodology-class
decision (per the queue rules, methodology decisions require an
explicit tap regardless of clock) so they will not auto-execute on
silence anyway.

The exact text of the three prerequisite drafts is TBD — this
draft is the umbrella for the question "do we surface a
prediction-markets leg at all?" The three sub-decisions are the
work that has to happen before that question can be answered.

If the reviewer wants to surface a degraded form (Option 3) first
as a low-risk way to ship reader value while the three
prerequisites are in flight, mark that decision explicitly before
queueing.

### Outcome Note

(Empty while `outcome: pending`.)