-- JEG-377 / JEG-380: versioned mirror of the live api.* functions and the
-- consolidated_values hardening that were applied directly in Supabase
-- (2026-10-04) without repo DDL. Exported verbatim with pg_get_functiondef on
-- 2026-10-05; re-export after any change so the repo stays the record.
--
-- Constraints present on public.consolidated_values (live, 2026-10-05):
--   consolidated_values_pkey PRIMARY KEY (player, source, season, week, scoring, teams, qb_variant, view)
--   ck_combo_reindexed_cap CHECK (view <> 'combo_reindexed' OR value <= 70)
--   fk_consolidated_values_bake_uuid FOREIGN KEY (bake_uuid) REFERENCES bakes(bake_id)
--   fk_consolidated_values_bake_id  FOREIGN KEY (bake_uuid) REFERENCES bakes(bake_id)  (duplicate of the above)
--   fk_consolidated_values_source   FOREIGN KEY (source) REFERENCES source_config(source)
--   consolidated_values_player_fk   FOREIGN KEY (player_key) REFERENCES players(player_key)
--   source_generated_at timestamptz NOT NULL (set NOT NULL 2026-10-05; 0 nulls of 20,865)
-- public.bakes: PRIMARY KEY (bake_id); source_generated_at timestamptz NOT NULL.

begin;

CREATE OR REPLACE FUNCTION api.activate_snapshot(p_product text, p_candidate uuid, p_contract_version text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'api'
AS $function$
DECLARE
  v_row_version TEXT;
  v_bake_ids    JSONB;
  v_gate_result JSONB;
  v_passed      BOOLEAN;
BEGIN
  IF p_product IS NULL OR p_candidate IS NULL OR p_contract_version IS NULL THEN
    RAISE EXCEPTION 'activate_snapshot: NULL arg(s) not allowed (product=% candidate=% contract_version=%)',
      p_product, p_candidate, p_contract_version;
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_product || ':' || p_contract_version, 0));
  SELECT s.contract_version, s.bake_ids
    INTO v_row_version, v_bake_ids
    FROM public.product_snapshot s
   WHERE s.snapshot_id = p_candidate
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'activate_snapshot: candidate snapshot % not found', p_candidate;
  END IF;
  IF v_row_version IS DISTINCT FROM p_contract_version THEN
    RAISE EXCEPTION 'activate_snapshot: contract_version mismatch (candidate=%, expected=%)',
      v_row_version, p_contract_version;
  END IF;
  IF v_bake_ids IS NULL THEN
    RAISE EXCEPTION 'activate_snapshot: candidate % has NULL bake_ids; cannot scope gates', p_candidate;
  END IF;
  v_gate_result := api.run_publish_gate(p_contract_version, v_bake_ids, p_candidate);
  v_passed := COALESCE(((v_gate_result -> 'passed') = to_jsonb(TRUE)), FALSE);
  IF NOT v_passed THEN
    RAISE EXCEPTION 'activate_snapshot: publish gates failed for candidate %: %', p_candidate, v_gate_result;
  END IF;
  UPDATE public.product_snapshot
     SET is_active = FALSE
   WHERE contract_version = p_contract_version
     AND is_active = TRUE
     AND snapshot_id <> p_candidate;
  UPDATE public.product_snapshot
     SET is_active   = TRUE,
         publishable = TRUE
   WHERE snapshot_id    = p_candidate
     AND contract_version = p_contract_version;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'activate_snapshot: candidate % vanished during flip (contract_version=%)',
      p_candidate, p_contract_version;
  END IF;
END;
$function$
;

