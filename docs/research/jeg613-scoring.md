# JEG-613: Value Goals Scoring and Engine Audit

2026-10-22. Read-only audit: no code changes. All measurements from the live
engine at the 12 standard setups (3 scorings x 8/10/12/14 teams), plus the
headless view-invariants sweep (15 settings including custom roster and bench
share variants). Engine dump: `tools/engine_dump.py`. View invariants:
`tests/test_view_invariants.py`.

## Jeremy's answers (quoted from Linear comment 2026-10-22)

Verbatim quotes are indented; analysis follows each.

## Q1: Indexed total (equal pies, capped at league rostered count)

> "The total pies should be the same size; but with consideration. If the pie is
> greater than the number of rostered players in the league configuration, then
> the total value should be set to the league player count, by position. If the
> player count provided is less than the associated league size dictates should
> be on rosters, then take the amount of the pie assumed by other trade charts
> for that portion of the roster counts, and make that that the total pie the
> underscoped trade value chart is assigning against."

### Current engine behavior

- **Pie** = `28 * teams * starting_slots` (VP-5.1). The pie is league-dependent
  (changes with teams, scoring via flex) but is NOT capped at any chart's player
  count.
- **Indexed** uses `fixedPieIndexed`: each chart's Indexed total over its listed
  players equals the blended DDF total over those same players. This ensures
  "equal pies" in the sense that the Indexed view is a rescaling of the chart's
  natives to the DDF basis.
- **Fill-in** (OC-5, VP-2.4): charts that list fewer players than the rosterable
  set get estimated values for the missing players. These estimates use
  cross-chart ratios (last-10 shared players) or the chart's own curve against
  projected points, capped at the chart's lowest listed value.

### Comparison with Jeremy's answer

Jeremy's rule has two parts:

1. **Cap at league rostered count, by position.** The current engine does NOT
   cap the pie per position at the rostered count. The pie is allocated to
   positions by the DDF weights (VP-4), not by headcount. A position's budget
   can exceed `count * max_value_per_player` in principle.

2. **Underscoped charts take the pie other charts assign.** The fill-in rule
   (VP-2.4) does something related but different: it estimates the value a short
   chart *would* assign to missing players, using other charts as peers. It does
   NOT take the pie other charts assign to that portion of the roster. The
   difference: VP-2.4 estimates a native value for the missing player, then that
   value flows through the normal pipeline (waiver subtraction, slicing, rates).
   Jeremy's rule would directly assign the pie allocation.

**Verdict: partial match.** The spirit (equal pies, short charts get reasonable
values for missing players) is met. The mechanism differs from what Jeremy
described. Whether the difference matters in practice depends on how the fill-in
estimates compare to the other-charts' pie allocation. Recommend: measure the
gap and decide whether to change.

### Measured at 12 setups

| Setup | fixedPieIndexed | indexedOrderOk |
|-------|-----------------|----------------|
| standard/8 | Pass | Pass |
| standard/10 | Pass | Pass |
| standard/12 | Pass | Pass |
| standard/14 | Pass | Pass |
| half_ppr/8 | Pass | Pass |
| half_ppr/10 | Pass | Pass |
| half_ppr/12 | Pass | Pass |
| half_ppr/14 | Pass | Pass |
| ppr/8 | Pass | Pass |
| ppr/10 | Pass | Pass |
| ppr/12 | Pass | Pass |
| ppr/14 | Pass | Pass |

## Q2: "Do not fix this" (ambiguous)

Jeremy's answer to Q2 (should fixed starting points follow the anchor's own
positional tops and change with scoring?):

> "Do not fix this."

### Two readings

1. **"Leave the fixed starting points alone"** -- the current fixed starting
   points (QB 25, RB 70, WR 55, TE 30) should stay as they are and should NOT
   track the anchor's positional tops. This reading is consistent with the pre-
   JEG-508 behavior and preserves the fixed reference frame.

2. **"This is not a problem to fix"** -- the question itself is moot (post
   JEG-508, the fixed starting points are retired in favor of VP-5.1 pie
   allocation, so there is nothing to fix).

### What the code does

Post-JEG-508, the fixed starting points (QB 25, RB 70, WR 55, TE 30) are no
longer used by the engine. The pie is computed as `28 * teams * starting_slots`
and allocated by the DDF weights (VP-4). The old starting points exist only in
legacy documentation.

