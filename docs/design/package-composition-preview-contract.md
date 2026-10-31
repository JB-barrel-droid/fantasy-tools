# Selected-package composition preview: contract (JEG-1275)

Part of JEG-1183. An isolated component that shows a package of trades someone else has already chosen. It is not the
optimizer, and it does not finish JEG-1183.

Files: `app/v2/package-composition-preview.js` and `.css` (global `TradeValuePackagePreview`). Tests:
`tests/test_package_composition_preview_contract.py` (node, no browser) and
`tests/test_package_composition_preview_render.py` (Playwright). Fixtures: `tests/fixtures/package_composition_preview/`
(`cases.json`, `preview.html`), all synthetic and labelled so on screen.

## What it shows

- The trades in the order given, each with its counterparty and the players listed on each side, behind a keyboard
  disclosure (a button with `aria-expanded` and `aria-controls`).
- Counts of the shown composition only: trades shown, distinct counterparties named, players listed to give and to get.
  A player listed twice counts twice; whether that is allowed is the roster check's answer, not the count's.
- The roster check: passed, failed (every supplied error, in the supplied order, with the supplied text), unavailable, or
  not checked (empty selection). Every trade stays on screen; a trade is flagged when a supplied error names its
  `tradeIndex`.
- The final lineup, only from a separately supplied lineup adapter, before and after, row for row as supplied.

## What it never does

- Select, rank, search, sort, price or re-order trades or packages. A reversed package renders reversed.
- Re-implement the JEG-1262 rules. The roster check is injected; the preview only reads its answer.
- Show `applyPackage`'s rosters as a lineup. They keep each player's recorded slot (the synthetic fixture ends with three
  "RB" slots), so without a lineup adapter the section says "Final lineup unavailable" and `applyPackage` is not called.
- Recalculate, fill or re-slot a lineup. An empty starting slot is shown as "Empty" and the lineup is marked incomplete.
- Write storage, fetch, or mutate its inputs (tests run on deep-frozen inputs under strict mode).

## Context

```
{fixture?: {kind: "synthetic" | "historical", label},
 league:  {myTeamId, teams: [{id, name?, entries: [{key, name, pos, slot?}]}]},     // as JEG-1262 reads it
 trades:  [{opponentId, give: [ref], receive: [ref]}] | null,                       // preselected, in order
 package: {validatePackage(league, trades), applyPackage(league, trades)} | null,   // the JEG-1262 adapter
 lineup:  {lineups(league, appliedLeague) -> {before, after, complete?, missing?: [text]}} | null}
ref  = key string | {key} | {player_key}, optionally with name
side = {starters: [row], bench: [row]};  row = {slot, key, name}
```

The roster-check answer must be `{ok: true, errors: []}` or `{ok: false, errors: [non-empty]}`. Anything else (missing
adapter, a throw, an unreadable or self-contradicting answer) is "Roster check unavailable", never "passed". The lineup
is asked for only when the check passed, a lineup adapter is supplied and `applyPackage` returns `{ok: true, league}`.

## Runtime hook (not in this ticket)

Waits on the reviewed JEG-1262 helper (PR 1116) and a real lineup adapter owned by JEG-1249 / JEG-1230. Tokens and the
shell stay with JEG-1137. `finder.js`, `opportunities.js`, `league.js` and shared UI are not touched.

## Known limits

- The JEG-1262 error text counts trades from 0 ("trade 0 names z") while the preview numbers trades from 1. The text is
  shown as supplied; a wording change belongs to the helper's owner.
- A duplicate-counterparty error carries one `tradeIndex` (the later trade), so only that row is flagged.
- The render test needs Chromium. It skips locally without one and errors under `RENDER_TESTS_REQUIRED=1`. It is not
  yet in a Makefile run list or workflow (the CI coordinator owns that wiring).
