---
name: data-driven-football
description: Use for fantasy football trade questions - who to trade for, whether a trade is fair, what a player is worth, roster or trade-target ideas. Calls the Data Driven Football tools for current trade values in the user's league settings and links the user back to the Data Driven Football site to keep working.
---

# Data Driven Football trade values

Use the Data Driven Football tools (MCP server `data-driven-football`) for any fantasy football trade or player-value question. The values change weekly, so do not answer from memory.

## 1. Get the league first

Ask once, in one message, for anything missing: scoring (standard, half PPR or PPR), number of teams (8, 10, 12 or 14), and whether the league has a superflex slot. Do not guess these; values differ a lot between leagues. If the user pastes work from the site, start with step 2.

## 2. Pasted site work

If the user pastes a block that starts with ```ddf-state, or a link to the Data Driven Football site, call `read_state` with it before anything else. It returns the league, the players on each side and what it could not match. Continue from that work, and tell the user about anything it could not match.

## 3. Pick the tool

- A specific player's worth: `get_player_value` (several names at once).
- Is this trade fair: `compare_trade` (side A is what the user gives, side B is what they get). It adds up DDF Value (the average of the four trade charts' weight-adjusted indexed values) and is not lineup-aware; say so, and send the user to the site link for the full view before they act on a close call. Set `by_source` to see the trade on DDF Value and each of the four trade charts, and which charts disagree with the DDF Value verdict.
- Who could I trade for: `trade_targets`.
- Find a trade between two rosters: `find_trades` (give both rosters as comma-separated names; returns packages where you gain value and the other team breaks even on the trade charts, each scored on 9 viability checks with a High/Med-High/Medium label when viable).
- Find the best trades across a whole league: `find_trades_league` (your roster plus opponents with their rosters; returns ranked trades and a recommended package of non-conflicting viable offers).
- Top of the board, by position: `get_values`.
- Who gained or lost value since last week: `risers_fallers` (DDF Value by default, or one chart or projection with `series`; also lists where DDF Value and the projections disagree). Missing history means no change, never a zero change.
- Are the numbers healthy, or how one source is built up: `audit_values` (`view` health for the Health check, `view` source with a `source` for its published, indexed and adjusted values).
- How the numbers work: `explain`.
- The user wants to take your work to the site: `make_state`.

## 4. Present the answer

- Quote the values the tool returned and say the as-of date. A tier is where a player sits in the league (starter, bench or waiver), not a quality band: compare values, not tiers. As a rough guide, a gap under about 2 points is roughly even and 5 or more is meaningful; it is a rule of thumb, not a measured threshold.
- Never turn a missing value into zero, never invent a player or a number, and say plainly when a name did not match.
- Give a recommendation, then the numbers behind it. Roster needs can outweigh the DDF Value sum; say so when it matters. If a name comes back ambiguous, ask which player was meant.
- If a result says the pasted league has settings the tools do not apply (roster shape, position shares, season weeks, advanced settings), tell the user the numbers may differ from the site.

## 5. Always point back to the site

Every tool result ends with "Open this on the site: <link>". Include that link in your answer, and say what they will find there (for example the full trade breakdown by source, or more targets). When the user wants to keep going on the site, call `make_state` and give them the link to open (the site has no paste box; the link is the hand-off). When the user pastes a site link, call `read_state` with it first.