**Implication of reading 1:** no code change needed (the fixed starting points
are already gone). **Implication of reading 2:** same -- no code change needed.
Both readings result in no action, but for different reasons.

**Recommendation:** ask Jeremy for a one-line confirmation of which reading he
intended, since Q1 (equal total pies) appears to supersede the fixed starting
points entirely.

## Q3: Saved vs browser recipe must match at the same settings

> "They should match then the settings are the same, and that is a check that
> the math, pipes, and logic is working properly."

### Measured

The `value_check compare` tool compares the Python reference pipeline
(`pipelines/value_reference.py`) against the browser engine
(`app/trade-value-chart/assets/value-model.js`) at all settings.

**Result: 836,995 values compared, 0 mismatches, tolerance 0.05.**

Every source, every view, every setting agrees to floating-point precision.

| Source | Compared | Mismatches | Max abs diff |
|--------|----------|------------|-------------|
| usatoday | 55,474 | 0 | 0.0000 |
| fantasycalc | 55,644 | 0 | 0.0000 |
| fantasypros | 55,836 | 0 | 0.0000 |
| cbs | 56,591 | 0 | 0.0000 |
| espn | 44,000 | 0 | 0.0000 |
| cbsros | 27,425 | 0 | 0.0000 |
| razzball | 46,700 | 0 | 0.0000 |

**Verdict: pass at all 12 setups.**

## Q4: Bias-adjusted charts in DDF Value (open; context written)

> "Need more context."

See `docs/research/jeg613-q4-context.md` for the context document with the three
options, measurements, and a recommendation.

## Q5: Bench share -- lean on the research

> "No, we researched this. Lean on the research."

Inline comment: "This % is no longer set at 15% and is dictated by project
research."

### Current engine behavior

The engine runs in **expected-starts mode** (ES-14/ES-15) at all default setups.
In this mode, the bench share is an **output** computed from the lineup
parameters (`config/lineup_parameters.json`), not the hardcoded 15%.

Measured bench share (fill-in share) at each setup:

| Setup | Bench share (fill-in) | Method |
|-------|----------------------|--------|
| standard/8 | 7.4% | expected-starts |
| standard/10 | 7.5% | expected-starts |
| standard/12 | 6.7% | expected-starts |
| standard/14 | 6.4% | expected-starts |
| half_ppr/8 | 5.0% | expected-starts |
| half_ppr/10 | 5.9% | expected-starts |
| half_ppr/12 | 5.9% | expected-starts |
| half_ppr/14 | 6.2% | expected-starts |
| ppr/8 | 6.2% | expected-starts |
| ppr/10 | 6.2% | expected-starts |
| ppr/12 | 6.1% | expected-starts |
| ppr/14 | 6.5% | expected-starts |

The 15% default (`VP_DEFAULT_BENCH_SHARE`) is only a fallback for when
expected-starts mode is not active (e.g., no lineup parameters available).

### Where 15% still appears in code

The hardcoded 0.15 appears in several pipeline builders and the product-data
default:

- `app/trade-value-chart/assets/value-model.js:557` -- `VP_DEFAULT_BENCH_SHARE = 0.15` (fallback)
- `app/trade-value-chart/assets/product-data.js:222` -- `bench_share_default: 0.15`
- `config/roster.json` -- `"bench_share": 0.15`
- `pipelines/build_ddf_two_tier_leg.py:76` -- fallback
- `pipelines/reindex_comparison_section.py:118` -- fallback
- `pipelines/build_razzball_section_from_ddf_leg.py` -- from config
- `pipelines/build_cbsros_section_from_ddf_leg.py` -- from config

These are all fallback paths. The live engine uses expected-starts.

### Disagreement with Jeremy's answer

**Partial.** The live engine already leans on the research (expected-starts).
But the 15% is still the documented default and is used by pipeline builders
that construct the reference data for non-ES settings. The goals doc says "bench
gets a set share of each position's pie (default 15%)" which is stale against
the current behavior (5-7.5% from expected-starts).

**Verdict: the engine matches Jeremy's intent. The documentation and pipeline
builder fallbacks are stale.**

## Q5 inline comment: "This % is no longer set at 15% and is dictated by project research"

Same finding as Q5 above. The engine uses expected-starts; the code and docs
still reference 15% as the default. The inline comment is correct about the
engine, but the code path that uses 15% as a fallback still exists.

## Q6: Raw VORP has no starter/bench logic

