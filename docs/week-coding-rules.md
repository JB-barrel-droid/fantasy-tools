# Week Coding Rules for Publisher Datasets

**Jeremy directive 2026-10-02:** "We need to codify elements of the page such as the headline to the dataset, so that we do not have these errors, along with rules on how weeks get coded to datasets."

## The Problem

On 2026-10-02, our dashboard labeled USA Today data as "Week 4" but the underlying pull was from a Week 3 article URL. The page headline clearly said "Week 4" on the live site, but our snapshot was stale. The week label was derived from the *request* (what we asked for), not from the *page content* (what we actually got).

## Rules

### Rule 1: Week must be extracted from page content, never assumed from request

Every publisher pull MUST extract the week number from page elements:
- **URL slug**: `.../trade-value-chart-week-N-...` → week N
- **Headline/title**: `"Week N <position> trade value chart"` → week N
- **Article H1**: Page headline containing "Week N"

The extracted week is the source of truth, not the `--week` argument.

### Rule 2: All week evidence must agree (fail closed)

Before a dataset is labeled with a week:
1. Extract week from URL slug
2. Extract week from all table titles/headlines
3. All table titles must agree (no mixed weeks)
4. URL week must match title week
5. Requested week (if given) must match extracted week

Any mismatch → **raise, do not label**. A dataset without a validated week is worse than no dataset.

### Rule 3: Week evidence travels with the dataset

Every pull output JSON MUST include:
```json
{
  "week": 4,
  "week_evidence": {
    "week": 4,
    "week_url": 4,
    "week_titles": [4],
    "week_requested": 4
  },
  "url": "https://...",
  "fetched_at": "2026-10-02"
}
```

Downstream consumers (fixture builders, validators) MUST check `week_evidence` before using the data.

### Rule 4: Fixture week labels must match pull week evidence

When building fixture sections from pull snapshots:
- The fixture's `week_designated` must equal the pull's `week`
- If they differ, the build FAILS (do not silently relabel)

### Rule 5: Display labels must reflect validated week

The dashboard's "Week N" labels must come from the fixture's validated `week`, not from the current NFL week or the request date. If the data is Week 3, the label says Week 3, even if it's currently Week 4.

## Implementation Status

| Puller | Week extraction | Validation | Status |
|--------|----------------|------------|--------|
| `ops/watchdog/pull_usatoday.py` | URL slug + table titles | Fail-closed on mismatch | ✅ Done 2026-10-02 |
| `ops/watchdog/pull_cbs.py` | URL slug only | None | ❌ TODO (JEG-77) |
| FantasyPros puller | TBD | None | ❌ TODO (JEG-77) |
| FantasyCalc puller | TBD (API-based) | None | ❌ TODO (JEG-77) |

## References

- JEG-77: End-to-end source fidelity checks
- `ops/watchdog/pull_usatoday.py::validate_week_consistency()` — reference implementation
- Incident 2026-10-02: USA Today Week 3 data labeled as Week 4
