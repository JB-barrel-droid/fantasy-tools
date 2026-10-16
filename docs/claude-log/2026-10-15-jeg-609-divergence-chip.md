## 2026-10-15 - JEG-609 Source divergence "Check" chip

- `source_divergence` from `assets/reference-freshness.json` (JEG-460 data) is loaded with the pipeline file and shown as a small chip next to the source name, in the prior-week badge's slot: warn or investigate = "Check" (tooltip and accessible name = the published message), reviewed = "Reviewed" (links to `resolution_issue`; a `JEG-NNN` id becomes its Linear issue link; not a link inside a column-header button). ok and n/a show nothing. DDF Value and VORP columns carry none. It never hides a source.
- Places: Trade targets column heads (folded away at 1280 px and up, so the page also says it once above the lists: chip plus message), the Showing legend, Player values column heads, both Customize lists, the Compare series rows.
- Contract GL-25 (check `gl25` compares the chips with the published file for the compared charts); tests `tests/test_v2_divergence_chip_render.py` (known statuses served; chip text, tooltip, links, no chip for ok/n/a, no lost columns, no DDF/VORP chip; 4 broken builds caught).
- Today's built data has one flagged source (FantasyPros, investigate), so the chip is live on the page now.
- Pre-existing red on main, same before and after: `test_v2_ddf_versions_render` (3), `test_v2_compare_render.test_rendered_numbers_match_engine`, `test_v2_contract_render` GL-05/09/16 and its guard, targets render layout and its prior-week guard.
- Claimed, not checked: full `make validate`.