CREATE OR REPLACE FUNCTION api.audit_publish_gate(p_contract_version text DEFAULT '1.0.0'::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'api'
AS $function$
    DECLARE
      v_snapshot_id UUID;
        v_bake_ids    JSONB;
          v_verdict     JSONB;
            v_passed      BOOLEAN;
              v_gates       JSONB;
                v_warnings    JSONB;
                  v_failed      TEXT[];
                    v_outcome     TEXT;
                      v_run_id      UUID;
                        v_run_at      TIMESTAMPTZ;
                        BEGIN

  IF p_contract_version IS NULL THEN
      RAISE EXCEPTION 'audit_publish_gate: NULL contract_version not allowed';
        END IF;
          SELECT s.snapshot_id, s.bake_ids
              INTO v_snapshot_id, v_bake_ids
                  FROM public.product_snapshot s
                     WHERE s.contract_version = p_contract_version
                          AND s.is_active = TRUE
                               AND s.publishable = TRUE
                                  ORDER BY s.built_at DESC NULLS LAST,
                                              s.generated_at DESC NULLS LAST
                                                 LIMIT 1;
                                                   IF v_snapshot_id IS NULL THEN
                                                       INSERT INTO public.gate_audits(
                                                             contract_version, snapshot_id, passed, gate_results, warnings,
                                                                   failed_gates, outcome, blocked_reason
                                                                       )
                                                                          VALUES (
                                                                                  p_contract_version, NULL, FALSE, '[]'::jsonb, '[]'::jsonb, '{}',
                                                                                        'blocked',
                                                                                              'no active publishable snapshot for contract_version=' || p_contract_version
                                                                                                  )

                                                                              RETURNING gate_audits.run_id, gate_audits.run_at
                                                                                  INTO v_run_id, v_run_at;
                                                                                      RETURN jsonb_build_object(
                                                                                            'run_id', v_run_id, 'run_at', v_run_at,
                                                                                                  'contract_version', p_contract_version,
                                                                                                      'snapshot_id', NULL, 'passed', FALSE,
                                                                                                            'outcome', 'blocked',
                                                                                                                  'blocked_reason', 'no active publishable snapshot'
                                                                                                                      );
                                                                                                                        END IF;
                                                                                                                          BEGIN
                                                                                                                              v_verdict := api.run_publish_gate(p_contract_version, v_bake_ids, v_snapshot_id);
                                                                                                                                EXCEPTION WHEN OTHERS THEN
                                                                                                                                    INSERT INTO public.gate_audits(
                                                                                                                                          contract_version, snapshot_id, passed, gate_results, warnings,
                                                                                                                                                failed_gates, outcome, blocked_reason
                                                                                                                                                    )
                                                                                                                                                      VALUES (
                                                                                                                                                              p_contract_version, v_snapshot_id, FALSE, '[]'::jsonb, '[]'::jsonb, '{}',
                                                                                                                                                                    'error', 'run_publish_gate raised: ' || SQLERRM
                                                                                                                                                                        )
                                                                                                                                                                            RETURNING gate_audits.run_id, gate_audits.run_at
                                                                                                                                                                                INTO v_run_id, v_run_at;

                                                                                                                                                          RETURN jsonb_build_object(
                                                                                                                                                                  'run_id', v_run_id, 'run_at', v_run_at,
                                                                                                                                                                        'contract_version', p_contract_version,
                                                                                                                                                                              'snapshot_id', v_snapshot_id, 'passed', FALSE,
                                                                                                                                                                                    'outcome', 'error',

                                                                                                                                                                'blocked_reason', 'run_publish_gate raised: ' || SQLERRM
                                                                                                                                                                    );
                                                                                                                                                                      END;
                                                                                                                                                                        v_passed   := COALESCE((v_verdict ->> 'passed')::BOOLEAN, FALSE);
                                                                                                                                                                          v_gates    := COALESCE(v_verdict -> 'gates', '[]'::jsonb);
                                                                                                                                                                            v_warnings := COALESCE(v_verdict -> 'warnings', '[]'::jsonb);
                                                                                                                                                                              SELECT COALESCE(array_agg(g ->> 'gate' ORDER BY g ->> 'gate'), '{}')
                                                                                                                                                                                  INTO v_failed
                                                                                                                                                                                      FROM jsonb_array_elements(v_gates) AS g
                                                                                                                                                                                         WHERE (g ->> 'passed')::BOOLEAN IS DISTINCT FROM TRUE;
                                                                                                                                                                                           v_outcome := CASE WHEN v_passed THEN 'pass' ELSE 'fail' END;
                                                                                                                                                                                             INSERT INTO public.gate_audits(
                                                                                                                                                                                                  contract_version, snapshot_id, passed, gate_results, warnings,
                                                                                                                                                                                                      failed_gates, outcome
                                                                                                                                                                                                        )
                                                                                                                                                                                                          VALUES (
                                                                                                                                                                                                              p_contract_version, v_snapshot_id, v_passed, v_gates, v_warnings,
                                                                                                                                                                                                                  v_failed, v_outcome
                                                                                                                                                                                                                    )

                                                                                                                                                                                              RETURNING gate_audits.run_id, gate_audits.run_at
                                                                                                                                                                                                INTO v_run_id, v_run_at;
                                                                                                                                                                                                  RETURN jsonb_build_object(
                                                                                                                                                                                                      'run_id', v_run_id, 'run_at', v_run_at,
                                                                                                                                                                                                          'contract_version', p_contract_version,
                                                                                                                                                                                                            'snapshot_id', v_snapshot_id, 'passed', v_passed,
                                                                                                                                                                                                                'outcome', v_outcome,
                                                                                                                                                                                                                    'failed_gates', to_jsonb(v_failed),
                                                                                                                                                                                                                        'warnings', v_warnings
                                                                                                                                                                                                                          );
                                                                                                                                                                                                                          END;
                                                                                                                                                                                                                          $function$
;

CREATE OR REPLACE FUNCTION api.begin_weekly_ingest(p_run_id uuid, p_writer_identity text, p_source text, p_code_revision text DEFAULT NULL::text)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'api', 'public'
AS $function$ DECLARE v_audit_id uuid; BEGIN INSERT INTO public.pipeline_write_audit (run_id, writer_identity, source, operation, table_name, code_revision, started_at) VALUES (p_run_id, p_writer_identity, p_source, 'insert', 'weekly_source_snapshots', p_code_revision, now()) RETURNING id INTO v_audit_id; RETURN v_audit_id; END $function$
;

CREATE OR REPLACE FUNCTION api.fail_weekly_ingest(p_audit_id uuid, p_error text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'api'
AS $function$
                                                                                                                                                                                                                                                                                                                                                                                                                                               BEGIN
                                                                                                                                                                                                                                                                                                                                                                                                                                                 UPDATE public.pipeline_write_audit
                                                                                                                                                                                                                                                                                                                                                                                                                                                      SET failed_at = now(), failure_reason = p_error, error_message = p_error
                                                                                                                                                                                                                                                                                                                                                                                                                                                         WHERE id = p_audit_id;
                                                                                                                                                                                                                                                                                                                                                                                                                                                         END
                                                                                                                                                                                                                                                                                                                                                                                                                                                         $function$
;

CREATE OR REPLACE FUNCTION api.gate_context_valid_fresh(p_contract_version text, p_candidate_snapshot_id uuid, p_bake_uuid uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'api', 'public'
AS $function$ DECLARE orphan_news BIGINT; orphan_adjustments BIGINT; active_snap_id UUID; has_news BOOLEAN; has_adjustments BOOLEAN; latest_news_at TIMESTAMPTZ; latest_adjustment_at DATE; warnings JSONB := '[]'::jsonb; BEGIN SELECT COUNT(*) INTO orphan_news FROM public.player_news n WHERE NOT EXISTS (SELECT 1 FROM public.product_snapshot s WHERE s.snapshot_id = n.snapshot_id); IF to_regclass('public.player_adjustments') IS NOT NULL THEN SELECT COUNT(*) INTO orphan_adjustments FROM public.player_adjustments a WHERE NOT EXISTS (SELECT 1 FROM public.product_snapshot s WHERE s.snapshot_id = a.snapshot_id); ELSE orphan_adjustments := 0; END IF; IF orphan_news > 0 OR orphan_adjustments > 0 THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'context_valid_fresh', 'orphan_news', orphan_news, 'orphan_adjustments', orphan_adjustments); END IF; IF p_candidate_snapshot_id IS NOT NULL THEN active_snap_id := p_candidate_snapshot_id; ELSE SELECT s.snapshot_id INTO active_snap_id FROM public.product_snapshot s WHERE s.contract_version = p_contract_version ORDER BY s.generated_at DESC NULLS LAST, s.built_at DESC LIMIT 1; END IF; IF active_snap_id IS NOT NULL THEN SELECT EXISTS (SELECT 1 FROM public.player_news WHERE snapshot_id = active_snap_id) INTO has_news; has_adjustments := FALSE; IF to_regclass('public.player_adjustments') IS NOT NULL THEN SELECT EXISTS (SELECT 1 FROM public.player_adjustments WHERE snapshot_id = active_snap_id) INTO has_adjustments; END IF; IF NOT has_news AND NOT has_adjustments THEN warnings := warnings || jsonb_build_object('warning', 'snapshot has no news or adjustments (empty context)'); END IF; END IF; SELECT MAX(n.published_at) INTO latest_news_at FROM public.player_news n WHERE n.snapshot_id = active_snap_id; latest_adjustment_at := NULL; IF to_regclass('public.player_adjustments') IS NOT NULL THEN SELECT MAX(a.date) INTO latest_adjustment_at FROM public.player_adjustments a WHERE a.snapshot_id = active_snap_id; END IF; RETURN jsonb_build_object('passed', TRUE, 'gate', 'context_valid_fresh', 'warnings', warnings, 'latest_news_at', latest_news_at, 'latest_adjustment_at', latest_adjustment_at); END; $function$
;

CREATE OR REPLACE FUNCTION api.gate_options_coverage(p_contract_version text, p_candidate_snapshot_id uuid, p_bake_uuid uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'api', 'public'
AS $function$ DECLARE declared_keys TEXT[]; adjusted_keys TEXT[]; pure_vorp_keys TEXT[]; as_published_keys TEXT[]; sources_in_meta JSONB; per_source_meta JSONB; bake_sources TEXT[]; bake_source TEXT; bake_row_count BIGINT; subset_violations JSONB; BEGIN SELECT po.source_keys, po.adjusted_indexed_keys, po.pure_vorp_keys, po.as_published_keys INTO declared_keys, adjusted_keys, pure_vorp_keys, as_published_keys FROM public.product_options po WHERE po.product_key = 'default'; declared_keys := COALESCE(declared_keys, ARRAY[]::TEXT[]); IF cardinality(declared_keys) = 0 THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'options_coverage', 'reason', 'product_options.source_keys is empty'); END IF; SELECT COALESCE(jsonb_agg(v), '[]'::jsonb) INTO subset_violations FROM (SELECT 'adjusted_indexed_keys' AS subset_name, t.k FROM unnest(COALESCE(adjusted_keys, ARRAY[]::TEXT[])) AS t(k) WHERE NOT (t.k = ANY (declared_keys))  UNION ALL SELECT 'as_published_keys', t.k FROM unnest(COALESCE(as_published_keys, ARRAY[]::TEXT[])) AS t(k) WHERE NOT (t.k = ANY (declared_keys))) v; IF jsonb_array_length(subset_violations) > 0 THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'options_coverage', 'reason', 'subset keys outside source_keys', 'violations', subset_violations); END IF; SELECT COALESCE(array_agg(DISTINCT source), ARRAY[]::TEXT[]) INTO bake_sources FROM public.consolidated_values WHERE bake_uuid = p_bake_uuid; IF cardinality(bake_sources) = 0 THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'options_coverage', 'reason', 'no consolidated_values rows for bake_uuid', 'bake_uuid', p_bake_uuid); END IF; IF cardinality(bake_sources) > 1 THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'options_coverage', 'reason', 'bake_uuid spans multiple sources (data anomaly)', 'bake_uuid', p_bake_uuid, 'sources', to_jsonb(bake_sources)); END IF; bake_source := bake_sources[1]; IF NOT (bake_source = ANY (declared_keys)) THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'options_coverage', 'reason', 'bake source is not in product_options.source_keys', 'bake_uuid', p_bake_uuid, 'source', bake_source); END IF; SELECT COUNT(*) INTO bake_row_count FROM public.consolidated_values WHERE bake_uuid = p_bake_uuid; IF p_candidate_snapshot_id IS NOT NULL THEN SELECT sources INTO sources_in_meta FROM public.product_snapshot WHERE snapshot_id = p_candidate_snapshot_id; ELSE SELECT sources INTO sources_in_meta FROM public.product_snapshot WHERE contract_version = p_contract_version ORDER BY generated_at DESC NULLS LAST, built_at DESC LIMIT 1; END IF; per_source_meta := COALESCE(sources_in_meta, '{}'::jsonb); IF NOT (per_source_meta ? bake_source) THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'options_coverage', 'reason', 'candidate snapshot missing per-source meta for bake source', 'bake_uuid', p_bake_uuid, 'source', bake_source); END IF; RETURN jsonb_build_object('passed', TRUE, 'gate', 'options_coverage', 'bake_uuid', p_bake_uuid, 'source', bake_source, 'rows', bake_row_count); END; $function$
;

