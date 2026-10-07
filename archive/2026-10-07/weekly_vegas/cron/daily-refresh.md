# Daily refresh runbook — Weekly Signals Dashboard

Verbatim copy of the scheduler's daily job (`weekly-signals-dashboard-refresh`,
daily ~09:07 America/Chicago), which keeps the Weekly Signals Dashboard fully
rebuilt, QA'd, and re-baked every morning for the current NFL week.

---

Daily refresh of the Weekly Signals Dashboard artifact (slug `weekly-dashboard`)
so it is fully rebuilt, QA'd, and re-baked every morning for the current NFL
week. Uses the pipeline in this tree (`pipeline/`).

## Source priority (2026-09-18)

PropLine is the PRIMARY raw sportsbook-price leg (free tier, full slate,
DK/FD/BetMGM/Pinnacle). The Odds API is the SELECTIVE AUDIT leg only (targeted
raw-book pulls to verify PropLine moves; never below 66 remaining credits,
preserve the 60-credit reserve). FDS is FANTASY-ONLY coverage (translated stats
with per-stat attribution; never a wager source, never in a Vegas column).

## Steps

1. Determine the current NFL week from the schedule (after Monday night's game,
   roll to the next week).
2. Refresh PropLine: run `collectors/propline.py` (refresh is the default; it
   re-pulls current prices for all week games, ~17 requests, under the
   1,000/day free tier). Verify the pull_meta.json timestamp advanced and all
   games have 4 books.
3. Build the Vegas leg with PropLine as primary: translate PropLine props to
   fantasy points via `engine/vegas.py` (our own math, never a vendor's blended
   number). FDS fills ONLY players PropLine missed (Sunday-only,
   vegas-attributed stats only, labeled fds-derived/fds-partial). The Odds API
   audit leg runs targeted pulls where PropLine and local translation disagree
   materially; disagreements are QA findings.
4. Enforce the two-layer ECR gate, fail-closed: snapshot mtime >= most-recent
   Thu 06:00 CT AND expert content vintage <= 3 days. If stale or undeterminable,
   block the Vegas-vs-ECR comparisons for this run and say so plainly.
5. Rebuild the weekly signal v4 snapshots + signals (`v4/compute_v4.py`) for
   Standard, Half PPR, and Full PPR. Verify row counts against the previous run
   and flag any coverage drop.
6. Apply the positive-EV play gate: a flag is a "play" only with a FRESH
   (<=24h), two-sided QUOTED sportsbook line+price where the distribution-modeled
   cover probability (Poisson for TDs, normal for yardage) beats breakeven by
   >=5pp. Otherwise it's a "fantasy" read (no bet side, no wager language).
   Thursday fantasy flags require >=3.5 PPR points. Missing/stale/one-sided/
   translated-only/post-kickoff inputs fail closed.
7. Run pipeline QA (fast tier + weekly QA bundle checks). Any failure = no
   artifact bake; report the failure in the delivery message.
8. Re-bake the Weekly Signals Dashboard artifact with the fresh data. Verify
   the rendered page actually shows the new data: the freshness/health section
   must show real pull times and the provenance mix (PropLine vs Odds-API-audit
   vs FDS-fantasy counts). Never claim fresh data is displayed until bundles,
   QA, and the bake are all verified.
9. Deliver to the user each day: a short verdict-first summary (new or dropped
   signal-worthy players since yesterday, plays vs fantasy reads, coverage %,
   data vintage, provenance mix, any QA caveats) plus the artifact card.

## Hard rules

Never publish or bake on a known flaw; the market side is always called "Vegas"
— never "the market"; FDS stats are never called Vegas; say ECR, never the
underlying provider brand; free sources first, paid quota only for
audit/verification. The plays section must honestly say when there are no
verified plays. Write run logs and watermarks outside the user-facing files.
