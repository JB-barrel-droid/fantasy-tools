# JEG-1198: can rest-of-season rankings anchor trade values?

Research only. Study runs 2026-10-29 UTC; corrections for review (JEG-1251) 2026-10-29.
No published value, pipeline, default or Supabase row changed. Scripts:
`tools/research/ros_rank_anchor*.py`, `tools/research/ros_rank_keys.py`,
`tools/research/ros_rank_baseline_check.py`. Inputs and outputs: `docs/research/data/jeg1198/`.

## Current finding (as of 2026-10-29)

Expert rest-of-season (ROS) rankings are available and readable: the expert consensus in
Half PPR, PPR and standard, 21 experts' own ROS lists (20 in PPR and standard), Scott
Pianowski's Yahoo tiers and one ESPN article (Eric Karabell). At study depth (QB12, RB30,
WR36, TE12; 89 players) they order players much as the DDF Value baseline does
(Spearman, by position and scoring, .88 to .99 for the consensus and .94 to .98 for the
mean of the fresh expert lists; the one value under .93 is the standard TE consensus).
Adding lists widens the spread between rankers; it does not move the center.

Recommendation, unchanged across all three runs: no-go on anchoring DDF Value to ROS
rankings. If anything is built, a review-only flag on players where the fresh expert
panel (lists updated within 14 days) disagrees with DDF Value, with the middle-half band
as the tolerance. Using ROS ranks in DDF Value or DDF Projections is a separate decision
for Jeremy.

The first study's framing ("the input does not exist", "the honest ceiling of what is
available today") is superseded: it described a limited retrieval audit made before the
option C feed read the expert lists. It is kept below as a dated, historical record.

## Scope, source availability and what this does not show

- Sources counted as available are the ones this study actually read, on the dates in
  the provenance table below. Sources that did not read on those dates did not read from
  a GitHub runner without a sign-in; that is not evidence that the rankings do not exist
  or cannot be read another way, and the list of sources tried is not exhaustive.
- Every list is rest-of-season. No weekly ranking is used, and no weekly list is averaged
  with a ROS list (Jeremy, 2026-10-29: "do not blend weekly data with ROS data, ever").
- Pianowski and Karabell do not state a scoring, and the consensus panel of the option C
  rerun used one Half PPR consensus for all three scorings. Reusing those lists across
  scorings is a sensitivity comparison (only the DDF Value curve changes with scoring),
  not evidence of three scoring-specific expert feeds. The expert consensus and the
  expert lists in the second rerun are per scoring.
- The rankings feed is PR #1081 (open). On 2026-10-29 the JEG-1198 ticket records
  migrations 015/016 as applied on Jeremy's approval and a first write run (Actions run
  40808666744); reconciling that record is the coordinator's, separate from this study.
  This study reads only the dry-run lists committed here, never the table. The daily
  schedule dispatches the workflow on main, so daily pulls depend on #1081 reaching main;
  nothing here assumes daily operation.
