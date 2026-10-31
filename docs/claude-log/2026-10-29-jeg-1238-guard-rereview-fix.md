## 2026-10-29 - JEG-1238 second correction: re-review holes on 05ce4aa4

Codex's focused re-review (Linear JEG-1238, 14:13 UTC) confirmed the first
four bypasses rejected and the direct canonical control accepted, and found
four more accepted injections: a `global canonical_players` write, a
`nonlocal` write by an invoked nested writer, a decorated wrapper, and an
async wrapper.

Contract: close those narrow holes without a rewrite, keeping the positive path.
- `_tainted`: a name with any `global`/`nonlocal` declaration in the module,
  an attribute write/delete on it, or setattr/delattr on it is never a trusted
  canonical or def binding (`_lookup`). Conservative: declaration alone counts,
  called or not.
- `_wrapper_ok`: only a plain, undecorated, sync module-level def can be a
  wrapper.

### Verified (check named)
- Codex's four new probes, standalone against the guard: each reports
  "build() is not given a canonical_players resolver"; direct control: none.
- `tests.test_player_identity_guard` 20 PASS; new `test_second_review_holes_fail`
  (global, nonlocal writer, uncalled global writer, global swap of the wrapper,
  module attribute write, setattr, decorated, decorated via lambda, async,
  async via lambda) plus real-file mutations (resolve_name decorated, made
  async, canonical_players written through global) all fail as expected.
- Guard mutations turn the suite red: taint ignored (7), no global/nonlocal
  taint (5), no attribute-write taint (1), no setattr taint (1), decorators
  allowed (3), async allowed (3).
- `test_sleeper_identity_layer`, `test_match_identity_keys`,
  `test_source_snapshot_match` PASS; no issue anywhere in pipelines/.

### Claimed, not confirmed
- Writes from another module (`mod.canonical_players = x`, monkeypatching) and
  reflective writes (`globals()[...]`, `vars()`) are outside this AST guard;
  none exist in pipelines/ today.
