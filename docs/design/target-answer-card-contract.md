# Trade target answer card: component contract (JEG-1274)

An isolated, presentation-only card for one trade target answer. It is part of JEG-1139 (targets rollout) and is not
wired to the targets route yet: that hookup waits on the JEG-1137 foundation, the JEG-1138 evidence handoff and the
JEG-1130 / JEG-1212 copy, and the coordinator serializes it. Files: `app/v2/target-answer-card.js` and `.css`.

## What it does and does not do

- Shows a supplied, precomputed answer: stable player identity, Buy / Sell / Fair price, the reasons, the values and
  which sources priced the player.
- Computes nothing. No gaps, medians, ranks, thresholds, defaults, sorting or filtering. It does not import the engine
  or `targets.js`, reads no storage, and makes no network request.
- Never mutates its input. A deep-frozen input works.
- The evidence detail is an injected slot. The reusable evidence internals belong to the Compare evidence view
  (JEG-1271); this card only mounts what `renderDetail` draws.
- No manager recommendations, Values table, QB treatment or new numerical, ranking or design policy.

## Input (one answer)

```js
{
  status: "ready" | "empty" | "unavailable",          // default "ready"
  fixture: {kind, label} | undefined,                // shown as a visible label when present (synthetic data)
  player: {id, name, pos?, team?},                   // id and name are required non-empty strings: the id is the identity
                                                     // (a numeric id gives the missing state, so the adapter stringifies it)
  answer: {side: "buy" | "sell" | "fair", reasons: [string]} | null,
  values: [{key, label, value: number | null, display?: string, reason?: string}],
  sources: [{key, name, status: "priced" | "waiver" | "missing" | "unavailable", value?, display?, reason?}],
  missing: [string],                                 // why there is no answer (missing state)
  message: string,                                   // optional text for empty / missing
  reason: string,                                    // why answers are unavailable (unavailable state)
  detail: any | null                                 // handed to renderDetail as is; null means no detail disclosure
}
```

The adapter that builds this from `TradeValueTargets.buildTargets` output is part of the route hookup (JEG-1139),
not this card. It decides the side; the card only shows it.

## States

| State | When |
| -- | -- |
| `buy`, `sell`, `fair` | `status` is `ready`, the player has an id and a name, and `answer.side` is that side |
| `empty` | no input, or `status: "empty"` (shows `message`, else a placeholder) |
| `missing` | `status` is `ready` but there is no answer, the side is unknown, the identity is incomplete, or the status is unknown. Shows `message`, the `missing` reasons and whatever values and sources were supplied |
| `unavailable` | `status: "unavailable"` (shows `reason`) |

## Numbers

One rule, `valueText`: a non-empty `display` string is shown verbatim; otherwise a finite number is shown as the number
itself (`String(value)`, so nothing is rounded), with `-0` shown as `0`. A real `0` is a value and shows `0`. A null,
absent or non-numeric value shows "No value" and its `reason`, never `0`. A source with status `missing` or
`unavailable` shows no number. The raw number is kept on `data-value` for checks. Because nothing is rounded, the
adapter passes a `display` string wherever the page shows a formatted number (one decimal, a sign), so the card
matches the page.

## Mount API

```js
const handle = TradeValueTargetAnswerCard.mount(el, {
  renderDetail(slot, detail, {playerId, state}) { /* draw; optionally return a cleanup function */ },
  labels: {buy: "…"},     // optional word overrides; the defaults are placeholders until approved copy
  headingLevel: 3,         // 2 to 6, default 3
});
handle.update(input);      // render or re-render
handle.open("sources" | "detail"); handle.close(key); handle.isOpen(key);
handle.destroy();
```

- Two disclosures, Sources and Evidence details (the second only when `detail` is supplied and `renderDetail` is given), are buttons with `aria-expanded` and `aria-controls`, closed by
  default, at least 44 px tall. Enter, Space, a click or a tap toggles; Escape inside an open panel closes it and
  returns focus to its toggle. Both act only on this card's own nodes and an Escape the card handles does not
  bubble further, so a card inside a detail slot or a page-level Escape handler is left alone.
- Open state lives in the handle only. It survives `update` with the same player id and resets when the id changes.
- Focus on a toggle survives a re-render. Focus inside the detail slot is the slot's own concern: the slot is
  re-mounted on re-render.
- `renderDetail` runs when the detail opens (and again after a re-render while open); its cleanup runs before every
  re-render, on close and on destroy. A throwing renderer leaves the card up with "Details could not be shown."

Pure helpers for tests and server-side checks: `viewModel(input, labels)` and `markup(vm, {uid, open, headingLevel})`.

## Checks

```
python3 -m unittest tests.test_target_answer_card_contract   # pure Node: states, exact values, zero, identity, frozen input, escaping, no storage/network/engine, plus a break-it proof per rule
python3 -m unittest tests.test_target_answer_card_render     # Playwright: every state at 1280, 390 and 320, keyboard, touch, focus, slot cleanup, no storage or network
TARGET_ANSWER_CARD_SHOTS=/tmp/tac python3 -m unittest tests.test_target_answer_card_render   # with screenshots
python3 -m http.server 8000   # from the repo root, then open /tests/fixtures/target_answer_card/preview.html (?case=buy for one)
```

Fixtures: `tests/fixtures/target_answer_card/cases.json` (synthetic, visibly labelled) covers buy, sell, fair, empty,
missing, unavailable, a real zero (including `-0` and a source at its waiver line) and a long name.

Neither module is in a Makefile run list yet: wiring belongs to the CI owner (proposed in the PR).