> "Raw VORP doesn't have starter/bench logic in it. Raw VORP is just value above
> waivers based on expected production compared to waiver lines at the given
> positions. It assumes no consideration for bench share."

Inline comment: "No reweighting for bench vs. starter either."

### Current engine behavior

Raw VORP (the `*_vorp` series: espn_vorp, cbsros_vorp, razzball_vorp) is
computed as:

```
vorpDisplay = vorp * vorpFactor
```

where `vorp = max(0, native - waiver)` and `vorpFactor = pie / surplusTotal`.

- **No starter/bench weighting:** correct. The vorpFactor is a single scalar per
  source (not per position or role). Unlike the Adjusted view, which uses
  separate rates for starter and bench slices, raw VORP applies one factor.

- **Same roster model as other views:** the waiver line IS set by the allocation
  (VP-2.2), which includes bench seats. The allocation determines which player
  is at the waiver line (the first player past rosterable depth), and rosterable
  depth includes bench seats.

### Potential disagreement

Jeremy says "no consideration for bench share." The engine gives raw VORP no
starter/bench *weighting* (one factor for all players), but the waiver line
itself is affected by bench seats. A change in bench size changes which player
sets the waiver line, which changes every raw VORP value.

This could be read two ways:

1. **"No bench weighting in the value formula"** -- this is what the code does.
   The vorpFactor has no position or role component. **Match.**

2. **"A completely separate roster model ignoring bench entirely"** -- this is
   NOT what the code does. The waiver line depends on bench seats. **Mismatch.**

**Verdict: match on the likely reading (no bench weighting). Flag the waiver-
line dependency for confirmation if reading 2 was intended.**

## Goal scoring table

Scored from the engine dump at all 12 setups. "Pass" = holds at every setup.

| Goal | Test | Result | Notes |
|------|------|--------|-------|
| S1 | Anchor top = 70 | **Partial** | Range 64.9 to 72.6 across setups. Not exactly 70; varies with league. |
| S2 | Waiver line at rostered+1 with flex | **Pass** | Allocation includes flex (VP-2.2). Waiver = work[rostered].native. |
| S3 | Settings move values | **Pass** | Pie changes with teams/scoring. Structural. |
| S4 | No series clipped at anchor top | **Pass** | No cap enforced. Several sources exceed ESPN's top at some setups. |
| S5 | Saved vs browser agree | **Pass** | 836,995 values, 0 mismatches. |
| Indexed | Total over shared = DDF total | **Pass** | fixedPieIndexed = True at all 12 setups. |
| VORP | Each source total = pie | **Pass** | Max relative error: 1.2e-15 (floating point). |
| Adjusted | Each source total = pie | **Pass** | Max relative error: 7.7e-16 (floating point). |
| DDF Value | Mean of inputs; no missing = 0 | **Pass** | 363 players checked per setup, 0 errors. |
| Families | Published order preserved; own projections only | **Pass** | Structural (VP-2, VP-1). Not independently re-measured (would need raw data comparison). |
| Honesty | Missing stays missing; derived labelled | **Pass** | Structural (VP-6 rowCell logic). Not independently re-measured. |

### S1 detail: anchor top player value

| Setup | ESPN top Adjusted |
|-------|------------------|
| standard/8 | 71.88 |
| standard/10 | 68.80 |
| standard/12 | 69.12 |
| standard/14 | 64.90 |
| half_ppr/8 | 70.57 |
| half_ppr/10 | 71.55 |
| half_ppr/12 | 72.63 |
| half_ppr/14 | 66.37 |
| ppr/8 | 68.58 |
| ppr/10 | 71.09 |
| ppr/12 | 71.11 |
| ppr/14 | 70.38 |

The goal says "top player = 70." The current engine does not enforce this: the
pie is `28 * teams * starting_slots`, and the top player's value depends on the
distribution of projected points relative to the waiver line and the DDF
weights. The value is NEAR 70 at most setups but can range from 64.9 to 72.6.

## Headless sweep (12-combo + extras)

The `test_view_invariants` sweep ran 15 settings (12 standard + custom roster +
two bench-share variants), 270 checks, **0 problems**.

Diagnostics checked per setting:
- `fixedPieIndexed`: each Indexed chart's total over listed players = DDF total
- `sourceScaleAgreement`: page's own viewInvariants gatedHold = true
- VORP totals = pie per source
- Adjusted totals = pie per source (less unfunded budget)
- Indexed totals = DDF totals per chart over shared players

## Where code and Jeremy's answers disagree

