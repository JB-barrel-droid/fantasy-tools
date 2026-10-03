# Eight-group VORP reweight proposal (JEG-209)

Status: design proposal for Jeremy/Roman review, not approved methodology.
Model version: reference-squared-surplus-batch70-proposal-v1. No production code or fixture changes.

## Input contract

Each row has a canonical numeric player_key, position, role, and nonnegative
VORP U in fantasy points per game above that position's waiver line. Granular
sources compute U from their own projections and roster allocation. Published
charts supply Option C imputed VORP from JEG-180; raw site values are never
accepted as U. JEG-206 must expose the eight disjoint groups and their roster
and replacement provenance before implementation.

Groups are QB/RB/WR/TE crossed with starter/bench. Each positive rostered row
belongs to exactly one group. Waiver rows contribute zero; missing projections
are unknown and remain unavailable. Never turn missing into zero. Reweighting
cannot resolve identity, infer content vintage, or approve review rows.

The league shape, scoring, source content vintage, input hashes, group membership,
waiver lines, VORP units, allocation reference, and model version travel with
the result. Custom roster changes require recomputing the input contract;
no source/configuration fallback is permitted.

## Scale contract

70 is the highest player's displayed value. It is not the sum of all values.
First allocate a positive arbitrary bookkeeping budget B0 across the groups,
then normalize the entire result by one common factor so its maximum is 70.
Record the resulting displayed total B and all eight displayed group budgets.
A single scale cannot generally fix both a chosen total B and a top value 70.
Do not clip individual values at 70, because clipping destroys conservation.

## Approval and downstream handoff

The proposal and arithmetic companion are review artifacts. Jeremy approves the
allocation policy; Roman reviews/integrates. JEG-182/206 implement the approved
contract and JEG-210 labels its views. Indexed is a simple native-chart rescale;
it never calls this reweight. VORP is the upstream U; Adj is this model's output.
K/DST belong to JEG-211. Existing chart behavior stays in place until a separate
implementation and its validation/promotion gates are complete.

## Proposed allocation: reference surplus with a concentration premium

Use one pinned, complete granular reference for a comparison batch (ESPN in
this example). It determines economics; each other source supplies player
judgments. Do not derive budgets from publisher chart magnitudes or already
adjusted values. Selecting ESPN as this reference is a proposal, not authority
to replace the current scale contract.

For reference player j, R_j = max(0, projection_j - waiver_position).
For group g, define:

```
T_g = sum(R_j)                      reference group surplus, points/game
E_g = sum(R_j * R_j)                allocation score, (points/game)^2
w_g = E_g / sum(E_h)                fraction of the bookkeeping budget
S_sg = sum(U_si)                    source s group VORP, points/game
q_si = w_g * U_si / S_sg            provisional value, unit budget
M = max(q_si across included sources and players)
lambda = 70 / M
B = lambda                         displayed total per complete source
B_g = lambda * w_g                  displayed group budget per source
v_si = lambda * q_si                player's displayed Adj value
```

The multiplication by itself is an explicit policy choice: reward concentrations
of hard-to-replace surplus more than broad pools of tiny advantages. It is not
an empirical utility estimate or a mathematically inevitable definition of
scarcity. It needs Jeremy's approval. There is no fitted exponent or solver.
For n reference players, E_g = n * (mean(R)^2 + population_variance(R)).
Thus actual roster demand (n), advantage over available replacements (mean),
and uneven drop-off (variance) determine the budget. Equal splits and a fixed
bench percentage never enter. A distribution with the same total but a sharper
drop-off receives more budget. More small-surplus bench players can increase
its budget; adding actual zero rows cannot.

Within a source/group, only relative U matters. Positive uniform scaling of
any source group cancels between U and S. Scaling all reference R by a common
unit conversion cancels in w. Scaling only one reference position changes the
allocation, so reference positions must share one scoring/time unit. Changes
to scoring rules are real economics changes, not unit conversions.

This separates allocation from mapping: the squared score affects group
budgets, while the player mapping remains linear within each group. It does
not square each publisher player's VORP. Option C must complete first and
record its reference; the same allocation reference should be used downstream.
Do not independently refit this method onto each publisher's native scale.

