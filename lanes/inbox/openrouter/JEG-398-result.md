# OpenRouter lane result — JEG-398

_Model: z-ai/glm-5.3-flash. Review-only unless the brief says otherwise. Roman integrates; OpenRouter results never merge/push/deploy._

---

# JEG-398 — Runbooks (do NOT run; Roman executes after review)

**Assumed schema:** `weekly_dashboard_runs(run_id uuid pk, season int, week int, created_at timestamptz, is_current bool, manifest jsonb)`; `weekly_dashboard_signals(run_id uuid, player_key text, position text, payload jsonb)` — adjust column names (`manifest`/`payload`) if the live schema differs; I've marked them.

---

## Step 1 — Evidence export (SELECT only, run each, save outputs)

```sql
-- 1.1 Run registry: full audit record
SELECT r.run_id, r.season, r.week, r.created_at, r.is_current,
       r.manifest,                    -- <-- rename if column differs
       (SELECT count(*) FROM public.weekly_dashboard_signals s
         WHERE s.run_id = r.run_id) AS signal_count
FROM public.weekly_dashboard_runs r
WHERE r.season = 2026 AND r.week IN (3, 4)
ORDER BY r.week, r.created_at;

-- 1.2 Per-run player_key-set hash (ordered md5 of aggregated keys)
SELECT r.run_id, r.week,
       md5(string_agg(s.player_key, ',' ORDER BY s.player_key)) AS player_set_hash,
       count(*) AS n_keys
FROM public.weekly_dashboard_runs r
JOIN public.weekly_dashboard_signals s USING (run_id)
WHERE r.season = 2026 AND r.week IN (3, 4)
GROUP BY r.run_id, r.week
ORDER BY r.week;

-- 1.3 Position-NULL counts per run
SELECT r.run_id, r.week,
       count(*) FILTER (WHERE s.position IS NULL) AS position_null_count,
       count(*) AS total
FROM public.weekly_dashboard_runs r
JOIN public.weekly_dashboard_signals s USING (run_id)
WHERE r.season = 2026 AND r.week IN (3, 4)
GROUP BY r.run_id, r.week
ORDER BY r.week;
```

Compare `player_set_hash` across the two 402-row week-3 runs. **If the hashes differ, STOP — do not run Step 2.** See the decision note at the bottom.

---

## Step 2 — Cleanup (ONE transaction; fill `:KEEP_RUN_ID` from Step 1)

