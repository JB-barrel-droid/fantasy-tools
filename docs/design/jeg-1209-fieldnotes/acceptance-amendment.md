# Current acceptance decisions (JEG-1209)

This amendment supersedes historical fit, ranking and selector behavior in the preserved prototype. Status: design continuation handed to Claude, 2026-10-29; no production rollout authorized by this artifact.

## Product decisions

- **Natural fit 1A:** both teams’ starter values improve; ours uses DDF, theirs uses the existing market view. Neither team’s existing DDF projection view may decline. Both roster-construction checks pass. No invented market projection, loss tolerance, new numerical epsilon or default. The calculation owner maps the exact existing fields and validates boundary/missing-data behavior.
- **Manager ranking 2B:** balance our gain with modeled opponent appeal. Exact scoring, normalization, weights and tie-breaking still require review. Do not present modeled appeal as acceptance probability.
- **Stretch offers 3A:** place separately below main recommendations. Do not mix them into the main list or invent a new eligibility threshold.
- **Both saved-team selectors:** both finder sides select saved teams using stable IDs; initial Your team follows the existing star. Keep both sides distinct and preserve selections across navigation. The historical prototype implements only the opponent selector and a fixed synthetic own team.
- **Shared preferences 5A:** common preferences are shared between trade surfaces; page-specific controls remain separate. Do not silently reset common settings when switching surfaces or persist presentation-only controls as calculation inputs. Confirm the field-level schema with the integration owner.

## Sequencing and presentation

Retain the Fieldnotes direction. League → Explore rosters → Trade preferences → Opportunities → inline details is an editable workspace, not a blocking wizard. Returning users can jump directly to saved opportunities. Find a Trade owns side-by-side roster exploration; Compare edits a specific package.

Default results order: our DDF starter and projected gains with magnitudes; our post-trade construction; their market starter and projected gains; their post-trade construction. Use the existing projection measure on both sides. Columns can reorder with keyboard controls. Opponent inclusion uses stable IDs, defaults to all, and offers explicit Select all/Clear (Clear means none).

Show truthful loaded counts and selected own team. Preserve league-wide discoverability of every roster’s strengths/thin positions, alongside selected-team summaries and sortable player/value tables. A value gap offers Explore trades involving this player but does not prove feasibility. Empty states need actual candidate/filter diagnostics, not speculative explanations.

Expand the selected trade immediately below its row or inside its phone card; show opponent and package names, focus the heading, and restore trigger focus on close/Escape. Package size includes 1-for-1 and existing maxima; minimum-backup controls remain visible with 0 starting values. Guardrail and search implementation remain with their owners.

## Source framework, setup and AI continuity

Categories remain Projections, Published charts, Observed-trade estimates; DDF Value and DDF Projections are outputs. No category rename changes membership, default math or identifiers. Values remains prominent and explains display view versus basis.

Use DDF in your AI assistant remains homepage-level. Separate host connection from one plain Copy link. Links transfer supported state, do not install MCP, freeze values or guarantee custom-basis/override parity. Phone league setup is desktop-first with supported link/export continuation, not account sync.

**ESPN correction:** fixture provenance is disputed and may be inferred. Do not claim an actual provider screenshot or successful whole-league copy is proven until provenance is reconciled. Yahoo’s documented route is one team at a time. Sleeper whole-league copying remains unverified. All visuals are labeled illustrations, not provider screenshots; DDF does not fetch a league from a URL/ID in this design.

## Component ownership and validation

JEG-1219 owns both saved-team selectors; JEG-1231 opponent inclusion; JEG-1232 column ordering/accessibility; JEG-1233 loaded-league status; JEG-1230 the explicit readout adapter/parity. Search candidate work remains its existing lane. Coordinate guardrail/common preference fields instead of duplicating engine logic. JEG-1137–1140 remain rollout lanes after design review.

Acceptance covers desktop/phone reading order, stable-ID rename/reorder behavior, retained stage state, accurate metrics/units, source coverage/missing states, keyboard reordering and disclosure focus, inline selection, and honest stale results after search changes. Verify both positive starter changes, both nondeclining projection measures, both construction checks, zero-starter/unchanged-projection boundaries and missing required metrics. Ranking requires its reviewed scoring contract. No production rollout, merge or publication is implied by this handoff.
