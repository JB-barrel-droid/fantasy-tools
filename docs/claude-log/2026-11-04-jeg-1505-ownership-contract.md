## 2026-11-04 - Ownership conflict and caller handoff / JEG-1505

Contract: preserve own/other provenance during ID normalization, following
the coordinator's latest #1296 contract. The owner keeps its caller and
evaluate_swaps / waiver_board_swaps.cjs / buildSwapBlock boundary. This lane
changes only its preflight and tests, with no math or backend changes.

### Verified (check named)

- A new regression failed against 69fc74f76: priced candidate 102 with own
  canonical 101 and other canonical "0101" wrongly reported ownershipReady
  true. These references resolve to the same key before filtering.
- The preflight retains own and other key sets, detects their intersection,
  reports new `ownershipConflictKeys`, adds pending boundary
  `ownership_conflict` / reason `Identity is claimed by own and other rosters`,
  and prevents wire submission. Repeated records inside one other bucket do
  not manufacture an own/other conflict.
- The final pure combined command from the consumer-corrections log, covering
  adapter, old consumer contract, integrated search, universe/sync, product
  wiring, source combo and worked-example engine tests, passed 112 tests.
  The integration module now has 20 tests. Log:
  `../jeg-1505-consumer-final-combined.log`. JS syntax and diff checks passed.
- Own unpriced roster gating and pending/disabled override hits remain as
  recorded in the previous correction. No numeric/source fixture changed.

### Caller contract and qualification limits

- `ownership.complete === true` is an explicit caller attestation, never
  inferred from arrays. The caller must establish authoritative roster scope,
  freshness and team-level conflicts before flattening other teams into the
  current `others` array. This API can detect mine-vs-others intersections;
  it cannot recover distinct other-team provenance already discarded upstream.
- Preflight remains synchronous. Inputs are explicit namespaced references;
  existing outputs now additionally include `unresolvedOwnKeys` and
  `ownershipConflictKeys`. Only readyForPricing plus wireKeys permits
  submission; pricedKeys remains diagnostic. Known unpriced other-team
  identities are exclusions, not a global own-roster pricing hold.
- Capture existing `C.getState()`, `C.isReady()` and product-data
  `getSnapshot().snapshot_id` consistently with the board used by the caller.
  Recompute on settings/roster/override changes. Pricing readiness is not
  identity coverage or ownership completeness.
- Search source version is `jeg1505-search-identities/1`. The optional
  product-data getter returns its schema/meta; meta retains source hashes,
  identity pull date, unverified registry freshness and absent/unknown
  lifecycle. Additional getPlayer rows have canonical player_key, name/pos/
  team/sleeper_id, lifecycle/selection metadata, search_identity_only=true,
  pricing_status=unknown, values all null and matching missing reasons.
  Existing canonical/computed rows preserve their prior shape and values.
- Aiyuk 568 / Sleeper 6803 remains unresolved for pricing when outside actual
  getAllRows membership, even if a lazy legacy row contains chart zeros.
- Coordinator-supplied #1296 constraint, not independently requalified here:
  the owner request rejects extra fields. Keep preflight, snapshot/version
  and pending diagnostics in a separate caller envelope; project only into
  that owner's existing allowlisted request fields. Do not spread this
  preflight result into evaluate_swaps/buildSwapBlock requests.
- No #1296 caller, main readout, CI registration, refresh hook, live/browser
  run or publication is claimed. Clean independent delta review is pending.