CREATE OR REPLACE FUNCTION api.gate_player_joins(p_contract_version text, p_bake_ids jsonb, p_bake_uuid uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'api', 'public'
AS $function$ DECLARE total_value_rows BIGINT; orphan_count BIGINT; sample_orphans JSONB; BEGIN SELECT COUNT(*) INTO total_value_rows FROM public.consolidated_values WHERE bake_uuid = p_bake_uuid; IF total_value_rows = 0 THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'player_joins', 'reason', 'no consolidated_values rows for bake_uuid', 'bake_uuid', p_bake_uuid); END IF; SELECT COUNT(*) INTO orphan_count FROM (SELECT DISTINCT cv.player_key AS pk FROM public.consolidated_values cv WHERE cv.bake_uuid = p_bake_uuid AND NOT EXISTS (SELECT 1 FROM public.players p WHERE p.player_key = cv.player_key)) o; IF orphan_count > 0 THEN SELECT COALESCE(jsonb_agg(pk), '[]'::jsonb) INTO sample_orphans FROM (SELECT DISTINCT cv.player_key AS pk FROM public.consolidated_values cv WHERE cv.bake_uuid = p_bake_uuid AND NOT EXISTS (SELECT 1 FROM public.players p WHERE p.player_key = cv.player_key) LIMIT 10) s; RETURN jsonb_build_object('passed', FALSE, 'gate', 'player_joins', 'bake_uuid', p_bake_uuid, 'orphan_count', orphan_count, 'sample_orphans', sample_orphans); END IF; RETURN jsonb_build_object('passed', TRUE, 'gate', 'player_joins', 'bake_uuid', p_bake_uuid, 'value_rows', total_value_rows); END; $function$
;

