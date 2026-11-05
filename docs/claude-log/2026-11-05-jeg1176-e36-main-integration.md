## 2026-11-05 - JEG-1176 pinned-main integration

Contract: integrate the history correction with main
`e36c26429087ff97ba9828e904ca789c4c46c27a`, preserving implementation,
regression coverage and value methodology.

### Verified (check named)

- Compared with main `b6b3983a27e919f6bb03cea3a471b198219f056c`, the pin
  adds two failed-chain status commits and one fidelity-pulse commit. Their net
  diff changes five operational JSON files: chain status in `dist/` and
  `output/`, fidelity pulse, GitHub Actions status and source import health.
- The normal merge applied without conflicts. All five imported JSON documents
  parse and match their pinned main blobs; the chain status copies match.
- The pause-control blob is unchanged and unpaused. This status delta does not
  establish fresh fixture or live-data recovery.
- Original rail/footer source and test blobs remain unchanged, and
  `git diff --check` passes for the integration delta.

### Claimed, not confirmed

- Required-browser `make validate` and `tests.test_v2_contract_render` must run
  sequentially through the baseline attribution wrapper on the resulting exact
  head. Prior-head results do not qualify this revision.
- Current-main green, exact-head remote CI, delta review and fresh chain/live
  acceptance remain separate gates.
