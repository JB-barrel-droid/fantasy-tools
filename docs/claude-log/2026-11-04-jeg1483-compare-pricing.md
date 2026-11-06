## 2026-11-04 - JEG-1483 native Compare dual-level pricing

### Contract and ownership

Parent delegated the remaining complete-league Find→Compare mismatch to the
existing PR1302 owner. Keep the coordinator's presentation files and PR1297
untouched. Current worktree/remote claim agreed at a229a784; no second local
writer or branch changes were found. No merge, deployment or access changes.

### Verified (check named)

- Confirmed native receiveCarried used modeledPricing while collectCompare,
  tiers and samples separately read modeled rows. A new regression first
  failed with missing comparePricing, then passes58 assertions on complete
  frozen USO/Charlotte original-engine runs.
- trade-context.js now owns one provider and the existing completeness gate.
  league.js delegates its level composition; v2.js consumes the same provider
  for carried validation, tables/rosters, tiers, examples and edited-link
  identity. Identity includes each raw level's values, allocation and weights.
- Partial/stale rosters use the modeled path for manual work; a requested
  carried league level cannot silently fall back. Missing/changed levels hold.
  Both source ancestry and zero/null semantics are retained.
-14 focused contract/context/legacy tests pass. Native read-only browser
  probes at390 and1280 on preserved67b08e30 pass:741 row coverage, equal prices
  and identities, no roster writes/page errors, reload, Swap, sample rotation,
  edited link, Back, missing-level hold/recovery, manual league/explicit opt-out.
- Prior league-site test's blanket league hold is replaced with stronger
  actual dual-level identity/price/reload assertions. Its focused built-page
  run passes:1 test/40.410s, standard3948 trades and league3685 trades, actual
  values/dual-level identity/reload/saved-state assertions. First attempt failed
  in build setup because the bundled Playwright executable was absent; the
  supported CHROMIUM_PATH=/usr/bin/chromium corrected that technical setup.
  No broad suite or production math rerun. Build-generated outputs are preserved
  under /tmp/jeg1483-compare-build-output and excluded from the source change.

### Claimed, not confirmed

- The new coordinator full/Simple preview is not this native browser probe.
  Keep its published handoff hold until this exact head is adopted and tested.
- Draft render/full-build finalizers and independent review/release gates
  remain. No rollout or overall design-complete claim.
- Optional PR metadata update stays unexecuted after its prior approval denial.
