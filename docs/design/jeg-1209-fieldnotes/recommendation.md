# Fieldnotes — Values and continuity

JEG-1209 • Fieldnotes handoff • 29 October 2026 • Design continuation, no rollout

**Notes-only amendment:** The product owner has approved the Natural-fit conditions below. The delivered PDF/HTML remain the historical revision-2 preview and have not been regenerated. Their pending-rule text and ESPN fixture-provenance claim are superseded by these notes; their labels and rankings are not a demonstration of the newly approved rule.

The product owner likes the Fieldnotes visual direction. This revision keeps its warm canvas, forest ink, Fraunces headings, neutral evidence panels and restrained motion, while correcting the hierarchy and explanation. The product promise is **“Understand the data. Make your own call.”** It does not claim earlier access, predictive superiority or a winning source model.

## The revised first minute

Home has two visible actions: **Explore Values** and **Use DDF in your AI assistant**. The main visual is an actual historical value curve, not a decorative illustration. A second homepage panel explains continuity: start on the site, pass supported context to a compatible chatbot, and return with a prepared state link. A link shares context; it does not install or connect tools.

Values is now a primary top-navigation and phone-navigation destination. The phone bar has Home, Values, Buy & sell, Check a trade and More. Settings, setup guides and deeper auditing/research remain reachable. No existing advanced destination is removed. Full-league setup is directed to desktop; a phone visitor can explore values immediately without pasting a roster.

The visual language remains one coherent selection, not a palette pass followed by a separate migration. These revisions are still private and do not authorize implementation, public publication or a new value rule.

## Values: what the number means

The Values screen includes an actual historical ranked curve, exact-value table, position filters, player search, display-view selection and player explanations. It uses the same captured engine rows as the comparison prototype. Data remains clearly labeled **Week 7 historical illustration**, Full PPR, 12 teams, one quarterback; it is not current advice.

A value of 60 means 60 **trade-value points under the shown recipe and league settings**. It is not 60 projected fantasy points, dollars, or a 60% chance of acceptance. Higher means more value in that view. Numeric zero is at/below that view’s waiver line; missing remains unavailable, never zero. The plotted lines join actual player values, not forecast trajectories. Players are ordered by the selected display view, and exact numbers remain available in the table.

| Choice | What changes | What does not change |
|---|---|---|
| Display view | The visible curve, table ordering, primary value column and explanation | DDF Value’s basis, target eligibility, trade rules and source membership |
| Value basis | In the existing engine, the recipe defining DDF Value across analysis; rankings, targets, trade reads and rescaled comparisons can change | Renaming categories alone does not change membership or give a model a new vote |
| Per-player override | The existing override mechanism replaces that player’s DDF Value | It is not a new source category or a projection of future scoring |

The prototype implements the display-view chooser. The basis explanation opens before any possible recipe change and explicitly says that this standalone review does not apply one. The production basis editor retains existing source/custom-weight choices; it must not become a cosmetic view toggle. Default remains DDF Value. Custom-basis and override continuity in connectors must be verified rather than promised.

Available illustrated views are DDF Value, DDF Projections, the current Combined trade-value average and the existing Observed-trade estimate series. The combined mean uses the same four comparison sources; it has not been relabeled as a pure Published chart average. A separate published-chart subtotal is not fabricated in this revision. Its implementation, coverage rules and availability must follow the selected source-framework contract.

## Approved input framework, unchanged math

Use the approved JEG-1212 three-category framework. Categories describe inputs; DDF outputs describe what the application does with them. Publisher names belong in detailed provenance rather than category identity.

| Input category | Reader question | Current inputs and limits |
|---|---|---|
| Projections | What might the player produce? | ESPN, CBS rest-of-season and Razzball. Converted to league-specific trade values for DDF Projections; available inputs are averaged. A forecast is not guaranteed or judgment-free. |
| Published charts | What should the player be worth? | USA Today, FantasyPros and CBS trade charts. Published assessments, not completed transaction prices. DDF estimates extending short charts must be marked. |
| Observed-trade estimates | What does completed-trade activity suggest? | FantasyCalc. An inferred value from transactions, not a raw price, universal market sample or acceptance probability. |

