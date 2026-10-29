# Compare evidence view: contract (JEG-1271, part of JEG-1138)

An isolated Fieldnotes presentation of a trade comparison's evidence. It renders outputs that already exist
and computes nothing. It is not hooked into the site: no page loads it yet, and `v2.js`, `v2.css`,
`shell.html`, `trade.js`, the shared readout and the build are untouched. Runtime hookup stays with the parent
JEG-1138 after the JEG-1137 foundation, JEG-1130 copy and JEG-1260/JEG-1259 readout and context work.

Files: `app/v2/compare-evidence-view.js` and `.css`, `tests/test_compare_evidence_view_contract.py`,
`tests/test_compare_evidence_view_render.py`, `tests/fixtures/compare_evidence_view/cases.json` and
`preview.html`.

## What it renders, and from where

| Part | Input field | Comes from today |
| --- | --- | --- |
| Verdict title, text, production line | `verdict` | `TradeValueTrade.dealRead(give, receive, chartKeys)`, unchanged. The title follows `renderDeal`'s rule: the action is added unless the title already contains it. |
| Three nets (value, market, projections) | `verdict.value` / `.market` / `.projections` plus `nets` (`{id, name, question}`) | `dealRead`, and the names/questions of `DEAL_NETS` in `v2.js`. Shown as `renderDeal` shows them: the net and side word, "Not enough charts" when `tooFew`, the split range when `split`, the missing mark when null. |
| Evidence groups | `groups: [{id, label, rows}]` | One group per JEG-1212 category (`DDFSourceViews.CATEGORIES`: Published charts, Observed-trade estimates, Projections). Each row is a `compareTrade` row (`{key, give, receive, net, missing}`) plus its `label`, and `held: {reason}` for a held source. |
| Conflicting mark | `againstKeys` | `tradeVerdict(rows, verdictKey).againstKeys`: the complete series that see the trade the other way. |
| Explanation, disclosures | `explanation: [line]`, `disclosures: [{id, summary, lines}]` | Existing explanation text (the Compare footnote, `NAME_DEFS`). |
| All other words | `copy` | Supplied by the caller: side words, missing mark, "Held", "no value", give/receive names, the three direction labels of `netLabel`, the conflicting label and the three section headings. |
| Synthetic marker | `synthetic`, `syntheticLabel` | Required to be stated. A synthetic input must carry a visible label; every fixture does. |
| Shared readout | none | An opaque slot. `mount(root, input, {readout(slot)})` lets the readout owner (JEG-1260) fill it once. The view never reads, clears or rebuilds it; `update()` moves the same node. |

The only text the module writes itself is the two number formats copied from `v2.js` (`fmtGap` for nets,
`fmt` for totals; the contract test checks them against the `v2.js` source) and the separators
`" · "`, `" ("`, `")"`, `": "`, `" "`, `", "`.

## Evidence states (per series row)

| State | When | Shows |
| --- | --- | --- |
| complete | `net` is a number other than 0 | the net, its `netLabel` direction, both side totals |
| zero | `net === 0` | `0.0`: a real value, never the missing mark |
| missing | `net === null` | the missing mark and each missing player with `copy.noValue`; never 0 |
| held | `held.reason` given | `copy.held` and the reason; no number |
| conflicting | a complete row whose key is in `againstKeys` | the complete row plus `copy.conflicting` |

## What it does not do

No sums, sides, thresholds, confidence, ranking or defaults; no choice of a winning model or view. Groups render
in input order with identical markup and styling, and nothing totals across them. Published charts, observed
trades and projections are never merged (a series named in two groups is refused). No engine, `localStorage`,
network, route or share-state access; inputs are read only (the tests run on deep-frozen input).

## API (for JEG-1274's detail slot)

`window.CompareEvidenceView` (or `module.exports`):

- `adapt(input)`: validates the contract and returns the view model; throws on a violation.
- `tree(model, {open, idBase})`: plain `{tag, attrs, children}` / `{text}` nodes, no DOM. `texts(node)` lists the text nodes.
- `toDom(document, node)`, and `mount(root, input, {readout})` returning `{update(input), readoutSlot, element(), destroy()}`.
  `update` keeps open disclosures, focus on a disclosure toggle, and focus on a control inside the readout slot
  (moving the slot blurs it; the view focuses it again, JEG-1294).
- Ids (headings, disclosures) carry `idBase`; a `tree()` call without one gets a fresh prefix, so two direct
  calls never share an id.
- The parts: `verdictTree(model)`, `netsTree(nets, copy)`, `evidenceGroupTree(group, copy)`, `disclosureTree(d, idBase, open)`.
- `format.gap`, `format.value`, `SEPARATORS`.

Disclosures are a native `<button aria-expanded aria-controls>` and a labelled `region`, so Enter and Space work
and focus stays on the button. Toggles are at least 44 px tall; the +/− glyph is CSS on an `aria-hidden` span,
so it is not part of the button's name. Sections are named by their own headings (`aria-labelledby`).

## Layout

Single column at phone widths; evidence groups go side by side from 900 px. Long names wrap
(`overflow-wrap: anywhere`, `min-width: 0` on grid children). Colours, type and spacing use the JEG-1137
Fieldnotes tokens with the same light values as fallbacks, so the preview renders without `v2.css`.
The view's resets (box sizing, margins, list style) stop at the readout slot, and the slot undoes the view's
`overflow-wrap`; colour and font still inherit from the page, as they would around any readout. The 900 px switch
follows the viewport, not the container; the render test asserts stacked at 320/390 and side by side at 1280.

## Checks

```
python3 -m unittest tests.test_compare_evidence_view_contract
python3 -m unittest tests.test_compare_evidence_view_render     # needs Playwright + Chromium; CEV_SCREENSHOT_DIR=... saves 320/390/1280 shots
```

The contract test recomputes every fixture's verdict, rows and `againstKeys` with the current `trade.js` and
fails if they drift, so the fixtures stay real current branches. It also checks each label by position against
its own copy key and reruns every case with all caller-supplied words altered, requiring every rendered word to
follow (JEG-1294), so a hard-coded literal or a word from the wrong key fails. Both tests run in `test-core`
(shard 4), so the preview CI runs them on every PR.

Preview: serve the repo root (`python3 -m http.server`) and open
`/tests/fixtures/compare_evidence_view/preview.html`, optionally `?case=<id>`.
