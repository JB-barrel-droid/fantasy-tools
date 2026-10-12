# Bench rule research (market bench versus fundamental bench)

Owner ticket: JEG-604. Sources: the JEG-556 comment thread (2026-10-10) and the Linear document "Thread handoff 2026-10-10: bench research and roster convention". Written 2026-10-12. The decision it fed is `roster-convention-001` in [../decisions.md](../decisions.md); the convention module is JEG-559 (PR 546).

## How to read the numbers here

- **Draft-data facts** (backups per starter, shares by season) come from Fantasy Football Calculator draft tables and do not depend on our projection pipeline. They are frozen in `config/market_bench.json` and reproducible with `python3 pipelines/derive_market_bench.py --derive` (inputs in `data/inputs/market_bench/`). The frozen values are authoritative; a re-derive differs by at most 0.02.
- **Value-effect tables** (how many bench seats each position gets, which players move, pie shares) were computed on 2026-10-10 on the engine of that day, before PR 499 and the Razzball hold (JEG-555/593). They show direction and size, not today's numbers. They are marked "stale, re-run after JEG-562/563" where used.
- **Scripts:** the analysis scripts are not committed yet (JEG-566 puts them in `tools/bench_research`). Until then the method column below is the record. A claim marked "script: none yet" cannot be reproduced from the repo.

## 1. What leagues hold: backups per starter

Fantasy Football Calculator 12-team PPR drafts, 8,857 drafts, 2016 to 2024 (2022 excluded for a truncated list). Script: `pipelines/derive_market_bench.py`.

| Season | Drafts | QB | RB | WR | TE |
|---|---|---|---|---|---|
| 2016 | 956 | 14.7% | 35.0% | 39.9% | 10.4% |
| 2018 | 2,494 | 14.9% | 35.7% | 38.7% | 10.7% |
| 2020 | 2,403 | 13.8% | 37.4% | 37.9% | 10.9% |
| 2022 | 1,633 | 13.7% | 36.3% | 39.7% | 10.3% |
| 2024 | 1,371 | 14.6% | 33.7% | 40.4% | 11.2% |
| Mean | 8,857 | 14.3% | 35.6% | 39.3% | 10.7% |

Share of skill-position picks; each position moves about 1 point across nine seasons. Converted at 13 skill players per team and 1/2/2/1/FLEX starters: rostered per team QB 1.86, RB 4.63, WR 5.11, TE 1.39; **backups per starter QB 0.86, RB 0.85, WR 1.05, TE 0.39**.

With kickers and defenses (15-round drafts): K rostered 1.00 per team and DEF 1.06, so backups per starter K 0.00 and DEF 0.06. Leagues stream both. Skill ratios barely move with K/DEF in (QB 0.88, RB 0.83, WR 1.03, TE 0.40).

Caveats: mock drafts (draft-day rosters, not in-season); only 12-team archives exist (10 and 14 team pages fell back to 12-team data); the 2025 page did not render; the source's lineup settings are not published (1/2/2/1/FLEX assumed). Draft data cannot show in-season streaming, so the QB ratio is an upper bound for 1-QB leagues.

## 2. Rules tested for bench seats (scorecard)

Fit is backups per team against observed draft rosters (observed QB 0.86, RB 2.13, WR 2.61, TE 0.39). Out-of-sample: fit on 2016 to 2020, predict 2022 to 2024. Stability: all 12 settings on the default roster. Zero rank inversions for every rule in every setting. Stale (2026-10-10 engine); script: none yet.

| Rule | Error vs observed | Held-out error | RB+WR share | Min rank corr vs fixed | Adapts to user roster |
|---|---|---|---|---|---|
| A. Fixed 10:27:33:10 mix | 0.18 | 0.18 | 75 to 77% | 1.000 | no |
| B. Lineup holes | 0.36 | 0.40 | 74 to 77% | 0.993 | yes |
| **C1. Draft ratio per starter (chosen)** | **0.06** | **0.10** | 82 to 83% | 0.986 | **yes** |
| C2. Draft ratio per team | 0.05 | 0.06 | 79 to 81% | 0.989 | no |
| C3. C1 with QB halved | 0.22 | 0.21 | 88 to 89% | 0.984 | yes |

Chosen rule C1: bench weight for a position is its starters (the user's roster, flex counted where it lands) times backups per starter; D'Hondt over the user's teams times bench. It changes mostly TE: TE starters lose about 2.5 to 5.5 points of value because the waiver line moves up when only about 0.4 backup TEs per team are held.

Rules rejected, and why (all unstable, circular or cliffed): open by points over the starter line (fills benches with QBs and TEs, starves RBs); open by chart value (QB bench spots 5, 4, 10, 14 as teams go 8 to 14); lineup holes times drop-off (WR share 9%, 19%, 13% across league sizes); starts by depth round (chunky, standard/8 gets zero TE bench spots); insurance plus upside points (TE bench 0, 6, 13, 13 across 8 to 14 teams); net-of-waivers value (weekly noise dominates; rank correlation down to 0.89); measured streaming coverage from history (circular).

## 3. What a bench spot is worth (fundamental bench)

2015 to 2025 nflverse actuals (`data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz`); lineups set each week on season-to-date points per game among players who play; non-starters compared with the best player who would be on waivers. Stale for the exact figures; script: none yet (JEG-566).

- Share of starting slots filled by non-starters (ppr/12): QB 45%, RB 39%, WR 36%, TE 48%.
- Starts per week per held player by depth round (ppr/12): first backup QB 0.28, RB 0.30, WR 0.33, TE 0.21; second backup QB 0.07, RB 0.17, WR 0.22, TE 0.08; third QB 0.00, RB 0.09, WR 0.14, TE 0.04.
- Net of the waiver alternative, points per week per held player: first backup QB +0.19, RB +0.37, WR +0.54, TE +0.09; second backup QB -0.01, RB +0.14, WR +0.25, TE +0.02.
- Findings for the research series: (1) net of waivers a bench spot is worth very little (0 to 0.5 points a week); (2) QB and TE upside is fully available on the waiver wire, RB and WR upside is not; (3) second QB or TE backups are worth about zero.
- Pooled ladder per team: RB1 +0.40 > WR1 +0.20 ~ WR2 +0.17 ~ QB1 +0.17 > RB2 +0.15 > TE1 +0.09.

This ladder is the **fundamental** bench. It lives in its own module (JEG-564, not built) and never sets tiers or lines.

## 4. What the field does (open-web scan, 2026-10-10)

PlayerProfiler Value Over Stream (replacement at QB19/TE19 and RB49/WR49 in 12-team leagues); Subvertadown (no value in holding a QB past QB12 to QB16 in 1-QB leagues); Fantasy Football Analytics baselines (worst starter, man-games, pick 100); HSAC weekly replacement level; Footballguys per-game VBD; Football Perspective (TE18 average backup); RotoWire 35,000 leagues (12 teams 51%, PPR 48%, most common roster 1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX + K + DEF, 7 bench). RotoWire is the source of the default roster decision `default-roster-001`. Links were in the ticket comments and were not re-verified for this page.

## 5. Open items

- Re-run the value-effect tables on the live engine after JEG-562 (expected starts on the convention) and JEG-563 (new default roster).
- Commit the scripts to `tools/bench_research` (JEG-566) and add the script name beside each claim above.
- Superflex and 2-QB extrapolate the 1-QB ratio; if in-season roster data shows fewer QB backups it is a one-number change in `config/market_bench.json`.
