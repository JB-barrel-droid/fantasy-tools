# Trade Value Chart — Module Map & Lanes

**Rule: One instruction → one lane. Never touch two modules for one fix. Never create branching conflicts within a module.**

## The 5 Modules

| # | Module | Files | What it owns | Health check |
|---|--------|-------|--------------|--------------|
| 1 | **data-pipeline** | `app/trade-value-chart/assets/comparison-sources-data.json` | Source snapshots, per-player values, `built_at` | Every source has >0 values; snapshot date is current |
| 2 | **curve-widget** | `app/trade-value-chart/assets/curve-widget.js`, `curve-widget.css` | Chart rendering, regression guards, smoothing, fixed-pie, bench share | `verify_live.py` markers present; `test_two_tier_frontend` green |
| 3 | **comparison-dashboard** | `app/trade-value-chart/assets/comparison-dashboard.js` | Player news (max 3, timing badges), health panel, dataset status | News capped at 3; timing badges present |
| 4 | **page-shell** | `app/trade-value-chart/index.html` | Header dates with time, build tag, footer, layout | Build tag current; `monthDayTime` present |
| 5 | **build-deploy** | `deploy.sh`, `verify_live.py`, `.github/workflows/pages.yml` | Sync app→dist, tests, push, deploy, live verification | `verify_live.py` exits 0; app/dist byte-identical |

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