CREATE OR REPLACE FUNCTION api.gate_source_freshness(p_contract_version text, p_candidate_snapshot_id uuid DEFAULT NULL::uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE
AS $function$
      DECLARE
        stale_tier_count   BIGINT;
          declared_keys      TEXT[];
            bake_ids_json      JSONB;
              per_source_bakes   JSONB;
                source_status      JSONB := '[]'::jsonb;
                  failed_sources     TEXT[] := ARRAY[]::TEXT[];
                    warned_sources     TEXT[] := ARRAY[]::TEXT[];
                      src                TEXT;
                        bake_uuid_text     TEXT;
                          bake_row           RECORD;
                            cfg_row            RECORD;
                              age_hours          NUMERIC;
                                per_source_entry   JSONB;
                                BEGIN
                                  SELECT COUNT(*) INTO stale_tier_count
                                      FROM public.player_values_tier_prices tpv
                                         WHERE tpv.tier_price_vintage IS DISTINCT FROM tpv.bake_id;
                                           IF stale_tier_count > 0 THEN
                                               RETURN jsonb_build_object('passed', FALSE, 'gate', 'source_freshness',
                                                     'reason', format('%s tier_price rows have tier_price_vintage != bake_id', stale_tier_count));
                                                       END IF;
                                                         SELECT po.source_keys INTO declared_keys
                                                             FROM public.product_options po WHERE po.product_key = 'default';
                                                               declared_keys := COALESCE(declared_keys, ARRAY[]::TEXT[]);
                                                                 IF p_candidate_snapshot_id IS NOT NULL THEN
                                                                     SELECT s.bake_ids INTO bake_ids_json FROM public.product_snapshot s
                                                                          WHERE s.snapshot_id = p_candidate_snapshot_id;
                                                                            ELSE
                                                                                SELECT s.bake_ids INTO bake_ids_json FROM public.product_snapshot s
                                                                                     WHERE s.contract_version = p_contract_version
                                                                                          ORDER BY s.generated_at DESC NULLS LAST, s.built_at DESC LIMIT 1;
                                                                                            END IF;
                                                                                              per_source_bakes := COALESCE(bake_ids_json -> 'per_source', '{}'::jsonb);
                                                                                                IF cardinality(declared_keys) > 0 THEN
                                                                                                    FOREACH src IN ARRAY declared_keys LOOP
                                                                                                          bake_uuid_text := per_source_bakes ->> src;
                                                                                                                IF bake_uuid_text IS NOT NULL THEN
                                                                                                                        SELECT b.source_generated_at, b.contract_version INTO bake_row
                                                                                                                                  FROM public.bakes b
                                                                                                                                           WHERE b.source = src
                                                                                                                                                      AND date_trunc('second', b.source_generated_at) = date_trunc('second', bake_uuid_text::timestamptz)
                                                                                                                                                               LIMIT 1;
                                                                                                                                                                     ELSE
                                                                                                                                                                             SELECT b.source_generated_at, b.contract_version INTO bake_row
                                                                                                                                                                                       FROM public.bakes b WHERE b.source = src
                                                                                                                                                                                                ORDER BY b.ingested_at DESC NULLS LAST, b.bake_id LIMIT 1;
                                                                                                                                                                                                      END IF;
                                                                                                                                                                                                            SELECT sc.max_age_hours, sc.block_on_stale INTO cfg_row
                                                                                                                                                                                                                    FROM public.source_config sc WHERE sc.source = src;
                                                                                                                                                                                                                          IF cfg_row.max_age_hours IS NULL THEN
                                                                                                                                                                                                                                  failed_sources := array_append(failed_sources, src);
                                                                                                                                                                                                                                          source_status := source_status || jsonb_build_array(jsonb_build_object(
                                                                                                                                                                                                                                                    'source', src, 'status', 'fail', 'reason', 'no source_config entry (cannot compute SLA)'));
                                                                                                                                                                                                                                                            CONTINUE;
                                                                                                                                                                                                                                                                  END IF;
                                                                                                                                                                                                                                                                        IF bake_row.source_generated_at IS NULL THEN
                                                                                                                                                                                                                                                                                failed_sources := array_append(failed_sources, src);
                                                                                                                                                                                                                                                                                        source_status := source_status || jsonb_build_array(jsonb_build_object(
                                                                                                                                                                                                                                                                                                  'source', src, 'status', 'fail', 'reason', 'no bake row found (cannot compute freshness)'));
                                                                                                                                                                                                                                                                                                          CONTINUE;
                                                                                                                                                                                                                                                                                                                END IF;
                                                                                                                                                                                                                                                                                                                      age_hours := EXTRACT(EPOCH FROM (now() - bake_row.source_generated_at)) / 3600.0;
                                                                                                                                                                                                                                                                                                                            IF age_hours > cfg_row.max_age_hours THEN
                                                                                                                                                                                                                                                                                                                                    IF cfg_row.block_on_stale THEN
                                                                                                                                                                                                                                                                                                                                              failed_sources := array_append(failed_sources, src);
                                                                                                                                                                                                                                                                                                                                                        source_status := source_status || jsonb_build_array(jsonb_build_object(
                                                                                                                                                                                                                                                                                                                                                                    'source', src, 'status', 'fail',
                                                                                                                                                                                                                                                                                                                                                                                'reason', format('stale: age=%.2fh exceeds max_age_hours=%s', age_hours, cfg_row.max_age_hours),
                                                                                                                                                                                                                                                                                                                                                                                            'source_generated_at', bake_row.source_generated_at, 'age_hours', age_hours, 'max_age_hours', cfg_row.max_age_hours));
                                                                                                                                                                                                                                                                                                                                                                                                    ELSE
                                                                                                                                                                                                                                                                                                                                                                                                              warned_sources := array_append(warned_sources, src);
                                                                                                                                                                                                                                                                                                                                                                                                                        source_status := source_status || jsonb_build_array(jsonb_build_object(
                                                                                                                                                                                                                                                                                                                                                                                                                                    'source', src, 'status', 'warn',
                                                                                                                                                                                                                                                                                                                                                                                                                                                'reason', format('stale but block_on_stale=false: age=%.2fh exceeds max_age_hours=%s', age_hours, cfg_row.max_age_hours),
                                                                                                                                                                                                                                                                                                                                                                                                                                                            'source_generated_at', bake_row.source_generated_at, 'age_hours', age_hours, 'max_age_hours', cfg_row.max_age_hours));
                                                                                                                                                                                                                                                                                                                                                                                                                                                                    END IF;
                                                                                                                                                                                                                                                                                                                                                                                                                                                                          ELSE
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  source_status := source_status || jsonb_build_array(jsonb_build_object(
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            'source', src, 'status', 'ok', 'source_generated_at', bake_row.source_generated_at,
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'age_hours', age_hours, 'max_age_hours', cfg_row.max_age_hours));
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            END IF;
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                END LOOP;
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  END IF;
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    IF cardinality(failed_sources) > 0 THEN
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        RETURN jsonb_build_object('passed', FALSE, 'gate', 'source_freshness',
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              'reason', 'computed freshness failed for one or more sources',
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    'failed_sources', to_jsonb(failed_sources), 'source_status', source_status);
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      END IF;
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        DECLARE warnings_arr JSONB := '[]'::jsonb;
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          BEGIN
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              SELECT COALESCE(jsonb_agg(w), '[]'::jsonb) INTO warnings_arr FROM (
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    SELECT jsonb_build_object('gate', 'source_freshness', 'source', (e ->> 'source'),
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            'reason', (e ->> 'reason'), 'age_hours', (e ->> 'age_hours')::NUMERIC,
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    'max_age_hours', (e ->> 'max_age_hours')::INT) AS w
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          FROM jsonb_array_elements(source_status) e WHERE e ->> 'status' = 'warn') s;
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              RETURN jsonb_build_object('passed', TRUE, 'gate', 'source_freshness',
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    'source_status', source_status, 'warnings', warnings_arr);
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      END;
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      END;
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      $function$
;

CREATE OR REPLACE FUNCTION api.gate_source_freshness(p_contract_version text, p_candidate_snapshot_id uuid, p_bake_uuid uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'api', 'public'
AS $function$ DECLARE v_source TEXT; v_source_generated TIMESTAMPTZ; v_max_age_hours INT; v_block_on_stale BOOLEAN; v_age_hours NUMERIC; v_fresh BOOLEAN; v_row_count BIGINT; BEGIN SELECT b.source, b.source_generated_at INTO v_source, v_source_generated FROM public.bakes b WHERE b.bake_id = p_bake_uuid; IF NOT FOUND THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'source_freshness', 'reason', 'bake not found', 'bake_uuid', p_bake_uuid::TEXT); END IF; SELECT count(*) INTO v_row_count FROM public.consolidated_values v WHERE v.bake_uuid = p_bake_uuid; IF v_row_count = 0 THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'source_freshness', 'reason', 'bake has no consolidated_values rows', 'bake_uuid', p_bake_uuid::TEXT, 'source', v_source); END IF; SELECT sc.max_age_hours, sc.block_on_stale INTO v_max_age_hours, v_block_on_stale FROM public.source_config sc WHERE sc.source = v_source; IF NOT FOUND OR v_max_age_hours IS NULL THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'source_freshness', 'reason', 'no freshness SLA configured for source', 'bake_uuid', p_bake_uuid::TEXT, 'source', v_source); END IF; IF v_source_generated IS NULL THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'source_freshness', 'reason', 'bakes.source_generated_at is NULL', 'bake_uuid', p_bake_uuid::TEXT, 'source', v_source); END IF; v_age_hours := EXTRACT(EPOCH FROM (now() - v_source_generated)) / 3600.0; v_fresh := v_age_hours <= v_max_age_hours; RETURN jsonb_build_object('passed', (v_fresh OR NOT COALESCE(v_block_on_stale, FALSE)), 'gate', 'source_freshness', 'bake_uuid', p_bake_uuid::TEXT, 'source', v_source, 'source_generated_at', v_source_generated, 'age_hours', round(v_age_hours, 2), 'max_age_hours', v_max_age_hours, 'fresh', v_fresh, 'block_on_stale', COALESCE(v_block_on_stale, FALSE), 'row_count', v_row_count); END; $function$
;