```sql
BEGIN;

-- Guard 1: week 4 / current run untouched, sanity on shape
DO $$
DECLARE
  empty_run  uuid;
  dup_run    uuid;
  keep_run   uuid := :'KEEP_RUN_ID';  -- psql var; if using SQL editor, inline the UUID from Step 1
  n_empty    int; n_dup int; n_keep int; n_w4 int;
BEGIN
  IF keep_run IS NULL THEN
    RAISE EXCEPTION 'JEG-398: KEEP_RUN_ID not set';
  END IF;

  -- Identify the empty week-3 run (0 signals) — no hardcoded UUIDs
  SELECT r.run_id INTO empty_run
  FROM public.weekly_dashboard_runs r
  WHERE r.season = 2026 AND r.week = 3 AND r.is_current = false
    AND NOT EXISTS (SELECT 1 FROM public.weekly_dashboard_signals s WHERE s.run_id = r.run_id);
  SELECT count(*) INTO n_empty FROM (
    SELECT r.run_id FROM public.weekly_dashboard_runs r
    WHERE r.season = 2026 AND r.week = 3 AND r.is_current = false
      AND NOT EXISTS (SELECT 1 FROM public.weekly_dashboard_signals s WHERE s.run_id = r.run_id)) x;
  IF n_empty <> 1 THEN RAISE EXCEPTION 'JEG-398: expected exactly 1 empty week-3 run, found %', n_empty; END IF;

  -- Identify the loser of the two 402-row runs: NOT the keeper, and is_current = false
  SELECT r.run_id INTO dup_run
  FROM public.weekly_dashboard_runs r
  WHERE r.season = 2026 AND r.week = 3 AND r.is_current = false
    AND r.run_id <> keep_run
    AND EXISTS (SELECT 1 FROM public.weekly_dashboard_signals s WHERE s.run_id = r.run_id);
  SELECT count(*) INTO n_dup FROM (
    SELECT r.run_id FROM public.weekly_dashboard_runs r
    WHERE r.season = 2026 AND r.week = 3 AND r.is_current = false
      AND r.run_id <> keep_run
      AND EXISTS (SELECT 1 FROM public.weekly_dashboard_signals s WHERE s.run_id = r.run_id)) x;
  IF n_dup <> 1 THEN RAISE EXCEPTION 'JEG-398: expected exactly 1 duplicate populated week-3 run, found %', n_dup; END IF;

  -- Keeper must exist, be week 3, populated, not current
  SELECT week, is_current,
         (SELECT count(*) FROM public.weekly_dashboard_signals s WHERE s.run_id = r.run_id)
    INTO n_keep, NULL, n_keep  -- split below if your PG version dislikes this form
  FROM public.weekly_dashboard_runs r WHERE r.run_id = keep_run;
  -- (safer, explicit:)
  IF NOT EXISTS (SELECT 1 FROM public.weekly_dashboard_runs
                 WHERE run_id = keep_run AND season = 2026 AND week = 3
                   AND is_current = false) THEN
    RAISE EXCEPTION 'JEG-398: keeper % is not a non-current week-3 run', keep_run;
  END IF;
  SELECT count(*) INTO n_keep FROM public.weekly_dashboard_signals WHERE run_id = keep_run;
  IF n_keep <> 402 THEN RAISE EXCEPTION 'JEG-398: keeper has % signals, expected 402', n_keep; END IF;

  -- Week-4 / current run must still exist untouched
  SELECT count(*) INTO n_w4 FROM public.weekly_dashboard_runs
  WHERE season = 2026 AND week = 4 AND is_current = true;
  IF n_w4 <> 1 THEN RAISE EXCEPTION 'JEG-398: week-4 current run missing/altered (% found)', n_w4; END IF;

  -- DELETE children before parents, week-3 only, non-current only
  DELETE FROM public.weekly_dashboard_signals s
  USING public.weekly_dashboard_runs r
  WHERE s.run_id = r.run_id AND r.run_id IN (empty_run, dup_run)
    AND r.week = 3 AND r.is_current = false;
  IF NOT FOUND AND (empty_run IS NOT NULL OR dup_run IS NOT NULL) THEN
    RAISE EXCEPTION 'JEG-398: expected signal deletions, none occurred';
  END IF;

  DELETE FROM public.weekly_dashboard_runs
  WHERE run_id IN (empty_run, dup_run) AND week = 3 AND is_current = false;
  IF NOT FOUND THEN RAISE EXCEPTION 'JEG-398: run deletion matched nothing'; END IF;

  -- Post-state assert: exactly one week-3 run with 402 signals remains; week 4 intact
  IF (SELECT count(*) FROM public.weekly_dashboard_runs WHERE season = 2026 AND week = 3) <> 1
     OR (SELECT count(*) FROM public.weekly_dashboard_runs WHERE season = 2026 AND week = 4 AND is_current) <> 1
     OR (SELECT count(*) FROM public.weekly_dashboard_signals s
          JOIN public.weekly_dashboard_runs r USING (run_id)
          WHERE r.season = 2026 AND r.week = 3) <> 402 THEN
    RAISE EXCEPTION 'JEG-398: post-state assertion failed';
  END IF;

  RAISE NOTICE 'JEG-398 cleanup OK: deleted % and %', empty_run, dup_run;
END $$;

COMMIT;
```

**Keeper selection rule (state this in the runbook, Roman picks from Step 1 output):**
1. Prefer the run whose `run_id` the week-3 signal rows actually reference with valid, consistent payloads — i.e., the one with the richer `manifest` (more fields / non-null `source`/`generated_at`).
2. Tie-break on **earliest** `created_at` (the original backfill, not the retry).
3. If both 402-row sets hash **identically**, either is safe — keeper choice is then purely cosmetic.

---

## Step 3 — Repair + hardening

