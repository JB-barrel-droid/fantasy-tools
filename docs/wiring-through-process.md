# Wiring-Through Process

**Standing rule (Jeremy, 2026-10-02):** When we fix things, they must always be wired through. A fix that is implemented but not connected to the live path is not done.

## The Problem

JEG-64 implemented VORP translation and stored values in Supabase, but the chart kept reading the old reindexed fixture values. The fix existed but wasn't wired through. This caused the Puka/JSN ordering flip to persist in production even though the correct values were in the database.

## The Process

Every fix must pass through these stages:

1. **Implement** — Write the code/fix
2. **Wire** — Connect it to the live data path (fixture, API, UI, etc.)
3. **Verify** — Prove the live path actually uses the fix (not just that the fix exists)
4. **Monitor** — Add a dashboard check that fails if the wiring breaks

### Verification Requirements

- **Don't just test the fix in isolation.** Test that the production artifact (fixture, API response, rendered page) reflects the fix.
- **Use ordering invariants.** For value transformations, verify that `if native A > native B then output A > output B`. This catches scaling bugs that preserve magnitudes but break ordering.
- **Check the actual bytes.** Read the fixture file, query the API, or inspect the rendered DOM — don't assume the pipeline connected them.

### Monitoring Checks

The monitoring dashboard must include checks that prove wiring, not just implementation:

- `test_vorp_wiring.py` — Verifies fixture reindexed values preserve native ordering (Puka/JSN test case). Fails if the per-bucket scaling bug returns or if VORP values aren't wired through.
- `pipelines/verify_vorp_wiring.py` — Standalone script for manual verification. Checks the same ordering invariant.

### Example: Puka/JSN Ordering Flip (2026-10-02)

**What happened:** FantasyCalc native had JSN (9914) > Puka (7386), but the chart showed Puka (53.3) > JSN (48.1).

**Root causes:**
1. Per-bucket reindex scaling (WR/dedicated vs WR/flex) used different scales, flipping order
2. JSN had no VORP-translated value due to name-matching failure ("jaxon smithnjigba" vs "jaxon smith-njigba")
3. JEG-64's VORP values were in Supabase but not wired into the fixture the chart reads

**Fixes applied:**
1. Fixed name normalization in `pipelines/vorp_translation/unified.py` (`_norm_name` strips non-alphanumeric)
2. Re-ran VORP translation (168 players, JSN included)
3. Re-ran `translate_via_vorp.py` to wire Supabase values into fixture
4. Added `test_vorp_wiring.py` regression test
5. Added `pipelines/verify_vorp_wiring.py` monitoring script

**Verification:** Fixture now has JSN 55.0 > Puka 41.0, matching native order. Test passes.

### Example: Stale _adjusted Sections (JEG-73, 2026-10-02)

**What happened:** The VORP-translation fix corrected raw FantasyCalc values (JSN 55.0 > Puka 41.0), but the `_adjusted` fixture sections were built from the OLD raw values and still showed the flipped ordering (JSN 31.2 < Puka 34.0). The live chart's adjusted curves were stale until someone manually re-ran the builder.

**Root cause:** `pipelines/translate_via_vorp.py` rewrote the raw `reindexed` values in the fixture but never triggered a rebuild of the `_adjusted` sections. The two writes were decoupled — the fix was implemented but not wired through to its downstream consumer.

**Fixes applied:**
1. Added `--rebuild-adjusted` to `translate_via_vorp.py`: after raw values change, it re-runs the (position, tier) affine adjustment cells over the fresh values and rewrites all four `{source}_adjusted` sections in the same pass. One write, no stale window.
2. Extended `pipelines/verify_vorp_wiring.py` with `ADJUSTED_ORDERING_TESTS`: 16 raw-vs-adjusted ordering pairs covering every 12-team combo on all 4 adjusted sources (fantasycalc, usatoday, fantasypros, cbs). The affine cells are monotonic, so any flip is staleness by definition.

**Verification:** `verify_vorp_wiring.py` prints all 16 OKs (e.g. fantasycalc_adjusted/half_12_qb1: JSN 40.0 > Puka 31.3). A stale rebuild would trip the check with the exact remediation (`build_adjusted_fixture_sections.py`).

**Wiring lesson:** When a pipeline stage rewrites values that a downstream stage derives from, the rebuild of the downstream stage belongs INSIDE the same write path (flag or automatic), never as a separate manual step someone must remember.

### Example: Player Identity Resolution (JEG-75, 2026-10-02)

**What happened:** Ad-hoc name normalization functions (`_norm_name`, `normalize_name`) were scattered across pipeline files, each implementing slightly different rules. This caused inconsistent player matching and broke the fail-closed identity rule ("nothing is guessed").

**Root cause:** Each saver implemented its own normalization logic instead of using a single canonical source. The differences in normalization (apostrophe handling, hyphen stripping, suffix handling, nickname expansion) caused 5/13 tricky names to differ, including:
- Ja'Marr (apostrophe variant)
- A.J. (period spacing)
- Amon-Ra (hyphen)
- Chris -> Christopher (nickname expansion)

**Fixes applied:**
1. Added `tests/test_player_identity_guard.py` - an AST-based regression test that scans the real pipelines tree and fails on new ad-hoc normalization functions, enforcing future use of the pre-existing `pipelines/lib/canonical_players.py` (`resolve()` registry-based resolution) for identity matching
2. Wired the guard into `make test-unit` to prevent regression
3. Deliberately did NOT migrate the existing local normalizers: a tricky-name battery (apostrophes, periods, hyphens, suffixes, nicknames) showed the canonical normalizer differs on 5/13 names (e.g. Chris->Christopher nickname expansion), which would have broken the fail-closed "nothing is guessed" rule in `save_razzball_references.py` and its identity tests. Migration of each existing site needs per-site analysis as follow-up work - the guard guarantees no NEW ad-hoc normalizers appear in the meantime.
4. Kept existing `normalize_name` in `match_source_snapshot.py` for label-only purposes (not identity matching)

**Verification:** The guard test passes, and the razzball identity tests (`test_nicknames_are_not_guessed`, `test_the_snapshots_own_player_norm_resolves_a_suffix_spelling`, `test_duplicate_players_stay_ambiguous_and_are_never_guessed`) all pass, proving the fail-closed behavior is preserved.