CREATE OR REPLACE FUNCTION api.gate_values_reconciliation(p_contract_version text, p_bake_ids jsonb, p_bake_uuid uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'api', 'public'
AS $function$ DECLARE row_count BIGINT; BEGIN SELECT COUNT(*) INTO row_count FROM public.consolidated_values WHERE bake_uuid = p_bake_uuid; IF row_count = 0 THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'values_reconciliation', 'reason', 'bake_uuid has no consolidated_values rows', 'bake_uuid', p_bake_uuid); END IF; RETURN jsonb_build_object('passed', TRUE, 'gate', 'values_reconciliation', 'bake_uuid', p_bake_uuid, 'row_count', row_count); END; $function$
;

CREATE OR REPLACE FUNCTION api.gate_view_coverage(p_contract_version text, p_candidate_snapshot_id uuid, p_bake_uuid uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'api', 'public'
AS $function$ DECLARE bake_sources TEXT[]; bake_source TEXT; combo_rows BIGINT; BEGIN SELECT COALESCE(array_agg(DISTINCT source), ARRAY[]::TEXT[]) INTO bake_sources FROM public.consolidated_values WHERE bake_uuid = p_bake_uuid; IF cardinality(bake_sources) = 0 THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'view_coverage', 'reason', 'no consolidated_values rows for bake_uuid', 'bake_uuid', p_bake_uuid); END IF; IF cardinality(bake_sources) > 1 THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'view_coverage', 'reason', 'bake_uuid spans multiple sources (data anomaly)', 'bake_uuid', p_bake_uuid, 'sources', to_jsonb(bake_sources)); END IF; bake_source := bake_sources[1]; SELECT COUNT(*) INTO combo_rows FROM public.consolidated_values WHERE bake_uuid = p_bake_uuid AND view = 'combo_reindexed'; IF combo_rows = 0 THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'view_coverage', 'reason', 'no combo_reindexed rows for bake_uuid', 'bake_uuid', p_bake_uuid, 'source', bake_source); END IF; RETURN jsonb_build_object('passed', TRUE, 'gate', 'view_coverage', 'bake_uuid', p_bake_uuid, 'source', bake_source, 'combo_reindexed_rows', combo_rows); END; $function$
;

