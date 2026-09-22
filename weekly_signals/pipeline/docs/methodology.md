# Methodology notes — football signal engine

Living document. Update when an investigation settles a question.

## 2026-09-11: The ▼ skew is a real house effect, not a translation bug

**Observation:** 88% of Week 1 v4 signals had Vegas below experts
(mean pts_delta_ppr −1.7; 11 of 12 post-worthy drafts were ▼).

**Investigation:**
- Decomposed the gap by component (Vegas-implied vs ESPN):
  TD expectation −0.07 pts (fine), receptions −0.1 (fine),
  receiving yards −5.2 yds (−0.5 pts), rushing yards −7.9 yds (−0.8 pts).
- Cross-checked against First Down Studio's independent Vegas-implied
  numbers for 68 WRs: same pattern (−4.6 yds, +0.1 rec, +0.0 TD).
  Two implementations, same result → the gap is in the market data,
  not the translation. (Our engine already matches FDS within 0.20
  half-PPR points mean abs diff.)
- Props were fresh (pulled 2026-09-10 15:00 CDT); not a staleness artifact.
- Missing-TD-market hypothesis ruled out: 147/148 signal players had an
  anytime-TD market; Poisson TD conversion is unbiased vs ESPN (−0.01 TDs).

**Interpretation:** Books price ~5 fewer yards (per game) than ESPN
projects, concentrated in yardage rather than receptions or TDs — i.e.
the market expects fewer yards per catch than the experts. Structural
market-vs-experts difference, not noise.

**Product consequences (agreed 2026-09-10):**
- Post raw Vegas vs ESPN numbers (honest, checkable). Do NOT de-bias
  the Vegas side toward experts — that would erase the signal.
- Treat ▲ signals (Vegas high) as stronger evidence than ▼ signals:
  they overcome the −1.7 house baseline; small ▼ signals near the
  −2.0 gate are mostly house effect.
- 2026-09-11: the rank-gap ≥ 8 gate was ELIMINATED by user directive.
  Post-worthiness is now purely |pts_delta_ppr| ≥ 2.0 plus the positional
  floor. Rank gaps remain informational only (still computed and shown
  on the data desk, never printed in posts).
- Gate left as-is for now; the calibration track record (Jan 2027)
  will empirically settle the hit rate of ▲ vs ▼ leans.

## 2026-09-11: Post format v4 (approved, points-only)

Singles (2 lines):
```
MARKET vs EXPERTS
▲ Tyler Shough, QB, NO
Vegas 18.2 vs ESPN 14.5 PPR (Δ +3.7)
```
Ranks no longer appear in posts — points only. Rank gaps are informational
only (computed on every signal, shown on the data desk) and no longer gate
post-worthiness; the gates are |pts_delta_ppr| ≥ 2.0 plus the positional floor.

Weekly thread (standard format): header tweet with a data-driven hook
("Vegas is down on 11 of 12 names vs the experts this week… with one
exception." — counts computed from the week's signals, with branches
for sweeps and balanced weeks), then one tweet per (position,
direction) group that has signals — "WRs Vegas is fading
vs the experts:" etc., lines like "▼ Tate (TEN): 8.8 vs 12.1".
The hook's final line states sources and as-of times (2026-09-11):
"Vegas: DraftKings + FanDuel lines (Odds API) as of Fri 2:46p CT ·
ESPN projections as of Fri 12:11p CT".
Order: WR, RB, TE, QB; loves before fades within a position; empty
groups skipped; big groups auto-split across numbered tweets
("(1/2)"). Player lines: "▼ C. Tate (TEN): 8.8 vs 12.1 (Δ -3.3)" —
first initial + last name, Vegas vs ESPN PPR, delta. No methodology explainer. Builder:
`engine/disagreement.py::build_thread`; stored as one `post_queue`
row with `post_type='thread'` (tweets joined by `\n---\n`).

