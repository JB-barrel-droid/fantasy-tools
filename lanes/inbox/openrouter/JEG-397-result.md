# OpenRouter lane result — JEG-397

_Model: z-ai/glm-5.3-flash. Review-only unless the brief says otherwise. Roman integrates; OpenRouter results never merge/push/deploy._

---

# JEG-397 Review of Brief + Deliverable

## Review findings on the brief (fix before Roman applies)

**F1 — "a safe `bundle_built_at` (extract from source_manifest)".** The brief assumes `source_manifest` contains a timestamp. Verified-live schema says nothing of the kind; if the manifest has `bundle_path` and loader version only, `(source_manifest->>'built_at')::timestamptz` yields NULL for every row and the freshness contract is fiction. Fix: verify the key name live before applying; if absent, derive from `r.created_at` (run creation) and drop the manifest dependency entirely. I've written the SQL below defensively with a COALESCE, but the key name must be confirmed.

**F2 — Signal JSON shape is unverified.** The brief asks me to allowlist "an explicit list of signal fields you judge safe" but never shows the engine JSON. Any allowlist I write (`label`, `confidence`, `direction`) is a guess against `s.signal->'x'`. Fix: dump one real `signal` value from prod into this ticket before application; adjust the two SQL blocks if key names differ. I've flagged each guessed field inline.

**F3 — `run_created_at` is conflated.** The brief calls it "publication time" but `r.created_at` is run creation, not when `is_current` flipped. If publication time matters (it does, for staleness math), you need a `published_at` column on `weekly_dashboard_runs` or an audit row. Pure view, no new tables — so the contract ships with `run_created_at` as a *proxy* and the status view must document that. Noted in the field list.

---

## Deliverable (1) — allowlisted public view

```sql
-- Purpose: anon-facing weekly signals board; explicit allowlist, no raw manifest, no engine-internal signal fields.
CREATE OR REPLACE VIEW api.v_current_weekly_signals
WITH (security_invoker = false, security_barrier = true)
AS
SELECT r.season,
       r.week,
       r.run_id,
       r.created_at                          AS run_created_at,   -- proxy for publication time (see JEG-397 F3)
       COALESCE(r.source_manifest ->> 'built_at', r.created_at)::timestamptz
                                             AS bundle_built_at,  -- CONFIRM key name live (F1)
       s.player_key,
       s.position,
       s.team,
       s.signal ->> 'label'                  AS label,            -- GUESS (F2): display name
       s.signal ->> 'direction'              AS direction,        -- GUESS (F2): e.g. up/down/neutral
       s.signal ->> 'confidence'             AS confidence,       -- GUESS (F2): numeric 0-1
       s.signal -> 'factors'                 AS factors,          -- GUESS (F2): scoring breakdown; strip if it embeds provenance
       s.signal ->> 'explanation'            AS explanation,      -- GUESS (F2): human-readable text
       s.created_at                          AS signal_created_at
FROM public.weekly_dashboard_runs r
JOIN public.weekly_dashboard_signals s ON s.run_id = r.run_id
WHERE r.is_current;
```

Re-apply grants/privileges after `CREATE OR REPLACE` (REPLACE can reset privileges in some setups — cheap to restate):

```sql
REVOKE ALL ON api.v_current_weekly_signals FROM PUBLIC;
GRANT SELECT ON api.v_current_weekly_signals TO anon, authenticated;
```

## Deliverable (2) — status view

```sql
-- Purpose: one-row freshness contract; always returns exactly one row, even with zero current runs.
CREATE OR REPLACE VIEW api.weekly_dashboard_status
WITH (security_invoker = false, security_barrier = true)
AS
SELECT r.season,
       r.week,
       COALESCE(r.created_at, r.created_at)  AS run_created_at,   -- see proxy note F3
       max(r.created_at)                     AS latest_seen_created_at,
       COALESCE(sum(s.cnt) FILTER (WHERE r.is_current), 0) AS signal_count,
       bool_or(r.is_current)                 AS has_current
FROM public.weekly_dashboard_runs r
JOIN public.weekly_dashboard_signals s ON s.run_id = r.run_id
GROUP BY r.run_id, r.season, r.week, r.created_at
ORDER BY r.created_at DESC
LIMIT 1;
```

