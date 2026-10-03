# JEG-233: DDF group unit provenance

`compute_groups` historically sums calibrated leg `value` and exports it as
`total_vorp`. That is a chart-value quantity, not raw PPG-minus-waiver VORP.
On pinned ESPN2026-09-30 half-PPR12-team data, the legacy total is2364.1097;
raw starter/bench surplus is739.99125 PPG. Mixing these definitions in JEG-209's
linear blended reference would implicitly preserve legacy calibrated economics.

This additive change keeps existing schema and all legacy numeric fields. It
adds `raw_surplus_contract: ddf-raw-surplus-ppg-v1`, `raw_surplus_ppg` per group,
and raw total/group sum. Raw fields retain full precision; existing fields keep
their original four-place rounding. Machine-readable `units` and `derivation`
identify the distinction. `source_inputs`, `source_generated_at`, and position
waiver PPG travel with the result; the file writer hashes the exact bytes it
parsed as `input_leg_sha256`. No source freshness or reviewed-coverage verdict
is inferred from those fields.

Raw definition: sum(max(0, row.ppg-calibration[position].rw)) for starter/bench
rows. Flex retains upstream starter classification. Waiver rows do not enter the
eight raw groups. Missing projections/replacements, booleans, numeric strings and
nonfinite values fail closed. Genuine zero remains zero. Legacy chart values also
reject booleans/infinity rather than emitting invalid JSON. Existing valid full
DDF legs carry these fields; incomplete old synthetic inputs must now provide
explicit calibration rather than receive a guessed zero waiver. No epsilon,
source/configuration fallback, fixture or allocation change is introduced.

Compatibility: JEG-180/182/207's existing `total_vorp` consumers keep their
approved numeric semantics. They must explicitly migrate to a raw-unit version
when implementation review chooses that contract. The new metadata does not
silently make their current translated values raw PPG. The approved206 group
totals/Google Sheet remain a legacy reference until that migration is reviewed.

Runnable validation:

```bash
python3 -m unittest tests.test_ddf_groups tests.test_lineage_group_vorp_loader
python3 pipelines/build_ddf_groups.py --leg data/ddf-two-tier/ddf-20260930-espn-half_ppr-12t-0p15/ddf_leg.json --out /tmp/jeg233-group-units.json
git diff --check
```

Initial31 tests pass. Synthetic rows distinguish legacy80 from raw20 and confirm
tripling chart values changes only legacy totals. A negative in-memory mutation
substituting the legacy total into the raw field fails that discriminator.
Missing/bool/string/NaN/infinite inputs reject; zero/waiver handling and the real
raw totals are checked independently. The unchanged lineage loader passes.
No rendered behavior changes; no F1 harness applies. Independent review and full
integration-suite evidence follow in PR/Linear. Main's known Indexed guard issue
requires PR43 for a clean full-suite run; no production QA or merge is claimed.

Next: Roman reviews this additive contract alongside JEG-182's active lane.
Raw blend consumers require both the contract identifier and explicit raw field;
never infer units from `total_vorp` naming. Reference weighting/horizon alignment,
canonical coverage, translated-value migration and production promotion are
separate implementation gates.
