# Linear eight-group VORP reweight (JEG-209 / JEG-231)

Status: revised design artifact reflecting Jeremy's recorded decisions on
2026-10-02. Supersedes the squared-surplus/ESPN-only proposal in the initial
PR #41 commit. No squared premium is retained. Production implementation is
JEG-182's separate active lane; this document and companion do not implement it.
Model: `linear-blend-controlled-batch70-design-v2`.

## Recorded policy and remaining implementation choices

Jeremy approved linear allocation throughout, a blended economics reference,
an all-source batch70 anchor, user-adjustable eight-box budgets with linear DDF
defaults, and eliminating within-position starter/bench inversions. Cross-position
inversions can be legitimate and are preserved. Source: JEG-209 decision comments
`64995485-73ac-4782-9fc3-c8875276ed4a` and
`e93da9bc-d0a9-4fdd-abcd-9c0ab1b3e170`.

The precise blend weights and time-horizon alignment were not specified in those
comments. Equal source weights below are an explicit illustrative choice, not a
new approved production policy. The proposed closed-form control constraint
below implements the no-inversion requirement without an optimizer. Its visible
requested/effective budget presentation still needs implementation review.
The parent being marked Done records policy decisions, not integration of this
revised artifact or production QA.

## Inputs, units and coverage

Eight groups are QB/RB/WR/TE crossed with starter/bench. Dedicated starters and
flex players belong to starter; waiver rows are zero and outside these groups.
Each included source/configuration has canonical numeric keys, disjoint groups,
complete reviewed coverage, and nonnegative finite upstream VORP U. Genuine zero
remains zero; missing observations stay unavailable, never zero-filled. Reference
and comparison manifests pin source set, exact content vintages, scoring, teams,
roster/flex/bench shape, projection horizon/divisor, waiver lines, hashes and model.
No identity resolution, review-row approval or freshness inference happens here.

Granular U is max(0, PPG minus position waiver PPG) from the DDF roster/replacement
pipeline. Publisher U is the approved JEG-180 Option C proportional imputed VORP,
computed upstream from the full group denominator. Raw chart magnitudes, previous
adjusted values, softplus values and stale reindex output are not VORP inputs.

**Current integration discrepancy:** `pipelines/build_ddf_groups.py:compute_groups`
sums each legacy leg row's `value`, which is an already calibrated chart value,
and labels the result `total_vorp`. It does not sum raw PPG-minus-waiver surplus.
The reported 2662.9907 total is therefore not evidence of raw VORP units. Do not
silently treat it as the raw-unit blend below or change its semantics without
versioning and updating JEG-180/182/207 consumers. The companion derives raw U
explicitly from pinned `ppg` and `calibration[pos].rw` to keep this distinction
inspectable. Record this discrepancy in the implementation handoff.

References must share scoring and time units before their totals are averaged.
A common unit conversion cancels; independently rescaling one reference changes
its influence. ESPN divides ROS totals by16, CBS uses player games, and Razzball
publishes PPG: these sample inputs are same labeled PPG units, but their remaining
horizons/vintages differ. The sample demonstrates arithmetic, not certification
that those horizons/coverage are production-comparable.

## Linear blended defaults and eight controls

Let R_rg be the sum of raw reference VORP in group g for granular reference r.
Let alpha_r be a positive recorded source weight. Then:

```
T_g = sum_r(alpha_r * R_rg) / sum_r(alpha_r)   linear blended group VORP
w_default_g = T_g / sum_h(T_h)                default fraction of budget
w_requested_g >= 0; sum_g(w_requested_g) = 1  eight user-controlled fractions
S_sg = sum_i(U_si in group g)                 source group VORP
```

The group default reflects measured replacement surplus and roster demand.
There is no squared concentration premium, fixed positional split, or inferred
extra value for a larger VORP delta. A sharper distribution with the same total
receives the same default budget. The historical15% bench setting defines the
pinned leg/configuration provenance; it is not applied a second time as a hard
budget split after measuring raw U. Controls start with linear defaults and may
change all eight fractions. Store defaults, requested controls and effective
controls separately so future defaults can improve without overwriting a user's
saved settings. A reset must be explicit. Config or batch changes recompute the
constraint; they must not silently reuse another configuration's allocations.