CREATE OR REPLACE FUNCTION api.ingest_consolidated_values(p_payload jsonb)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
  v_tbl            regclass := 'public.consolidated_values'::regclass;
    v_rows           jsonb;
      v_missing_cnt    integer;
        v_missing_example jsonb;
          v_constraint     text;
            v_key_cols_raw   text[];
              v_all_cols_raw   text[];
                v_update_cols_raw text[];
                  v_update_clause  text;
                    v_sql            text;
                    BEGIN
                      IF (pg_catalog.jsonb_typeof(p_payload) = 'object') AND (p_payload ? 'rows') THEN
                          IF pg_catalog.jsonb_typeof(p_payload->'rows') <> 'array' THEN
                                RAISE EXCEPTION 'payload.rows must be a JSON array';
                                    END IF;
                                        v_rows := p_payload->'rows';
                                          ELSIF pg_catalog.jsonb_typeof(p_payload) = 'array' THEN
                                              v_rows := p_payload;
                                                ELSE
                                                    RAISE EXCEPTION 'payload must be a JSON array, or an object with "rows": array';
                                                      END IF;
                                                        IF pg_catalog.jsonb_array_length(v_rows) = 0 THEN
                                                            RAISE EXCEPTION 'no rows to ingest';
                                                              END IF;
                                                                WITH elems AS (
                                                                    SELECT elem FROM pg_catalog.jsonb_array_elements(v_rows) AS elem
                                                                      ),
                                                                        norm AS (
                                                                            SELECT CASE WHEN NOT (elem ? 'bake_id') AND (elem ? 'bake_uuid')
                                                                                      THEN elem || pg_catalog.jsonb_build_object('bake_id', elem->>'bake_uuid')
                                                                                              ELSE elem END AS elem FROM elems
                                                                                                ),
                                                                                                  checked AS (
                                                                                                      SELECT elem,
                                                                                                            (NOT (elem ? 'player')) AS miss_player,
                                                                                                                  (NOT (elem ? 'detail_locator')) AS miss_detail_locator,
                                                                                                                        (NOT (elem ? 'bake_id')) AS miss_bake_id
                                                                                                                            FROM norm
                                                                                                                              )
                                                                                                                                SELECT pg_catalog.jsonb_agg(elem),
                                                                                                                                    COUNT(*) FILTER (WHERE miss_player OR miss_detail_locator OR miss_bake_id),
                                                                                                                                        (SELECT elem FROM checked WHERE miss_player OR miss_detail_locator OR miss_bake_id LIMIT 1)
                                                                                                                                          INTO v_rows, v_missing_cnt, v_missing_example FROM checked;
                                                                                                                                            IF v_missing_cnt > 0 THEN
                                                                                                                                                RAISE EXCEPTION 'missing required fields (player, detail_locator, bake_id/bake_uuid) in % row(s); example: %',
                                                                                                                                                      v_missing_cnt, v_missing_example;
                                                                                                                                                        END IF;
                                                                                                                                                          IF (pg_catalog.jsonb_typeof(p_payload) = 'object') AND (p_payload ? 'conflict_constraint') THEN
                                                                                                                                                              v_constraint := p_payload->>'conflict_constraint';
                                                                                                                                                                ELSE
                                                                                                                                                                    SELECT conname INTO v_constraint FROM pg_catalog.pg_constraint c
                                                                                                                                                                        WHERE c.conrelid = v_tbl AND c.contype = 'p' LIMIT 1;
                                                                                                                                                                            IF v_constraint IS NULL THEN
                                                                                                                                                                                  RAISE EXCEPTION 'could not auto-detect PRIMARY KEY on %; provide payload.conflict_constraint', v_tbl::text;
                                                                                                                                                                                      END IF;
                                                                                                                                                                                        END IF;
                                                                                                                                                                                          PERFORM 1 FROM pg_catalog.pg_constraint c
                                                                                                                                                                                            WHERE c.conrelid = v_tbl AND c.conname = v_constraint AND c.contype IN ('p','u');
                                                                                                                                                                                              IF NOT FOUND THEN
                                                                                                                                                                                                  RAISE EXCEPTION 'conflict_constraint "%" is not a UNIQUE/PRIMARY constraint on %', v_constraint, v_tbl::text;
                                                                                                                                                                                                    END IF;
                                                                                                                                                                                                      SELECT pg_catalog.array_agg(att.attname ORDER BY x.ord)::text[] INTO v_key_cols_raw
                                                                                                                                                                                                        FROM pg_catalog.pg_constraint c
                                                                                                                                                                                                          JOIN LATERAL pg_catalog.unnest(c.conkey) WITH ORDINALITY AS x(attnum, ord) ON true
                                                                                                                                                                                                            JOIN pg_catalog.pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = x.attnum
                                                                                                                                                                                                              WHERE c.conrelid = v_tbl AND c.conname = v_constraint;
                                                                                                                                                                                                                SELECT pg_catalog.array_agg(a.attname ORDER BY a.attnum)::text[] INTO v_all_cols_raw
                                                                                                                                                                                                                  FROM pg_catalog.pg_attribute a
                                                                                                                                                                                                                    WHERE a.attrelid = v_tbl AND a.attnum > 0 AND NOT a.attisdropped;
                                                                                                                                                                                                                      SELECT pg_catalog.array_agg(col ORDER BY ord)::text[] INTO v_update_cols_raw
                                                                                                                                                                                                                        FROM (
                                                                                                                                                                                                                            SELECT col, ord FROM pg_catalog.unnest(v_all_cols_raw) WITH ORDINALITY AS u(col, ord)
                                                                                                                                                                                                                                WHERE NOT (col = ANY (v_key_cols_raw))
                                                                                                                                                                                                                                      AND NOT EXISTS (
                                                                                                                                                                                                                                              SELECT 1 FROM information_schema.columns ic
                                                                                                                                                                                                                                                      WHERE ic.table_schema = 'public' AND ic.table_name = 'consolidated_values'
                                                                                                                                                                                                                                                                AND ic.column_name = col
                                                                                                                                                                                                                                                                          AND (ic.is_generated = 'ALWAYS' OR ic.identity_generation IS NOT NULL)
                                                                                                                                                                                                                                                                                )
                                                                                                                                                                                                                                                                                  ) s;
                                                                                                                                                                                                                                                                                    IF v_update_cols_raw IS NULL OR pg_catalog.array_length(v_update_cols_raw, 1) = 0 THEN
                                                                                                                                                                                                                                                                                        v_update_clause := NULL;
                                                                                                                                                                                                                                                                                          ELSE
                                                                                                                                                                                                                                                                                              SELECT pg_catalog.string_agg(pg_catalog.format('%I = EXCLUDED.%I', col, col), ', ')
                                                                                                                                                                                                                                                                                                  INTO v_update_clause FROM pg_catalog.unnest(v_update_cols_raw) AS t(col);
                                                                                                                                                                                                                                                                                                    END IF;
                                                                                                                                                                                                                                                                                                      v_sql := pg_catalog.format(
                                                                                                                                                                                                                                                                                                          'INSERT INTO %s SELECT r.* FROM pg_catalog.jsonb_populate_recordset(NULL::%s, $1) AS r ON CONFLICT ON CONSTRAINT %I %s',
                                                                                                                                                                                                                                                                                                              v_tbl::text, v_tbl::text, v_constraint,
                                                                                                                                                                                                                                                                                                                  COALESCE(pg_catalog.format('DO UPDATE SET %s', v_update_clause), 'DO NOTHING')
                                                                                                                                                                                                                                                                                                                    );
                                                                                                                                                                                                                                                                                                                      EXECUTE v_sql USING v_rows;
                                                                                                                                                                                                                                                                                                                        RETURN;
                                                                                                                                                                                                                                                                                                                        END;
                                                                                                                                                                                                                                                                                                                        $function$