## Common scale and proofs

A complete source has the same eight B_g as every other source in its batch.
Because sum(w_g)=1, sum(B_g)=lambda=B. Because sum(U/S)=1 inside each
positive group, sum(v_si in group)=B_g. These are exact identities before
floating point and display rounding. Use full precision for calculations;
rounded tables need not add exactly.

Inside a positive group, v_si has one positive multiplier on U_si. Strict
ordering and ties are preserved, and a genuine zero remains zero. Across
groups, ordering may change intentionally. Cross-role ordering is not guaranteed
for every possible publisher distribution; a concentrated bench source could
outvalue a marginal starter. Report such inversions for review rather than
silently ironing or clipping them.

One lambda is shared across the entire complete comparison batch. Then every
v lies in [0,70], and some player/source reaches 70. Independently forcing each
source's own maximum to 70 would create unequal totals and incomparable group
budgets. The proposed batch anchor changes when an included source's concentration
changes, even if its vintage differs. Freeze the source set, configuration,
reference hash, source hashes and model version together. Recompute the whole
batch atomically; never mix cached values with another lambda.

The current ESPN-only 70 anchor and all-source bounded values cannot both be
guaranteed when another source concentrates more of its group budget on one
player. Jeremy must approve the proposed all-source anchor, or retain an ESPN
anchor and explicitly allow values above70. This example uses a one-source
batch, so it does not supply evidence that the full seven-source maximum would
remain ESPN. Missing sources stay unavailable and are excluded explicitly from
the batch manifest; never reuse another configuration as their substitute.

## Degenerate inputs

- Reject unresolved/duplicate keys, extra/missing group definitions, nonfinite
  values and negative input VORP. Projection-to-VORP floors are upstream;
  reweighting must not silently repair corrupted input.
- A reference group with no positive R has weight0. It may have empty or
  genuine-zero source rows; positive source VORP there is a coverage mismatch.
- A positive reference budget requires a positive source S. Empty or all-zero
  source groups cannot absorb it. Mark that source's complete Adj output
  unavailable with the reason, not zero and not a redistributed budget.
- Reject an all-zero reference or an empty comparison batch. There is no peak
  to normalize. Missing source observations remain null/unavailable; even when
  enough others exist to compute S, coverage review must certify the pool.
- Benchless leagues use explicit empty bench groups, not an invented epsilon.
  A finite overflow is an arithmetic failure, never a partial result.

## Why it differs from a simple linear rescale

The baseline is L_i = 70 * U_i / max(U) for the same single-source pool.
If E_g were just T_g and U=R, w_g * U_i/T_g would reduce to U_i/sum(R):
allocation would do nothing beyond global scaling. That is a legitimate simpler
alternative and should be preferred if the concentration premium has no product
benefit. Squaring R prevents that cancellation: the group multiplier is
proportional to E_g/T_g, the surplus-weighted mean advantage above replacement.

The premium sharply favors the reference's largest starter pools. This is a
material risk, not proof that a RB value of70 and QB value near12 are desirable.
The worked example suppresses TE/bench especially strongly. Jeremy should
compare this with global linear and the current utilization model before
choosing. A piecewise utilization model would need a separately approved
utilization/premium rule; algebra alone cannot identify real bench option value.
No calculus is needed to implement any formula here, and no claimed quality
gap justifies introducing an optimizer.

## Pinned worked example and runnable acceptance

Input: `data/ddf-two-tier/ddf-20260929-espn-half_ppr-12t-0p15/ddf_leg.json`.
SHA-256: `d29beb2e3481e4fa1ecd71b194e11428a9a64d0900fe9c0636f933517865b98d`.
Content vintage:2026-09-29; generated2026-09-30; half PPR,12 teams,16-game
projection divisor. Dedicated slots QB1/RB2/WR3/TE1, one RB/WR/TE flex;
league bench mix QB10/RB27/WR33/TE10. Uses only canonical keys, ppg, tier,
and position rw from that artifact. Its calibrated values, raw_value, pie,
pb/ps, bench_share and softplus curve are not used. Existing review_rows
remain unresolved context: this is a historical arithmetic sample, not a
freshness or promotion-ready verdict.

Run from the repository root:

```bash
python3 docs/design/reweight_example.py > /tmp/jeg209-example.json
```

This standalone standard-library companion is deliberately outside pipelines.
It verifies the pinned bytes, group/total conservation, within-group order,
70 anchor, unit changes and shared two-source budgets. It rejects missing group,
all-zero reference, missing/negative/NaN/infinite VORP, empty funded group and
duplicate canonical key. The second source is synthetic and labeled as such;
it proves the common-scale identity, not real publisher integration. Production
implementation and its tests follow approval; this script is no production API.

| Group | Players | Sum VORP | Squared score | Budget share | Adj budget | Linear budget |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| QB/starter | 12 | 46.293750 | 193.703640 | 4.054112% | 78.687931 | 183.887786 |
| QB/bench | 10 | 12.321875 | 19.867031 | 0.415806% | 8.070553 | 48.944886 |
| RB/starter | 32 | 279.888125 | 2736.810013 | 57.279944% | 1111.770109 | 1111.770109 |
| RB/bench | 27 | 60.278750 | 186.469530 | 3.902706% | 75.749230 | 239.438928 |
| WR/starter | 40 | 220.817500 | 1402.417370 | 29.351832% | 569.701845 | 877.130089 |
| WR/bench | 33 | 47.928750 | 98.303976 | 2.057449% | 39.933872 | 190.382324 |
| TE/starter | 12 | 36.256250 | 135.974108 | 2.845864% | 55.236552 | 144.016882 |
| TE/bench | 10 | 4.909375 | 4.409425 | 0.092287% | 1.791234 | 19.500993 |

Total displayed budget B = 1940.941325915, not70.

| Player (canonical key) | Group | VORP | Proposed Adj | Linear |
| --- | --- | ---: | ---: | ---: |
| Josh Allen (869) | QB/starter | 6.997500 | 11.894020 | 27.795432 |
| Jahmyr Gibbs (2227) | RB/starter | 17.622500 | 70.000000 | 70.000000 |
| Jordan Mason (2821) | RB/bench | 4.462500 | 5.607796 | 17.725919 |
| Puka Nacua (1370) | WR/starter | 10.666250 | 27.518572 | 42.368421 |
| Trey McBride (3133) | TE/starter | 6.366250 | 9.699009 | 25.287984 |
| Mark Andrews (324) | TE/bench | 1.533125 | 0.559376 | 6.089871 |

For Josh Allen: U=21.19875-14.20125=6.9975; QB/starter S=46.29375;
E=193.70363984375; w=0.040541117714697886. His final value is
B*w*U/S=11.894020155458248. Gibbs anchors this one-source example at70.
Bench share is not set at15%: QB is9.302%, RB6.379%, WR6.551%, TE3.141%
of each position's proposed budget (rounded). These are consequences of this
sample and policy, not constants for future vintages.

## Decisions required before implementation

Approve or reject the squared concentration premium, the common pinned economics
reference, and the all-source batch70 anchor together. Approve the coverage
contract from JEG-206/180 and review cross-role inversions on complete real
seven-source inputs. Alternative: choose linear global scaling and explicitly
accept that eight-group allocation collapses to that baseline. No methodology
or public-copy decision is made by the arithmetic companion.

## Validation and continuation record

Base main: `bdf43bd` (2026-10-02 inspection); branch
`codex/jeg-209-reweight-design`. `python3 docs/design/reweight_example.py`,
`python3 -m py_compile docs/design/reweight_example.py`, `git diff --check`
and `make validate` passed locally on2026-10-02. The repository suite reports
its existing skips; this is not production QA. Validation-generated timestamp
changes in app/dist were discarded, preserving design-only scope.

Independent review was requested through Claude Code MCP. Its initial option
and follow-up report contained incorrect arithmetic/conservation assertions;
those assertions were rejected by Codex. The accepted proof here is total=lambda,
maximum=70, independently reproduced by the companion. Final artifact review
and methodology approval are recorded in the PR/Linear handoff when available.
This document does not claim an independent approval or integration verdict.

Next action: Jeremy/Roman choose allocation and anchor policy. Then implement
an approved shared contract in a separate issue branch; validate all seven
real source outputs, review coverage/inversions and follow promotion gates.