Controls represent fractions (or weights normalized to fractions), not eight
fixed displayed dollar amounts. The70 anchor determines the eventual total.
The UI must label this relationship before presenting an absolute budget.

## Within-position inversion constraint: closed-form and visible

A positive source/group maps linearly with slope w_g/S_sg. With position total
P = w_requested_starter + w_requested_bench and bench fraction t, every starter
must be at least every bench player of that position, for every included source.
For each source s define:

```
a_s = minimum starter U / S_s,starter
b_s = maximum bench U / S_s,bench
c_s = a_s / (a_s + b_s)                       maximum feasible bench fraction
c_position = minimum_s(c_s)                  shared comparison-batch cap
t_requested = w_requested_bench / P
t_effective = min(t_requested, c_position)
w_effective_bench = P * t_effective
w_effective_starter = P - w_effective_bench
```

The inequality is (1-t)*a_s >= t*b_s, solved directly for t. No iteration,
optimization, clipping of individual players, or calculus is required. Preserve
the user's total for each position; shift only the infeasible within-position
bench fraction to starter. All sources use the same effective eight fractions.
Do not iron cross-position comparisons: a bench RB can still exceed a starter TE.

This is a **proposed visible constraint**, not permission for hidden budget edits:
show the requested and effective fractions, maximum allowed bench fraction and
limiting source. Prefer constraining the UI to the feasible range; reloading an
old setting or changing the batch must display any adjustment. Effective budgets
are the budgets that conserve exactly; requested budgets are not falsely reported
as satisfied. Arbitrary infeasible budgets, proportional group mapping, and
no cross-role inversion cannot all be guaranteed simultaneously.

Empty roles impose no comparison. A genuine-zero starter minimum with positive
bench VORP forces a zero bench budget. If both normalized boundary values are
zero, the inequality imposes no cap. Any newly funded starter group without
positive source VORP makes the complete source/batch unavailable, not repaired
with synthetic epsilons. Nonnegative slopes preserve within-group order and ties;
strict order is preserved only when its effective group budget is positive.

## Shared70 anchor, values and conservation

After the constraint, use one unit bookkeeping budget for each source:

```
q_si = w_effective_g * U_si / S_sg           provisional share per player
M = max(q_si across the whole included batch)
lambda = 70 / M                             one common scale multiplier
B = lambda                                 displayed total per complete source
B_g = lambda * w_effective_g                 effective displayed group budget
v_si = lambda * q_si                         displayed Adj value
```

A zero-budget/zero-total group maps genuine zeros to zero. A positive budget
requires positive complete source U. Reject missing/extra groups, null/negative/
nonfinite/nonnumeric values, boolean numbers, duplicate/unresolved keys, overflow,
all-zero references, empty batches, malformed weights and positive funded groups
without a positive pool. A missing source is explicitly unavailable; do not
redistribute its own budgets or fabricate partial complete output. A batch can
exclude it only through an explicit validated manifest and full recalculation.

Since sum(w_effective)=1, sum(B_g)=lambda. Since sum(U/S)=1 in each positive
group, sum(v in group)=B_g, and sum(v for each complete source)=lambda. The
inversion constraint preserves each position's provisional total, hence the total
budget. Positive group slopes preserve order; the common positive lambda preserves
the cross-role inequalities. All values lie in[0,70], and at least one source/player
reaches70. Display rounding is separate; retain full precision internally.

70 is the highest player value, **not** total budget. One scale cannot generally
fix an independently chosen displayed total as well as the maximum70. Never clip
individual values or normalize each source independently: those approaches break
shared group budgets. Freeze references, controls, manifest and lambda together;
recompute atomically on source/configuration changes. A new source can alter the
batch maximum and the feasible bench caps.

## Comparison with global linear rescale

