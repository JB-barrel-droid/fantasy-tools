# JEG-1198: can rest-of-season rankings anchor trade values?

Research only, 2026-10-29 UTC. No published value, pipeline, default or Supabase row
changed. Script: `tools/research/ros_rank_anchor.py`. Inputs and outputs:
`docs/research/data/jeg1198/`.

## Answer

The mechanism works, the input does not exist. A positional rank can be turned into a
value on the published scale without assuming equal gaps (match rank r at a position to
the published value of the r-th player there). But there is no current, full-depth,
non-ECR consensus ROS ranking we can read, and the modeled ranks we do have disagree
most on exactly the disputed players, so ranks cannot settle a dispute. Recommendation:
no-go on a ROS-ranking anchor for published values.

Option C rerun (below, same day): with real expert ROS ranks, the answer holds but for a
different reason. Expert ranks exist and agree with the published chart closely, so as a
value anchor they would mostly confirm it. They work as a review check, not a new value.

## Data and labels

| Input | Label | Vintage | Depth | Scoring |
|---|---|---|---|---|
| DDF Value, 12 teams, 1QB, from the DDF connector `get_values` | published | as_of 2026-10-28 | 163 to 166 rows per scoring with value > 0 or listed | Standard, Half PPR, PPR |
| ESPN, CBS ROS, Razzball ROS points from `data/fixtures/current/players.json` (sha256 `eef4f2a2…4647`, commit `d4d995f`), ranked within position | modeled (ranks derived from published projection inputs), weeks 8-18 | ESPN and CBS ROS 2026-10-28, Razzball 2026-10-27 | ESPN 347, CBS ROS 366, Razzball 639 complete rows | all three |
| StickToTheModel ROS PPR, top 30 per position | stale (page dated 2026-10-20, weeks 7-18), external model | 2026-10-20 | 30 per position | PPR only |

What was looked for and not usable (evidence from 2026-10-26 on):

- FantasyPros ROS rankings (2026-10-28): expert consensus. ECR is hard-excluded repo-wide
  (`pipelines/import_supabase_references.py` `HARD_EXCLUSIONS`; `pull_dynasty_daddy.py`
  drops `fantasypros_ros`). The anonymous page also exposed only 5 rows.
- Draft Sharks ROS (2026-10-29, week 8): rows load client-side; names not in the page.
- RotoStreetJournal week 8 ROS (2026-10-26, Half PPR): the big board is an image.
- Supabase (read-only): `ranker_rankings` holds only FantasyPros ECR (ROS last on
  2026-09-11, weekly last 2026-10-05). `dynasty_daddy_trade_values` (would carry ESPN,
  FanDuel and FantasyGuys ROS ranks) and `numberfire_ros_projections` have 0 rows.
- Any 2023-2025 ROS article is previous-season and was not used.

So the "rankers" below are modeled ranks, not expert consensus. That is the honest
ceiling of what is available today.

## Method compared

1. Rank curve. The published value at each positional rank, read off the live chart.
   Gaps are far from equal (PPR): QB1 to QB2 is 11.0 points against a median gap of 1.55
   across QB1-12; RB 7.0 vs 1.8; WR 4.1 vs 1.45; TE 3.8 vs 1.4. Below about QB17, RB54,
   WR66 and TE23 the curve is 0, so a rank there implies nothing.
2. Interpolation. Positional rank-matching, linear between neighbouring published ranks
   for a fractional (averaged) rank. No parametric curve and no 0-70 cap: the anchor is
   whatever the live chart says at that rank, so it moves when the chart moves.
3. Replacement and positional scarcity. Rank within position keeps scarcity. Ranking
   all positions together on points destroys it (PPR, ESPN points): Josh Allen QB1 is
   overall 2 and would imply 67.6 against 32.0 published; Brock Bowers TE1 is overall 62
   and would imply 13.5 against 33.5. Any build must be positional.
4. Ranker aggregation. Mean of the implied values vs value at the mean rank vs value at
   the median rank. Because the curve is convex, the mean of values runs above the value
   at the mean rank (PPR median gap 0.0 QB, 0.2 RB, 0.6 WR, 1.0 TE; up to 5.2 for a TE).
   The median rank can move a player a lot when rankers split (Drake Maye PPR: 8.3 by
   mean of values, 5.4 at the median rank).

