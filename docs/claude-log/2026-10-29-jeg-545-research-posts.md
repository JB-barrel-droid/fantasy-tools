## 2026-10-29 - JEG-545 refresh research posts 4, 5 and 6

Contract: bring posts 4 (rescaling), 5 (missing, zero and one-source rules) and
6 (trade confidence) up to the rules on main with reproducible current
examples, cited code evidence and a stale-claim checklist. Drafts only; no
value math, default, ranking rule or design changed; not published.

### Verified (check named)
- DDF Value is the four charts' Adjusted values and projections are the
  alternate: read `docs/methodology.md` VP-6.3, `pipelines/value_reference.py`
  `DDF_FAMILY`, `app/v2/v2.js` `DDF_ROW_TIPS`.
- Unlisted chart at a priced position is 0, projection gap is null: read
  `value_reference.row_value` and `value-model.js` lines 1363-1368.
- The Compare propose/accept headline is not rendered: `rg tradeHeadlines app`
  finds no caller outside `trade.js`; `git log -S "tradeHeadlines(" --
  app/v2/v2.js` shows it removed in 90cc8f5 (#947).
- Every figure in the three posts: `python3 tools/research/posts04_06_readout.py`
  (reference engine, fixture built 2026-10-28 23:27 UTC, week 8), outputs in
  `docs/research/data/posts04_06/`.
- One factor keeps every pair's order on all four charts this week
  (`one_factor_inversions` 0 in post04.json).
- Worked Compare example matches the site's own `app/v2/trade.js` `dealRead`
  run in node (`site_deal_read` in post06.json).
- No open PR touches the three posts or the research README (file lists of all
  32 open PRs read through the GitHub API).

### Claimed, not confirmed
- Engine parity for these exact figures rests on `value_check` (not rerun
  here); the browser engine was not run headless.
- `make validate` was not run: the change is docs plus a standalone research
  script that nothing imports.
