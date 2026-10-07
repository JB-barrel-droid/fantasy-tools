# The Odds API — NFL kicker & DST market check (2026-09-16)

Verified live against the v4 API (skill: `~/workspace/skills/the-odds-api/`).
Test event: Detroit Lions @ Buffalo Bills, 2026-09-18 00:15 UTC (Thu-night game).
Total quota spent on this check: 7 credits. Remaining after check: **58 / 500**
(used 442, free tier resets monthly).

## 1. Kicker markets — EXIST, live on the free tier

All six market keys returned data on a single event-odds request (6 credits, all
markets had data × 1 region):

| Market key | Bookmakers offering |
|---|---|
| `player_kicking_points` | draftkings, betmgm, bovada |
| `player_field_goals` | draftkings, betmgm |
| `player_pats` | draftkings, betmgm |
| `player_kicking_points_alternate` | draftkings |
| `player_field_goals_alternate` | draftkings |
| `player_pats_alternate` | draftkings |

- **2 kickers priced** for the game: Jake Bates (DET) and Tyler Bass (BUF) —
  every listed market above covers both kickers at DraftKings.
- Books on the free tier: draftkings, betmgm, bovada all have live kicker props;
  fanduel/betonlineag did not show kicker markets for this game.
- These are **per-game** props, not season-long.

Implication for the K build: the earlier "kickers must be experts-only"
recommendation is **superseded for weekly values**. Kickers can have a genuine
weekly Vegas leg via `player_kicking_points` (+ FGs/PATs as component legs).
Alternate lines exist only at DraftKings — use the base lines, not alternates.

Quota note for a weekly collector: requesting the 3 base kicker markets across
~16 games = ~48 credits/week only if all three markets have data for every
game. At ~3–6 credits/game, a Thu-night-focused subset or sampling is safer;
cap spend and keep the 60-credit reserve guard used by the v1 collector
(`~/workspace/football-signal/collectors/odds_api.py`).

## 2. Team defensive markets — NONE exist

Requesting these market keys for the same event returned **HTTP 422
INVALID_MARKET** (`team_defensive_tds, team_fantasy_points, team_interceptions,
team_sacks, team_turnovers`). Cost: 0 (error response, no data).

There is no API surface for:
- team sacks
- team takeaways / interceptions
- defensive TDs
- team DST fantasy points
- any "team defensive" market

Implication for the DST build: DST has **no direct market leg**. DST Vegas
input must be explicitly **derived**, e.g.:
- `team_totals` (confirmed live — see below) for opponent implied points,
- spread + game total → game script,
- historical game-script relationships to sacks/takeaways/PA brackets.

Do NOT present summed individual IDP sack/interception props as a DST market —
no such team market exists.

## 3. Opponent team totals — live (the DST input leg)

`team_totals` for the same game (1 credit): fanduel, betonlineag, betmgm all
posting. Example: Bills 30.5 (Over -108 / Under -118 at FanDuel),
Lions 24.5. Opponent implied points are directly readable and give the DST
points-allowed anchor.

## Quota status

- Free tier: 500/month. `/v4/sports/` and `/v4/sports/{sport}/events` cost 0.
- Event-odds cost = (unique markets with data) × regions. Bookmakers do not
  add cost (up to 10 = 1 region).
- **Remaining: 58 credits** as of 2026-09-16 ~18:40 CT (used 442, mostly from
  earlier season-futures pulls). The daily/season-loop consumers need to be
  careful until the monthly reset — prefer the free endpoints and minimal
  markets until quota refreshes.