DDF Value’s current default still combines the three league-adjusted published-chart inputs with the observed-trade estimate. DDF Projections remains the alternate projection-derived output. The current four-source comparison mean and targets’ compared-source median remain distinct. Source categories do not silently exclude FantasyCalc, change weightings, introduce a deciding view, count a subtotal twice or rewrite saved identifiers.

The approved framework does not authorize public publication of the JEG-1212 article. It also does not establish live parity between every website view and every connector response. The research recorded actual differences between its pinned replay and live connector values; this design therefore promises shared supported context and explicit results, not universal numeric parity.

## Desktop setup, phone return

Phone league entry now says **“Set up your league on desktop.”** It explains three steps: open DDF on a computer; copy/paste and review teams; copy a prepared state link and open that exact link on the phone. Local browser storage does not sync across devices. A generic homepage bookmark does not carry rosters.

The prototype’s prepared review link demonstrably restores its sample team, rosters, trade and selected display view after local storage is cleared. It is labeled as a private review format. The production DDF link uses the unchanged DDFState codec and carries supported league settings, a selected roster and the trade. It is not claimed to transfer every multi-team league record, new basis/override fields, or the private design itself.

Desktop setup retains the existing parser, actual match counts, review of unresolved names, team selection and per-team accumulation. The guide is designed around a provider-specific source page on the left and the DDF destination on the right, with numbered annotations for copy scope and match review. Verified official links and exact copy scope are required before a guide is described as ready. Constructed Yahoo/Sleeper fixtures are not evidence of the current provider UI. Annotated schematics must say they are schematics; invented provider menus must never be presented as screenshots.

ESPN: League → Rosters and the fixture’s real-copy provenance require reconciliation. A fresh guide review says the fixture may be inferred. Do not claim that an actual screenshot or successful whole-league page copy has been verified until provenance is established. Yahoo: the verified one-team route is My Teams and Leagues → team → My Team → Roster. Sleeper’s whole-league copy UI remains unverified; the prototype offers a reviewed player-name-list fallback. Every guide labels its diagram as an illustration and links to the actual DDF textbox. Copy the page body, not its address. No URL/ID league fetch is claimed. Authenticated provider UI was not captured in this review.

## Chatbot continuity is homepage-level

The primary handoff is the previously selected **one plain Copy link**. It is not replaced by a complicated set of Copy/Paste-for-LLM packets. The separate setup path explains compatible MCP tools; readable text remains an optional fallback when tools cannot be connected.

| Path | Honest promise | Required limitation |
|---|---|---|
| Copy link | Transfer supported DDF league/work context to the site or a connected DDF state reader | A URL does not install MCP; a generic chatbot may not resolve internal player IDs or read a URL fragment |
| Connect DDF tools | A compatible host can request supported current values and read/create supported state links after setup | Availability depends on host, plan and workspace policy. The prototype does not detect or establish a connection. |
| Readable snapshot fallback | Share explicit player names, historical displayed numbers, settings and a question | Static, not live. No refreshed values or tool execution should be claimed. |

The chatbot page shows the current league, basis, displayed view and work context. The production link encodes the default league, selected roster and current trade through the existing codec. It does not include an unverified custom basis or override contract. The optional readable snapshot names the selected display view and supplied values. A live query may use newer data, so links carry inputs rather than frozen numeric results.

A connected workflow should first read the state, name unresolved players/ignored fields, then run the supported tool. Returning to the site should use the tool-created link and surface what was applied. On timeout, rate limit, unavailable host setup or unsupported views, keep context, explain the limitation and use the snapshot fallback. Do not substitute invented results.

