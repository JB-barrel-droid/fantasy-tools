# Trade Value Chart — Module Map & Lanes

**Rule: One instruction → one lane. Never touch two modules for one fix. Never create branching conflicts within a module.**

## The 5 Modules — With Layers

### 1. data-pipeline — 🔴 DEGRADED
**Owns:** Source snapshots → live fixture (`comparison-sources-data.json`)

| Layer | Script / File | Status |
|-------|---------------|--------|
| L1 · Source pulls | `data/raw/sources/<source>/` | ✅ All 5 have snapshots |
| L2 · Import → Supabase | `import_source_snapshot.py`, `save_espn_cbs_references.py` | ✅ Tables populated |
| L3 · Health gate | `verify_import_health.py` → `output/source-import-health.json` | ✅ All 5 "ok" |
| L4 · Build section | `build_comparison_source_section.py` → candidate | ❓ Unknown for 4 sources |
| L5 · Review | `review_comparison_candidate.py` | ❓ Unknown |
| L6 · Promote → live | `promote_comparison_section.py` → `comparison-sources-data.json` | 🔴 Only ESPN promoted |
| L7 · Bake players | `bake_players.py` → `data/fixtures/current/players.json` | ❓ Check needed |

**Live data (2026-09-22):**
- ESPN: 7,152 values, snapshot 2026-09-21 — ✅
- CBS: 0 values (372 rows in Supabase, Week 2) — 🔴 not promoted
- FantasyCalc: 0 values (594 rows in Supabase, Week 2) — 🔴 not promoted
- FantasyPros: 0 values (534 rows in Supabase, 2026-09-15) — 🔴 not promoted
- USA Today: 0 values (714 rows in Supabase, 2026-09-15) — 🔴 not promoted

### 2. curve-widget — 🟡 NEEDS ATTENTION
**Owns:** Chart rendering, guards, smoothing, fixed-pie

| Layer | File / Check | Status |
|-------|--------------|--------|
| L1 · Guard logic | `activeKeysForGuard`, empty-source skip | ✅ Present, needs negative test |
| L2 · Rendering | `quadraticCurveTo` smoothing | ✅ Present |
| L3 · Fixed-pie math | Two-tier, bench share | 🔴 6 test failures (data drift) |

### 3. comparison-dashboard — 🟢 HEALTHY
**Owns:** Player news, health panel, dataset status

| Layer | File / Check | Status |
|-------|--------------|--------|
| L1 · Player news | `ingest_player_news.py` → max 3 + timing badges | ✅ |
| L2 · Health panel | Dataset health display | ✅ |

### 4. page-shell — 🟢 HEALTHY
**Owns:** Header dates, build tag, layout

| Layer | File / Check | Status |
|-------|--------------|--------|
| L1 · Header/dates | `monthDayTime`, asOfDate + ecrContentDate | ✅ Dates show time |
| L2 · Build tag | `trade-chart-build` meta + footer | ✅ Current |

### 5. build-deploy — 🟢 HEALTHY
**Owns:** Sync, tests, push, deploy, verify

| Layer | Script / Check | Status |
|-------|---------------|--------|
| L1 · Sync | `deploy.sh`: app/ → dist/ | ✅ Byte-identical |
| L2 · Tests | `test_two_tier_frontend` | 🟡 6 failures (see lane 2) |
| L3 · Push/deploy | GitHub API → Pages | ✅ Remote: `6a5dd0e09fc9` |
| L4 · Verify | `verify_live.py` | ✅ LIVE OK |

## Live Dashboard

**URL:** https://jb-barrel-droid.github.io/fantasy-tools/modules/dashboard.html

Fetches live `comparison-sources-data.json` + `source-import-health.json` via JavaScript.
Click any module to expand its layers. No baked values — always current.

## Lane Rules

1. **Jeremy's instruction goes in exactly one lane.** If it touches two modules, split it into two lane items.
2. **One active change per lane.** Finish or explicitly pause the current item before starting the next in the same lane.
3. **Cross-lane dependencies are explicit.** If lane 2 needs lane 1's data, write it down; don't silently couple them.
4. **verify_live.py is the gate for lanes 2, 3, 4.** Nothing is "done" until the live check passes.
5. **Data staleness (lane 1) never blocks code fixes (lanes 2-4).** Ship the code; mark the data honestly.

## Current Lane Status (2026-09-22)

### Lane 1: data-pipeline — 🔴 DEGRADED
- `built_at`: 2026-09-19T15:48:29Z (stale, 3 days old)
- ESPN: 596 values, max 81.8 — OK
- CBS: 0 values — EMPTY
- FantasyPros: 0 values — EMPTY
- USA Today: 0 values — EMPTY
- **Open items:**
  - [ ] Refresh source data (needs pipeline run — blocked on source pulls)
  - [ ] OR explicitly mark CBS/FantasyPros/USA Today as paused in UI

### Lane 2: curve-widget — 🟡 NEEDS ATTENTION
- Guard fix (`activeKeysForGuard`): present
- Empty-source skip: present
- Smoothing (`quadraticCurveTo`): present
- **Open items:**
  - [ ] `test_two_tier_frontend`: 6 failures (caused by data/fixtures changes from background workstreams, not the guard fix — needs data lane to resolve or test update)
  - [ ] Guard still needs negative-test proof against simulated empty-source defect

### Lane 3: comparison-dashboard — 🟢 HEALTHY
- News max-3 cap: present
- Timing badges (`post-values`/`pre-values`): present
- **Open items:** none

### Lane 4: page-shell — 🟢 HEALTHY
- Build tag: `tv-20260922-1439-cbbcefe` (current)
- `monthDayTime` formatter: present
- Header shows date + time: yes
- **Open items:** none

### Lane 5: build-deploy — 🟢 HEALTHY
- `deploy.sh` syncs app→dist: working
- `verify_live.py`: exits 0 (LIVE OK as of 2026-09-22)
- app/dist byte-identical: yes
- **Open items:** none
- **Note:** `deploy.sh` does not auto-push; API push is manual step. This is intentional (user controls pushes).
