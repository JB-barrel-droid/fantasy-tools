-- ============================================================
-- Migration 007: on-demand VORP-family computation
-- Date: 2026-10-04
-- Branch: minimax/jeg-332-vorp-view
-- Status: DESIGNED — apply via the Supabase SQL editor.
--         (PostgREST cannot run DDL. After apply: NOTIFY pgrst, 'reload schema'.)
--
-- PURPOSE
--   Replace any pre-stored Cartesian (shape × teams × roster_shape × bench_share)
--   row explosion with a single shape-independent layer queried on demand.
--   Per-port semantics live in pipelines/build_reweighted_values.py
--   (8-group methodology, 15% bench default, ROS horizon) and
--   pipelines/preview_vorp_views.py (how vorp / vorp_indexed / adj_values are
--   derived per combo). This migration reproduces those semantics in SQL.
--
-- INPUT CONTRACT (p_base jsonb)
--   Per player:
--     {
--       "player_key":   "<positive integer as text>",  -- canonical key
--       "position":     "QB" | "RB" | "WR" | "TE",
--       "surplus_ppg":  <numeric, >= 0>,  -- raw PPG above waiver (shape-independent)
--       "native":       <numeric, >= 0>   -- as-published native trade value (for indexed)
--     }
--   p_base MAY omit `native` for sources that do not publish trade values;
--   vorp_indexed for such players is NULL, never a fabricated value.
--
-- ROSTER SHAPE (p_roster_shape jsonb)
--   The four named shapes from docs/contract/fe-read-contract-v1.md:
--     default 1QB    -> {"QB":1,"RB":2,"WR":3,"TE":1,"FLEX":1,"BENCH":6}
--     default SUPERFLEX, custom-A, custom-B -> NEEDS-REVIEW (not in repo)
--   This function takes shape as a jsonb parameter and never defaults it.
--   The shape MUST define at least {QB, RB, WR, TE, FLEX, BENCH} as
--   nonnegative integers; values outside that schema FAIL CLOSED.
--
-- BENCH_SHARE (p_bench_share numeric)
--   Default 0.15. Hard-bounded to [0.01, 0.30] — values outside the bounds
--   RAISE EXCEPTION. The bench share is the proportion of each position's
--   total surplus that is allocated to the bench role; the remainder goes
--   to starters. This is the 8-group methodology parameter; the single
--   constant of 15% bench is the as-published default.
--
-- OUTPUT
--   RETURNS TABLE (player_key text, vorp numeric, vorp_indexed numeric,
--                  adj_values numeric)
--     vorp        : 8-group proportional allocation of surplus_ppg per player.
--     vorp_indexed: native * 70 / max_native across non-cut players (NULL if
--                   no native values were supplied).
--     adj_values  : vorp * 70 / max(vorp) across non-cut players.
--
-- FAIL-CLOSED IDENTITY
--   * bench_share outside [0.01, 0.30]                -> RAISE EXCEPTION
--   * scoring not in {'standard','half_ppr','ppr'}   -> RAISE EXCEPTION
--   * teams <= 0                                     -> RAISE EXCEPTION
--   * roster_shape missing required keys              -> RAISE EXCEPTION
--   * roster_shape values not nonnegative ints       -> RAISE EXCEPTION
--   * duplicate canonical player_key in p_base       -> RAISE EXCEPTION
--   * position outside {QB,RB,WR,TE}                  -> RAISE EXCEPTION
--   * surplus_ppg / native not finite, nonnegative   -> RAISE EXCEPTION
--   * sum_surplus[pos, role] == 0 while target > 0   -> RAISE EXCEPTION
--   * max_native == 0 while native values provided   -> RAISE EXCEPTION
--   * No eligible native values for vorp_indexed     -> all NULL (NOT an error)
-- ============================================================

-- =========================================================
-- 1. Input validators (PL/pgSQL, IMMUTABLE per-call semantics).
-- ============================================================

-- Validate bench_share in [0.01, 0.30]. Default 0.15.
CREATE OR REPLACE FUNCTION public._vorp_validate_bench_share(p_bench_share numeric)
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v numeric;
BEGIN
    IF p_bench_share IS NULL THEN
        v := 0.15;
    ELSIF p_bench_share < 0.01 OR p_bench_share > 0.30 THEN
        RAISE EXCEPTION 'bench_share % out of bounds [0.01, 0.30]'
            USING ERRCODE = '22023';
    ELSE
        v := p_bench_share;
    END IF;
    RETURN v;
