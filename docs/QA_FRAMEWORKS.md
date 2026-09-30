# QA Frameworks for Trade Value Dashboard

## Principle
One-off checks ("does Barkley match?", "is McBride within 22%?") are brittle and miss systemic issues. Each framework below validates an entire dimension systematically, for ALL players and ALL sources, with clear pass/fail criteria and root-cause attribution.

## Framework 1: Source Fidelity
**Question:** Does the data in our pipeline exactly match what the publisher published?

**Coverage:** Every source, every player, every value.

**Stages:**
1. **Live Page → Snapshot:** Scrape the rendered human-readable page. Compare each value against the snapshot's `native_value`. Must match exactly (or within documented rounding).
2. **Snapshot → Fixture:** Compare snapshot `native_value` against fixture `native`. Must match exactly.
3. **Fixture → Chart:** Compare fixture `values`/`reindexed` against what the chart renders. Must match exactly.

**Fail criteria:**
- Any mismatch at any stage = FAIL for that (source, player, stage)
- Missing snapshot path = FAIL (not "skip")
- API-derived "live" data = FAIL (must be rendered page)

**Root cause attribution:**
- Live ≠ Snapshot → Publisher updated page OR scraper broken
- Snapshot ≠ Fixture → Pipeline import bug
- Fixture ≠ Chart → Build/sync bug

## Framework 2: Identity Resolution
**Question:** Are we correctly identifying the same player across all sources?

**Coverage:** Every player name in every source.

**Rules:**
- All joins use numeric `player_key` from Supabase registry, never name strings
- Ambiguous names (two players, same normalized name) → FAIL CLOSED (excluded, not guessed)
- Team/position conflicts → FAIL visibly (not silent)
- Unanchored players (no ESPN anchor for reindex) → Excluded with reason, not silently dropped

**Fail criteria:**
- Name-based join (not player_key) = FAIL
- Ambiguous identity resolved by guessing = FAIL
- Player appears in output with wrong team/position = FAIL

## Framework 3: Transformation Verification
**Question:** Is every mathematical transformation correct for every player?

**Coverage:** Every player, every transformation step.

**Transformations:**
1. **ESPN:** `ros_half_ppr / 16 = native_per_game` → DDF leg → `fixture values`
   - Verify: `fixture_value == round(ddf_leg_value)` for ALL 353 players
2. **Reindexed sources:** `native → isotonic_reindex → fixture`
   - Verify: Rank order preserved (if A > B in native, then A > B in reindexed)
   - Verify: No value invented (reindexed values come from isotonic fit, not manual)
3. **Adjusted sources:** `published → bias_adjustment → fixture`
   - Verify: `adjusted = max(0, alpha + beta * published)` for ALL players
   - Verify: `bake_id` matches the DDF leg used for fitting

**Fail criteria:**
- Any player where `recomputed != actual` = FAIL
- Any transformation using stale inputs (bake_id mismatch) = FAIL
- Any manual value override = FAIL

## Framework 4: Temporal Consistency
**Question:** Are we using fresh data consistently, or mixing vintages?

**Coverage:** Every data file, every snapshot, every fixture.

**Rules:**
- Freshness = content vintage (when publisher updated), never file mtime
- ESPN CSV vintage must match the DDF leg vintage must match the fixture vintage
- Snapshot picker must skip `_archived*` directories
- No output may be rescaled/pinned to a pie older than its inputs

**Fail criteria:**
- Fixture built from mixed vintages (e.g., 09-29 ESPN with 09-30 USA Today) = FAIL
- `_archived*` directory selected by picker = FAIL
- Adjusted sections using older bake_id than base = FAIL

## Framework 5: Cross-Source Agreement
**Question:** Where do sources genuinely disagree, and is the disagreement real?

**Coverage:** Every player, every pair of sources.

**Method:**
- For each player, compute pairwise divergences between sources
- Flag divergences > 25% for investigation
- Distinguish REAL disagreement (different projections) from ARTIFACT (stale data, scale mismatch, identity error)

**Fail criteria:**
- Divergence flagged but not investigated = FAIL (must have root cause)
- Divergence due to stale data = FAIL (refresh, don't exclude)
- Player excluded from guard without documented root cause = FAIL

**Not a fail:**
- Genuine projection disagreement (e.g., ESPN loves Allen more than peers) → Document, don't hide

## Framework 6: Rendered Output Verification
**Question:** Does the live production page show the correct data?

**Coverage:** Desktop and mobile, every chart control.

**Checks:**
- Live JSON loads and parses
- Player count matches fixture
- Top player values match fixture (spot-check top 10 per source)
- Week labels match data vintage (not hardcoded)
- No JavaScript errors in console

**Fail criteria:**
- Live JSON 404 or parse error = FAIL
- Live values differ from fixture = FAIL (sync bug)
- Hardcoded "Week N" label doesn't match data week = FAIL

## Implementation Status

| Framework | Status | Builder | Monitor Section |
|-----------|--------|---------|-----------------|
| Source Fidelity | ✅ Live | `build_source_fidelity.py` | "Source fidelity — pre-indexed values" |
| Identity Resolution | ⚠️ Partial | Manual (needs automation) | N/A |
| Transformation Verification | ✅ Live | `build_index_math.py` | "Index math — raw to indexed" |
| Temporal Consistency | ⚠️ Partial | `verify_import_health.py` | "Import health" |
| Cross-Source Agreement | ❌ Missing | Needs builder | N/A |
| Rendered Output Verification | ⚠️ Partial | Manual | N/A |

## Next Steps
1. Automate Identity Resolution framework (player_key join verification)
2. Build Cross-Source Agreement framework with systematic divergence detection
3. Automate Rendered Output Verification (headless browser checks)
4. Add header verification to scrapers (confirm page title matches expected week)
