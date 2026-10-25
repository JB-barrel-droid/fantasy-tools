## 2026-10-23 - JEG-969 step 1: bench share readout diagnosis

Ticket: JEG-969 lane A. Branch: research/JEG-969-bench-share.

### Verified (check named)

- Python reference `value_reference.Setting(inp, 'ppr', 12).result()` reproduces
  page readout: QB 23.46%, RB 9.80%, WR 11.94%, TE 4.37%, overall 11.70%,
  applied 6.35%. All 12 combos measured (standard/half_ppr/ppr x 8/10/12/14).
- Page `bench_seats()` (value_reference.py:212, value-model.js:207) computes
  bench weights from **dedicated slots only** (no flex_filled), giving QB 15
  bench seats at ppr/12. The ES model's `alloc()` (expected_starts_model.py:140)
  calls `allocate_league` which passes `flex_filled`, giving QB only 4 bench
  seats.
- Bench seat allocation verified numerically: without flex_filled, D'Hondt on
  weights {QB 0.88, RB 1.66, WR 2.06, TE 0.40} = {QB 15, RB 28, WR 35, TE 6};
  with flex_filled {RB 3, WR 9}, weights {QB 0.88, RB 4.15, WR 11.33, TE 0.40}
  = {QB 4, RB 21, WR 57, TE 2}.

### Claimed (not confirmed)

- The JS engine matches the Python reference for the readout. (The audit
  writing.md says it does; I reproduced only the Python side.)

### Root cause

The QB bench share discrepancy (page 23.5% vs post 1 6.4%) is a methodology
disagreement in how bench seats are allocated. The page counts only dedicated
starter slots in bench weights; the ES model counts dedicated + flex starters.
Counting flex starters dramatically shifts bench seats from QB/TE to RB/WR
(where flex slots go), reducing QB bench seats from 15 to 4. With fewer bench
QBs, less value sits in the bench tier, so the bench share drops.

This is NOT the same artifact as the 22.6% recorded in qb-bench-share.md
(which was caused by Razzball misclassifying starter QBs). The 23.5% persists
after the Razzball fix because the bench seat allocation issue is independent.

### Math review item

Added MR-28 to docs/math-review-agenda.md: should bench weight count flex
starters?
