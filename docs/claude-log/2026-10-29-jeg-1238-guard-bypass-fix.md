## 2026-10-29 - JEG-1238 correction: four guard bypasses on 49e825dd

Correction to `2026-10-29-jeg-1238-identity-guard.md`: Codex's independent
review (Linear JEG-1238, 12:23 UTC, CHANGES REQUIRED) found that head accepted
four unsafe injections: a wrapper that discards the canonical answer and
returns 5; a wrapper whose only canonical call is in a dead nested helper; a
caller parameter named canonical_players; and canonical_players rebound to a
fake after import. Root cause: "any canonical-looking call in the body" and
module-global alias names stood in for return provenance and lexical binding.

Contract: replace the general allowance with a pinned one and prove provenance.
- `INJECTED_RESOLVER_CONTRACTS` lists the only (module, function, param)
  injection point (`lib/projection_capture.py`, `cbs_capture_rows`, `resolve`)
  and its only caller file (`save_cbsros_references.py`). Unregistered points,
  unpinned callers and a pinned caller that stops calling all fail.
- Every name is resolved lexically at its use (`_lookup`); a name bound two
  ways in one scope is never canonical; only the real import paths count.
- Wrapper defs need return provenance (`_returns_canonical`): every return is
  None, a canonical call (optionally indexed), a tuple/conditional of those, or
  a local bound only by `x[, y] = <canonical call>`.

### Verified (check named)
- Codex's four probes, run standalone against the new guard: each reports
  "build() is not given a canonical_players resolver"; the direct canonical
  control reports nothing.
- `tests.test_player_identity_guard` 19 PASS, with new cases for the four
  bypasses, a fake bound before the import, wrapper fallback/rebound/augmented/
  literal-branch/loop-var/own-input/generator/no-return/redefined, lambda
  fallback/ad-hoc/permit-all/shadowed-wrapper/untraceable/missing, impostor
  imports, and pinned-contract cases. Real-file mutations of
  `save_cbsros_references.py` (ad-hoc lambda, `or 0`, no canonical call,
  `return (5, None)`, `key or 5`, canonical_players rebound, caller moved or
  removed) fail.
- Guard mutations each turn the suite red: permit-all injection (30 failures),
  provenance by any canonical call (12), module-global alias names (6), first
  binding wins (1), unregistered points allowed (1), unpinned callers allowed
  (2), no missing-caller check (2), lambda fallback (2), wrapper `or` fallback
  (2), any literal return (4), partly rebound locals (2).
- Workflow identity modules `test_sleeper_identity_layer`,
  `test_match_identity_keys`, `test_source_snapshot_match` PASS; no issue
  anywhere in pipelines/.

### Claimed, not confirmed
- Runtime monkeypatching of `resolve_name` from another module is outside an
  AST guard; none exists in pipelines/ today (tests/ stubs are not scanned).
- The next Sleeper refresh passes its test step: not run (not authorized).
