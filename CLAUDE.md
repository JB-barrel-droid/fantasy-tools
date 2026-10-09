# Working agreements for AI sessions in this repo

Read this first. It is short on purpose.

## Pre-launch: ship, and keep the numbers honest

Jeremy, 2026-10-07: the site has no users yet. One owner (Claude) writes,
reviews and merges, so the multi-agent policing built up in late September has
been retired. Optimize for getting fresh data live every week. Protect only what
makes the numbers worth looking at. Methodology can be refined after launch.

The live plan is the Linear ticket **JEG-440 (GO LIVE)**. Linear is the source
of truth for status: at most 3 tickets In Progress, and Done means merged and
live.

## Linear (team Jegabee, project Trade Value Chart)

Follow the user-level "Work Tracking in Linear" rules for all work here. They
cover: a ticket per workstream, status comments, decisions quoted on the
ticket, delegated agents naming their ticket, and "(part of JEG-xxx)" PR titles.

- The back end owns tickets for pipelines, Supabase, engine math and
  workflows. The v2 front-end session owns its own tickets.
- Front-end requests that need engine or data changes become back-end
  tickets, linked to the front-end ticket.
- Fidelity findings from the pulse, an audit or a reviewer get a ticket
  (Urgent if live numbers are wrong) and a row in `docs/risk-register.md`.

## Standing constraints

- **Finish end to end.** For a fix, refresh or deploy repair: commit, merge to
  `main`, wait for GitHub Actions, and check the live site when published
  output changes. Stop only if Jeremy says not to publish, the change needs a
  force push or history rewrite, or it is a production Supabase schema change
  he hasn't approved.
- **Block only on the data math.** `make validate` is the deploy gate. It runs
  the build plus `make test-core`: curve shapes and starts, missing values
  never shown as zero, source integrity, and the published surfaces the page
  needs. The full suite (`make test-unit`) runs in preview CI and does not
  block. Staleness, review holds, coverage drift, import health and monitoring
  are warnings: label them on the page and don't stop the site.
- **Bug fixes ship with a test that fails without the fix.** That test is the
  proof. No PR checklist or written proof is needed.
- **Do not adjust tests to go green.** If a test fails, assume the code is
  wrong. Change an assertion only when the assertion itself was wrong or the
  rule it pins was changed by Jeremy, and say which in the commit message.
- **The commit message and PR description are the record.** Say what you
  verified (name the check) separately from what you assumed. No separate
  session log is required; `docs/claude-log/` is kept as history.
- **`make sync` is the single publish path** and stamps the build tag. Do not
  re-add `dist/static`, `dist/server`, `space.json` or `deploy.sh`.
- **Do not touch `~/Projects/"fantasy tools"`** on the user's machine beyond the
  `Claude outputs/` folder. It holds `data/raw` (33MB, gitignored), the only
  copy of the player-news pipeline's inputs.
- **Muse owns nothing here.** Claude owns merges, deploys, QA and schedules.
  Schedules run from Supabase pg_cron; GitHub Actions does the build and deploy.

## Copy rules (user-facing text)

- Do not reference "Vegas" (Jeremy, 2026-09-30). The public charts are named by
  publisher (USA Today, FantasyCalc, FantasyPros, CBS). Frame comparisons as
  trade targets (sell where a chart pays more than we would, buy where less).
- No abbreviations in titles or headlines (PPR, FC, USAT, FP, Wk).
- The brand is **Data Driven Football** only. No FantasyPros, Muse, or Meta
  branding anywhere user-facing.
- The only allowed user-facing use of "VORP" is the exact phrase **"VORP vs
  waivers"** (decision copy-vorp-001). `espn_vorp` as an internal data key is
  exempt.

## Before changing the trade-value chart

Run the 12-combo headless sweep (3 scorings × 4 league sizes) against the built
`dist/`, and check `fixedPieIndexed` in `TradeValueCurveDiagnostics` for each.
Pie totals agreeing across sources proves nothing about curve shape: compare
where each position's curve starts. Since JEG-482 (2026-10-09), Indexed is one
order-preserving factor per chart and league setting, with no per-position
correction layer and no cap at 70. A published chart's curve therefore starts
where its own values put it, and it must keep the publisher's ranking:
`pipelines/check_rank_guard.py` and `tests/test_rank_guard.py` must show zero
inversions. The ESPN, CBS ROS and Razzball lines also start where their own
projections put them. (`sourceScaleAgreement`, the peak-vs-anchor
band on published charts, was retired 2026-10-08, GAP-026: publisher shape
disagreement is the product.)
