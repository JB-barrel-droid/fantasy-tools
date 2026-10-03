# JEG-241: conserving within-position inversion constraint

Jeremy approved linear allocation, a shared batch70 anchor and ironing out
within-position bench-over-starter inversions in JEG209. Cross-position inversions
remain allowed. The former player clamp loses budgets and changes bench ratios.
This slice constrains budgets once across the complete included source batch.

For position total P and requested bench fraction t, let each source have
`a = min(starter U)/sum(starter U)` and
`b = max(bench U)/sum(bench U)`. The ordering requirement is
`P*t*b <= P*(1-t)*a`, hence `t <= a/(a+b)`. Use the tightest
source cap, `t_eff = min(t_requested, min_source cap)`, then allocate
`bench = P*t_eff`, `starter = P-bench`. Each position total is conserved.
Within each resulting group, U proportions remain linear; the common70 scale
preserves ordering, group sums and ratios. No epsilon clipping or player rounding
is applied. Requested fractions/weights, effective fractions, source caps,
limiting sources and constrained flags are present in the candidate artifact.

Positive requested groups without positive source pools reject before constraints;
missing coverage is not repaired by shifting budget. A genuine zero starter at
the boundary forces bench budget0. If this creates a positive starter allocation
with an all-zero starter pool, output rejects. An absent role has no ordering
comparison; zero-position budgets remain0. The compatibility ironing helper is
now a diagnostic that rejects stale infeasible budgets and returns values unchanged.
The single-source adapter still requires effective shared budgets from its caller.

## Evidence

For starter U1/10 and bench U1/2, requested budgets20/10 become26.4/3.6,
with cap3/25. Provisional position total stays30; final values7/70/3.5/7
sum87.5 and preserve the bench ratio1/2. The old player clamp produced
23.632727 instead of30 and flattened the bench ratio. A second source uses the
same tightest cap and final group budgets. Feasible controls remain unchanged;
RB bench70 greater than TE starter17.5 remains allowed.

```bash
python3 -m unittest tests.test_reweight_inversion_budget tests.test_reweighted_batch_anchor tests.test_imputed_roster_config tests.test_imputed_vorps_precision tests.test_imputed_vorps_validation -v
git diff --check
```

31 tests pass:6 inversion,7 anchor,18 prior. The immutable historical ESPN/CBS ROS/
Razzball example uses raw PPG surplus and illustrative equal reference weights,
not an approved production weighting policy. Its shared final total matches the
revised design:2387.4243126568526, with conserved eight group sums and all
within-position boundaries ordered. Numerical comparisons allow floating-point
roundoff (relative1e-12); no presentation rounding enters computation.

Independent review and full composite validation are recorded below when complete.
This candidate slice is stacked on PR50. JEG243 still owns verified blend defaults;
JEG242 owns pipeline/view integration and production gates. No fixtures, canonical
coverage, source-vintage approval or production promotion is claimed. Roman owns
independent integration and deployment; JEG183 remains in review.

Read-only Claude Code MCP review independently ran13 inversion/anchor tests and
found no correctness defect. Codex checked the proof and reran31 combined tests.
The review's description of the zero boundary was imprecise: the passing case has
one zero starter and one positive starter, not absent starters. The failing case
has an all-zero starter pool. The test/code evidence above is authoritative.

`make validate` exits0 on the detached composite based on main5792ba5 plus
PR47–50/this change and pending PR43. Log: /private/tmp/jeg241-combined-validate.log.
This does not certify later main39a3f29 or production. No generated outputs are
included in this branch.
