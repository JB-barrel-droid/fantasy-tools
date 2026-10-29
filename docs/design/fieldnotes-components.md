# Fieldnotes foundation: component contract (JEG-1137)

What the JEG-1137 foundation provides to the lanes that put pages into Fieldnotes (JEG-1138 Compare, JEG-1139 Trade
targets, JEG-1140 Settings, JEG-1265 Values, JEG-1266 the AI panel, JEG-1263 the simplified site), and what they may rely
on. The approved design is JEG-1209 (Jeremy, 2026-10-29: "so A"). Its source is
`docs/design/jeg-1209-fieldnotes/recommendation.md` and `prototype.html` on the JEG-1209 branches (#1089, #1096).

## The flag

- `?design=fieldnotes` in the page URL makes `app/v2/design-flag.js` set `<html data-design="fieldnotes">` before first
  paint. The script loads synchronously in `<head>` (from `pipelines/build_v2_page.py`).
- Every Fieldnotes rule is scoped to `:root[data-design="fieldnotes"]`, so the site without the flag is unchanged.
  `tests/test_v2_tokens.py` enforces the scoping, and `tests/test_v2_fieldnotes_league_entry_render.py` checks the
  unchanged default page in a browser.
- Turning Fieldnotes on for everyone is a separate public-rollout decision, not part of this contract.

## Tokens

The values live once, at the end of `app/v2/v2.css`, in light, in dark through `prefers-color-scheme`, and in dark
through `data-theme="dark"`. `tests/test_v2_tokens.py` pins every role value and checks contrast in both themes: text at
least 4.5:1, control edges and focus at least 3:1.

| Role | Names to use |
| --- | --- |
| Page and surfaces | `--ddf-canvas` / `--v2-canvas`, `--ddf-surface` / `--v2-surface`, `--ddf-subtle` (hover, quiet fills) |
| Lines | `--ddf-line` / `--v2-border` (dividers only, never a control edge), `--ddf-control` / `--v2-field-border` (the edge of anything you can press or type in) |
| Text | `--ddf-ink` / `--v2-ink`, `--ddf-muted` / `--v2-muted` |
| Action | `--ddf-action` / `--v2-action` (fill), `--ddf-action-ink` (text on it), `--ddf-action-hover`, `--v2-action-text` (action-colored text) |
| Meaning | `--ddf-good-ink`, `--ddf-bad-ink` / `--v2-negative`, `--ddf-warn-ink` / `--v2-older` |
| Focus | `--ddf-focus` / `--v2-focus` |
| Type | `--ddf-font-display` (Fraunces 600: headings and answers only), `--ddf-font-ui` (everything else); sizes `--ddf-type-hero` (52, phone 37), `--ddf-type-body` (16, line 1.5), `--ddf-type-support` (14), `--ddf-type-meta` (12) |
| Space | 4, 8, 12 (`--ddf-space-mid`), 16, 24, 32, 48, 64 (`--ddf-space-7`); gutters `--ddf-page-pad-phone` (16) and `--ddf-page-pad-desktop` (32); content up to `--ddf-content-max` (1184) |
| Shape | `--ddf-radius-card` (16), `--ddf-radius-control` (9), `--ddf-hit` (44) |
| Motion | `--ddf-motion-feedback` (160 ms, 0 under reduced motion), `--ddf-ease` |

## Controls

**Existing classes pick up Fieldnotes under the flag**, with no markup change:
- `.v2-btn` and `.v2-btn-primary`: control radius, control edge, 44 px, prototype hover. A pressed (`aria-pressed="true"`) or disabled button keeps its own look on hover.
- `.v2-card`: surface, line, card radius.
- `.v2-link`: action text.
- Fields in `.v2-find-import-body`, `.v2-find-paste` and `.v2-popover` sit on the control edge. The whole-league paste box is the one large field (176 px).
- Disclosures: `.v2-find-import` uses the Fieldnotes disclosure, and the league card's heading sits beside its arrow.
- `h1`: the display face. Focus ring: 3 px with a 3 px offset.

**`ddf-fn-*` classes are for new components.** They are CSS only, so the markup keeps native elements and ARIA state:

| Class | Markup |
| --- | --- |
| `.ddf-fn-btn`, `.ddf-fn-btn--primary` | `<button>` |
| `.ddf-fn-segmented` | a container of `<button aria-pressed>`; exactly one is `true` |
| `.ddf-fn-stepper` | `<button>` `<output>` `<button>`; each button gets an `aria-label` |
| `.ddf-fn-checks` | `<fieldset>` with a `<legend>`, then `<label><input type="checkbox"> text</label>` rows (each row is the 44 px target) |
| `.ddf-fn-disclosure` | `<details>` with a `<summary>`; plus and minus are drawn at the end |
| `.ddf-fn-display`, `.ddf-fn-hero` | a heading or answer in the display face, and at hero size |
| `.ddf-fn-focus` | any custom focusable that needs the Fieldnotes ring |

## Rules for consuming lanes

- Use the token names above, never literal colors or sizes, so both themes and any later value change follow.
- Use `--ddf-control` (not `--ddf-line`) for the edge of anything you can press or type in.
- Keep a component's own CSS under its own root class, as JEG-1265, JEG-1266 and JEG-1140 do. A rule that changes an existing surface must also carry the flag selector.
- A new token is added only to the Fieldnotes block in `v2.css`, with a value in all three modes and a pin in `tests/test_v2_tokens.py`.
- Every target is at least 44 px. A checkbox's target is its label. A link inside a sentence is exempt.
- Don't use `!important`, don't declare a second `@font-face` for Fraunces, and don't load fonts from the network.
- Don't change values, copy or storage here. Copy is JEG-1130's, values come from the engine, and state goes through DDFState.

## Evidence

- `tests/test_v2_tokens.py`: role values in all three modes, contrast in both themes, flag scoping, unchanged default token values, the self-hosted font with its license, and mutation checks.
- `tests/test_v2_fieldnotes_league_entry_render.py`: the JEG-1137 done-when, checked at 390 and 1280 px with the flag on. A new visitor pastes the Yahoo whole-league fixture and sees the team count and each team's matched players, presses a team's star, and gets the same teams, rosters and marked team back after a reload. At each step it checks for no sideways scroll, 44 px targets, text contrast, the paste box's 3:1 edge, and a keyboard focus ring. It also checks that the unflagged league section's computed styles are unchanged, and runs a guard that fails without this slice.

## Compare a trade (JEG-1138)

The `v2.css` block between `/* JEG-1138: Compare a trade in Fieldnotes` and `/* JEG-1138 end */` puts Compare into
Fieldnotes under the same flag. It's presentation only: the markup, copy, numbers and verdict rules stay with `v2.js` and
`trade.js`, and no verdict cutoff is added.

**Reusable for other pages (JEG-1139 adds its selectors to these lists):**
- Kicker: the 12 px, 750, all-caps label above an answer or a value (the verdict eyebrow, "Deal read").
- Value view: muted 12 px column heads, rows on `--ddf-line`, tabular figures.
- Expandable detail: the Fieldnotes disclosure on an existing `<details>` (rule above, ink label, 44 px summary, plus and
  minus at the end), and row toggles ("Show players") whose own box is the 44 px target.

**Compare only:**
- The verdict card is the prototype's result card: card radius, 24 px padding (16 on phone), and the heading in the
  display face at 28 px (24 on phone). The left edge keeps its meaning (win `--v2-action`, lose `--v2-negative`,
  incomplete `--v2-older`), and a verdict with no side (even, none) takes `--ddf-ink`. The phone verdict bar follows the
  same rule.
- "Copy link to this trade" is a 44 px target at every width, not only on touch screens.
- The sides: kicker headings, the search box on the control edge at 44 px, totals in tabular figures.

**Evidence:** `tests/test_v2_fieldnotes_compare_render.py`. At 390 and 1280 px it opens each verdict branch (none, win,
lose, even, incomplete) as a trade link. For each, it checks that Compare's text is identical to the unflagged page's,
the display face, the edge colour, no sideways scroll, 44 px targets and text contrast. It also drives Tab and Enter
on "Every pairing", on a row's "Show players" and on "Copy link", and checks the phone verdict bar. The unflagged page's
computed styles are unchanged, and a guard fails without the block.

## Trade targets (JEG-1139)

Trade targets reuses JEG-1138's value view and expandable detail: the shared selector lists in the JEG-1138 block also
name `#v2Targets` (the targets and weight tables, and "How to use it"). Its own layout is the `v2.css` block between
`/* JEG-1139: Trade targets in Fieldnotes` and `/* JEG-1139 end */`. Presentation only: target signals, QB treatment,
thresholds, copy and numbers stay with `targets.js` and `v2.js`.

- The two checks and the sell and buy list headings are in the display face at 22 px (20 on phone).
- The search box and position choice sit on the control edge at 44 px, and the DDF Value and Compare against pickers
  keep their tint with the control radius.
- Lists use 24 px card padding (16 on phone). Player names are at body size, 650. The gap is the row's value, at 650
  and 20 px on the phone cards.
- The chart links inside an opened row are 44 px targets without moving the line.

**Evidence:** `tests/test_v2_fieldnotes_targets_render.py`. At 390 and 1280 px it checks that the text is identical to
the unflagged page's, with the lists closed and with the sell list opened. It checks the display-face headings, no
sideways scroll, 44 px targets and text contrast. By keyboard it drives Show more and Show top 5, a weight group's
toggle and "How to use it". At 1280 it drives a row's per-chart toggle by keyboard; at 390 a tap on a card opens the
player. The unflagged page's computed styles are unchanged without either block. A guard fails without the JEG-1139
block (headings), and without the JEG-1138 shared lists ("How to use it" under 44 px).

## Boundary and what's next

- **JEG-1137 owns:** the tokens, type, controls and flag above; league entry in Fieldnotes; and later the shell and navigation (slice 2b: the Fieldnotes phone bar, a Home route, and the phone "Set up your league on desktop" entry). Slice 2b touches `shell.html`, `v2.js` (a hot file) and `league.js`. Codex sequences it against JEG-1130, JEG-1263, JEG-1140 and JEG-1259.
- **JEG-1137 does not own:** the Values page (JEG-1265), the AI panel (JEG-1266), Settings (JEG-1140), Compare and the value-view components (JEG-1138), or Trade targets (JEG-1139). Those lanes consume this contract.
- **Default-site defects this slice fixes only under the flag** (JEG-1281): the paste boxes' edge is 1.3:1, and the "Your league" heading drifts away from its arrow.
- **Seen with the flag on, outside league entry** (for the table owners, JEG-1281 and JEG-1232; not fixed here): on Find a trade: league-wide, the team summary has eleven info disclosures 16 to 18 px tall and 32 px sort buttons, and the opportunities table has a 30 px text filter. Its checkboxes are fine, because their labels are 44 px.
