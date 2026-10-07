# Current Plan

This is the only live plan file. Keep it short; move completed investigation
details to `docs/claude-log/` and durable gaps to `docs/risk-register.md`.

## Objective

Pre-launch: keep fresh, correct numbers live every week and ship the v2 front
end tab by tab. Block only on wrong numbers (see `docs/methodology.md`, "The
Three Views").

## Current Tasks

- [x] Week 5 on the live chart for FantasyCalc, USA Today, FantasyPros
  (2026-10-07). Ingests ask for the publisher week; FantasyPros saves in CI.
- [ ] CBS Week 5: the daily `trade-chart-ingest` picks it up once CBS posts.
  Confirm it lands; nothing to do unless it doesn't.
- [x] #387 merged: Value above waivers and Adjusted views at every league
  setting.
- [x] v2 Player values live at `/v2/`.
- [ ] v2: build the next tab (Figma frame 03, Market disagreement), same
  engine-wrapping approach (`docs/v2-design-notes.md`).
- [ ] Open number/page issues in `docs/risk-register.md` still marked `Open`
  (e.g. GAP-025 injured players priced, GAP-041 ESPN scrape, GAP-043 freshness
  display).

## Operating Rule

Do not add a second backlog, plan, or gap tracker. Use:

- `execution/current-plan.md` for the live task list.
- `docs/risk-register.md` for durable gaps and follow-ups. Rows marked
  `Deferred (pre-launch)` are gates/monitoring/process, parked by decision.
- `docs/claude-log/` for session evidence.