END;
$$;

COMMENT ON FUNCTION public._vorp_validate_bench_share(numeric) IS
    'JEG-332: bench_share hard-bounded to [0.01, 0.30]; NULL defaults to 0.15; out-of-range raises.';

-- Validate scoring string.
CREATE OR REPLACE FUNCTION public._vorp_validate_scoring(p_scoring text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_scoring IS NULL OR p_scoring NOT IN ('standard', 'half_ppr', 'ppr') THEN
        RAISE EXCEPTION 'scoring must be one of standard, half_ppr, ppr; got %', p_scoring
            USING ERRCODE = '22023';
    END IF;
    RETURN p_scoring;
END;
$$;

COMMENT ON FUNCTION public._vorp_validate_scoring(text) IS
    'JEG-332: scoring whitelist {standard, half_ppr, ppr}; anything else raises.';

-- Validate teams count.
CREATE OR REPLACE FUNCTION public._vorp_validate_teams(p_teams int)
RETURNS int
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_teams IS NULL OR p_teams <= 0 THEN
        RAISE EXCEPTION 'teams must be a positive integer; got %', p_teams
            USING ERRCODE = '22023';
    END IF;
    RETURN p_teams;
END;
$$;

COMMENT ON FUNCTION public._vorp_validate_teams(int) IS
    'JEG-332: teams must be a positive integer; anything else raises.';

-- Validate roster_shape jsonb. Returns the parsed jsonb so the caller
-- can index keys without re-parsing. Required keys: QB,RB,WR,TE,FLEX,BENCH,
-- each a nonnegative integer.
CREATE OR REPLACE FUNCTION public._vorp_validate_roster_shape(p_roster_shape jsonb)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    required text[] := ARRAY['QB','RB','WR','TE','FLEX','BENCH'];
    k text;
    v jsonb;
    n int;
BEGIN
    IF p_roster_shape IS NULL OR jsonb_typeof(p_roster_shape) <> 'object' THEN
        RAISE EXCEPTION 'roster_shape must be a jsonb object; got %', p_roster_shape
            USING ERRCODE = '22023';
    END IF;
    FOREACH k IN ARRAY required LOOP
        IF NOT p_roster_shape ? k THEN
            RAISE EXCEPTION 'roster_shape missing key %; required keys: %', k, required
                USING ERRCODE = '22023';
        END IF;
        v := p_roster_shape -> k;
        IF jsonb_typeof(v) <> 'number' THEN
            RAISE EXCEPTION 'roster_shape[%] must be a number; got %', k, v
                USING ERRCODE = '22023';
        END IF;
        n := (v #>> '{}')::int;
        IF n IS NULL OR n < 0 OR (v #>> '{}')::numeric <> n::numeric THEN
            RAISE EXCEPTION 'roster_shape[%] must be a nonnegative integer; got %', k, v
                USING ERRCODE = '22023';
        END IF;
    END LOOP;
    RETURN p_roster_shape;
END;
$$;

COMMENT ON FUNCTION public._vorp_validate_roster_shape(jsonb) IS
    'JEG-332: roster_shape must be a jsonb object with QB,RB,WR,TE,FLEX,BENCH as nonnegative integers; otherwise raises.';

-- =========================================================
-- 2. The on-demand computation.
--
-- Signature mirrors the task spec; semantics ported from
--   pipelines/build_reweighted_values.py (8-group methodology,
--   15% bench default, ROS horizon, apply_70_anchor) and
--   pipelines/preview_vorp_views.py (indexed = native * 70 / peak).
-- =========================================================

CREATE OR REPLACE FUNCTION public.compute_vorp_views(
    p_base          jsonb,
    p_scoring       text,
    p_teams         int,
    p_roster_shape  jsonb,
    p_bench_share   numeric DEFAULT 0.15
)
RETURNS TABLE (
    player_key     text,
    vorp          numeric,
    vorp_indexed  numeric,
    adj_values    numeric
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_scoring      text;
    v_teams        int;
    v_roster       jsonb;
    v_bench_share  numeric;

    -- Per-position slot counts per team (from p_roster_shape).
    slot_qb        int;
    slot_rb        int;
    slot_wr        int;
    slot_te        int;
    slot_flex      int;
    slot_bench     int;

    -- 8-group totals over non-cut players.
    -- (pos, role) totals of surplus_ppg, plus count of native values seen.
    sum_surplus    numeric[][]; -- [pos_idx][role_idx] (1=starter,2=bench)
    max_native     numeric;
    max_imputed    numeric;
    peak           numeric;

    -- Per-player derived state collected into temp arrays via jsonb_each.
    rec            record;

    -- Iterators.
    k              text;
    v              jsonb;
    pos            text;
    surp           numeric;
    native_val     numeric;

    -- Roster inference state.
    candidates     jsonb;  -- [{k, position, surp, native, native_present}, ...]
    c              jsonb;
    j              int;
    n_cand         int;
    flex_pool      jsonb;
    remaining      jsonb;

    -- 8-group role assignment per player (text id -> text 'starter'|'bench'|'cut').
    role_of        jsonb := '{}'::jsonb;

    -- Effective targets per (pos, role).
    eff_target     jsonb := '{}'::jsonb;
    pos_total      numeric;
    starter_target numeric;
    bench_target   numeric;

    -- Per-player imputed_vorp, collected then scaled.
    imputed        jsonb := '{}'::jsonb;
    imp_pos_total  numeric;
    starter_sum    numeric;
    bench_sum      numeric;

    -- Final outputs.
    out_vorp       numeric;
    out_indexed    numeric;
    out_adj        numeric;
    pos_idx        int;
BEGIN
    -- ------------------------------------------------------------
    -- 1. Validate inputs (fail-closed). The result of each validator
    --    is the canonicalized value the rest of the function uses.
    -- ------------------------------------------------------------
    v_scoring      := public._vorp_validate_scoring(p_scoring);
    v_teams        := public._vorp_validate_teams(p_teams);
    v_roster       := public._vorp_validate_roster_shape(p_roster_shape);
    v_bench_share  := public._vorp_validate_bench_share(p_bench_share);

    slot_qb    := (v_roster ->> 'QB')::int;
    slot_rb    := (v_roster ->> 'RB')::int;
    slot_wr    := (v_roster ->> 'WR')::int;
    slot_te    := (v_roster ->> 'TE')::int;
    slot_flex  := (v_roster ->> 'FLEX')::int;
    slot_bench := (v_roster ->> 'BENCH')::int;

    IF p_base IS NULL OR jsonb_typeof(p_base) <> 'object' THEN
        RAISE EXCEPTION 'p_base must be a jsonb object keyed by player_key'
            USING ERRCODE = '22023';
    END IF;

    -- ------------------------------------------------------------
    -- 2. Parse p_base. Each row MUST have {position, surplus_ppg};
    --    native is OPTIONAL. Duplicate keys, malformed positions,
    --    and non-finite / negative numbers all RAISE EXCEPTION.
    -- ------------------------------------------------------------
    candidates := '[]'::jsonb;
    FOR k, v IN SELECT * FROM jsonb_each(p_base) LOOP
        IF jsonb_typeof(v) <> 'object' THEN
            RAISE EXCEPTION 'p_base[%] must be an object; got %', k, v
                USING ERRCODE = '22023';
        END IF;
        pos := v ->> 'position';
        IF pos IS NULL OR pos NOT IN ('QB','RB','WR','TE') THEN
            RAISE EXCEPTION 'p_base[%] position must be QB/RB/WR/TE; got %', k, pos
                USING ERRCODE = '22023';
        END IF;
        IF v ->> 'surplus_ppg' IS NULL THEN
            RAISE EXCEPTION 'p_base[%] missing surplus_ppg', k
                USING ERRCODE = '22023';
        END IF;
        BEGIN
            surp := (v ->> 'surplus_ppg')::numeric;
        EXCEPTION WHEN OTHERS THEN
            RAISE EXCEPTION 'p_base[%] surplus_ppg not numeric: %', k, v ->> 'surplus_ppg'
                USING ERRCODE = '22023';
        END;
        IF surp IS NULL OR NOT (surp = surp) OR surp < 0 THEN
            RAISE EXCEPTION 'p_base[%] surplus_ppg must be finite nonnegative; got %', k, surp
                USING ERRCODE = '22023';
        END IF;
        native_val := NULL;
        IF v ? 'native' AND v ->> 'native' IS NOT NULL THEN
            BEGIN
                native_val := (v ->> 'native')::numeric;
            EXCEPTION WHEN OTHERS THEN
                RAISE EXCEPTION 'p_base[%] native not numeric: %', k, v ->> 'native'
                    USING ERRCODE = '22023';
            END;
            IF native_val IS NULL OR NOT (native_val = native_val) OR native_val < 0 THEN
                RAISE EXCEPTION 'p_base[%] native must be finite nonnegative; got %', k, native_val
                    USING ERRCODE = '22023';
            END IF;
        END IF;

        candidates := candidates || jsonb_build_array(jsonb_build_object(
            'k', k,
            'position', pos,
            'surplus_ppg', surp,
            'native', native_val
        ));
    END LOOP;

    -- Reject duplicate canonical numeric keys: convert text to numeric and dedupe.
    -- (Mirrors pipelines/build_imputed_vorps._canonical_number.)
    IF (
        SELECT count(*) FROM jsonb_array_elements(candidates) j1
        WHERE (j1 ->> 'k') ~ '^[0-9]+$' AND (j1 ->> 'k')::int <= 0
    ) > 0 THEN
        RAISE EXCEPTION 'player_key must be a positive integer; got non-positive value'
            USING ERRCODE = '22023';
    END IF;
    IF (
        SELECT count(*) - count(DISTINCT (j ->> 'k')::int)
        FROM jsonb_array_elements(candidates) j
        WHERE (j ->> 'k') ~ '^[0-9]+$'
    ) > 0 THEN
        RAISE EXCEPTION 'duplicate canonical player_key in p_base'
            USING ERRCODE = '22023';
    END IF;

    -- ------------------------------------------------------------
    -- 3. Infer roster. Mirrors pipelines/build_imputed_vorps.infer_roster.
    --    Ties break by ascending numeric player_key. Sort by descending
    --    surplus_ppg so the highest-surplus players are starters first
    --    (Python sorts by -value, native trade value; the as-published
    --    ranking is the same one native captures when native == surplus).
    --    Where native is unavailable we sort by surplus_ppg.
    -- ------------------------------------------------------------
    n_cand := jsonb_array_length(candidates);

    -- Dedicated starters: top (teams * slot_pos) per position by surplus_ppg.
    FOR pos IN (SELECT unnest(ARRAY['QB','RB','WR','TE'])) LOOP
        j := CASE pos WHEN 'QB' THEN slot_qb WHEN 'RB' THEN slot_rb
                      WHEN 'WR' THEN slot_wr WHEN 'TE' THEN slot_te END;
        FOR c IN (
            SELECT j2
            FROM jsonb_array_elements(candidates) j2
            WHERE j2 ->> 'position' = pos
            ORDER BY (j2 ->> 'surplus_ppg')::numeric DESC,
                     CASE WHEN (j2 ->> 'k') ~ '^[0-9]+$'
                          THEN (j2 ->> 'k')::int ELSE 2147483647 END ASC
            LIMIT (v_teams * j)
        ) LOOP
            role_of := role_of || jsonb_build_object(c ->> 'k', 'starter');
        END LOOP;
    END LOOP;

    -- Flex pool: top teams*FLEX from {RB, WR, TE} not already a starter
    -- (mirrors FLEX_ELIGIBLE = ('RB','WR','TE')). SUPERFLEX shapes (QB
    -- included) are NEEDS-REVIEW in the repo and are not handled here:
    -- a custom SUPERFLEX roster would need to mutate flex_eligible before
    -- reaching this function. See docs/vorp-on-demand-port-notes.md.
    flex_pool := (
        SELECT coalesce(jsonb_agg(j ORDER BY ord), '[]'::jsonb)
        FROM (
            SELECT j,
                   row_number() OVER (
                       ORDER BY (j ->> 'surplus_ppg')::numeric DESC,
                                CASE WHEN (j ->> 'k') ~ '^[0-9]+$'
                                     THEN (j ->> 'k')::int ELSE 2147483647 END ASC
                   ) AS ord
            FROM jsonb_array_elements(candidates) j
            WHERE j ->> 'position' IN ('RB','WR','TE')
              AND NOT (role_of ? (j ->> 'k'))
        ) sub
    );
    j := 0;
    FOR c IN SELECT * FROM jsonb_array_elements(flex_pool) LOOP
        IF j >= v_teams * slot_flex THEN
            EXIT;
        END IF;
        role_of := role_of || jsonb_build_object(c ->> 'k', 'starter');
        j := j + 1;
    END LOOP;

    -- Bench: top teams*BENCH from the remainder (any position).
    remaining := (
        SELECT coalesce(jsonb_agg(j ORDER BY ord), '[]'::jsonb)
        FROM (
            SELECT j,
                   row_number() OVER (
                       ORDER BY (j ->> 'surplus_ppg')::numeric DESC,
                                CASE WHEN (j ->> 'k') ~ '^[0-9]+$'
                                     THEN (j ->> 'k')::int ELSE 2147483647 END ASC
                   ) AS ord
            FROM jsonb_array_elements(candidates) j
            WHERE NOT (role_of ? (j ->> 'k'))
        ) sub
    );
    j := 0;
    FOR c IN SELECT * FROM jsonb_array_elements(remaining) LOOP
        IF j >= v_teams * slot_bench THEN
            EXIT;
        END IF;
        role_of := role_of || jsonb_build_object(c ->> 'k', 'bench');
        j := j + 1;
    END LOOP;
    -- Anything still unassigned is 'cut' (excluded from the eight groups).

    -- ------------------------------------------------------------
    -- 4. 8-group totals over non-cut players.
    --    sum_surplus[pos][role_idx] where role_idx 1=starter, 2=bench.
    -- ------------------------------------------------------------
    sum_surplus := ARRAY[
        ARRAY[0::numeric, 0::numeric],  -- QB
        ARRAY[0::numeric, 0::numeric],  -- RB
        ARRAY[0::numeric, 0::numeric],  -- WR
        ARRAY[0::numeric, 0::numeric]   -- TE
    ];

    FOR c IN SELECT * FROM jsonb_array_elements(candidates) LOOP
        k := c ->> 'k';
        pos := c ->> 'position';
        IF NOT (role_of ? k) THEN
            CONTINUE;  -- cut: outside the eight groups
        END IF;
        pos_idx := CASE pos WHEN 'QB' THEN 1 WHEN 'RB' THEN 2
                            WHEN 'WR' THEN 3 WHEN 'TE' THEN 4 END;
        IF (role_of ->> k) = 'starter' THEN
            sum_surplus[pos_idx][1] := sum_surplus[pos_idx][1]
                + (c ->> 'surplus_ppg')::numeric;
        ELSE  -- bench
            sum_surplus[pos_idx][2] := sum_surplus[pos_idx][2]
                + (c ->> 'surplus_ppg')::numeric;
        END IF;
    END LOOP;

    -- ------------------------------------------------------------
    -- 5. Effective targets per (pos, role) and proportional allocation.
    --    For each position, total position surplus is split
    --    bench_share/1-bench_share between bench/starter.
    --    Within each role, surplus_ppg is reweighted proportionally
    --    to hit that role's effective target.
    -- ------------------------------------------------------------
    FOR pos_idx IN 1..4 LOOP
        starter_sum := sum_surplus[pos_idx][1];
        bench_sum   := sum_surplus[pos_idx][2];
        pos_total   := starter_sum + bench_sum;
        starter_target := pos_total * (1 - v_bench_share);
        bench_target   := pos_total * v_bench_share;

        eff_target := eff_target || jsonb_build_object(
            CASE pos_idx WHEN 1 THEN 'QB' WHEN 2 THEN 'RB'
                         WHEN 3 THEN 'WR' WHEN 4 THEN 'TE' END,
            jsonb_build_object(
                'starter_target', starter_target,
                'bench_target', bench_target,
                'starter_sum', starter_sum,
                'bench_sum', bench_sum
            )
        );

        -- Fail-closed: positive target with no source pool must raise.
        IF starter_target > 0 AND starter_sum = 0 THEN
            RAISE EXCEPTION 'position % starter has positive target but no source pool',
                CASE pos_idx WHEN 1 THEN 'QB' WHEN 2 THEN 'RB'
                             WHEN 3 THEN 'WR' WHEN 4 THEN 'TE' END
                USING ERRCODE = '22023';
        END IF;
        IF bench_target > 0 AND bench_sum = 0 THEN
            RAISE EXCEPTION 'position % bench has positive target but no source pool',
                CASE pos_idx WHEN 1 THEN 'QB' WHEN 2 THEN 'RB'
                             WHEN 3 THEN 'WR' WHEN 4 THEN 'TE' END
                USING ERRCODE = '22023';
        END IF;
    END LOOP;

    -- Per-player imputed_vorp[k] = surplus_ppg[k] * (role_target / role_sum).
    imputed := '{}'::jsonb;
    FOR c IN SELECT * FROM jsonb_array_elements(candidates) LOOP
        k := c ->> 'k';
        IF NOT (role_of ? k) THEN
            imputed := imputed || jsonb_build_object(k, 0::numeric);
            CONTINUE;
        END IF;
        pos := c ->> 'position';
        imp_pos_total := CASE (role_of ->> k)
            WHEN 'starter' THEN ((eff_target -> pos) ->> 'starter_target')::numeric
            ELSE ((eff_target -> pos) ->> 'bench_target')::numeric
        END;
        IF imp_pos_total = 0 THEN
            imputed := imputed || jsonb_build_object(k, 0::numeric);
            CONTINUE;
        END IF;
        imputed := imputed || jsonb_build_object(
            k,
            round((c ->> 'surplus_ppg')::numeric * imp_pos_total
                  / CASE (role_of ->> k)
                      WHEN 'starter' THEN ((eff_target -> pos) ->> 'starter_sum')::numeric
                      ELSE ((eff_target -> pos) ->> 'bench_sum')::numeric
                    END, 12)
        );
    END LOOP;

    -- ------------------------------------------------------------
    -- 6. Compute peaks. max_imputed over non-cut; max_native over
    --    non-cut players that actually have a native value. vorp_indexed
    --    is NULL if no player has a native value (the function still
    --    emits rows — vorp_indexed is just null per row, not an error).
    -- ------------------------------------------------------------
    SELECT COALESCE(MAX((v ->> 1)::numeric), 0)
      INTO max_imputed
      FROM jsonb_each(imputed) v
     WHERE (v ->> 1)::numeric > 0;

    SELECT COALESCE(MAX((c ->> 'native')::numeric), 0)
      INTO max_native
      FROM jsonb_array_elements(candidates) c
     WHERE role_of ? (c ->> 'k')
       AND c ->> 'native' IS NOT NULL;

    IF max_native IS NULL OR max_native < 0 THEN
        max_native := 0;
    END IF;

    IF max_imputed IS NULL OR max_imputed < 0 THEN
        max_imputed := 0;
    END IF;

    -- ------------------------------------------------------------
    -- 7. Emit rows. vorp[k] = imputed_vorp[k].
    --    adj_values[k] = imputed_vorp[k] * 70 / max_imputed  (0 if peak == 0).
    --    vorp_indexed[k] = native[k] * 70 / max_native       (NULL if no native).
    -- ------------------------------------------------------------
    peak := 70.0;
    FOR c IN
        SELECT j2
          FROM jsonb_array_elements(candidates) j2
    LOOP
        k := c ->> 'k';
        out_vorp := (imputed ->> k)::numeric;
        IF max_imputed > 0 THEN
            out_adj := round(out_vorp / max_imputed * peak, 9);
        ELSE
            out_adj := 0;
        END IF;
        IF (c ->> 'native') IS NOT NULL AND max_native > 0 THEN
            out_indexed := round(((c ->> 'native')::numeric / max_native * peak), 9);
        ELSE
            out_indexed := NULL;
        END IF;
        player_key     := k;
        vorp           := round(out_vorp, 9);
        vorp_indexed   := out_indexed;
        adj_values     := out_adj;
        RETURN NEXT;
    END LOOP;
END;
$$;

COMMENT ON FUNCTION public.compute_vorp_views(jsonb, text, int, jsonb, numeric) IS
    'JEG-332: on-demand 8-group proportional VORP-family computation. Validates bench_share in [0.01,0.30], scoring in {standard,half_ppr,ppr}, teams>0, roster_shape keys. Returns (player_key, vorp, vorp_indexed, adj_values). Native is optional; vorp_indexed is NULL when absent. Bench share default 0.15. Fail-closed on bad inputs.';

-- =========================================================
-- 8. Verification comments (run by hand in the SQL editor).
-- =========================================================
-- SELECT * FROM public.compute_vorp_views(
--     '{"1": {"position":"QB","surplus_ppg":5.2,"native":4500},
--       "2": {"position":"RB","surplus_ppg":8.1,"native":6200}}'::jsonb,
--     'half_ppr', 12, '{"QB":1,"RB":2,"WR":3,"TE":1,"FLEX":1,"BENCH":6}'::jsonb
-- );
--
-- SELECT public._vorp_validate_bench_share(0.40);  -- expect RAISE EXCEPTION