2026-09-11 (approved): players with notable injury info get one indented
sub-line directly beneath their line in group tweets —
`  ⚠️ Questionable (ankle) — limited in practice`. The status half comes
from the injuries-table gate (`injury_flag`); the note half comes from
nflverse practice-participation rows first ("limited in practice" /
"did not practice"), then from a conservative news headline extractor
(`engine/disagreement.py::news_injury_snippet`) that only fires when the
headline is about that player's own injury concern (clearance headlines
like "off injury report" / "expected to play" / "practicing fully" and
teammate injuries never attach). Healthy players with no news get no
sub-line. Packing treats each player as one indivisible block (line +
sub-line) so sub-lines never detach when big groups re-split; the
280-char X-counted assert still applies to every tweet.

## 2026-09-11: Expert-points source = ESPN, not FP projections

Tried switching the engine's expert-points side from ESPN to
FantasyPros' own projections (fully DB-driven via
projection_snapshots). Result: 12 post-worthy signals collapsed to 1.
Two causes:
1. FP's projections sit *between* ESPN and Vegas on almost every name
   (e.g. Shough: ESPN 14.5 / FP 16.9 / Vegas 18.2) — FP's numbers look
   market-informed, which mutes the disagreement by construction.
2. The DB ECR join (ranker_rankings → players) silently drops rookies
   with no players-table row (Jeremiyah Love, Terrance Ferguson), which
   the file-based ECR flow handles.
Decision: keep ESPN (independent of both market and ECR pool) as the
expert-points source and the file-based ECR until the FP loader's
player-mapping gaps are closed. Then migrate compute to DB.

Three-line single with a rank line ("Vegas rank #10 vs ECR QB20
(gap 8)"). Dropped 2026-09-11 per user: points only.

## 2026-09-12: Vegas completeness gate (user-approved)

**Rule:** never publish a Vegas number whose full value can't be computed.
Every `vegas_implied` projection row carries `vegas_provenance`
(`projection_snapshots.vegas_provenance`, surfaced on `v_latest_signals`):

| Position | Required for publishable | complete | td-filled | partial |
|---|---|---|---|---|
| QB | passing-yards market + TD coverage | pass_yds + direct TD line | pass_yds + anytime-TD fill | missing either |
| RB | rushing-yards market + TD coverage | rush_yds + direct TD line | rush_yds + anytime-TD fill | missing either |
| WR/TE | receiving-yards + receptions markets + TD coverage | all three direct | yards+receptions direct, TD via fill | missing anything |

- `complete` = every required market is a direct line market (including TD).
- `td-filled` = required yardage/reception markets are direct; TD comes from
  the approved anytime-TD Poisson fill.
- `partial` = anything else missing. Computed and stored, but informational
  only — never post-worthy, clearly flagged wherever surfaced.

**TD source precedence (per player):** a direct player-TDs over/under line
(`player_pass_tds` / `player_rush_tds` / `player_reception_tds`) beats the
anytime-TD market; anytime-TD Poisson applies only when no direct TD line
exists; otherwise no TD component. Rationale: counting both double-counts
TD expectation (verified live: Jalen Hurts carried a 1.5 pass-TD line AND an
anytime-TD λ=0.54 — the old code added both, inflating his Vegas number by
~3.2 pts and nearly erasing a real Δ −3.3 signal).

**Anytime-TD → expected TDs:** per book, no-vig the two sides when both are
posted (`p = q_yes / (q_yes + q_no)` from raw implied probs); when only Yes
is posted, subtract half the book's estimated hold (measured from its own
two-sided line markets, 0.05 fallback). Median the fair p across books, then
Poisson `λ = −ln(1−p)`, capped at `λ = 3.0` (`engine/vegas.py::
ANYTIME_TD_LAMBDA_CAP`). Cap rationale: λ=3.0 ⟺ P(≥1 TD)=95.0%; the market
essentially never prices anytime-TD above ~−1900 (95.2%), so anything beyond
is the Poisson tail wagging on estimation noise — uncapped, a prob at the
0.99 clamp would imply 4.6 expected TDs (~27 fantasy points from TDs alone).

**Gating (all paths):** `v4/compute_v4.py` (weekly chain + `--dry-run`
verification), `bin/game_day.py` (game-day cards), and the
`v_latest_signals.post_worthy` SQL flag all require provenance in
`('complete', 'td-filled')`. This subsumes the old TD-only coverage gate
(TD-only players are partial by construction). Fail-closed: rows written
before 2026-09-12 have NULL provenance and are never post-worthy.

