## 2026-11-05 - JEG-1176 current-main status integration

Contract: integrate the history loader with pinned main
`216a9143ed33da42220777124c44c55d6fac1d3c` while preserving implementation,
regression coverage and value methodology.

### Verified (check named)

- The normal merge applied without conflicts. Compared with main
  `96bcd199bb3802db7958e9874f387d039cf548fc`, the pin adds one chain-status
  commit changing four operational JSON files: chain status in `dist/` and
  `output/`, GitHub Actions status and source import health.
- The imported documents parse as JSON and match their pinned main blobs.
  Both chain status copies match. The pause control remains unchanged.
- The landed capture-clock implementation and regression, original rail/footer
  blobs, pricing engine, Python reference, waiver-band tests and the
  `priced > 100` assertion are unchanged. `git diff --check` passes.
- The imported status records a prospective Week 9 waiver-band validation
  failure and no fixture publication. This is distinct from qualification
  against the committed fixture; it does not establish live-data recovery.

### Claimed, not confirmed

- The clock regression and required-browser `make validate` must qualify the
  resulting exact head. The contract suite follows successful validation,
  sequentially through the baseline attribution wrapper.
- Prior-head results do not qualify this revision or clear the recorded
  prospective-data failure. Current-main green, exact-head remote CI, delta
  review and fresh chain/live acceptance remain separate gates.
