-- JEG-414: the evaluator read monitoring.v_check_observations, which mapped only
-- live_page_checks; directly reported observations (monitoring.check_observations,
-- written by public.monitoring_record_observation) were never evaluated.
-- Applied 2026-10-05 as migration jeg414_observations_view_union.
create or replace view monitoring.v_check_observations as
 select c.check_id, l.checked_at as run_at,
    (l.verdict = any (array['ok'::text, 'content_mismatch'::text])) as ok,
    l.response_ms as latency_ms, l.status_code as http_status,
    case when l.verdict = 'content_mismatch' then false
         when l.verdict = 'ok' and c.check_type = 'http_status_and_content'::monitoring.check_type then true
         else null::boolean end as content_ok,
    case l.verdict when 'timeout' then 'timeout' when 'dns_error' then 'dns' when 'tls_error' then 'tls'
         when 'connect_error' then 'connect' when 'http_error' then 'http' else null::text end as error_code
   from live_page_checks l join monitoring.check_config c on c.url = l.url
 union all
 select o.check_id, o.run_at, o.ok, o.latency_ms, o.http_status, o.content_ok, o.error_code
   from monitoring.check_observations o;