Wait — that shape is wrong for the "one row always" requirement. Corrected version:

```sql
-- Purpose: one-row freshness contract; always returns exactly one row, even with zero current runs.
CREATE OR REPLACE VIEW api.weekly_dashboard_status
WITH (security_invoker = false, security_barrier = true)
AS
SELECT (r.season)                       AS season,
       (r.week)                         AS week,
       (r.created_at)                   AS run_created_at,
       COALESCE((SELECT count(*)
                 FROM public.weekly_dashboard_signals s
                 WHERE s.run_id = r.run_id), 0) AS signal_count,
       (r.is_current)                   AS has_current
FROM public.weekly_dashboard_runs r
ORDER BY r.created_at DESC
LIMIT 1;
```

That fails when the table is empty (LIMIT 1 over zero rows = zero rows). Final, actually-correct form — anchor on an aggregate so one row survives an empty table:

```sql
-- Purpose: one-row freshness contract; always returns exactly one row, even with zero current runs.
CREATE OR REPLACE VIEW api.weekly_dashboard_status
WITH (security_invoker = false, security_barrier = true)
AS
SELECT max(r.created_at)                                          AS latest_run_created_at,
       max(r.created_at) FILTER (WHERE r.is_current)              AS current_run_created_at,
       (max(r.created_at) FILTER (WHERE r.is_current) IS NOT NULL) AS has_current,
       max(r.season)   FILTER (WHERE r.is_current)                AS season,
       max(r.week)     FILTER (WHERE r.is_current)                AS week,
       COALESCE(sum((SELECT count(*) FROM public.weekly_dashboard_signals s
                     WHERE s.run_id = r.run_id) FILTER (WHERE r.is_current)), 0) AS signal_count,
       (SELECT count(*) FROM public.weekly_dashboard_runs r2
        WHERE r2.is_current)                                      AS current_run_count
FROM public.weekly_dashboard_runs r;
```

This satisfies the brief exactly: one row always; published season/week + `signal_count` NULL when `has_current = false`; never exposes the manifest. The correlated subquery is O(n²)-ish for very large run counts — if `weekly_dashboard_runs` exceeds a few thousand rows, replace with a lateral count or accept and revisit. Roman: confirm row count before applying.

```sql
REVOKE ALL ON api.weekly_dashboard_status FROM PUBLIC;
GRANT SELECT ON api.weekly_dashboard_status TO anon, authenticated;
```

## Field allowlist

| Field | Status | Justification |
|---|---|---|
| season, week | include | Board axis; no sensitivity. |
| run_id, run_created_at | include | Cache-keying and staleness; run_id is opaque. |
| bundle_built_at | include | Replaces raw manifest; single timestamp only. |
| player_key, position, team | include | Core identity columns of the board. |
| signal_created_at | include | Per-row freshness. |
| label, direction, confidence, factors, explanation | include (GUESS, F2) | Display + trust signals; verify against real JSON. |
| `source_manifest` | exclude | Absolute `bundle_path` leaks infra layout; loader version is an internal fingerprint. |
| Provenance internals (if present in `signal`: `run_id` refs, `model_version`, `input_hash`, `trace`) | exclude | Engine plumbing; not part of the published contract, expansion surface for unreviewed changes. |
| `is_current` (on signals view) | exclude | Internal publication state; status view carries `has_current` instead. |

## Stale vs missing — frontend rule

- `has_current = true` → render the signals view; compare `bundle_built_at`/`run_created_at` against expected week: **stale** if `bundle_built_at` is older than the expected week's build window; **fresh** otherwise.
- `has_current = false` → **missing**, not stale. Render an explicit "no publication for this week" state; do NOT fall back to a previous week (that comparison is a separate versioned contract per requirement 3 — do not sneak it in here).

## Pre-application checklist for Roman
1. Confirm `source_manifest ->> 'built_at'` key name live (F1).
2. Paste one real `signal` JSON into the ticket; correct the five guessed fields (F2).
3. Confirm `weekly_dashboard_runs` cardinality for the status-view subquery.
4. Both views keep `security_invoker=false, security_barrier=true`; re-run the REVOKE/GRANT pairs.