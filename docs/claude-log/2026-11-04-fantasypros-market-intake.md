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