**Week 1 dry-run under the gate (2026-09-12):** 399-signal ECR/Vegas
intersection → 17 clear the points gate → 3 excluded as partial (all TEs
with TD-only markets: C. Heyward, O. Gadsden II, D. Njoku — phantom
Δ −5.x ▼ signals from ~0.5-pt TD-only Vegas numbers) → 14 publishable
(13 td-filled, 1 complete), 0 injury exclusions. Provenance mix across the
full intersection: 30 complete (all QB), 174 td-filled, 195 partial
(QBs always complete; RB/WR/TE partials are depth players lacking yardage
or reception lines). The Tuesday scorecard grades complete and td-filled
separately.

## 2026-09-12: No-market-read flags (user-approved)

**What it is:** a NEW signal category, not a points delta. It flags
fantasy-relevant players the books refuse to price — ECR (experts) has a
real projection on them, but Vegas posted no production prop lines at all.

**Definition:**
- *Relevant* = ECR full-PPR projection >= positional floor (QB 10 / RB 7 /
  WR 7 / TE 5) — the same floors as the points-signal gate.
- *No market read* = zero non-TD prop markets in the latest week-scoped
  odds pull. Non-TD markets are the production line markets
  (`player_pass_yds`, `player_rush_yds`, `player_receptions`,
  `player_reception_yds`). Anytime-TD-only counts as NO read — a TD line
  alone is not a pricing of the player's production. (A QB with only a
  `player_pass_tds` line likewise counts as no read.)
- *Timing rule:* the flag is only meaningful at a late-pregame snapshot.
  It is evaluated at signal-computation time and ALWAYS stamped with
  `market_read_as_of` (the newest prop `recorded_at` actually consumed).
  Midweek absences may just be unposted lines; the authoritative
  evaluation is the Sunday-morning weekly chain run.

**Rationale (revealed preference):** a book leaves handle on the table
for a relevant player only when the pricing risk beats the hold — i.e.
the player's production is too uncertain to price without getting
picked off. The absence of a line IS the variance signal. (User's
framing, 2026-09-12: "notable when ECR is there and Vegas is not —
interesting to prove that Vegas avoids high variance, and to use that
in strategy.")

**Started-game guard:** once a game kicks off, books pull props, so "no
line" means "game over", not "books refuse to price". Players whose
team's game has already started (`starts_at <= now`, UTC — the
game-status field lags) are excluded from the flag.

**Rules:**
- Informational only. `post_worthy` is ALWAYS False — no approved post
  format exists for this category, so flag rows never enter `post_queue`.
- Computed in `engine/no_market_read.py`, wired into the weekly chain
  (`v4/compute_v4.py::main`, skipped in `--dry-run`) and the game-day
  path via the same module. Flag entries ride the signals JSON with
  `category='no_market_read'` and neutral/None Vegas-side fields.
- Persisted per week in `no_market_read_flags`
  `(season, week, player_name, player_id, game_id, position, team,
  ecr_points, ecr_pos_rank, market_read_as_of, computed_at)`,
  `UNIQUE(season, week, player_name)`, idempotent replace-per-week.
  Surfaced via `v_no_market_read_latest` (latest week, with resolved
  player/game rows).

**Scorecard validation plan:** the Tuesday scorecard tracks whether this
cohort booms/busts more than same-tier prop'd players (same ECR
projection band, with production props posted). If the no-read cohort
shows systematically wider outcome distributions, the flag is validated
as a variance tag — usable both as its own signal category and as a
variance input to the lineup optimizer's matchup risk engine.

**Week 1 preliminary backfill (2026-09-12, as-of Fri ~8:41 PM CT — NOT
authoritative):** 3 flags, all TEs with TD-only markets and zero
production lines:
- Oronde Gadsden II (LAC TE): ECR 6.2 PPR, TE30
- David Njoku (LAC TE): ECR 6.0 PPR, TE31
- Connor Heyward (LV TE): ECR 5.8 PPR, TE112
11 additional ECR-relevant SEA/NE players initially flagged were
correctly excluded by the started-game guard (SEA vs NE played Thu;
their props were never pulled post-game — "no line" meant "game over").
The authoritative Week 1 list comes from the Sunday 8:05 AM chain run.
