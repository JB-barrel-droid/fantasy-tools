## 2026-10-09 - JEG-508 spec reference conformed to the lead's spec rulings (PR #484)

Contract: update `pipelines/spec_reference/` (branch `jeg508-specref`) to the
rulings in PR #484 (methodology.md VP-0 "Sources and natives", VP-6.4, "Spec
rulings (lead, 2026-10-09)"). Read only that spec text (clean-room rule).

### Verified (check named)
- Projection natives now come from players.json `espn_ppg` / `cbsros_ppg` /
  `rz_ppg` at full precision. ESPN-ineligible players are listed at 0 (ESPN
  ppr: 567 listed, 212 at 0). Before this change, 325 ESPN natives differed
  from the rounded section copies, e.g. 11.69 vs 11.688333.
- The superflex overlay now adds players only it lists. At PPR 12 the CBS list
  goes from 117 to 139 players with SF1; FantasyCalc gains 1.
- A null Indexed factor now nulls the whole chart, below-depth players
  included.
- `tests/test_spec_reference_value_pipeline.py` has 16 tests, 2 of them new
  for the rulings. Run against the previous commit's package (copied into a
  scratch tree), both new guards fail: the live-natives test errors and the
  null-factor test fails. On the branch all 16 pass, and the worked example
  still matches 4,455 leaves at 1e-6 with 0 mismatches.
- `python3.12 pipelines/spec_reference/compare.py pipeline` was rerun.
  - PPR 12 line: `ppr/12/sf0 pie 2688 I=espn,cbsros,razzball,cbs,fantasycalc,fantasypros,usatoday rows 737 DDF numeric 737 zero 520 estimates 84 prior yes`.
  - Changes from the first run: PPR 10 has 40 estimates (was 38) and PPR 12 SF1 has 80 (was 101). Every other summary line is unchanged.

### Claimed, not confirmed
- New readings SA-17 (an Indexed factor of 0 when every shared player's DDF
  is 0) and SA-18 (the prior-week ESPN snapshot lacks the ineligible zeros)
  are literal readings; the lead has not ruled on them.
