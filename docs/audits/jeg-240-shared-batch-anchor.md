# JEG-240: one full-precision all-source70 anchor

The old producer calls70/max separately per source. Equal provisional source
budgets20 withA10/10 andB18/2 become totals140 versus77.8, both maxima70. This
violates the approved shared comparison scale.

`build_batch_three_views` normalizes explicit eight nonnegative allocation weights
to fractions totaling1, prepares every included source, finds one global maximum
M, then uses lambda=70/M for every source. No per-player rounding or clipping
enters the anchor. Effective group budgets are lambda*share; each complete source
has total lambda. In the sampleA is38.8888889/38.8888889 andB is70/7.7777778:
both total77.7777778. The single-source adapter/helper now requires the caller's
batch maximum; it cannot silently derive a local scale.

Malformed/nonfinite/negative/zero-batch inputs and positive funded groups without
positive complete pools reject. Cut rows remain0 and native values remain unchanged.
The old inversion clamp still exists pending JEG241, but if it changes any player,
the batch refuses output rather than lose budget. JEG241 adds the conserving
visible constraint; JEG243 supplies verified blend defaults. This candidate CLI
requires **all eight explicit control weights** and does not invoke the legacy
calibration/default reader. Existing calibration-as-blend is not approved here.

## Explicit source batch input

Call `build_reweighted_values.py --batch batch.json --controls controls.json
--out candidate.json`. Batch schema:

```json
{
  "schema": "vorp-source-batch-v1",
  "configuration": {
    "schema":"option-c-publisher-roster-v1","teams":12,"scoring":"half_ppr",
    "slots":{"QB":1,"RB":2,"WR":3,"TE":1},"flex_count":1,
    "flex_eligible":["RB","WR","TE"],"bench_total":72
  },
  "sources": {
    "fantasycalc":{"values":"fc.json","manifest":"fc.json.manifest.json"}
  },
  "excluded_sources": {
    "usat":"unavailable input","fantasypros":"unavailable input","cbs":"unavailable input",
    "espn":"granular adapter pending","cbsros":"granular adapter pending","razzball":"granular adapter pending"
  }
}
```

Every source is included or excluded with an explicit reason. Paths are relative
to the batch JSON. Published sources require JEG239's Option C manifest/method;
granular sources require `granular-vorp-manifest-v1`, method
`ppg-above-waiver-v1`, matching `source_config` with schema
`granular-roster-config-v1`, teams/scoring/slots/flex/eligibility and explicit
bench_mix. Their Indexed map is unavailable/empty; raw PPG is never invented as
published chart price. Granular adapter production wiring remains JEG242.

Artifact/sidecar output hash, source method/config and native/U validity are checked
before output. Each source's hashes/metadata plus the batch/config/exclusions and
controls hash are recorded. These are integrity checks, not source authenticity,
canonical coverage, current vintage or approval evidence. Output remains explicitly
candidate. Controls JSON has exactly QB/starter,QB/bench,RB/starter,RB/bench,
WR/starter,WR/bench,TE/starter,TE/bench; nonnegative numeric weights are normalized.
No guessed reference weighting/time-horizon policy is selected.

## Runnable evidence

```bash
python3 -m unittest tests.test_reweighted_batch_anchor tests.test_imputed_roster_config tests.test_imputed_vorps_precision tests.test_imputed_vorps_validation -v
git diff --check
```

25 tests pass (7anchor+18prior). Checks include shared peak/group and total budgets,
full precision, unit conversions, required/stale common peak, invalid/missing/funded
zero pools, refused legacy clamp, a mixed publisher/granular CLI candidate with
explicit exclusions, and hash/config/undeclared-source failures preserving sentinel
output. The original49 producer reproduces140/77.8 unequal totals; new outputs
match77.7777778. Synthetic examples/IDs do not certify real source coverage.
Makefile includes the new anchor module.

Independent review/full composite results follow in PR/Linear. Stacked on PR49
(48→47); main's separate guard fix is PR43. No fixture, UI, promotion or production
ready claim. Roman independently reviews/integrates/deploys. JEG183 remains open;
JEG241–243 complete inversion/default/integration contracts.
