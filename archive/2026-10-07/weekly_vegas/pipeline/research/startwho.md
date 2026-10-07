# StartWho — Competitive Research Memo

*Researched 2026-09-10 via startwho.com and web search. No accounts created.*

## What StartWho is

**StartWho** (startwho.com, tagline "Trust the Market") is a fantasy rankings product built on the exact props-to-fantasy translation the user described. Its homepage states the pipeline explicitly:

1. Fetch player prop bets from 5+ major sportsbooks
2. Aggregate lines for passing yards, TDs, receptions, etc.
3. Convert to fantasy points using standard scoring
4. Rank players to help you make fantasy decisions

Positioning is openly anti-expert: *"Forget 'expert' opinions… Traditional fantasy sites rely on subjective 'expert rankings.' We use live betting market data."* So the user's belief is confirmed — StartWho already translates Vegas props into fantasy points, and it's their core mechanic, not a side feature.

**Product surface (observed):**
- Weekly rankings pages per sport: NFL, NBA, MLB, NHL, EPL tabs
- Table columns: Rank | Player | Pos | Proj | **Vegas** — the Vegas column is a percentage (mostly 100%, lower for deep-bench players/DSTs, e.g. DST1 49%), which reads as sportsbook coverage of that player's props
- Tabs: weekly rankings, **Draft Rankings**, and **Results**
- Email capture: "Get Projections in Your Inbox" (weekly projections newsletter)
- X account: @StartWhoFantasy
- Pages carry a "Last updated" timestamp (e.g. Sep 10, 2026, 5:01 PM UTC) — rankings refresh intraday

**Pricing:** No pricing page or paywall observed; email signup appears free. (Caveat: not definitively confirmed — they may monetize later via the list.)

**Who it's for:** Season-long fantasy managers making start/sit and draft decisions. Not DFS-focused (no salaries, ownership, or lineup builder) and not betting-focused (no odds recommendations or edge calls — the market is an input, not the product).

**Company:** Soni Digital LLC — the same shop behind **PickWho**, a separate free pick'em game app (pick winners, win ad-funded cash prizes; $2.99/mo Premium removes ads). PickWho is a different product; StartWho is the fantasy-rankings one.

## Where StartWho already does "accountability"

This is the uncomfortable finding: StartWho has a **Results: Projections vs Actuals** section (startwho.com/nfl/results). Each week's projections are **frozen at kickoff** and kept next to real box scores, with a line-by-line per-player comparison and aggregate stats: players projected, graded count, **avg miss**, and **within-3-pts rate**. That is genuine public grading, including the misses. Our "publish complete scorecards including failures" idea overlaps with this significantly.

## What StartWho does NOT do (gaps)

- **No expert comparison at all.** StartWho is market-only by ideology. There is no ECR, no individual ranker, and therefore no *disagreement* signal — the concept our product is built around doesn't exist there.
- **No change detection or alerts.** Rankings refresh intraday, but there's no feed of what changed, no new/widening/closing gap events, no push or post when a prop appears or a line moves into disagreement. It's a static board you have to re-check.
- **No intraday movement history.** Only the kickoff-frozen snapshot is kept. How a player's market-implied rank moved Tuesday→Sunday is not visible.
- **No per-ranker granularity.** Nothing about *which* experts the market disagrees with.
- **Signals aren't graded — projections are.** StartWho grades "was our projection close to actual." Nobody grades "did the market-vs-expert gap identify value," because nobody publishes the gap.
- **Standard scoring only** (per their homepage) for the prop conversion; no PPR/half-PPR flexibility observed.
- **No social/event layer.** The X account exists, but there's no evidence of automated disagreement posts or a change-driven content engine.

## Differentiation assessment

**Real differentiation (defensible):**
1. *The disagreement is the product.* StartWho publishes market-implied ranks; we publish where the market and the experts disagree, as ranked, tradable signals. Different question, different answer.
2. *Event-driven, not board-driven.* New gap / widening / closing / final-call / scorecard posts are a content engine StartWho doesn't have.
3. *Per-ranker comparison.* "The market disagrees with ECR by 12 spots on Player X, driven by rankers A, B, C" — a dimension StartWho structurally can't produce.
4. *Grading signals, not projections.* Our scorecard answers "did betting the disagreement win?" — adjacent to StartWho's "was the projection accurate?" but a distinct, bettor-relevant metric.

**Thin or overlapping (do not claim):**
1. *Props→fantasy translation.* StartWho does this today, publicly, as its headline feature. Claiming novelty here would be false.
2. *"Trust the market" positioning.* They own that narrative. Our frame should be the *tension* (market vs. experts), not market supremacy.
3. *Public accountability / grading failures.* They freeze at kickoff and publish avg miss. Our version is differentiated only in *what* gets graded (signals vs. projections) — say that precisely.

**Where StartWho is strong (respect it):** multi-sport coverage, a clean weekly-board UX, real kickoff-frozen accountability with aggregate accuracy stats, free email distribution, and an existing X presence. It's a finished consumer product; ours is earlier. The gap in the market isn't "props to fantasy points" — it's everything that happens *between* the market and the experts, *as it changes*, graded afterward.

## Bottom line

StartWho validates the core translation approach (good — it means the mechanic works as a consumer product) but leaves the entire disagreement-and-change layer untouched. Our product should never pitch itself as "fantasy points from props" — that's StartWho's sentence. Ours is: "we watch the fight between the market and the experts, tell you when it changes, and keep score."