For one reference equal to the sole source, linear defaults are w_g=S_g/sum(S).
If the source's roster split has no inversion, the cap is inactive and
q_i=U_i/sum(U); therefore v_i=70*U_i/max(U) exactly. Eight boxes introduce no
extra premium. A blended reference, deliberate user allocations, or an active
cross-role constraint changes group slopes, so source outputs can differ from
a global linear rescale while each group still maps linearly. These differences
must be explained by those recorded inputs, not a nonlinear player utility rule.

## Real pinned arithmetic example

Run `python3 docs/design/reweight_example.py > /tmp/jeg209-linear-example.json`.
The standalone standard-library script is outside production pipelines. It pins
three half-PPR12-team DDF snapshots, reconstructs raw VORP, uses equal reference
weights for illustration, and includes those same three sources in the batch:

| Reference | Vintage | SHA-256 |
| --- | --- | --- |
| ESPN | 2026-09-30 | af508f01700ebf5ee791aa932360b8da2b83b26b39d537144e7c04aa22162021 |
| CBS ROS | 2026-09-30 | afdf7a80a05655a1ba6f9845ba562dfd77b6e0846df79360b75c75b503ba6591 |
| Razzball | 2026-10-01 | a28babbf2a1d57fc26086ab69e1809b22f642f3c26c0ffb7142a50eb092856d0 |

Paths and full source/roster metadata are in `PINS` and the JSON manifest. This is
historical arithmetic, not a current seven-source production/promotion verdict.

| Group | Requested share | Effective share | Displayed budget |
| --- | ---: | ---: | ---: |
| QB/starter | 6.147712% | 6.251057% | 149.239251 |
| QB/bench | 1.547456% | 1.444112% | 34.477076 |
| RB/starter | 39.201081% | 39.850800% | 951.407690 |
| RB/bench | 7.971145% | 7.321426% | 174.793506 |
| WR/starter | 32.037408% | 33.025293% | 788.453877 |
| WR/bench | 6.198257% | 5.210372% | 124.393692 |
| TE/starter | 5.847936% | 5.847936% | 139.615036 |
| TE/bench | 1.049004% | 1.049004% | 25.044186 |

Total displayed budget per source =2387.424312657. CBS ROS Jahmyr Gibbs is70;
ESPN Gibbs=56.984028 and Razzball Gibbs=57.688530. ESPN Josh Allen=22.927082.
The common cap is active for QB (CBS ROS,18.766474% of that position), RB
(Razzball,15.520629%) and WR (CBS ROS,13.626995%); TE's requested15.209707%
remains below its15.954362% cap. This real example demonstrates that even linear
blended defaults can need a cross-role constraint. No cross-position correction
is applied.

## Runnable acceptance and continuation

```bash
python3 docs/design/reweight_example.py > /tmp/jeg209-linear-example.json
python3 -m py_compile docs/design/reweight_example.py
git diff --check
```

The companion checks exact-budget conservation for every included source,
within-group order/zero, within-position order, batch70, the one-source linear
identity, common unit conversion, and deliberately infeasible99% QB bench controls
with visible effective caps and conserved position total. Nine negative inputs
(null/bool/string/negative/NaN/infinity, missing/empty groups and duplicate key)
are rejected. It is a review artifact, not production API or coverage certification.
No rendered/F1 workflow changes apply to these two design files.

PR #41 is rebased onto main6086b1f. Initial squared arithmetic was independently
reviewed by Roman but superseded by Jeremy's decisions; it must not be reused as
approved methodology. Revised independent review and command results are recorded
in the PR/Linear handoff. Repository-wide validation currently has separate fixes
in PR #43/#44; design checks must not be conflated with a clean integration suite.

Next implementation handoff: use raw-unit inputs, resolve/version the existing
`total_vorp` artifact discrepancy, record blend weighting and horizon/coverage
policy, implement eight controls with visible feasible limits, apply all-source
batch70 once, and validate real granular and Option C publisher outputs. Indexed
remains native rescale; VORP remains upstream U; Adj is this output. Roman owns
integration and deployment. JEG-182 remains owned by its active lane.
