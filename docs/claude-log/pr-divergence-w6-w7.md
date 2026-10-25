## 2026-10-24 - Source divergence weeks 6 and 7: seven resolutions recorded (laptop-2)

Tickets: JEG-788, JEG-789, JEG-790, JEG-794, JEG-795, JEG-796, JEG-830
(resolved here) and JEG-797 (closed without a resolution). Parent JEG-460.

### Findings

- **FantasyCalc w7, FantasyPros w6/w7 (trade charts):** outlier rates of
  43-48% are inside each chart's own range for weeks 3-6 and close to its
  trailing baseline, with bias near 0. Indexed is one factor per combo
  (min = max factor over all players). FantasyPros publishes one
  scoring-agnostic Value column reused for all three scorings, which is why
  standard is its worst combo.
- **ESPN and CBS ROS w6/w7 (projections):** compared native per-game
  projections source against source for weeks 5-7. The disagreement is
  stable and identical in every scoring: CBS ROS QB +17 to +19% and RB
  -12 to -20%; Razzball QB -19 to -23%; ESPN RB +7 to +9%. Reception
  scoring matches across the three sources (half-PPR share 0.50, same
  full-minus-standard gap), so no scoring path is broken. Razzball's live
  QB page (updated 2026-10-23) matches the fixture: Josh Allen 20.3 STD
  PPG, and his stat line rescores to 223.1 against 223.2 published. With
  three sources the leave-one-out consensus is the mean of two, so one
  low line moves the other sources' rates. All are 1-3 points over the
  45% fixed ceiling, and projection sources have no baseline (JEG-952).
- **Razzball w7 (JEG-797):** computes `ok` on the current fixture (built
  2026-10-23); the TE flag from 2026-10-22 no longer reproduces. No
  resolution recorded, so a new break later in the week would still show.

### Verified (named checks)
- `pipelines/check_source_divergence.py` on the current fixture: overall
  `ok`; FantasyCalc, FantasyPros, ESPN and CBS ROS `reviewed` (computed
  status kept); no resolution problems.
- Simulated broken entries (empty note, unknown kind) are still reported
  by `load_resolutions` and dropped.
- `tests.test_source_divergence`, `tests.test_open_divergence_issues`,
  `tests.test_v2_divergence_chip_render` (run one at a time): OK.

### Assumed, not verified
- FantasyCalc's API and the FantasyPros article were not re-fetched live;
  their dates come from the fixture.