## Shared visual and interaction system

Retain the selected direction from revision 1. Light roles: canvas #F5F2EA, surface #FFFDF8, ink #182D27, muted #52635C, subtle #EAE8DF, decorative line #D4D8CD, control boundary #79897F, action #126044 with white text, negative #922F3E, focus #175BC1. Dark counterparts remain implemented. Light contrast measured previously: ink 13.00:1, muted 6.26:1, action text 7.55:1, negative 7.66:1, control boundary 3.63:1.

Fraunces 600 carries the main answer; system sans carries controls, explanations and tabular figures. Body 16/1.5; support 13–14; metadata 12. The revised hero is 52 desktop / 37 phone. Spacing remains 4/8/12/16/24/32/48/64; 16px phone gutter and 32px desktop gutter; maximum content width 1184px. Required controls are at least 44px high. Color alone never identifies a source, change or input category.

At desktop, the curve and explanatory panels have room to breathe. At tablet, navigation wraps to its own row. At phone, five labeled primary destinations stay visible and the rest of the page scrolls normally. Values tables scroll inside their own container with a sticky player column. The chart is backed by a text description and exact-value table; hover is not required. Dialogs use keyboard focus, Escape and focus restoration.

Motion remains 160ms feedback and a small result reveal, with no counting, confetti or celebratory model colors. Reduced-motion and screenshot mode settle instantly. Basis explanations, state disclosures and provider limitations remain ordinary readable content, not hover-only tooltips.

## Finder: recommended sequence and visual organization

Use a sequenced workspace with editable summaries, not a blocking wizard. The sequence is **League → Explore rosters → Trade preferences → Opportunities → inline details**. The first four stages stay visible as compact buttons (one desktop row, two phone rows). State persists while navigating between roster exploration and opportunities. No step requires starting over.

First use: desktop paste and match review → select own team → explore an opponent → set package and minimum-backup preferences → inspect results. Returning users open their last workspace/result and change any earlier stage directly. Compare stays focused on editing a particular deal. The product owner explicitly approved Find a Trade as the roster-exploration home.

A single long page makes discovery and controls compete with hundreds of player rows; a rigid wizard makes repeat adjustments slow. Two focused workspace views—Explore rosters and Opportunities—plus editable League/Trade preferences panels preserve context with less vertical noise. Columns and Filters remain visible beside results; they are never buried in a global menu. Filters contains opponent inclusion and fit; Trade preferences contains search generation/guardrails; Columns changes presentation only.

## Roster exploration: implementation-ready contract

The opponent selector uses stable team IDs and updates the selected opponent’s summary and sortable player/value table without losing your roster or search preferences. Your summary uses DDF Value; theirs uses the current market view. Display the basis beside each. Show rank in DDF, projections and market, plus current strengths, light positions, and the exact reasons on expansion. Preserve existing allocation/median rules; “light” is not a guessed managerial intent.

Every team remains discoverable in an always-available league overview, with strengths/thin positions and all three ranks. Selecting a team there opens it in the side-by-side explorer. Player tables sort by name, DDF Value, DDF Projections or Combined trade-value average. Missing is unavailable, never zero. K/DEF remain counted but not evaluated. On phone stack the two team panels; keep the opponent selector and stage controls above them, with horizontally scrollable value tables and a sticky player column.

A value gap has **Explore trades involving this player**. Your player focuses outgoing candidates; their player focuses incoming candidates for that opponent. Keep the player/opponent focus visible with a clear reset. A gap is a possible signal, not evidence of a feasible recommendation. Zero matches must distinguish selected filters, generated candidates and search coverage when real diagnostics exist. This prototype truthfully reports only zero matches among stored results. The separate JSN investigation owns its findings; no numerical explanation or missed-opportunity verdict is fabricated.

## Opportunities: outcomes before package capture

