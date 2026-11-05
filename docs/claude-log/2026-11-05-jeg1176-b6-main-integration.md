## 2026-11-05 - JEG-1176 main integration

Contract: integrate the history correction with main
`b6b3983a27e919f6bb03cea3a471b198219f056c` while preserving the rail,
footer, pricing implementation and methodology.

### Verified (check named)

- The normal merge applied without conflicts. Compared with prior main
  `94600b901f3bf4dd4313df8655c0c74da938c8ae`, the pinned revision adds
  three commits: release-switch activation, restoration and chain status.
- Their net diff changes four JSON files: chain status in `dist/` and
  `output/`, GitHub Actions status and source import health. The documents
  parse and match the pinned main blobs; both chain status copies match.
- The pause control has the same unpaused blob before and after these commits.
  Workflow health and import observations change; this status update does not
  establish fresh fixture or live-data recovery.
- The original rail and footer source and test blobs are unchanged.
  `git diff --check` passes for the integration delta.

### Claimed, not confirmed

- Required-browser `make validate` and `tests.test_v2_contract_render` must
  qualify the resulting exact head sequentially through the baseline attribution
  wrapper. Prior-head test results do not qualify this revision.
- Current-main checks, exact-head remote CI, delta review and fresh chain/live
  acceptance remain separate gates.
