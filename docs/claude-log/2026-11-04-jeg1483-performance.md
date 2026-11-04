## 2026-11-04 - JEG-1483 canonical search hot path

Contract: address the UI owner's reported slow enumeration without dropping
valid candidates or changing formulas. Own backend/tests/CI only; no presentation
files, baseline, source transfer or Simplified branch changes.

### Verified (check named)

- Browser profile of the same full four-team historical input:24,675 bounded
  packages completed without cancellation/caps. Before5.6656s, after1.3462s.
  Both counts1269 Natural/23406 Other, top-ten IDs identical, full Review
  decisions equal prepared search records. Source hashes/observations are in
  docs/specs/jeg1483-performance-receipt.json.
- Reuse the existing before-lineup and noise formula; optional cached lineups
  feed the same rosterConstructionOk. A private per-pair evaluator caches row
  indexes/source conversions/before-lineups only. Every candidate and after
  lineup is still evaluated; no legacy filters or early truncation is added.
  Decision-only scans omit physical table rendering work; canonicalReadout
  still builds the full original evidence for an opened package.
- Canonical yields use native cooperative tasks, eliminating an rAF dependency.
  Original legacy scheduling stays unchanged. Existing snapshot and final
  cancellation protections remain.
-62 readout assertions,60 candidate/parity assertions,32 policy-matrix cases,
  unchanged319 legacy readout checks, and focused Python contract/legacy
  opportunity tests pass. The numeric oracle's records are unchanged; only
  module source provenance hashes are refreshed. No broad rerun.

### Claimed, not confirmed

- This executor's isolated kernel benchmark is not the full coordinator UI's
  latency. UI callbacks/layout and larger supplied virtual-partner workloads
  still need its author measurements. No UI file or baseline was modified.
- Full required CI remains gated by draft status; no ready transition, merge
  or deploy occurs here. Independent review and final journey remain separate.
- Optional PR metadata refresh remains unexecuted after its approval rejection;
  no metadata workaround or unapproved retry occurs.
