# Methodology section: page outline (draft)

Draft for Jeremy's review (JEG-1105). Nothing here publishes. It lists the pages a reader-facing Methodology section would hold under a "Learn" group in the menu, what each page is for, where its facts come from, and which pages cannot be finished until JEG-1081 (two-DDF naming and defaults) is decided. Last updated 2026-10-25. Branch `docs/JEG-1105-methodology-outline`.

Copy rules for every page (lane rules, research posts are public-facing): no internal references, define every term and constant on first use, no vanity stats, no abbreviations in titles, sentence case, plain words.

## Today, in the app

The Writing tab (`#writing`) holds three sections: Manifesto, How values work, Research (`app/v2/shell.html`, `docs/v2-design-notes.md` "Writing tab"). "How values work" (`#v2How`) already says: two numbers for every player (DDF Value and Trade chart average), where the edge comes from, three method cards (projections priced for your league, rescaled trade charts, value over a waiver player), "Your league shapes the comparison" (position weights, bench share), a link to the full value logic page, and six reading rules (methods can disagree, missing is not zero, zero is real, older weeks are opt-in, week changes compare one source, label and symbol).

## Proposed pages

| # | Page title | One-line purpose | Draws from | Waits for JEG-1081? |
|---|---|---|---|---|
| 1 | What DDF Value is | Define the one number: an equal-weight average of each included source's value after it is put on your league's scale. | `docs/methodology.md` "Live and pending" (JEG-1073), VP-6; `docs/manifesto.md` section 1 | Yes. Which view is called "DDF Value" and which is the alternate is the open naming question. |
| 2 | The two DDF views | Explain the Trade Charts view and the Projections view side by side, and when to read each. | `docs/methodology.md` VP-6, "DDF Composite Value"; JEG-1073 impact report (see `ddf-two-views-article-outline.md`) | Yes (names, which is the default). |
| 3 | How sources are rescaled | Show how each publisher's own scale becomes a common scale without changing that publisher's ranking order. | `docs/methodology.md` VP-2, VP-5, VP-6.4 (Indexed); research post 04 | Partly. Body is stable; the word "Indexed" vs "Rescaled" in labels follows JEG-1081 if names change. |
| 4 | Position weights | Say how a league's total value is split across QB, RB, WR, TE, starters and bench, and why the split moves with league size, scoring and superflex. | `docs/methodology.md` VP-3, VP-4, "Superflex"; existing "How position weights work" paragraph in `shell.html` | No. |
| 5 | Bench share | Explain what share of a bench player's value reaches a lineup (expected starts) and where the readout lives. | `docs/methodology.md` ES-0 to ES-14, "Expected-starts value"; `docs/research/bench-share-*.md`; research posts 01, 02 | No. |
| 6 | The waiver line | Define "value above waivers": the value of the first player past what the league rosters, and why zero means at or below it. | `docs/methodology.md` VP-2, VP-0 definitions; reading rules in `shell.html` | No. |
| 7 | Trade confidence | Explain High, Medium and Low on the two headline answers (propose or accept, will they accept), what agreement means, and the thin-margin rule. | `docs/v2-design-notes.md` "Compare a trade: headline answers with confidence" (CT-02); research post 06 | Partly. The "agreement" series for line 1 may change if the default view changes. |
| 8 | Fit labels | Define Natural fit, Value fit, Market fit and Force fit in plain words with the numbers. | `docs/product/fit-label-glossary-draft.md`; `app/v2/finder.js`, `app/v2/opportunities.js` | Yes for the Natural variants (charts only / projections only). |
| 9 | What each tool uses | One table: for each tool (Trade targets, Compare a trade, Find a trade, Waivers, Risers and fallers, Player values, assistant connector) which value and which view it reads. | `docs/v2-design-notes.md` per-tab sections; `docs/contract/`; JEG-1073 impact report section 3 | Yes. Defaults per tool depend on JEG-1081. |
| 10 | Using the values in Claude and ChatGPT | How to connect the values to a chat assistant. | `docs/use-ddf-in-claude-chatgpt.md` (rewrite for readers; drop internal refs and ticket ids) | No. |
| 11 | Reading the numbers | The six reading rules (missing, zero, older weeks, week changes, labels). | Existing `shell.html` block, kept as is | No. |

Order for the menu: 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 10. Manifesto and Research stay where they are; Methodology is the explanatory middle between them.

## Pages that must wait for JEG-1081

1, 2, 9 in full; the Natural variants inside 8; the default-view sentences inside 7. Pages 4, 5, 6, 10, 11 can be drafted now. Page 3 can be drafted now with the label names left as placeholders.

## Overlap with what already exists

- **Writing > How values work** (`shell.html` `#v2How`): covers pages 1 (short), 3 (two paragraphs), 4 (one paragraph), 11 (the reading rules). The new section would replace this block, not sit beside it. Its text still says DDF Value is the Adjusted trade charts averaged and names "DDF Value (projections)", which matches JEG-1073 but not any final naming.
- **Writing > Manifesto** (`docs/manifesto.md`, mirrored in `shell.html`): reasoning, not mechanics. Link to it from pages 1 and 6; do not repeat. Manifesto sections 3 to 5 (replacement, bench as options) are the "why" behind pages 5 and 6.
- **Writing > Research** (`docs/research/posts/`): posts 01 to 08 and 10 already explain bench value, backups, why DDF Value, rescaling, missing/zero/one-source, trade confidence, whether the gap predicts, when charts agree, how DDF Value should be built. Pages 3, 5 and 7 would be shorter reader summaries linking to these posts. Caution: posts 03, 06, 07, 08 and 10 define DDF Value as projections-only (written before JEG-1073 on 2026-10-25). They are stale on that definition until revised; do not copy their definition into Methodology.
- **`docs/methodology.md`** (1892 lines): internal spec with ticket ids, VP/ES codes and history paragraphs. It is the source, never the page text. "Live and pending" block is the current-truth summary.
- **`docs/v2-design-notes.md`**: build notes for developers; page 7 and 9 source only.
- **`docs/use-ddf-in-claude-chatgpt.md`**: already close to page 10 but written for the team (ticket ids, `make sync`, file paths). Needs a reader rewrite, not a copy.
- **Full value logic page** ("Open DDF Value Logic", rebuilt each deploy): engine figures for a standard league. Keep as the deep link at the bottom of pages 3 to 6.

## Open questions for Jeremy

1. Section name: "Methodology" under the "Learn" group, and does "Learn" also hold Manifesto and Research (moving them out of Writing)? Recommend yes, one group, three entries.
2. Replace "How values work" or keep it as a one-screen summary that links into the section? Recommend replace.
3. Whether the Methodology pages are static text in `shell.html` (like Manifesto) or generated from the engine for live league figures. Recommend static text plus live numbers only on pages 4 and 5.
