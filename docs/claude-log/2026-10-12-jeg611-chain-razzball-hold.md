## 2026-10-12 - JEG-611 chain's Razzball section holds the missed-games rates

Contract: apply the JEG-555 hold to the chain's Razzball section so the main table and the chart drop the same players. Checked first: main has no other change to the leg (JEG-591/592/593 and PR 530 touch the bake-level guard, readouts and fidelity_hold.py, not `build_razzball_ddf_leg.py`), so not a duplicate.

### Verified (check named)
- `build_razzball_ddf_leg.py` drops a row when `bake_players.razzball_outlier_reason` holds it against the ESPN/CBS rates in players.json; held players go to `review_rows` as `rz_held`: `tests/test_razzball_chain_hold.py`.
- The guard catches the bug: with `hold_reason` forced to None, 2 of 3 tests fail (run ad hoc).
- `tests/test_suffix_identity.py` identity test now gives the Razzball loader no references (flat 10 ppg would hold Kenneth Walker against his real references); assertions unchanged.

### Claimed, not confirmed
- Effect on the live section waits for the next rebuild-chain Razzball run; fixture sections were not regenerated here. The chart (players.json) is unchanged, so no engine sweep.
