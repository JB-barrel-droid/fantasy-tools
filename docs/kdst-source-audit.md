# Kicker and defense (K/DST) values on the trade value chart: source audit and recommendation

JEG-19, diagnosis only. Nothing was implemented. Evidence gathered 2026-10-01 from the checked-in fixtures and inputs.

## Source audit

"Verified" means checked this session against the file named. "From the issue" means carried over from the JEG-19 description and not re-checked.

| Source | K/DST data available? | Freshness | Notes | Status |
| --- | --- | --- | --- | --- |
| ESPN projections | Yes: 45 K, 32 DST in `players.json` (`pricing: espn_only`, all 77) | Input files `espn_k_ppg_2026-09-21.json` and `espn_dst_ros_2026-09-21.json`, `as_of` 2026-09-21 (10 days old). `meta.kdst_snapshot` is `"?"`, but `data/inputs/espn_pies.json` records both pull dates as 2026-09-21 | The only source with K/DST numbers. K ROS = per-game rate x 16, DST ROS = per-game rate x 15; one scoring-invariant number | Verified |
| Comparison sources (USA Today, FantasyCalc, FantasyPros, CBS, CBS ROS, Razzball and their adjusted variants) | No: 0 K/DST rows across all 11 sections of `comparison-sources-data.json` | n/a | No peer to compare or anchor against | Verified |
| Razzball projections | No: `razzball_projections.csv` is QB 77 / RB 127 / WR 188 / TE 121 | n/a | | Verified |
| Prediction markets | No: `prediction_markets_season.csv` is QB 26 / RB 33 / WR 51 / TE 15 | n/a | | Verified |
| FantasyPros ECR | The site publishes K/DST; our daily job pulls only QB/RB/WR/TE. Supabase holds `fp_season_kdst_projections` | ECR is stale chart-wide | ECR-based and hard-excluded from the trade-value pipeline per `docs/supabase-source-mapping.md` | From the issue |

## What the data says about pricing

- The roster config and the two-tier math cover QB/RB/WR/TE only: `config/roster.json` `positions` and `REF_SLOTS` in `build_ddf_two_tier_leg.py` have no K or DST.
- ESPN's measured pies already include K and DST (`espn_pies.json`, 12 teams: K 6.56, DST 8.57, against QB 58.99, RB 393.59, WR 290.04, TE 45.93 at half PPR). K plus DST is 1.7-2.0% of the total pie in all three scorings.
- The spread is small. Half PPR ROS points: kickers top 142.4, median 111.7, 13th 123.6 (12-team replacement); defenses top 84.2, median 59.1, 13th 67.0. Top-over-replacement is 1.15x for kickers and 1.26x for defenses, so a value-above-waivers curve for them is almost flat.
- K/DST have one scoring-invariant number, so the standard/half/full views would be identical.

## Options

1. **Honest exclusion (smallest).** Keep K/DST off the curves. Replace the silent grey-out with a plain explanation next to the existing `Include K/DST` toggle (default off), and show the real ESPN pull date.
2. **ESPN-only, own pie, separate scale.** A K/DST leg built with the same two-tier math but its own slots (K 1, DST 1), its own pie, drawn as a single "ESPN projections only" line outside the skill-position fixed-pie indexation. No adjusted view (no peers to fit against).
3. **Join the skill pie.** Not recommended: K/DST would take 2% of a pie they cannot be calibrated against and would move every skill value.
4. **Modeled values.** Not recommended: invents data.

## Recommendation

Do option 1 now and option 2 only if you want K/DST curves, in that order. Reasons: the value at stake is about 2% of the pie and nearly flat; there is no second source, so any "adjusted" or "agreement" view is meaningless; and the ESPN pull is 10 days old.

If option 2 is approved, what it takes (not started):

- A separate leg builder (`build_kdst_leg.py`) reusing the two-tier functions with its own slots. Do **not** add K/DST to `config/roster.json` `positions`: that list drives the skill pies, the guards and the fixtures.
- A separate fixture section and a widget series on its own axis, shown only behind the toggle, with coverage text.
- Its own guards: the pie sums to its measured total, a real pull date is present and fresh, and K/DST are excluded from `fixedPieIndexed` and `sourceScaleAgreement`.
- A fresh ESPN K/DST pull. That needs the data pull on the owner's machine; Claude cannot do it from here.

## Decisions needed

1. Is a K/DST curve worth building at about 2% of the pie, or is the honest explanation enough?
2. Is a fresh ESPN K/DST pull (and recording its date in `meta.kdst_snapshot`) acceptable before anything is surfaced?
3. Should FantasyPros K/DST ECR ever be used, given it is ECR and hard-excluded today? (Out of scope here.)