| Item | Jeremy says | Code does | File:line | Severity |
|------|------------|-----------|-----------|----------|
| Q1 pie cap | Cap at league rostered count by position | Pie = 28*teams*starting_slots, no per-position cap | value-model.js:1013-1018 | Medium: affects short charts |
| Q1 underscoped | Take other charts' pie for that roster portion | VP-2.4 fill-in estimates native values, not pie portions | value-model.js:1043-1117 | Medium: different mechanism, similar goal |
| Q5 docs | Bench share dictated by research | Code: 0.15 default in config/roster.json, product-data.js, pipeline builders | config/roster.json:1, product-data.js:222 | Low: engine uses ES; docs/config stale |
| S1 top=70 | Anchor top = 70 (goals doc) | Top ranges 64.9-72.6 | value-model.js:1013 (pie formula) | Low-medium: near 70 but not pinned |

## Q2 ambiguity

Jeremy's "Do not fix this" has two readings:

1. **Leave the fixed starting points alone** -- but they are already retired
   post-JEG-508. No action either way.
2. **The question is moot** -- same conclusion.

Recommend: ask Jeremy to confirm which reading, since Q1 (equal pies) is the
active rule now.

## Proposed tickets (for Jeremy's approval)

Each is a recommended change based on the scoring. None should be opened without
Jeremy's approval.

### Ticket 1: Pin the anchor top to 70

**Title:** Pin anchor top player to exactly 70 at every setup
**Why:** Goal S1 says "top player = 70" but the current engine produces 64.9 to
72.6 depending on league. The pie formula (`28 * starting_slots * teams`) does
not guarantee this. A post-pipeline rescale or a pie formula change would fix
it.
**Files:** `app/trade-value-chart/assets/value-model.js` (VP-5.1 pie),
`pipelines/value_reference.py`

### Ticket 2: Implement Q1 per-position pie cap

**Title:** Cap Indexed pie at league rostered count by position (Q1)
**Why:** Jeremy's Q1 answer says the total value should not exceed the league
player count by position. The current engine has no such cap. For charts that
list more players than the roster holds, the excess value inflates their
Indexed total.
**Files:** `app/trade-value-chart/assets/value-model.js` (VP-5, VP-6.4),
`pipelines/value_reference.py`

### Ticket 3: Update Q1 underscoped chart handling

**Title:** Underscoped charts take other charts' pie allocation (Q1)
**Why:** Jeremy's Q1 answer says underscoped charts should take the pie other
charts assign to the missing roster portion. The current fill-in (VP-2.4)
estimates native values instead. Measure the gap; if material, implement
Jeremy's rule.
**Files:** `app/trade-value-chart/assets/value-model.js` (VP-2.4, VP-5),
`pipelines/value_reference.py`

### Ticket 4: Remove 15% bench share from config and docs

**Title:** Replace hardcoded 0.15 bench share with expected-starts defaults
**Why:** Jeremy confirmed bench share is dictated by research, not 15%. The
engine already uses expected-starts, but config/roster.json,
product-data.js and several pipeline builders still reference 0.15 as the
default. Update them to match the live behavior.
**Files:** `config/roster.json`, `app/trade-value-chart/assets/product-data.js`,
`pipelines/build_ddf_two_tier_leg.py`, `pipelines/reindex_comparison_section.py`,
`pipelines/build_razzball_section_from_ddf_leg.py`,
`pipelines/build_cbsros_section_from_ddf_leg.py`

### Ticket 5: Resolve Q4 (bias-adjusted charts in DDF Value)

**Title:** Decide and implement bias-adjusted charts in/out of DDF Value (Q4)
**Why:** Jeremy asked for more context (now in
`docs/research/jeg613-q4-context.md`). Once he decides, the composite input
lists need updating.
**Files:** `app/trade-value-chart/assets/curve-widget.js` (COMPOSITE_INPUT_KEYS,
COMPOSITE_VERSIONS), `pipelines/value_reference.py`

### Ticket 6: Confirm Q6 raw VORP waiver-line model

**Title:** Confirm raw VORP uses the same waiver line as other views
**Why:** Jeremy says raw VORP has "no consideration for bench share." The engine
applies no bench weighting but DOES use the same roster allocation (including
bench seats) to set the waiver line. If Jeremy intends a separate, bench-free
waiver line, that is a change.
**Files:** `app/trade-value-chart/assets/value-model.js` (VP-2),
`pipelines/value_reference.py`
