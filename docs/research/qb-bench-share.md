# QB bench share: the 22.6% artifact (JEG-546)

Owner ticket: JEG-604. Source: the JEG-544 comments of 2026-10-10 (back-end answer) and 2026-10-12 (re-run after the Razzball hold). Written 2026-10-12.

**Do not quote 22.6% or any QB bench-share number.** The 22.6% is a data artifact and is superseded. The 2026-10-12 re-run (14.6% at 12 teams) is a simulated bake that has not been confirmed on the published JSON (JEG-593 owns that confirmation) and does not yet use the tier-basis fix (JEG-562).

## Finding (2026-10-10)

Two starting quarterbacks, Lamar Jackson and Patrick Mahomes, were counted as bench because one projection source (Razzball) had them far too low: Razzball 7.1 and 10.5 points per game (ranks 32 and 28) against ESPN 21.39 and 20.05 and CBS rest of season 23.02 and 20.75. Averaging Razzball in dragged both below the QB12 line (17.2 and 17.1 against 18.6) while the charts still valued them as starters, so their full starter value counted as bench value (Lamar 9.6% of all QB value, Mahomes 5.9%). Those two players are about 15.5 of the 22.3 points. Without them the bench tier holds about 6.8%, in line with WR (7.5%) and RB (8.3%).

Definition used (`value_reference.bench_share_readout`): order players by mean projected points per game over the included sources; the bench tier is indices `[S_p, N_p)` of that order (QB: S=12, N=21); share = blended DDF value of the bench tier over all players of the position. The tier is chosen by projections but its value includes the charts' values; that mismatch is the defect. No code bug was found in the readout; the defect is the tier basis combined with the Razzball input error.

Hypotheses checked: few QB starters (denominator only); start-worthy term (real but secondary, the line is league-wide, not the backup's own starter; not sized); flex or superflex leak (none); byes (same 7.8% for all positions, fine).

## What fixed it

- **JEG-555 / JEG-593:** the Razzball missed-games guard holds a rate below 60% of the ESPN and CBS mean; see `docs/risk-register.md` GAP-RZ-MISSED-GAMES-DISCOUNT. JEG-611 applied the same rule in the chain.
- **JEG-562:** tiers move onto the roster convention ([roster-convention-audit.md](roster-convention-audit.md)); not done.

## Re-run after the Razzball hold (2026-10-12, simulated bake, JEG-593)

QB at 12 teams 22.7% to 14.6%; at 14 teams 20.5% to 9.4%; at 8 and 10 teams QB rises 13 to 18 and 11 to 17 (two players no longer fall into the waiver tier). Overall stays 7.8 to 10.0% in every setting.

## Script

None committed: the decomposition ran as scratchpad scripts (`qb_decomp.py`, `qb_show.py`). JEG-566 commits the bench scripts to `tools/bench_research`; add the name here then. A suggested guard from the finding: flag a player whose rank in one projection is more than about 20 places from the median of the others (both cases tripped it). The Razzball hold implements the equivalent rule on rate.