Default order: our DDF starter change and projected starter change; our post-trade construction; their market starter change and projected starter change; their post-trade construction. The six columns can move earlier/later or be hidden in Columns. Keep trade identity visible. Projection magnitudes are projection-derived **trade-value points**, not weekly fantasy points. Both sides use DDF Projections for that comparison; there is no invented “market projection” source.

The historical fixture demonstrates the distinction: top-ranked package capture is +13.7, while our DDF starters fall 13.7 and projected starters fall 20.2. Their market starters rise 11.8 and projected starters rise 8.6. These are outputs from unchanged checkout functions, not mocked gains. Ranking is preserved; the layout makes its consequences visible. Negative changes stay visible rather than being renamed improvements.

Compact League loaded status shows 4 teams, 51 entries and The product owner’s team in this illustrative fixture, with edit/expand. Production must use actual counts and selected own-team ID. Opponent inclusion defaults to all other teams, with checkboxes, Select all and Clear. Clear means none. Persist membership by stable team ID, not display name/index; resolve deleted teams and own-team changes explicitly.

Selecting a result inserts its details directly below that row (or inside that phone card). Add selected styling, a heading naming the opponent, send/receive names, before/after starter figures, and post-trade starters/bench by position. Use one primary Review both teams action. The heading receives focus; phone scroll reveals the heading while retaining the package context in the expanded panel. Close/Escape returns focus to the original trigger. Reorder/filter should retain selection when the result remains present; if excluded, close with an announcement, never leave an orphan detail panel.

## Fit language and search preferences

Market supported: their current market-weighted roster change is above 0.05 points. Starters count fully, bench uses current weights. This does not guarantee healthy construction, agreement from every source or acceptance by the manager. Show the actual gain and any construction concern beside the label.

**Approved Natural-fit product rule, 29 October:** both teams’ starter value must improve; neither team’s projected value may decline; and both roster-construction checks must pass. Our starter perspective is DDF Value; theirs is the existing market perspective. Use the existing projection measure for each team; do not invent a market-projection source or silently substitute a different projection metric. Conceptually the starter changes are positive and projection changes nonnegative. Do not reuse the old negative-market tolerance to admit a starter decline, and do not require a strictly positive projection gain when an unchanged projection is permitted. Missing required metrics cannot establish a Natural fit.

This supersedes the former pending product question. The historical preview still executes the old predicate: weighted DDF gain above 0.05, our starters at least −0.05, their market-weighted change within negative tau, and construction checks. Its existing labels are therefore not acceptance evidence for the approved rule. Implementation, numeric precision/boundary mapping and validation remain with the calculation/integration owners; this design amendment changes no thresholds or production code.

**Manager-aware ranking:** balance our gain and modeled opponent appeal. Exact scoring, weights, normalization and tie-breaking still require review; no formula is approved by this note. Explain modeled appeal as a calculation, not acceptance likelihood. Present stretch offers separately below the main opportunities, without mixing them into the main ranking or styling them as Natural fits. Do not invent a stretch eligibility threshold; its calculation contract must be explicit in the implementation review.

Trade preferences shows 1-for-1 only plus the existing maximum-package choices. Minimum backups are visible QB/RB/WR/TE steppers, initially 0, with minus disabled at 0. Explain post-lineup bench count and scope. The guardrail owner supplies engine/persistence behavior; this prototype only marks example results stale after a preference change. Never show old rows as recomputed output. Do not duplicate guardrail code here.

## Coordination and release acceptance

Acceptance: correct default reading order at desktop and phone; exact unchanged numeric mapping; columns reorder by accessible buttons (drag optional); all/none opponent semantics survive rename/reorder; stage navigation retains state; both selected-roster and all-league tables available; value-gap action and honest empty state; inline selection visible without scrolling to the end; focus restored on close; minimum-backup/package changes trigger current engine recompute and mark stale rows; missing/incomplete rosters distinguished; no acceptance-likelihood language; the newly approved Natural-fit rule mapped and validated by the calculation owner before shipping. Verify both positive starter changes, both nondeclining existing projection measures, and both construction checks; include unchanged-projection, zero-starter, negative-change, missing-metric and construction-failure cases. Manager-aware ranking requires a reviewed scoring contract and inspectable components; stretch offers appear separately below the main list. Numeric and candidate-generator changes belong to their existing owners, not this design lane.

