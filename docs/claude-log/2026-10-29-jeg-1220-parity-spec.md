## 2026-10-29 - JEG-1220 trade-page parity spec

Contract: write the source-grounded parity matrix and shared-contract plan for Find a trade (your team), Find a trade
(league-wide) and Compare as `docs/specs/trade-page-parity.md`, honouring every recorded decision on JEG-1220, with
UI-only gaps separated from Jeremy's decisions and independently shippable slices ordered against open PRs. Docs only.

### Verified (check named)
- Read on `main` 5c07ad6: two read-only source inventories (finder.js, league.js, opportunities.js, workspace.js,
  team-summary.js; v2.js Compare section, trade.js, lineup-comparison.js, ddf-state.js), then spot-checked by line:
  `compareRosterContext` v2.js:5057-5066, Compare construction on `DDF_KEY` v2.js:5233-5236, `tradeFit` finder.js:745-763,
  `NET_FLOOR` finder.js:632, `EXTRA_PLAYER_WEIGHT` finder.js:26, league keep flags hard-coded league.js:1239-1240,
  league size options league.js:1048, `contextSig` opportunities.js:74-78, Open in Compare hrefs finder.js:2221 and
  league.js:895, `tradeHeadlines` only defined and exported (rg over app/v2), `slimOffer` and league `work` in
  mcp/tools.ts:433-462 and 1054-1058, finder settings defaults workspace.js:28-41 and 83-86.
- Open PR file lists from `git diff --name-only` against each branch's merge base with main (28 branches), and
  GitHub file lists for #1033, #1037 and #1057 (their merge bases are not comparable locally).
- `trade-context.js` (#1086 / #1147) and `trade-readout.js` (#1088) APIs read from their branch heads.

### Claimed, not confirmed
- No browser QA (no Chromium in cloud sessions); rendered behaviour is inferred from source.
- Line numbers will move as the listed PRs land.
- Whether the 2.2-point projections fall from the 14:24 UTC finding is inside that side's noise floor was not measured.
