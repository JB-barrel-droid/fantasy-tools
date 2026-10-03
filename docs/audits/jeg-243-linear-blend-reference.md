# JEG-243: explicit pinned raw linear blend defaults

The former defaults reader accepts a single DDF leg and consumes calibrated
starter_raw/bench_raw fields. It cannot prove raw linear economics or an approved
blend policy. `load_group_budgets` now requires a versioned reference manifest;
it never substitutes legacy calibration or a single-source fallback.

`linear-blend-reference-v1` has exact top-level fields: schema, method
`ppg-above-waiver-v1`, units `raw_surplus_ppg`, configuration, policy, sources,
excluded_sources. Configuration is exact `granular-roster-config-v1` with teams,
scoring, slots, flex_count, flex_eligible and four-position bench_mix. All included
legs must match this entire shape. Batch matching checks common shape/scoring;
publisher bench_total72 remains separate from reference granular bench_mix80.

At least two of ESPN/CBS ROS/Razzball are included; remaining sources have explicit
exclusion reasons. Each entry has leg path, SHA256, positive numeric weight,
content_date and horizon. Content date matches the source's snapshot_date input;
hash pins exact bytes. Weights are normalized explicitly. Every canonical numeric
key format is unique; all rows have valid position/tier/finite nonnegative PPG and
finite nonnegative waiver threshold. Every eight-group raw pool is present.
Compute each group as sum(max(0,PPG-waiver)); average with declared weights.
Ignore leg value/raw_value/starter_raw/bench_raw/calibrated scale entirely.
This validates key format/uniqueness, not membership or coverage certification.

Policy has status candidate/reviewed, decision_url (null for candidate, HTTPS
record for reviewed), and explicit nonempty horizon matching source declarations.
The loader preserves the declaration; it does NOT authenticate a URL, approve
weights, establish source-horizon equivalence or freshness, or grant promotion.
Every output remains candidate. Real source methodology notes require independent
review before a policy is used in production. Exact weighting/horizon policy
remains unapproved; the tests'2:1:1 weights are illustrative arithmetic only.

CLI chooses exactly one of `--controls` (complete eight explicit user weights) or
`--reference` (defaults contract), with `--batch` and `--out`. Reference provenance
contains manifest hash, each leg hash/date/horizon, raw source group sums,
normalized weights, raw blend budgets, shape and policy. Existing all-source70
anchor and conserving inversion constraints expose requested/effective allocation.
No output write occurs until source/reference/math validations finish.

## Reproduction and verification

```bash
python3 -m unittest tests.test_reweight_reference_contract tests.test_reweight_inversion_budget tests.test_reweighted_batch_anchor -v
git diff --check
```

17 tests pass:4 reference+13 prior. The reference tests pin the same three historic
leg hashes as JEG241. Independent row arithmetic validates the2:1:1 raw blend and
discriminates calibrated QB starter totals. Single leg/source, legacy units,
scoring/bench-shape/date/horizon/hash/weight errors and missing review evidence
reject. Mixed source batch CLI emits candidate defaults with complete provenance;
mismatched scoring preserves preexisting sentinel output. Required Makefile gate
runs the new module. No policy/default manifest or generated fixture is installed.

Stacked on PR51. Roman owns independent integration/deployment. JEG242 still owns
refresh/view wiring and approved Sheet/canonical/vintage/promotion gates; parent
JEG183 remains in review. This slice fixes admission and arithmetic contracts,
without treating illustrative policy inputs as an approved production decision.