## Anchor agreement and stability

Spearman rank correlation with the published order, within the published top 12 QB,
30 RB, 36 WR, 12 TE (PPR; Half PPR and Standard are within about 0.05 except TE):

| Pos | ESPN | CBS ROS | Razzball | STTM (stale) |
|---|---|---|---|---|
| QB | 0.60 | 0.19 | 0.34 | 0.36 |
| RB | 0.91 | 0.90 | 0.81 | 0.91 |
| WR | 0.88 | 0.91 | 0.84 | 0.87 |
| TE | 0.87 | 0.51 | 0.88 | 0.76 |

Rankers agree with each other about as well as with the chart at RB and WR (0.78 to 0.94)
and poorly at QB (0.36 to 0.74) and TE (CBS ROS vs Razzball 0.45). Ranker bias is
position-specific: CBS ROS is the outlier at QB and TE, Razzball at QB.

Stability, ESPN ranks 2026-09-23 vs 2026-10-28 (PPR, same depth): Spearman QB 0.46,
RB 0.72, WR 0.77, TE 0.79; median rank move 4 to 7 places, worth a median 4.0 (TE) to
9.4 (RB) points on today's curve. A ranking anchor would move week to week by about as
much as the disputes it is meant to settle.

## Worked examples (rank, implied value, chart)

PPR, 12 teams, 1QB. Implied = published value of the player at that positional rank.

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

## Divergences and uncertainty

- Using Jeremy's materiality rule (over 5% and over 2 points), 57 of the 90 compared
  PPR starters diverge (58 Half PPR, 56 Standard). Median absolute gap 2.3 (TE) to 3.8
  (RB) points PPR, 5.7 RB in Standard. This is a different view of value, not a fill-in.
- Largest PPR divergences: Chase Brown +22.3, Malik Nabers −17.3, Jalen Coker +13.1,
  Drake Maye −12.7, D'Andre Swift −11.9, Jayden Daniels +10.9, Chris Olave −10.8,
  Tony Pollard +10.6, Breece Hall −10.1.
- These are mostly the market (trade charts) against the projections. DDF Projections
  already shows that gap with cardinal numbers; ranks throw the size of the gap away.
- Uncertainty: median rank SD across the three rankers is 2.2 to 3.0 places (PPR), a median
  implied range of 6.5 (TE) to 10.6 (RB) points PPR. The disputed players carry the
  widest ranges (Jalen Coker 30.1, Josh Jacobs 21.2, Chase Brown 15.0, Malik Nabers 15.5).

## Thin and missing anchors

- Every compared starter had all three modeled rankers, but the external evidence is
  thin: one stale external list (30 per position, PPR only), no readable consensus.
- Beyond the depth where the chart reaches 0, a rank implies 0 whatever it says.
- Ranked by a source but unpriced on the chart (PPR): Malik Willis (ESPN QB12, CBS QB10),
  Justin Herbert (Razzball QB8), Greg Dulcich (CBS TE9), Mike Gesicki (CBS TE12, STTM TE12);
  Half PPR and Standard add Alec Pierce, Caleb Douglas, Malik Washington. A build would
  need a rule for these; the Oct 28 fill-in decision (FantasyCalc and projection sources
  only) would apply.

## Recommendation

No-go on anchoring published values to ROS rankings. Any later build is a separate
decision for Jeremy: a review-only "rank check" flag built from the projection sources
(no value change), or lifting the ECR rule to bring in a real consensus feed.

Shared inputs with JEG-1195 to JEG-1197: canonical `player_key`, the ROS projection
fields in `players.json`, and the published curve; no new feed is needed for any of them.

## Option C rerun: real expert ROS rankings

Jeremy picked option C on 2026-10-29 ("start with 4-5 sources, piped through supabase"),
which lifts the expert-consensus ban for rankings only (docs/pipeline-rules.md section 7).
The feed is on PR #1081 and saves nothing until the draft table is approved. This rerun
uses what that feed read on a runner, plus one ESPN article read once by hand. Script:
`tools/research/ros_rank_anchor_experts.py`.

