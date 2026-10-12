# JEG-548 + JEG-549: bench-share bounds reconciliation and decomposition

Date: 2026-10-12
PR: (pending)
Tickets: JEG-548, JEG-549

## What was done

### JEG-548: Bench-share bounds reconciliation

**Verified:** The 8.6%/13.3% vs 8.1%/13.1% discrepancy comes from two different parameter sets (approved-defaults "recent" m vs eleven-session "all" m), not a bug. The key difference is bye share: 7.8% (recent) vs 7.2% (all). Confirmed by running both parameter sets against current data (post-Razzball fix) where they converge to 8.3%/13.4%.

Correct at approved defaults: 8.6%/13.3%. The methodology ES-7 sensitivity text quotes the eleven-session run.

**Verified:** 12-setting bounds table produced by `tools/bench_research/bench_share_bounds.py --from-log --params recent`. Script reproduces the bounds from the expected-starts model.

**Verified:** Step-by-step math for fill-in floor and VORP ceiling at ppr/12 documented in `docs/research/bench-share-bounds.md`.

### JEG-549: Bench-share decomposition

**Verified:** Displacement absorbs 83% of the gross start-worthy gain. At ppr/12: bench players gain 20.1 value units from start-worthy probabilities, starters lose 16.6 to displacement, net 3.5 on a 2688-unit pie. Computed by `tools/bench_research/bench_share_decomposition.py`.

**Verified:** Individual bench players (RB33-38, WR40-45) get 25-40% of surplus from start-worthy, but aggregate barely moves because marginal starters lose a matching amount.

### Not verified (waiting on JEG-562)

Both scripts and docs need re-running on convention-based tiers after JEG-562 lands. The reconciliation and displacement mechanism are complete; only the exact numbers change.

## Files changed

- `tools/bench_research/bench_share_bounds.py` (new)
- `tools/bench_research/bench_share_decomposition.py` (new)
- `docs/research/bench-share-bounds.md` (new)
- `docs/research/bench-share-decomposition.md` (new)
- `docs/research/research-post-1-facts.md` (updated status for JEG-548, JEG-549)
