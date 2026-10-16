# 2026-10-15 JEG-678 v2 contract render triage; JEG-450 "ESPN Tier" label

Verified (RENDER_TESTS_REQUIRED=1, py3.12):
- (a) RS-01..03 missing from CHECKS: already fixed on main (rs01..03 in CHECKS); test_mirror_every_id_has_a_check passes.
- (c) Real bug, fixed: JEG-543 places the Research page inside #v2App, so the built page embeds compose_shell(shell.html, posts), not shell.html verbatim. run_contract's shell override now swaps compose_shell(original) for compose_shell(broken). The guard's assertion is unchanged.
- (b) GL-05 part: the freshness fixture left pipeline-wide rows (source_import.checked_at, comparison.built_at) at the live file's freshness_ok=false, so every source read "stuck". Fixture now pins them true like the per-source rows.
- Still red, data-driven (week 6 saved but not published; live dist is week 5, DDF charts/projections unavailable): GL-05 residual (cbs/chip read "Prior week" from engine stale flags), GL-09 and GL-16 (ddf_value_charts not offered), and the guard's PV-09 mutation check (surfaced now that the shell step passes; not confirmed independent of the same cause). Expected to go green on week 6 publish; re-run then (JEG-678).
- JEG-450 Q1: header "ESPN Tier" (Player values), Columns popover, drawer line. test_v2_expand_render and test_v2_ddf_render pass, no copy pin needed changing. Decision recorded in docs/math-review-agenda.md; GAP-TIER-FROM-ESPN marked decided in risk-register.

Claimed, not verified: the week-6 cause of the residual GL-05/GL-09/GL-16/PV-09 failures (inferred from freshness file + curve-widget "not yet published" gate). docs/feature-contract.md GL-16 still says "Tier"; it mirrors a Google Doc, left for Jeremy to update.