| Ranker | Label | Vintage | Scoring | Read how |
|---|---|---|---|---|
| Expert consensus (6 experts) | published | 2026-10-28 | Half PPR only | feed, dry run 40802150829 |
| Scott Pianowski, Yahoo dollar tiers | published, QB and TE stale | QB 09-30, TE 10-07, RB 10-14, WR 10-21 | unstated | feed, same run |
| Eric Karabell, ESPN ROS article | published | 2026-10-27 | unstated | read once; a runner gets HTTP 202, so not piped |
| ESPN, CBS ROS, Razzball projections | modeled | fixture `d4d995f` | per scoring | first study |

Pianowski is ranked by dollar value, ties sharing the average rank. The same three
rankings are used for all three scorings, since none publishes per-scoring ROS lists;
only the published curve changes with scoring. Depth: QB12, RB30, WR36, TE12 of the
published chart (89 players).

Spearman rank agreement with the published chart, PPR:

| | QB | RB | WR | TE |
|---|---|---|---|---|
| Expert consensus | .93 | .99 | .98 | .96 |
| Pianowski | .56 | .90 | .96 | .76 |
| Karabell | .82 | .97 | .89 | .81 |
| Modeled (range of three) | .19 to .60 | .81 to .91 | .83 to .91 | .53 to .88 |

The experts agree with each other at RB (.87 to .96) and WR (.90 to .98), less at QB (.56
to .71) and TE (.69 to .85). Half PPR and Standard are within a few hundredths.

Implied value (rank matched to the published curve, averaged over the three experts):
35 of 89 players move materially (over 5% and over 2 points) in each scoring, against
54 to 57 for the modeled mean. Median gap to published is 1.2 to 2.2 points. Median spread
between the three experts is 4 to 6.5 points, wider than the median gap, so for most
players the published value already sits inside the experts' range.

Largest PPR gaps, and why:
- Josh Jacobs, 30.5 published, experts mean 20.7: Pianowski has him RB45 in his Oct 14
  article; the other two have RB17 and RB12.
- Drake Maye, 21.0 published, experts mean 12.1: Pianowski's QB article is from Sep 30;
  expert consensus has him QB2, matching published.
- Luther Burden III -8.5 and Nico Collins +6.9: all three experts lean the same way.

The disputed players from the first study mostly sit near published under the experts:
Chase Brown 28.3 vs 23.8 published (modeled 46.1), Malik Nabers 43.5 vs 45.4 (modeled
27.6), Jalen Coker 15.1 vs 14.7 (modeled 27.8). Jayden Daniels is the exception: 5.5 vs
9.0, with the modeled ranks at 19.9.

What this means:
- Expert ROS ranks track the market chart closely. That is a check on it, not new
  information to average in; averaging them into DDF Value would mostly double count
  the same opinion.
- The useful signal is the few players where all experts agree against the chart
  (Burden, Collins). A review flag on those is the build this supports.
- Stale articles drive most of the outliers, so any flag needs a vintage cutoff (for
  example, ignore a source older than 14 days).
- Two sources piped plus one read by hand is short of the 4 to 5 Jeremy asked for; the
  rest did not read (PR #1081 lists why).

Inputs: `data/jeg1198/roslist_2026-10-29.txt` (feed lists, trimmed to study depth),
`data/jeg1198/espn_ros_karabell_2026-10-27.txt`. Outputs:
`data/jeg1198/ros_rank_experts_out.json`, `data/jeg1198/ros_rank_experts_console.txt`.

## Reproduce

    python3 tools/research/ros_rank_anchor.py

It reads the files above and writes `data/jeg1198/ros_rank_study_out.json`; the console
summary from the 2026-10-29 run is `data/jeg1198/ros_rank_study_console.txt`.
`players.json` changes as the fixture is rebuilt, so later runs need the pinned version
(commit `d4d995f`) to match these figures.

The option C rerun:

    PLAYER_ALIASES_SOURCE=json python3 tools/research/ros_rank_anchor_experts.py