```sql
-- 3.1 PRE-CHECK: report week-3 rows where pos is absent or non-allowlisted
SELECT s.run_id, s.player_key, s.payload->>'pos' AS pos_value, s.position AS current_position
FROM public.weekly_dashboard_signals s
JOIN public.weekly_dashboard_runs r USING (run_id)
WHERE r.season = 2026 AND r.week = 3
  AND (s.payload->>'pos' IS NULL
       OR s.payload->>'pos' NOT IN ('QB','RB','WR','TE'));

-- If 3.1 returns rows: STOP. Report them; do not run 3.2 until data is understood.

-- 3.2 Guarded backfill of position
BEGIN;
DO $$
DECLARE n_updated int; n_bad int;
BEGIN
  SELECT count(*) INTO n_bad
  FROM public.weekly_dashboard_signals s
  JOIN public.weekly_dashboard_runs r USING (run_id)
  WHERE r.season = 2026 AND r.week = 3
    AND (s.payload->>'pos' IS NULL OR s.payload->>'pos' NOT IN ('QB','RB','WR','TE'));
  IF n_bad > 0 THEN RAISE EXCEPTION 'JEG-398: % week-3 rows fail pos allowlist', n_bad; END IF;

  UPDATE public.weekly_dashboard_signals s
  SET position = s.payload->>'pos'
  FROM public.weekly_dashboard_runs r
  WHERE s.run_id = r.run_id AND r.season = 2026 AND r.week = 3
    AND s.position IS NULL
    AND s.payload->>'pos' IN ('QB','RB','WR','TE');
  GET DIAGNOSTICS n_updated = ROW_COUNT;
  IF n_updated <> 402 THEN RAISE EXCEPTION 'JEG-398: updated % rows, expected 402', n_updated; END IF;
  RAISE NOTICE 'JEG-398 position backfill OK: % rows', n_updated;
END $$;
COMMIT;

-- 3.3 Pre-checks for constraints (report-only)
-- FK: orphaned signals?
SELECT s.run_id, count(*) FROM public.weekly_dashboard_signals s
LEFT JOIN public.weekly_dashboard_runs r USING (run_id)
WHERE r.run_id IS NULL GROUP BY s.run_id;

-- UNIQUE: duplicate (run_id, player_key)?
SELECT run_id, player_key, count(*) FROM public.weekly_dashboard_signals
GROUP BY run_id, player_key HAVING count(*) > 1;

-- 3.4 Add constraints ONLY if both pre-checks return 0 rows
ALTER TABLE public.weekly_dashboard_signals
  ADD CONSTRAINT wds_run_fk FOREIGN KEY (run_id)
    REFERENCES public.weekly_dashboard_runs(run_id);
ALTER TABLE public.weekly_dashboard_signals
  ADD CONSTRAINT wds_run_player_uniq UNIQUE (run_id, player_key);
```

Note: `ALTER TABLE ADD CONSTRAINT` is not transactional-safe to mix with the DO-block guards here — run 3.3 checks first, and if clean, run 3.4 in its own transaction (or wrap 3.3+3.4 in one `BEGIN/COMMIT` since a failed ADD CONSTRAINT rolls back anyway).

---

## Decision: if the two 402-row sets have DIFFERENT content hashes

**Keep both; do not run Step 2.** Rationale:

- Different hashes means the two runs disagree on week-3 truth. Deleting either silently destroys a version of history that has no other backup, and no FK exists to tell you which set downstream consumers actually read.
- The task premise ("signals point at a run that is not the current one") assumed one canonical set; different hashes falsifies that premise, so the cleanup's keeper-selection heuristic (manifest richness, created_at) is no longer sufficient to determine which set is correct.
- Concrete action: export both full signal sets (`COPY (SELECT ... ORDER BY player_key) TO CSV` per run_id), diff them, and determine which is authoritative from the upstream source (the week-3 `pos`-mapping fix suggests the **later** run is the corrected one — but verify against the manifest's `generated_at`/source, don't assume). Then rerun Step 2 with the corrected keeper and add the loser's run to the delete set explicitly. The empty-run deletion and Step 3 hardening are unaffected by this ambiguity and can proceed independently.

---

**Review notes for Roman (things I'd flag about this plan):**
- The brief says "no FK from signals.run_id" — Step 2's delete-children-first ordering is therefore belt-and-braces, but keep it anyway; it makes the transaction correct after Step 3.4 lands.
- Step 2's guards hardcode the expectation `402`. If a guard trips on `402` after Step 1 showed different counts, that's a stop-condition, not a bug to fix by editing the number.
- The DO-block above uses `psql`-style `:'KEEP_RUN_ID'`; in a GUI SQL editor, inline the UUID literal directly. That is the only fill-in value in the runbook, sourced from Step 1.1.