# Roster convention audit (JEG-556)

Owner ticket: JEG-604. Source: the JEG-556 description (audit table, 2026-10-10) and its comments. Written 2026-10-12. Decisions: `roster-convention-001` and `default-roster-001` in [../decisions.md](../decisions.md).

Jeremy, 2026-10-10: "I don't want some corner case logic for QBs that should be applied in other places too, the transformations logic should be consistent." The audit (branch `jeg-521-expected-starts-spec` @ d889dbe) found no QB-specific logic. The problem was general: the same step implemented differently in different places, several of them live. The 22.6% QB bench share was one symptom ([qb-bench-share.md](qb-bench-share.md)).

## What was inconsistent (audit table, before JEG-559)

| Step | Rules in use |
|---|---|
| Bench seats per position | (1) `floor(BENCH_MIX_12 x teams/12 + 0.5)`, ignoring the user's bench setting: two-tier legs and the ESPN, CBS rest of season and Razzball curves. (2) D'Hondt on `BENCH_MIX_12` with the user's bench: published-chart translation. (3) Open across positions by surplus: raw value-above-waivers curves (`projectionRoles`). (4) Open by value: DDF tier and anchor budgets (`roleMap`). |
| Seat totals at 6 bench | Rule 1: 54/67/80/95 at 8/10/12/14 teams. Rules 2 to 4: 48/60/72/84. |
| List the tiers are ranked on | Each source's own list; the blended DDF value; ESPN cut-offs applied to every series (v2 Tier column); the consensus projection mean (expected-starts analysis, the cause of the QB artifact). |
| Starter line | Midpoint of last starter and first non-starter (two-tier legs); first non-starter (expected starts); last starter with `>=` (`score_lineup_values`). |
| Waiver line on a short list | Imputed from other charts (translation); 0.0 (two-tier); last listed value (raw curves, expected starts). |
| Flex | Greedy by value (most paths); D'Hondt weighted by VORP (translation); fixed RB/WR split with TE excluded (`derive_lineup_parameters`). |
| Roster shape / superflex | The anchor two-tier path always used the reference roster, rescaled afterwards; other live paths followed the user's roster. |

Mismatch example: at 12 teams, two-tier rosters 176 against `roleMap` rosters 168, so about 8 players the anchor priced as bench counted as waiver in the Adjusted budgets.

Retired code that still defined its own rules at audit time: `curve-widget.js benchMixFor`, `twotier_reference.py:297`, `build_imputed_vorps.infer_roster`, `translate_phase_b.py`, `translate_via_ddf.py`. (Part of these were deleted by JEG-539, PR 514 and 532; check the code before relying on this list.)

## The convention (decisions as of 2026-10-12)

1. **Bench seats:** market bench. Bench weight = starters x backups per starter (QB 0.86, RB 0.85, WR 1.05, TE 0.39; K 0.00, DEF 0.06, from `config/market_bench.json`), D'Hondt over the user's teams x bench. The fundamental bench never sets seats ([bench-rule-research.md](bench-rule-research.md)).
2. **Tier basis:** rank within each position on the list being valued. A source is tiered on its own list; blended DDF on the blended value.
3. **Waiver line:** the first player not rostered. On a short list, **estimate from other charts** (Jeremy, 2026-10-12).
4. **Starter line:** **midpoint of the last starter and the first non-starter** (Jeremy, 2026-10-12).
5. **Flex:** greedy by score on the list being valued (points for projections, value for charts).
6. **Roster shape:** every path uses the user's roster, including superflex. K and DEF are in the roster model with no value legs and 0 bench backups for K.
7. **One guard:** a parity test that fails when two paths disagree. JEG-559 (PR 546) shipped it; it pins four divergences as expected failures (bench seats on VP and two-tier, starter line, waiver line on short lists) that go green as JEG-560, 561 and 563 land.

## Status 2026-10-12

JEG-559 landed. JEG-560 (live value paths), JEG-561 (baked legs, week history, DDF groups) and JEG-563 (default roster switch) are not done. Until they are, the live site still contains the divergent rules in the audit table.
