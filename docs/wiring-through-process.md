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
