## 2026-10-28 - Projection path to published value / JEG-1199

Contract: Explain ESPN, CBS ROS and Razzball from the engine's points-per-game input to the value displayed in Player values. Read existing `TradeValueCurveControls.getInspection()` outputs only; do not derive or change values.

### Verified (check named)
- Latest Linear ticket read: JEG-1199, updated 2026-10-28 14:56 UTC. GitHub PR #1044 is merged; `git fetch origin main` returned `2e7a2c7c68c721e3ee52b37c7308e7cfab4d4555`. GitHub PR search for JEG-1199 returned no existing PR.
- Contract/code inspection: `curve-widget.js` `seriesField()` returns Adjusted for projection sources in every view. `getInspection()` exposes native PPG, per-player surplus, start-worthy probability, lineup share, starter/fill-in parts, source position lines/availability and group rates. No engine changes needed for this path.
- Reversible presentation choice: label projection input “Projected points/game” and final output “Published value”; explain that this is a modeled value, not a publisher's trade-chart value. Preserve chart labels and existing series/model keys. Offer a selectable worked player following source, position and league settings.
- Missing intermediates remain unavailable, retained excluded-source outputs carry an explicit warning, and numeric zero remains zero.
- `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python3 -m unittest tests.test_v2_audit_projection_render tests.test_v2_audit_source_render.AuditSourceRenderTest.test_single_source_view`: 2 tests passed in 35.527s. New test checks all 3 projections at 1440/375 px, two worked players each, exact equality with engine intermediates and Player values, league-setting changes, unchanged active sources, missing/held honesty, numeric zero and zero page errors. Existing seven-source audit render test also passed.
- `node --check app/v2/audit-source.js` and `git diff --check` passed.

### Claimed, not confirmed
- Initial browser command could not build: Playwright's bundled headless Chromium was absent. The environment provides `/usr/bin/chromium`; rerun with supported `CHROMIUM_PATH=/usr/bin/chromium`.
- No duplicate full `make validate` gate run; required remote CI and parent release verification remain outstanding.
- Missing upstream readout contract: `getInspection()` starts at full-precision PPG and does not expose publisher projection totals/stat lines, games denominators, or their bake conversion. The UI explicitly marks that boundary. An upstream raw-stats-to-PPG trace needs a separately scoped readout contract; none was reconstructed in the UI.
- No merge, deployment, live verification or Supabase change performed. Parent owns independent review, exact-head/current-main remote CI and serial release/live checks. Ticket remains open.
- Linear shared-context lookup failed with `Tool get_agent_context not found`; issue retrieval succeeded.
