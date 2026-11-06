## 2026-11-04 - FantasyPros Market intake / JEG-1506

Contract: add FantasyPros Trade Market Values as a separate, as-published
comparison source without changing DDF math or blends. This draft contains
only the acquisition and normalized-row identity boundaries. It does not
complete the ticket.

### Verified (check named)

- Read JEG-1506 and its comments before claiming
  `codex/JEG-1506-fantasypros-market` at Jeremy's direction.
- Cloud runtime `environment_status` and `/etc/codex/network-policy.json`:
  enforced restricted network policy excludes `www.fantasypros.com`.
  Requested the host be added; did not bypass the policy.
- `PLAYER_ALIASES_SOURCE=json python3 -m unittest
  tests.test_fantasypros_market_intake` (included in the focused run below):
  18 tests pass on synthetic
  data. Extraction preserves nulls, nested histories and the full JSON
  container, and refuses missing/truncated/duplicate declarations,
  non-finite numbers, duplicate keys and executable JS expressions.
- The same test module exercises shared canonical naming plus mandatory
  position/team matching, unmatched/ambiguous/duplicate identity failures,
  source-ID/canonical-key separation, native/null preservation, shared team
  aliases and explicit K/DST exclusion receipts.
- Focused integration command adding `tests.test_source_snapshot_match`,
  `tests.test_one_name_resolver` and
  `tests.test_pipelines_import_standalone`: 32 tests pass. The resolver guard
  caught an initial use of the legacy name index; the implementation was
  corrected to use `canonical_players.load_registry/resolve_with_reason`,
  and the existing guard passes unchanged.
- The capture schema is distinct from every publishable source artifact;
  it retains the page HTML and embedded container for replay and explicitly
  records `publishable=false`. No comparison chain stage consumes it.
- No DDF, value-model, blend, chart fixture or source recipe code is changed.
- `CHROMIUM_PATH=/usr/bin/chromium make validate`: PASS, including the full
  core/render and integration suites. The strict engine/Python comparison
  agreed on 1,234,507 values with zero source mismatches. The first attempt
  stopped because Playwright's bundled browser was absent; the installed
  system Chromium resolved that environment issue.
- Generated build changes were preserved in
  `/tmp/jeg1506-generated-backup` and restored out of the worktree; only the
  authored intake, identity, tests, Makefile entry and this log are in the PR.
- Read-only integration trace: `curve-widget.js::seriesValuesFrom` currently
  requires a pipeline source, while `COMPOSITE_INPUT_KEYS`,
  `PIPELINE_SOURCE_KEYS` and `COMPOSITE_CHART_INPUTS` name the DDF input
  sources. The new comparison-only source must not be added to those input
  lists. `product-data.js::getPlayerValues` currently calls `Number(rawValue)`;
  explicit nulls must not reach that coercion (`Number(null)` is zero).
  The future adapter must retain nulls in the source snapshot/counts while
  preserving missing cells through comparison publication and rendering.
- Draft PR #1311 at `1cd13f79`: `security-contracts`, `settings-render`,
  `waivers-mutation-offline` and both `pr-state` checks passed.
  `preview`/`v2-render` are red because the draft skips full verification;
  the workflow summaries deliberately fail when verification is deferred.
  Checked through `gh pr checks 1311`, the job API, and the workflow code.

### Claimed, not confirmed

- The ticket's intake says the public page embeds `initialPlayers`. No live
  HTML could be fetched in this environment, so the exact declaration and
  row schema have not been verified against this extractor.
- This is not a scheduled, publishable source intake. The live row adapter,
  publisher values timestamp, priced-row guards, `/standard` comparison,
  scheduled acquisition, fixed-pie comparison integration, dataset_status,
  coverage/pie contracts and rendered chart acceptance remain outstanding.
  `source_values_timestamp=null` is an honest acquisition placeholder, not
  permission to publish without a source timestamp.
- Resume after `www.fantasypros.com` is allowed: capture half-PPR and PPR
  with `pipelines/pull_fantasypros_market.py --scoring <half_ppr|ppr>
  --out <capture.json>`, inspect their actual row/timestamp schema, add the
  verified adapter and carry keyed identities into the existing published
  reindexing path. Re-check `/standard`; never create a standard leg from
  a half-PPR mirror. Stop on any value-math/methodology decision.
