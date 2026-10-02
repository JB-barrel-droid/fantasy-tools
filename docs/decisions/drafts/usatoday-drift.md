## draft-2026-10-02-usatoday-drift: USA Today native drift — refresh or accept
- id: draft-2026-10-02-usatoday-drift
- created: 2026-10-02
- deadline: 2026-10-09
- category: native-drift
- silence-default: proceed
- outcome: pending
- outcome_date:
- recommendation: DRAFT: refresh the USA Today snapshot through the documented `pull_usatoday.py` flow, then re-run the cascade and review; if the refresh fails twice, accept the existing snapshot and queue a follow-up.

### Context

The USA Today weekly trade chart is one of the four as-published
sources priced in the comparison dashboard. USA Today's per-week
article layout has been the source of three classes of drift in this
window:

1. Sitemap truncation. A truncated sitemap body (missing the closing
   `</urlset>`) must fail closed via `DiscoveryFailed`; the watchdog
   puller already enforces this. The half_12 combo's last refresh on
   2026-09-30 produced 238 rows with the proper 402-fetch fix in
   place; before that the page returned persistent 402 errors.
2. QB-table-under-h2 layout drift. The QB table sits under the
   generic "Week N fantasy trade charts" h2 (lazy h2->table pairing);
   `pull_usatoday.py::_clean_title_position` infers the QB title from
   the 1QB / 6-TD / SFLEX header signature. If the upstream layout
   moves again, the inferred QB title can land on the wrong column
   and the half_12 / full_12 / standard_12 QB rows silently zero out.
3. Native vs published drift. The lineage rebuild step compares the
   committed `native` against the published chart's values; if the
   page returns 402 or a degraded body, the lineage section turns
   red (`live_stale_sources`) without changing the snapshot.

This draft is the parked item for the next drift incident: when the
next native-vs-live delta trips the 5%/20% gate, do we (a) refresh
and re-review, or (b) accept and log a stale marker?

### Problem

When the USA Today snapshot's `native` no longer matches the live
published chart, the project has two competing defaults:

- Auto-refresh via the puller, re-run the cascade, and re-review —
  this keeps the dashboard honest but burns a review cycle and risks
  a wider layout-drift regression slipping through while the refresh
  is in flight.
- Accept the current snapshot and surface the drift visibly — this
  preserves the snapshot's identity (a Tuesday-Wednesday article
  lives for one NFL week) but the monitor stays red on the lineage
  section until next week's refresh.

Which default governs the next incident?

### Options

1. **Refresh and re-review.** Run `ops/watchdog/pull_usatoday.py
   --week N+1`, save through `save_usatoday_references.py`, rerun
   the cascade. Cheapest when the drift is real (article updated,
   values moved); most expensive when the drift is the watchdog
   hitting 402 again (refresh fails twice).
2. **Accept the snapshot, surface drift visibly.** Keep the
   committed snapshot, mark the lineage section
   `live_stale_sources` on USA Today, and queue the next week's
   article for refresh on the regular schedule. Cheapest when the
   drift is the fetch layer, not the data.
3. **Hybrid: bounded retry then accept.** Try the refresh once. If
   it succeeds, re-review. If it 402s or returns zero rows, accept
   and surface the stale marker. Caps the blast radius at one extra
   watchdog run per drift incident.

### Recommendation

DRAFT: Option 3 — bounded retry then accept. Reasoning: the project
already has a working fetch-fix recipe (the 2026-10-01
Accept-Language / Upgrade-Insecure-Requests header fix), and a
single refresh attempt is cheap. Two failures in a row is the
two-failure-rule trip — accept and queue the next week's article on
the normal schedule. The exact retry count and the exact threshold
for "the drift is large enough to act on" are TBD: this draft
follows the standing 5%/20% drift gate that
`check_fantasycalc_drift.py` already enforces for FantasyCalc, which
is the closest analog. If the reviewer wants a tighter gate for USA
Today, mark the threshold TBD here and decide before queueing.

### Outcome Note

(Empty while `outcome: pending`.)