## Verified setup sources

OpenAI’s current custom MCP guide: https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt . The prototype describes Plugins → Add custom MCP server, endpoint/authentication/tool review, then plugin selection in a new conversation; role/plan restrictions are visible.

Claude remote connectors: https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp and https://support.claude.com/en/articles/11176164-use-connectors-to-extend-claude-s-capabilities . Setup uses Customize → Connectors and an account-appropriate custom connector path; organization permissions and Free’s one-connector limit are stated. The live DDF endpoint was not exercised.

Yahoo roster help: https://help.yahoo.com/kb/SLN22673.html . ESPN provenance under reconciliation: tests/fixtures/league_paste/espn-league-rosters.txt may be inferred rather than a verified real copy. Earlier assertions of verified provenance are withdrawn pending evidence; neither an actual screenshot nor a successful whole-league copy is established by the fixture alone. Sleeper’s exact copy path remains unverified. Cloudflare’s Agent setup pattern (https://developers.cloudflare.com/ai-search/how-to/connect-mcp-client/) and Mintlify’s contextual actions (https://www.mintlify.com/docs/ai/contextual-menu) inform the prominent host-specific connection path. They do not prove DDF integration parity.

## Bounded implementation handoff

JEG-1137 remains the shared shell/control foundation plus desktop-oriented setup and phone return. The newly prominent Values surface and homepage chatbot path need explicit implementation ownership—either separately bounded tickets or an explicit scope amendment—before rollout. Do not hide them inside an unrelated color migration. Preserve the existing DDFState, parser and engine contracts behind presentation adapters.

JEG-1138 continues to own Compare and reusable value-view/evidence components; JEG-1139 consumes those for targets, with existing target rules unchanged. JEG-1140 remains an independent Settings/explanations lane after design/copy readiness, coordinating common controls with 1137 rather than waiting for all other pages.

Acceptance additions: Values visible in primary navigation; exact curve/table values; display selection does not mutate basis; basis changes tested against the existing engine separately; coverage/missing/estimated states; three-category labels without membership changes; one Copy link; compatible-host setup and explicit unconnected/error states; truthful tool-view/basis limitations; desktop guide links/copy scope verified; mobile prepared-state round-trip; no automatic cross-device sync claim. Retain all original value parity, parser, export/import, nine-cell verdict, multi-player/roster, accessibility, phone/desktop and reduced-motion gates. Public article publication remains separately gated.

## Evidence and scope

The live site could not be opened: Chromium returned ERR_TUNNEL_CONNECTION_FAILED; the web reader also could not access the URL. Review continued against an isolated build from the current checkout and real historical engine rows, with frozen illustrative league rosters. This is not a certified audit of the latest deployed commit. No public code was changed.

The prototype still uses the labeled historical engine snapshot (tv-20261027-0014-1bdef712; source Week 7; capture October 28; content clock October 25), unchanged trade/target rule copies and the unchanged DDFState codec. The display comparison mean is arithmetic over the same existing four numeric series; no new source group or threshold was introduced. Full production and live connector values were not rerun or certified by this design task.

Revision-2 browser checks cover Home, Values, chatbot, guides, setup, Compare, targets, Settings, finder and roster exploration at 320, 390, 768 and 1280px without page overflow or JavaScript errors. Interaction checks cover display/basis separation, filtering and player detail, real desktop parsing, canonical state codec round-trip, private prepared-link restore, phone setup guidance and reduced motion. Physical-device, Safari, screen-reader and live tool/API parity certification remain rollout work.