- The ECR exclusion is lifted for rankings only, by option C (docs/pipeline-rules.md
  section 7 as amended on PR #1081, not yet on main). DDF Value and DDF Projections inputs
  are unchanged.

## The baseline: what "published" means here

The baseline column ("published") is DDF Value as the DDF connector's `get_values`
returned it on 2026-10-29 at 01:3x UTC (as_of 2026-10-28; 12 teams, 1QB; Standard, Half
PPR and PPR), copied into `published_<scoring>.txt`.

Recipe, from the code that serves it: `get_values` returns `ddfByVersion.blended.value`
from `value-model.js` `runValuePipeline` (supabase/functions/get-values/index.ts). Under
JEG-1073 (Jeremy, 2026-10-25) that is the equal-weight mean of the Adjusted values of the
trade charts included that week. The trade charts are of two kinds (#1071, JEG-1212):
publisher charts (USA Today, FantasyPros, CBS) and FantasyCalc's observed-trade estimate.
So the baseline is a trade-chart composite that includes an observed-trade estimate; it is
not a publisher-only average and not any one chart's raw value. The capture did not record
which charts were included that week (the connector prints a "Sources included" line that
was not copied). #1071 merged at 02:03 UTC, after the capture, and changed presentation
only; it did not change DDF math, defaults or source membership.

Reproduction check (`tools/research/ros_rank_baseline_check.py`): the same recipe, run
offline with the repo's headless edge runner (`tests/_edge_pipeline_runner.cjs`) on the
site bundle committed at `cbaac75` (the last automated rebuild before the capture,
2026-10-29 00:08 UTC), does not reproduce the capture exactly:

| | PPR | Half PPR | Standard |
|---|---|---|---|
| Rows compared (joined on player_key) | 163 | 165 | 166 |
| Within 0.05 of the capture | 6 | 5 | 13 |
| Median absolute gap (points) | 1.1 | 1.3 | 1.3 |
| Largest gap (points) | 8.5 | 8.2 | 10.8 |

The cause is not established (the included chart set, the bundle actually live at the
capture, or the deployed function version are all candidates). So the captured files are
the pinned baseline (sha256 below); they are reproducible as files, not as a recomputation.
The players with the largest capture-vs-rebuild gaps include several the study names:
Nico Collins (PPR 25.7 captured, 34.2 rebuilt), Josh Jacobs (30.5, 23.3), Chase Brown
(Half PPR 25.5, 33.7), Tee Higgins, Luther Burden III and Malik Nabers. Gaps of that size
for those players are within baseline uncertainty and should not be read as findings on
their own. The rank-agreement results are less sensitive, but were not rerun on the
rebuilt baseline.

## Provenance and joins

All joins are on the canonical `player_key` (public.players), resolved through the repo's
one resolver (`pipelines/lib/canonical_players.resolve_with_reason`, with the shared alias
list), built from the committed registry snapshot `data/inputs/players_identity_snapshot.json`
(sha256 `e1ff38fc…a1f362`, 4,702 rows; no active flag, so same-name same-position players
fail closed as ambiguous). The alias list is read from the committed JSON, not the table.
Rows from `players.json` carry the bake's own `player_key`. A name that does not resolve
to exactly one key is left out and listed in each output's `joins` block with its reason.

Result on the stored inputs: every name resolved (614 study rows, 1,071 option C rows,
17,532 second-rerun rows), with no unmatched, ambiguous, position-conflict or duplicate
rows. The earlier name-keyed joins produced identical outputs: the `scorings` blocks of
all three output files are byte-for-byte unchanged; only `provenance` and `joins` blocks
were added. The feed lists were written by the #1081 puller; whether it dropped rows
upstream is recorded in that PR's dry runs, not here.

| Input file | What it is | How and when captured | Source address | Label |
|---|---|---|---|---|
| `published_{ppr,half_ppr,standard}.txt` | DDF Value, 12 teams 1QB | DDF connector `get_values`, 2026-10-29 01:3x UTC, as_of 2026-10-28 | DDF connector (get-values edge function) | published (see baseline) |
| `data/fixtures/current/players.json` (sha256 `eef4f2a2…4647`, commit `d4d995f`) | ESPN, CBS ROS, Razzball ROS projections, weeks 8-18 | repo bake; ESPN and CBS ROS snapshots 2026-10-28, Razzball 2026-10-27 (snapshot ids in its meta) | repo fixture | modeled |
| `data/fixtures/snapshots/players_2026-09-23.json` (sha256 `6add0a76…af98e`) | earlier ESPN ROS read, weeks 4-18 | repo fixture, as_of 2026-09-23; its ESPN pull is labelled 2026-09-29 | repo fixture | modeled, previous read |
| `sttm_ros_ppr_2026-10-20.txt` | StickToTheModel ROS PPR, top 30 per position | read by hand for the first study on 2026-10-29; page dated 2026-10-20 | exact page address not recorded at capture | stale |
| `espn_ros_karabell_2026-10-27.txt` | Eric Karabell's ESPN ROS article | read once by hand on 2026-10-29; article dated 2026-10-27; ESPN story id 49949224 per the study notes | full address not recorded at capture | published |
| `roslist_2026-10-29.txt` | expert consensus (Half PPR) and Pianowski | feed dry run 40802150829, 2026-10-29 | addresses in `pipelines/pull_ros_rankings.py` on #1081 (consensus start page `https://www.fantasypros.com/nfl/rankings/?type=ros`; Pianowski's Yahoo author page and four article seeds) | published; Pianowski QB and TE stale |
| `roslist_2026-10-29b.txt` | consensus per scoring, 21 expert lists, Pianowski | feed dry run 40806312909, 2026-10-29 | as above; expert lists are linked from the consensus page's expert table | published; 8 expert lists stale |

## First study (historical, 2026-10-29): modeled ranks only

This section is the original study as run before the expert feed existed. Its
availability statements describe that day's audit, not the current state.

| Input | Label | Vintage | Depth | Scoring |
|---|---|---|---|---|
| DDF Value from the DDF connector `get_values` | published | as_of 2026-10-28 | 163 to 166 rows per scoring | Standard, Half PPR, PPR |
| ESPN, CBS ROS, Razzball points from `players.json`, ranked within position | modeled, weeks 8-18 | ESPN and CBS ROS 2026-10-28, Razzball 2026-10-27 | ESPN 347, CBS ROS 366, Razzball 639 complete rows | all three |
| StickToTheModel ROS PPR, top 30 per position | stale, external model | 2026-10-20 | 30 per position | PPR only |

Retrieval audit at the time (2026-10-26 to 2026-10-29; limited to these sources):

- FantasyPros ROS rankings (2026-10-28): expert consensus, then hard-excluded repo-wide
  (`pipelines/import_supabase_references.py` `HARD_EXCLUSIONS`; `pull_dynasty_daddy.py`
  drops `fantasypros_ros`). The anonymous page's visible table showed 5 rows. Superseded:
  the #1081 feed later read the full list from the page's embedded data.
- Draft Sharks ROS (2026-10-29, week 8): rows load client-side; names were not in the
  page as fetched. Not retried.
- RotoStreetJournal week 8 ROS (2026-10-26, Half PPR): the big board is an image. Its
  expert list was later read through the consensus site's expert table.
- Supabase, read-only on 2026-10-29: `ranker_rankings` held only FantasyPros ECR (ROS last
  2026-09-11, weekly last 2026-10-05); `dynasty_daddy_trade_values` and
  `numberfire_ros_projections` had 0 rows.
- 2023-2025 ROS articles are previous-season and were not used.

Within that audit no usable full-depth non-ECR consensus was found, so the rankers in this
section are modeled ranks, not experts.

### Method compared

1. Rank curve. The DDF Value at each positional rank, read off the captured baseline.
   Gaps are far from equal (PPR): QB1 to QB2 is 11.0 points against a median gap of 1.55
   across QB1-12; RB 7.0 vs 1.8; WR 4.1 vs 1.45; TE 3.8 vs 1.4. Below about QB17, RB54,
   WR66 and TE23 the curve is 0, so a rank there implies nothing.
2. Interpolation. Positional rank-matching, linear between neighbouring ranks for a
   fractional (averaged) rank. No parametric curve and no 0-70 cap: the anchor is
   whatever the baseline says at that rank, so it moves when DDF Value moves.
3. Replacement and positional scarcity. Rank within position keeps scarcity. Ranking
   all positions together on points destroys it (PPR, ESPN points): Josh Allen QB1 is
   overall 2 and would imply 67.6 against 32.0 published; Brock Bowers TE1 is overall 62
   and would imply 13.5 against 33.5. Any build must be positional.
4. Ranker aggregation. Mean of the implied values vs value at the mean rank vs value at
   the median rank. Because the curve is convex, the mean of values runs above the value
   at the mean rank (PPR median gap 0.0 QB, 0.2 RB, 0.6 WR, 1.0 TE; up to 5.2 for a TE).
   The median rank can move a player a lot when rankers split (Drake Maye PPR: 8.3 by
   mean of values, 5.4 at the median rank).

### Anchor agreement and stability

Spearman rank correlation with the baseline order, within the top 12 QB, 30 RB, 36 WR,
12 TE (PPR; Half PPR and Standard are within about 0.05 except TE):

| Pos | ESPN | CBS ROS | Razzball | STTM (stale) |
|---|---|---|---|---|
| QB | 0.60 | 0.19 | 0.34 | 0.36 |
| RB | 0.91 | 0.90 | 0.81 | 0.91 |
| WR | 0.88 | 0.91 | 0.84 | 0.87 |
| TE | 0.87 | 0.51 | 0.88 | 0.76 |

Rankers agree with each other about as well as with the baseline at RB and WR (0.78 to
0.94) and poorly at QB (0.36 to 0.74) and TE (CBS ROS vs Razzball 0.45). Ranker bias is
position-specific: CBS ROS is the outlier at QB and TE, Razzball at QB.

Stability over one interval. ESPN's ROS order in the fixture as_of 2026-09-23 (its ESPN
pull labelled 2026-09-29) against the fixture as_of 2026-10-28: 29 to 35 days, one pair of
reads, joined on player_key, ESPN's current top 12/30/36/12 (all present in both). PPR:
Spearman QB 0.46, RB 0.72, WR 0.77, TE 0.79; median rank move 5.5, 4, 7 and 4.5 places,
worth a median 6.9, 9.4, 8.4 and 4.0 points on the 2026-10-28 curve (Half PPR and
Standard in `ros_rank_study_out.json`, `stability_espn`). The two reads also cover
different horizons (weeks 4-18, then 8-18). This bounds how far one modeled source's order
moved over that interval; it is not a week-to-week rate, and no adjacent-week reads were
compared. Over that interval the move is about as large as the disputes a ranking anchor
would be used to settle.

### Worked examples (rank, implied value, baseline)

PPR, 12 teams, 1QB. Implied = DDF Value of the player at that positional rank.

| Player | Published (pos rank) | ESPN | CBS ROS | Razzball | Implied, mean of values | Range |
|---|---|---|---|---|---|---|
| Kenneth Walker III, RB | 67.6 (RB3) | RB2 → 67.6 | RB2 → 67.6 | RB2 → 67.6 | 67.6 | 0 |
| Chase Brown, RB | 23.8 (RB18) | RB11 → 36.1 | RB5 → 51.1 | RB5 → 51.1 | 46.1 | 36.1-51.1 |
| Malik Nabers, WR | 45.4 (WR6) | WR10 → 34.3 | WR20 → 18.8 | WR12 → 31.1 | 28.1 | 18.8-34.3 |
| Drake Maye, QB | 21.0 (QB2) | QB5 → 14.9 | QB11 → 5.4 | QB12 → 4.6 | 8.3 | 4.6-14.9 |
| Jalen Coker, WR | 14.7 (WR25) | WR13 → 28.2 | WR30 → 12.5 | WR7 → 42.6 | 27.8 | 12.5-42.6 |
| Jayden Daniels, QB | 9.0 (QB9) | QB2 → 21.0 | QB3 → 17.6 | QB2 → 21.0 | 19.9 | 17.6-21.0 |
| Josh Jacobs, RB | 30.5 (RB15) | RB18 → 23.8 | RB14 → 30.8 | RB27 → 9.6 | 21.4 | 9.6-30.8 |

Standard moves the same way with bigger RB numbers (Chase Brown 30.0 published, 38.4
implied; Tony Pollard 17.3 vs 35.0). Full rows for all three scorings are in
`data/jeg1198/ros_rank_study_out.json`.

### Divergences and uncertainty

- Using Jeremy's materiality rule (over 5% and over 2 points), 57 of the 90 compared
  PPR starters diverge (58 Half PPR, 56 Standard). Median absolute gap 2.3 (TE) to 3.8
  (RB) points PPR, 5.7 RB in Standard. This is a different view of value, not a fill-in.
- Largest PPR divergences: Chase Brown +22.3, Malik Nabers −17.3, Jalen Coker +13.1,
  Drake Maye −12.7, D'Andre Swift −11.9, Jayden Daniels +10.9, Chris Olave −10.8,
  Tony Pollard +10.6, Breece Hall −10.1. Several of these players also carry the largest
  baseline uncertainty (see the baseline section).
- These gaps set the trade-chart composite (DDF Value) against projection-derived ranks.
  DDF Projections already shows that gap with cardinal numbers; ranks throw the size of
  the gap away.
- Uncertainty: median rank SD across the three rankers is 2.2 to 3.0 places (PPR), a median
  implied range of 6.5 (TE) to 10.6 (RB) points PPR. The disputed players carry the
  widest ranges (Jalen Coker 30.1, Josh Jacobs 21.2, Chase Brown 15.0, Malik Nabers 15.5).

### Thin and missing anchors

- Every compared starter had all three modeled rankers, but the external evidence in this
  first run was thin: one stale external list (30 per position, PPR only).
- Beyond the depth where the curve reaches 0, a rank implies 0 whatever it says.
- Ranked by a source but unpriced by DDF Value (PPR): Malik Willis (ESPN QB12, CBS QB10),
  Justin Herbert (Razzball QB8), Greg Dulcich (CBS TE9), Mike Gesicki (CBS TE12, STTM TE12);
  Half PPR and Standard add Alec Pierce, Caleb Douglas, Malik Washington. A build would
  need a rule for these; the Oct 28 fill-in decision (FantasyCalc and projection sources
  only) would apply.

Shared inputs with JEG-1195 to JEG-1197: canonical `player_key`, the ROS projection
fields in `players.json`, and the DDF Value curve.

## Option C rerun (historical, 2026-10-29): first expert ROS rankings

Jeremy picked option C on 2026-10-29 ("start with 4-5 sources, piped through supabase"),
which lifts the expert-consensus ban for rankings only. This rerun uses what the #1081
feed read on a runner in dry run 40802150829, plus one ESPN article read once by hand.
Script: `tools/research/ros_rank_anchor_experts.py`. "Published" in the label column means
published by that ranker.

| Ranker | Label | Vintage | Scoring | Read how |
|---|---|---|---|---|
| Expert consensus (6 experts) | published | 2026-10-28 | Half PPR only | feed, dry run 40802150829 |
| Scott Pianowski, Yahoo dollar tiers | published, QB and TE stale | QB 09-30, TE 10-07, RB 10-14, WR 10-21 | unstated | feed, same run |
| Eric Karabell, ESPN ROS article | published | 2026-10-27 | unstated | read once; a runner gets HTTP 202, so not piped |
| ESPN, CBS ROS, Razzball projections | modeled | fixture `d4d995f` | per scoring | first study |

Pianowski is ranked by dollar value, ties sharing the average rank. The same three
expert lists are used for all three scorings, since none of them was read per scoring;
only the DDF Value curve changes. That makes the Half PPR and Standard columns a
sensitivity comparison, not three scoring-specific expert feeds. Depth: QB12, RB30, WR36,
TE12 (89 players).

Spearman rank agreement with the baseline, PPR:

| | QB | RB | WR | TE |
|---|---|---|---|---|
| Expert consensus | .93 | .99 | .98 | .96 |
| Pianowski | .56 | .90 | .96 | .76 |
| Karabell | .82 | .97 | .89 | .81 |
| Modeled (range of three) | .19 to .60 | .81 to .91 | .83 to .91 | .53 to .88 |

The experts agree with each other at RB (.87 to .96) and WR (.90 to .98), less at QB (.56
to .71) and TE (.69 to .85). Half PPR and Standard are within a few hundredths.

Implied value (rank matched to the DDF Value curve, averaged over the three experts):
35 of 89 players move materially (over 5% and over 2 points) in each scoring, against
54 to 57 for the modeled mean. Median gap to the baseline is 1.2 to 2.2 points. Median
spread between the three experts is 4 to 6.5 points, wider than the median gap, so for
most players DDF Value already sits inside the experts' range.

Largest PPR gaps, and why:
- Josh Jacobs, 30.5 published, experts mean 20.7: Pianowski has him RB45 in his Oct 14
  article; the other two have RB17 and RB12. Jacobs is also one of the most
  baseline-sensitive players (rebuilt baseline 23.3).
- Drake Maye, 21.0 published, experts mean 12.1: Pianowski's QB article is from Sep 30;
  expert consensus has him QB2, matching the baseline.
- Luther Burden III -8.5 and Nico Collins +6.9: all three experts lean the same way. Both
  are within the baseline uncertainty above, so neither is a finding on its own.

The disputed players from the first study mostly sit near the baseline under the experts:
Chase Brown 28.3 vs 23.8 published (modeled 46.1), Malik Nabers 43.5 vs 45.4 (modeled
27.6), Jalen Coker 15.1 vs 14.7 (modeled 27.8). Jayden Daniels is the exception: 5.5 vs
9.0, with the modeled ranks at 19.9.

What this means:
- At study depth, expert ROS ranks order players much like DDF Value. As a value input
  they would add little ordering information the baseline does not already carry (an
  inference from rank agreement, not from shared inputs). That makes them a check, not a
  value to average in.
- The candidate signal is the few players where all experts agree against DDF Value; a
  review flag on those is the build this supports, subject to the baseline caveat.
- Stale articles drive most of the outliers, so any flag needs a vintage cutoff (for
  example, ignore a source older than 14 days).
- At this run two sources were piped and one read by hand, short of the 4 to 5 Jeremy
  asked for; the second rerun widened it.

Inputs: `data/jeg1198/roslist_2026-10-29.txt` (feed lists, trimmed to study depth),
`data/jeg1198/espn_ros_karabell_2026-10-27.txt`. Outputs:
`data/jeg1198/ros_rank_experts_out.json`, `data/jeg1198/ros_rank_experts_console.txt`.

## Second rerun (2026-10-29): consensus per scoring and each expert's own list

Jeremy asked on 2026-10-29 to "try fantasylife, footballguys, rotoballer, roto street
journal, and multiple cuts of the fantasypros data". Every list below is rest-of-season.
Script: `tools/research/ros_rank_anchor_panels.py`.

What read (feed on PR #1081, dry run 40806312909):

| Ranker | Label | Vintage | Scoring |
|---|---|---|---|
| Expert consensus, one list per scoring | published | 2026-10-28 | Half PPR, PPR, standard |
| 21 experts' own ROS lists | published; 8 stale (older than 14 days) | 2026-09-15 to 10-29 | Half PPR (21), PPR and standard (20) |
| Wolf of Roto Street (Roto Street Journal), one of the 21 | published | 2026-10-26 | Half PPR only; PPR and standard say not available |
| Scott Pianowski, Yahoo | published, QB and TE stale | as above | unstated (reused across scorings) |
| Eric Karabell, ESPN | published | 2026-10-27 | unstated (reused across scorings) |

What did not read on 2026-10-29 from a runner without an account: Fantasy Life's ROS table
fills only behind a sign-in wall; Footballguys shows only QBs without an account;
RotoBaller's ROS page had no list, and its ranking widget serves draft-style data; Roto
Street Journal's own site refuses a runner and posts its lists as images (its list arrives
through the expert table instead). These are retrieval results for those pages on that
day, not proof that no other source exists.

Double count: the consensus averages a subset of the experts' lists, so the two are never
averaged together. Two panels are compared, one analyst one vote:
- consensus panel: the consensus (matched to scoring), Pianowski, Karabell (3 lists);
- expert panel: the 13 expert lists updated within 14 days (12 in PPR and standard, where
  Roto Street Journal has no list), Pianowski, Karabell (14 to 15 lists).

Results, 89 players at study depth:

| | PPR | Half PPR | Standard |
|---|---|---|---|
| Consensus vs fresh-expert mean, rank agreement | .93 to .98 | .97 to .99 | .94 to .98 |
| Material moves vs published, consensus panel | 38 | 35 | 33 |
| Material moves vs published, expert panel | 36 | 31 | 28 |
| Median gap to published, expert panel (points) | 0.6 to 2.3 | 0.5 to 1.6 | 0.7 to 2.0 |
| Median full range across expert panel (points) | 12 to 19 | 11 to 18 | 9 to 21 |
| Median middle-half range, expert panel (points) | 2.1 to 5.3 | 2.6 to 4.6 | 2.5 to 6.3 |

What this shows:
- The consensus and the mean of the experts' own lists order players almost the same.
  The consensus is a fair stand-in for the lists; using both would count the same
  experts twice.
- One expert alone agrees with DDF Value less (median .85 to .97 by position) than their
  mean does (.94 to .98). Single lists are noisy; the full range across 14 lists is 9 to
  21 points, so a range is not a useful band. The middle half (2 to 6 points) is.
- The same names lead the gaps as in the first rerun, in all three scorings: Malik
  Nabers lower (PPR 35.3 vs 45.4 published), Chase Brown higher (32.2 vs 23.8), Josh
  Jacobs lower (22.7 vs 30.5), Nico Collins higher, Luther Burden III lower, Drake Maye
  lower (15.5 vs 21.0: the six-expert consensus has him QB2, matching the baseline, but
  most of the fresh expert lists have him QB3 to QB5). Most of these names are also the
  most baseline-sensitive players, so their gap sizes are uncertain by several points.
- Where the two panels part materially it is mostly late RBs and WRs with a wide expert
  middle half (Cam Skattebo, Matthew Golden, Christian Watson), which is where single
  lists and the 3-list panel are both thin.

The recommendation does not change: no anchoring of DDF Value to ROS rankings. If a
review flag is built, the expert panel with a 14-day vintage cutoff and the middle-half
band is the better input than the consensus alone, and never both.

Inputs: `data/jeg1198/roslist_2026-10-29b.txt` (feed lists, each cut to three times study
depth). Outputs: `data/jeg1198/ros_rank_panels_out.json`,
`data/jeg1198/ros_rank_panels_console.txt`.

## Remaining limitations

- The DDF Value baseline is pinned as captured files; recomputing it offline from the
  committed bundle differs by a median 1.1 to 1.3 points and up to 10.8. The named-player
  gaps above are not robust to that; the agreement statistics were not rerun on the
  rebuilt baseline.
- The StickToTheModel and Karabell captures have no recorded page address; they are
  identified by name, date and, for Karabell, ESPN's story id only.
- The stability comparison is one pair of reads 29 to 35 days apart, for ESPN only.
- The audited sources are the ones listed; the audit is not exhaustive.

## Reproduce

All from stored files; no network and no Supabase read.

    python3 tools/research/ros_rank_anchor.py
    python3 tools/research/ros_rank_anchor_experts.py
    python3 tools/research/ros_rank_anchor_panels.py
    python3 tools/research/ros_rank_baseline_check.py   # needs node and git history to cbaac75

They write `data/jeg1198/ros_rank_{study,experts,panels,baseline_check}_out.json`; the
console summaries are the matching `_console.txt` files. Each output carries a
`provenance` block (input sha256s, registry snapshot, alias list) and a `joins` block.
`players.json` and the registry snapshot change as fixtures are rebuilt, so later runs
need the pinned versions (sha256 in the provenance block) to match these figures. The
alias list is forced to the committed JSON (`PLAYER_ALIASES_SOURCE=json`).