;

CREATE OR REPLACE FUNCTION api.ingest_weekly_snapshots(p_audit_id uuid, p_snapshots jsonb, p_flags jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'api'
AS $function$
                    DECLARE
                      v_inserted int := 0; v_updated int := 0; v_flags int := 0;
                        v_n_ins int; v_n_upd int;
                          v_snap record; v_flag record;
                            v_audit_run_id uuid; v_audit_source text;
                            BEGIN
                              SELECT run_id, source INTO v_audit_run_id, v_audit_source
                                  FROM public.pipeline_write_audit WHERE id = p_audit_id;
                                    IF v_audit_run_id IS NULL THEN
                                        RAISE EXCEPTION 'audit row % not found', p_audit_id;
                                          END IF;
                                            IF p_snapshots IS NOT NULL THEN
                                                FOR v_snap IN SELECT * FROM jsonb_to_recordset(p_snapshots) AS x(
                                                      season int, week int, source text, scoring_format text, player_id uuid,
                                                            player_id_space text, content_date date, pulled_at timestamptz, run_id uuid,
                                                                  vegas_provenance text, vegas_stats_used jsonb, fds_stat_sources jsonb,
                                                                        fds_projection_stats jsonb, raw_source_payload jsonb)
                                                                            LOOP
                                                                                  WITH ins AS (
                                                                                          INSERT INTO public.weekly_source_snapshots (
                                                                                                    season, week, source, scoring_format, player_id, player_id_space,
                                                                                                              content_date, pulled_at, run_id, vegas_provenance,
                                                                                                                        vegas_stats_used, fds_stat_sources, fds_projection_stats, raw_source_payload)
                                                                                                                                VALUES (v_snap.season, v_snap.week, v_snap.source, v_snap.scoring_format,
                                                                                                                                          v_snap.player_id, v_snap.player_id_space, v_snap.content_date,
                                                                                                                                                    v_snap.pulled_at, v_snap.run_id, v_snap.vegas_provenance,
                                                                                                                                                              v_snap.vegas_stats_used, v_snap.fds_stat_sources,
                                                                                                                                                                        v_snap.fds_projection_stats, v_snap.raw_source_payload)
                                                                                                                                                                                ON CONFLICT (season, week, source, scoring_format, player_id, player_id_space, content_date)
                                                                                                                                                                                        DO UPDATE SET pulled_at = excluded.pulled_at,
                                                                                                                                                                                                  raw_source_payload = excluded.raw_source_payload,
                                                                                                                                                                                                            vegas_provenance = excluded.vegas_provenance,
                                                                                                                                                                                                                      vegas_stats_used = excluded.vegas_stats_used,
                                                                                                                                                                                                                                fds_stat_sources = excluded.fds_stat_sources,
                                                                                                                                                                                                                                          fds_projection_stats = excluded.fds_projection_stats
                                                                                                                                                                                                                                                  WHERE (excluded.vegas_provenance IS DISTINCT FROM public.weekly_source_snapshots.vegas_provenance
                                                                                                                                                                                                                                                              OR excluded.vegas_stats_used IS DISTINCT FROM public.weekly_source_snapshots.vegas_stats_used
                                                                                                                                                                                                                                                                          OR excluded.fds_stat_sources IS DISTINCT FROM public.weekly_source_snapshots.fds_stat_sources
                                                                                                                                                                                                                                                                                      OR excluded.fds_projection_stats IS DISTINCT FROM public.weekly_source_snapshots.fds_projection_stats
                                                                                                                                                                                                                                                                                                  OR excluded.raw_source_payload IS DISTINCT FROM public.weekly_source_snapshots.raw_source_payload)
                                                                                                                                                                                                                                                                                                          RETURNING (xmax = 0) AS inserted
                                                                                                                                                                                                                                                                                                                )
                                                                                                                                                                                                                                                                                                                      SELECT count(*) FILTER (WHERE inserted), count(*) FILTER (WHERE NOT inserted)
                                                                                                                                                                                                                                                                                                                              INTO v_n_ins, v_n_upd FROM ins;
                                                                                                                                                                                                                                                                                                                                    v_inserted := v_inserted + v_n_ins;
                                                                                                                                                                                                                                                                                                                                          v_updated := v_updated + v_n_upd;
                                                                                                                                                                                                                                                                                                                                              END LOOP;
                                                                                                                                                                                                                                                                                                                                                END IF;
                                                                                                                                                                                                                                                                                                                                                  IF p_flags IS NOT NULL THEN
                                                                                                                                                                                                                                                                                                                                                      FOR v_flag IN SELECT * FROM jsonb_to_recordset(p_flags) AS x(
                                                                                                                                                                                                                                                                                                                                                            season int, week int, source text, player_id uuid, player_id_space text,
                                                                                                                                                                                                                                                                                                                                                                  run_id uuid, reason text, pulled_at timestamptz)
                                                                                                                                                                                                                                                                                                                                                                      LOOP
                                                                                                                                                                                                                                                                                                                                                                            INSERT INTO public.weekly_no_market_read_flags (
                                                                                                                                                                                                                                                                                                                                                                                    season, week, source, player_id, player_id_space, run_id, reason, pulled_at)
                                                                                                                                                                                                                                                                                                                                                                                          VALUES (v_flag.season, v_flag.week, v_flag.source, v_flag.player_id,
                                                                                                                                                                                                                                                                                                                                                                                                  v_flag.player_id_space, v_flag.run_id, v_flag.reason, v_flag.pulled_at)
                                                                                                                                                                                                                                                                                                                                                                                                        ON CONFLICT (season, week, source, player_id, player_id_space, run_id) DO NOTHING;
                                                                                                                                                                                                                                                                                                                                                                                                              GET DIAGNOSTICS v_n_ins = ROW_COUNT;
                                                                                                                                                                                                                                                                                                                                                                                                                    v_flags := v_flags + v_n_ins;
                                                                                                                                                                                                                                                                                                                                                                                                                        END LOOP;
                                                                                                                                                                                                                                                                                                                                                                                                                          END IF;
                                                                                                                                                                                                                                                                                                                                                                                                                            UPDATE public.pipeline_write_audit
                                                                                                                                                                                                                                                                                                                                                                                                                                 SET completed_at = now(), row_count = v_inserted + v_updated,
                                                                                                                                                                                                                                                                                                                                                                                                                                          metadata = jsonb_build_object('inserted', v_inserted, 'updated', v_updated, 'flags', v_flags)
                                                                                                                                                                                                                                                                                                                                                                                                                                             WHERE id = p_audit_id;
                                                                                                                                                                                                                                                                                                                                                                                                                                               RETURN jsonb_build_object('inserted', v_inserted, 'updated', v_updated, 'flags', v_flags, 'audit_id', p_audit_id);
                                                                                                                                                                                                                                                                                                                                                                                                                                               END
                                                                                                                                                                                                                                                                                                                                                                                                                                               $function$
;

CREATE OR REPLACE FUNCTION api.run_publish_gate(p_contract_version text, p_bake_ids jsonb, p_candidate_snapshot_id uuid DEFAULT NULL::uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'api', 'public'
AS $function$ DECLARE EXPECTED_CONTRACT CONSTANT TEXT := '1.0.0'; bake_uuids UUID[]; bu UUID; g JSONB; all_passed BOOLEAN := TRUE; gates JSONB := '[]'::jsonb; warnings JSONB := '[]'::jsonb; declared_keys TEXT[]; pure_vorp_keys TEXT[]; covered_sources TEXT[]; missing_keys TEXT[]; BEGIN IF p_contract_version IS DISTINCT FROM EXPECTED_CONTRACT THEN RETURN jsonb_build_object('passed', FALSE, 'gate', 'run_publish_gate', 'reason', 'contract_version mismatch', 'expected', EXPECTED_CONTRACT, 'got', p_contract_version); END IF; SELECT COALESCE(array_agg(b.bake_id),ARRAY[]::UUID[]) INTO bake_uuids FROM jsonb_each_text(COALESCE(p_bake_ids->'per_source','{}'::jsonb)) AS t(src,ts) JOIN public.bakes b ON b.source=t.src AND date_trunc('second', b.source_generated_at)=date_trunc('second', t.ts::timestamptz); IF bake_uuids IS NULL OR cardinality(bake_uuids)=0 THEN RETURN jsonb_build_object('passed',FALSE,'gate','run_publish_gate','reason','candidate declares no resolvable bake UUIDs in bake_ids'); END IF; FOREACH bu IN ARRAY bake_uuids   LOOP     g := api.gate_values_reconciliation(p_contract_version, p_bake_ids, bu);     gates := gates || g;     all_passed := all_passed AND (g ->> 'passed')::BOOLEAN;     g := api.gate_player_joins(p_contract_version, p_bake_ids, bu);     gates := gates || g;     all_passed := all_passed AND (g ->> 'passed')::BOOLEAN;     g := api.gate_options_coverage(p_contract_version, p_candidate_snapshot_id, bu);     gates := gates || g;     all_passed := all_passed AND (g ->> 'passed')::BOOLEAN;     g := api.gate_view_coverage(p_contract_version, p_candidate_snapshot_id, bu);     gates := gates || g;     all_passed := all_passed AND (g ->> 'passed')::BOOLEAN;   END LOOP;   g := api.gate_context_valid_fresh(p_contract_version, p_candidate_snapshot_id, bu);   gates := gates || g;   all_passed := all_passed AND (g ->> 'passed')::BOOLEAN;   g := api.gate_source_freshness(p_contract_version, p_candidate_snapshot_id, bu);   gates := gates || g;   all_passed := all_passed AND (g ->> 'passed')::BOOLEAN;   SELECT po.source_keys, po.pure_vorp_keys     INTO declared_keys, pure_vorp_keys     FROM public.product_options po    WHERE po.product_key = 'default';  declared_keys  := COALESCE(declared_keys, ARRAY[]::TEXT[]);   pure_vorp_keys := COALESCE(pure_vorp_keys, ARRAY[]::TEXT[]);   SELECT COALESCE(array_agg(DISTINCT source), ARRAY[]::TEXT[])     INTO covered_sources     FROM public.consolidated_values    WHERE bake_uuid = ANY (bake_uuids);   SELECT COALESCE(array_agg(t.k), ARRAY[]::TEXT[])     INTO missing_keys     FROM unnest(declared_keys) AS t(k)    WHERE NOT (t.k = ANY (pure_vorp_keys))      AND NOT (t.k = ANY (covered_sources))      AND NOT (t.k = 'cbs_adjusted' AND 'cbs' = ANY (covered_sources));   missing_keys := COALESCE(missing_keys, ARRAY[]::TEXT[]);   IF cardinality(missing_keys) > 0 THEN     gates := gates || jsonb_build_object(       'passed', FALSE,       'gate',   'bake_set_coverage',       'reason', 'declared sources with no bake in the candidate set',       'missing', to_jsonb(missing_keys),       'bake_uuids', (SELECT jsonb_agg(t.u) FROM unnest(bake_uuids) AS t(u))     );     all_passed := FALSE;   END IF;   SELECT COALESCE(jsonb_agg(u.w), '[]'::jsonb)     INTO warnings     FROM jsonb_array_elements(gates) AS t(gate),          LATERAL jsonb_array_elements(COALESCE(t.gate -> 'warnings', '[]'::jsonb)) AS u(w);   RETURN jsonb_build_object(     'passed',     all_passed,     'warnings',   warnings,     'gates',      gates,     'bake_uuids', (SELECT jsonb_agg(t.u) FROM unnest(bake_uuids) AS t(u))   ); END; $function$
;

-- Permissions (migration jeg377_jeg380_api_lockdown, 2026-10-05). JEG-378 was
-- marked Done but PUBLIC still had EXECUTE on activate_snapshot, the gates and
-- ingest_consolidated_values (anon could write chart values).
do $$
declare r record;
begin
  for r in select p.oid::regprocedure as sig from pg_proc p
           join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'api' loop
    execute format('revoke execute on function %s from public, anon, authenticated', r.sig);
    execute format('grant execute on function %s to service_role', r.sig);
  end loop;
end $$;
revoke insert, update, delete, truncate, references, trigger on public.product_snapshot from anon, authenticated;
alter table public.consolidated_values alter column source_generated_at set not null;

commit;
