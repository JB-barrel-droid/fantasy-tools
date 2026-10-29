# JEG-1171: CBS rest-of-season week-8 divergence warn

Read-only diagnosis. No parser, reporter, resolutions file, live data or
source-feed branch was changed. Evidence checked 2026-10-29 against `main` at
`b863069` (2026-10-29 15:41Z).

## Verdict

**Mostly a scoring-basis (column) mismatch, with genuine CBS opinion on top.
Not a parser or date error.**

CBS's `nonppr` ROS page scores with CBS's own rules. On the one stored raw
snapshot that has stat components (2026-09-30), CBS's fpts match 6-point
passing TDs plus whole-point yardage per game. They do not match the 4-point,
fractional scoring the ESPN leg uses (`pipelines/fidelity_sources/espn.py`).
Against that basis CBS's points run QB x1.12, RB x0.86, WR x0.89 and TE x0.91.
This is the same sign pattern as the week-8 position biases: CBS QBs high,
CBS RBs and WRs low.

Re-pricing CBS with those position factors (a counterfactual only, see below)
takes it from 46.7% to 40.0% outliers in half PPR and from 43.3% to 39.3% in
full PPR. Both land under the 45% ceiling. The remaining disagreement is CBS's
own view: David Montgomery 6.1 points a game against 10.1 and 12.1 elsewhere,
and Tyler Warren 12.5 against 8.5 and 8.1.

The fix belongs in a follow-on ticket (a mapping fix: rescore CBS's stat
components to the shared basis, or document the basis and accept it). It needs
review and an ownership handshake first. This PR does not resolve the warn.

## Evidence

| What | Stored value |
| -- | -- |
| Alert report | `dist/modules/source-divergence.json` at `e2c191c` (committed 2026-10-27 10:59Z, generated 10:56:44Z) |
| Fixture behind it | `comparison-sources-data.json` built 2026-10-26T15:42:37Z |
| CBS URL | `https://www.cbssports.com/fantasy/football/stats/QB/2026/restofseason/projections/nonppr/` (one URL per position) |
| CBS vintage | 2026-10-26, raw built 11:51:59Z, snapshot `sha256:d678c90d…`, held amber (`publisher_vs_stored`, week 7) |
| Legs | `data/ddf-two-tier/ddf-20261026-cbsros-{standard,half_ppr,ppr}-12t-0p15` |
| Served week | The report's "week 8" is the content week. In that build ESPN, CBS ROS and Razzball were all served as **week 7** (`data/history/index.json`), so the group is not mixed. All three are rest-of-season. |
| Column | Base `nonppr` totals. Half and full are CBS fpts + 0.5 or 1.0 per reception. This was checked per player (half = std + 0.5 x (full − std)). |
| Indexed factor | 1.0 at every position and every combo (`index_total`) |

The reproduction matches the published numbers exactly. The test's own
leave-one-out and the check's `divergence` give the same result.

| Combo | n | Outlier rate | Bias |
| -- | -- | -- | -- |
| half_12 (headline) | 135 | 46.7% | −2.96 |
| full_12 | 134 | 43.3% | −1.70 |
| standard_12 | 132 | 40.9% | −2.05 |

### Trace: five sample players, half PPR 12-team

Native is CBS points per game. Raw is the two-tier price, re-implemented in
the test from the leg's calibration. Displayed = raw x 3.29531 (scale) x 1.0
(Indexed), rounded to one decimal.

| Player | Pos | CBS ppg | ESPN / Razzball ppg | Raw | Displayed | ESPN / Razzball shown |
| -- | -- | -- | -- | -- | -- | -- |
| Joe Burrow | QB | 25.06 | 21.77 / 16.50 | 15.297 | 50.4 | 36.1 / 17.4 |
| David Montgomery | RB | 6.06 | 10.06 / 12.10 | 1.070 | 3.5 | 19.3 / 25.7 |
| Jalen Coker | WR | 8.41 | 13.00 / 13.20 | 1.875 | 6.2 | 27.1 / 29.1 |
| Tyler Warren | TE | 12.52 | 8.46 / 8.10 | 5.456 | 18.0 | 7.2 / 5.4 |
| Bijan Robinson (control) | RB | 18.06 | 18.86 / 19.00 | 14.905 | 49.1 | 52.2 / 53.9 |

The chain from leg to fixture is exact for all 366 CBS players in all three
combos: no value or native mismatches.

Missing and zero are kept apart. Aaron Rodgers is present at 0.0, priced
below CBS's QB waiver line at 15.48 ppg. Efton Chism III has no CBS row. The
check skips both, so neither counts toward n. A side effect: a CBS 0.0
against real value elsewhere (Tyler Allgeier at 0.0 against 7.4 and 6.2) is
never counted as disagreement. That is reported here only. No change is
proposed.

### Scoring basis (2026-09-30 raw, 33 QBs, 61 RBs, 99 WRs, 33 TEs with 40+ points)

| Model | QB | RB | WR | TE |
| -- | -- | -- | -- | -- |
| 4-pt pass TD, fractional (ESPN leg) | x1.123 | x0.857 | x0.892 | x0.905 |
| 6-pt pass TD, whole points per game | x0.985 | x0.952 | x0.982 | x1.000 |

(Each cell is the median of CBS fpts / recompute.) A free least-squares fit
gives 6.07 points per passing TD and about −0.8 points per game per player.
That per-game loss is consistent with rounding yardage down to whole points
each game.

## Unknowns, where stored evidence runs out

- **The 2026-10-26 raw snapshot is not in git.** Only its legs and its
  sha256 are. The scoring basis is measured on the 2026-09-30 raw and assumed
  to carry over, since the URL and parser are the same. A per-player rescore
  of week 8 needs those components. I did not read Supabase.
- CBS's published scoring rules were not confirmed from a CBS page. The basis
  is inferred from the fit.
- The 12:07Z / 7:07 AM CBS import job no longer exists, and CBS ROS is held
  amber. The live feed reloads only when CBS changes its page. Later builds
  (for example the 2026-10-29 rebuild at `ca51f2f`, CBS vintage 2026-10-29)
  are different inputs: 45.3% half, 48.2% full on `main` now.
- `gp` is CBS's own remaining-games column (the puller cross-checks fpts/gp
  against CBS fppg). The 10-26 pull ran before that night's Monday game, and
  whether those two teams' `gp` included it can't be checked without the raw.
- The counterfactual uses one factor per position, not a per-player rescore.
- ESPN half_12 also sits near the ceiling (44.4%, bias +3.58, positive at
  every position). It is not investigated here.

## Commands

```
git show e2c191c:dist/modules/source-divergence.json            # published warn
python3 docs/research/JEG-1171/extract_fixtures.py               # writes tests/fixtures/JEG-1171/
python3 -m unittest -v tests.test_jeg1171_cbsros_w8_divergence_trace
python3 docs/research/JEG-1171/counterfactual_rescore.py --identity   # reproduces 46.7%
python3 docs/research/JEG-1171/counterfactual_rescore.py              # rescored: 40.0% half
```

`extract_fixtures.py` and `counterfactual_rescore.py` read only from git
history. The counterfactual writes its synthetic inputs to a temp directory,
and none of them is a source capture.
