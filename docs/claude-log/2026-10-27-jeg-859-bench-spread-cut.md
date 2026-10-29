## 2026-10-27 - JEG-859 bench spread across sources: role cut vs budget cut

Contract: answer JEG-859 (bench totals differ about 62% across sources while starters agree) on current main, with root cause, numbers and a reproducible check. No value change.

### Verified (check named)
- `python3 tools/research/bench_spread_by_cut.py` (built page at main 43917129 plus a CSS-only branch, data week 7, Full PPR, 12 teams, pie 2352, expected-starts): summed by the engine's own budget cut (rate x benchSlice, rate x starterSlice; `value-model.js` VP-5, around L1279-L1320), every source has the same bench total per position (QB 8.0, RB 108.7, WR 52.2, TE 8.6; all 177.6) and the same starter total (2174.4). Spread 0.0%. The script exits 1 if this ever breaks.
- Same run, summed by the Health check tab's cut (`role`, `value-model.js` L1154: rank above the starter line is "starter", up to the rostered line is "bench"; summed in `app/v2/audit-pie.js` L194-L201): bench totals run from 128.6 (CBS) to 290.1 (CBS rest of season), spread 81.0% (QB 108%, RB 51%, WR 116%, TE 163%); starters 7.5%.
- Seat counts are identical for every source (QB 12/20, RB 27/60, WR 33/66, TE 12/22), and filled-in (estimated) rows carry almost nothing (CBS RB bench 4.8, everything else 0), read from `tools/audit_health_dump.py --weeks 7 --teams 12 --scorings ppr`.

### Claimed, not confirmed
- The role-cut gap is source shape: projection sources (ESPN, CBS rest of season, Razzball) keep more of a position's value on ranks just below the starter line than trade charts do. Inferred from the per-source sums above, not from a per-player trace.
- Measured on week 7 only (the latest saved week in this build); other settings were not run.
