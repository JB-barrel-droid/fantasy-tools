JEG-339 — Observation producer contract for the heartbeat evaluator (SPEC ONLY)

Owner lane: chatgpt/jeg-339-producer-spec

Scope and grounding
- Evaluator shapes and semantics are taken from pipelines/heartbeat_evaluator.py at 54ae7a0 (branch-only per context). This module is hermetic and consumes CheckConfig + Observation collections and emits a Heartbeat. Key names used in this spec cite callable/type names and state reasons visible in that commit:
  - Observation fields as exercised in tests and function signatures: run_at (datetime), ok (bool), latency_ms (int|None), http_status (int|None), content_ok (bool|None), error_code (str|None). For example: "Observation(run_at=at(-30, now), ok=True,  http_status=200)" and the function signature "def classify_observation(obs: Observation, check_type: CheckType, latency_budget_ms: Optional[int])" (54ae7a0).
  - CheckConfig fields used by the state machine: check_id, enabled, cadence_seconds or cron_expr (xor), grace_override_seconds, latency_budget_ms, check_type, scheduler_owner_type, scheduler_owner_id, active_ownership_count. These are referenced across helpers like expected_next_run(...), effective_grace_seconds(...), and in tests constructing CheckConfig, e.g.: "cfg = CheckConfig(check_id=\"c11\", cadence_seconds=300, latency_budget_ms=400, scheduler_owner_type=SchedulerOwnerType.GITHUB_ACTIONS, scheduler_owner_id=\"wf-11\")" (54ae7a0).
  - Heartbeat fields emitted by compute_state(...): check_id, state, ownership_status, scheduler_down, state_reason, expected_next_run_at, last_run_at, last_ok_at, last_error_at, latest_details. These are asserted in TestCase11EndToEndShape: "self.assertEqual(h.state, HeartbeatState.HEALTHY) ... self.assertIsNotNone(h.expected_next_run_at) ... self.assertFalse(h.scheduler_down)" (54ae7a0).
  - Deterministic transition reasons and ordering, directly quoted from compute_state(...) branches in 54ae7a0: "failed run in window"; "no runs in window"; "no runs in window; scheduler_down=true → route to platform"; "latest ok run (HEALTHY|DEGRADED)"; and the initial "enabled=false" and "no schedule resolvable" guards.
  - Duplicate-observation tolerance is explicit in tests at 54ae7a0: "latest_observation returns whichever appears later in the iteration; the spec calls for deterministic behaviour. We pin by picking the second one." and "test_full_state_machine_handles_duplicate_runs_without_crash".
- Live table today: public.live_page_checks exists with zero rows and columns (checked_at, url, status_code, response_ms, verdict) per Roman (2026‑10‑04). This spec defines the producer contract against that table shape.
- SQL monitoring shim in this repo (supabase/migrations/jeg339_monitoring_schema.sql) provides a read-only view stub mapping live_page_checks to the evaluator’s Observation shape. Today it incorrectly assumes live_page_checks already has evaluator-native columns. Quote: "create or replace view monitoring.v_check_observations as select check_id::text as check_id, run_at as run_at, ok::boolean as ok, latency_ms::integer as latency_ms, http_status::integer as http_status, content_ok::boolean as content_ok, error_code::text as error_code from public.live_page_checks;" This mismatch is recognized here; the producer spec below establishes the canonical live_page_checks row contract and the mapping rule to Observation that the evaluator caller must apply.
- Existing daily synthetic workflow (.github/workflows/live-page-synthetic.yml) is scheduled daily at 06:00 UTC. Quote: "on: schedule: - cron: \"0 6 * * *\"" and it writes a JSON artifact, not to DB.

1) Producer design: process, cadence, single‑flight, cost
- Process
  - A stateless HTTP checker (minimal fetcher) that, per CheckConfig row, performs a single HTTP GET (or JS-rendered fetch where required by check_type) and emits one row to public.live_page_checks per run.
  - Allowed scheduler owners are aligned with the evaluator’s SchedulerOwnerType (54ae7a0 and SQL enum): pg_cron, github_actions, vercel_cron, fly_cron, external. The production default is pg_cron for reliability and cost; others are supported in non-prod or as interim.
- Cadence
  - Target: every 60 seconds per enabled check (cadence_seconds=60). The evaluator’s grace derives from cadence; tests assert floor/ceiling bounds (e.g., "cadence=60 → grace=... floor 120" at 54ae7a0). The producer must not miss consecutive minutes under normal operation.
  - For checks using cron_expr, the producer simply runs at its own 60s sweep but only executes a check whose expected window opens (expected_next_run(...) mirrors evaluator logic). This keeps a single codepath and avoids an extra scheduler per check.
- Single‑flight and idempotency
  - No schema changes are assumed in this spec; specifically, live_page_checks has no unique key. Because the evaluator explicitly tolerates duplicates at the same run_at (54ae7a0 TestCase13DuplicateObservations), producer correctness does not require global mutual exclusion to prevent occasional duplicate inserts. Nonetheless, to keep the table cheap and tidy:
    - The producer computes an idempotency key per (check_id, window_floor_minute). It uses a best‑effort application lock: before issuing an HTTP request, it performs a cheap cache lock (e.g., Redis SET NX with 90s TTL) or a Postgres advisory pg_try_advisory_lock via a tiny RPC. If the lock is held, the instance skips the run for that check.
    - If two instances race and both insert, evaluator correctness is unchanged, per 54ae7a0: "the algorithm is stable and does not crash on duplicates."
  - Cost containment
    - One small always-on worker (e.g., Fly.io single shared-cpu) or Supabase pg_cron + http extension/edge function keeps cost near-zero. GitHub Actions on a 1-minute schedule is not supported and would be both unreliable and costly at minute cadence; we do not use GA for the 60s producer.
  - Rollout order
    - Stage in dev with a dry-run mode (writes disabled) and an opt-in allowlist of checks. Production writes require explicit approval (see item 6).

2) Exact row contract for public.live_page_checks
- Columns to set on insert (all timestamps are UTC; producer must send timezone-aware values; do not rely on DB defaults):
  - checked_at (timestamptz, required): The wall-clock time at which the HTTP result was determined (end of response or terminal error). Set by the producer, in UTC. This maps to Observation.run_at.
  - url (text, required): The absolute URL that was checked. This is the stable join key to CheckConfig (see item 3).
  - status_code (integer, nullable): The HTTP status received. Null when no HTTP response was obtained (timeout, DNS, TLS, connect errors). Maps to Observation.http_status.
  - response_ms (integer, nullable): Total time in milliseconds from request start until success/failure decision. Always set when a connection attempt was made; may be null if the measurement could not be captured due to early abort before a clock start. Maps to Observation.latency_ms.
  - verdict (text, required): One of the following producer-level values, case-sensitive:
    - ok: HTTP response received; status_code present; content expectations (if any) matched. Maps to Observation.ok=True, content_ok=True or None (see below).
    - content_mismatch: HTTP response received; status_code present; response body did not match required content for checks of type http_status_and_content. Maps to Observation.ok=True, content_ok=False (note evaluator treats this as an error per 54ae7a0: "and obs.content_ok is False → return HeartbeatState.ERROR"). For non-content checks, producer must not emit this verdict.
    - timeout: No HTTP response within the configured timeout budget. Maps to Observation.ok=False, error_code="timeout".
    - dns_error: DNS resolution failed. Maps to Observation.ok=False, error_code="dns".
    - tls_error: TLS negotiation failed. Maps to Observation.ok=False, error_code="tls".
    - connect_error: TCP connect failed or was refused. Maps to Observation.ok=False, error_code="connect".
    - http_error: HTTP response received with a non-2xx status; status_code present. Maps to Observation.ok=False, error_code="http".
  - Semantics and mapping to Observation consumed by evaluator caller:
    - ok → ok=True; content_ok=True (or None when check_type does not evaluate content); http_status=status_code; latency_ms=response_ms; error_code=None.
    - content_mismatch → ok=True; content_ok=False; http_status=status_code; latency_ms=response_ms; error_code=None. Evaluator elevates this to HeartbeatState.ERROR for CheckType.HTTP_STATUS_AND_CONTENT per 54ae7a0 classify_observation.
    - timeout|dns_error|tls_error|connect_error|http_error → ok=False; content_ok=None; http_status as available (null except http_error); latency_ms=response_ms; error_code as listed above.
  - Timezone: Producer must write checked_at in UTC (ISO 8601 with Z) to eliminate clock skew ambiguity. Evaluator examples use tz-aware UTC datetimes, e.g., "now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)".
- Missing/partial row interpretation
  - status_code may be null for non-HTTP terminal failures; response_ms may be null in rare aborts. verdict is never null. checked_at and url are never null.
  - A "partial" row (e.g., status_code null, response_ms set, verdict=timeout) is a valid failed Observation and must be treated as ok=False by the caller mapping into Observation.
  - Duplicate rows at the same checked_at for the same url are tolerated; evaluator dedupes by run_at and remains deterministic on ties (54ae7a0 TestCase13DuplicateObservations).

3) CheckConfig source of truth (what is checked and who owns edits)
- Canonical store: monitoring.check_config in Supabase (DDL exists in supabase/migrations/jeg339_monitoring_schema.sql). Fields align with the evaluator’s CheckConfig: check_id (PK), enabled, cadence_seconds xor cron_expr, grace_override_seconds, latency_budget_ms, check_type, scheduler_owner_type, scheduler_owner_id, active_ownership_count, alert_policy.
- URL binding: Add a required url column to monitoring.check_config in a follow-up migration, owned by Jeremy. The producer will enumerate enabled rows and use config.url as the target written to live_page_checks.url. This avoids encoding URLs into check_id and gives a stable join for the v_check_observations mapping. Until that migration lands, dev can maintain a small in-repo mapping file config/live_checks.yml mapping check_id→url; production must not rely on the file.
- Edit ownership: Jeremy is the single approver for adding/editing checks, cadence, latency budgets, content matchers, and ownership metadata. Changes flow by PR + Roman DB migration for production.

4) Failure modes and required evaluator behavior
- Producer down
  - If the producer stops, no new rows will appear. Evaluator must never surface green in that case. This follows directly from 54ae7a0 compute_state transitions:
    - Missed condition: "gap since last_run exceeds grace and no run in current window" returns HeartbeatState.MISSED with state_reason "no runs in window" and, when scheduler_down is true, explicitly "no runs in window; scheduler_down=true → route to platform".
    - scheduler_is_down(...) returns True when no heartbeat exists: "No heartbeat ever recorded → treat as down" in 54ae7a0.
  - The scheduler heartbeat for the producer’s owner_type/owner_id must be updated by the runner every sweep; if stale or absent, scheduler_down=true ensures routing goes to platform, not product.
- Clock skew
  - Producer writes checked_at in UTC from its own clock. Small skew is tolerated because the evaluator windows are anchored at now with grace ≥120s (54ae7a0: GRACE_FLOOR_SECONDS=120). The caller mapping to Observation.run_at must use checked_at as-is; do not rebase.
- Duplicate rows
  - Harmless by design per 54ae7a0 TestCase13; latest_observation is stable across duplicates and state machine remains correct.
- Slow checks exceeding the 60s window
  - The producer sets response_ms to the full observed latency. Evaluator degrades an ok observation when latency exceeds cfg.latency_budget_ms: in 54ae7a0 classify_observation: "if latency_ms > latency_budget_ms: degraded=True" and returns HeartbeatState.DEGRADED when ok. If a run finishes after the grace window, the "Missed" path takes precedence because runs_in_window will be empty and the time gap condition fires; the next ok run recovers to ok/degraded accordingly. The ordering in compute_state enforces this with the Missed branch placed before the latest-ok branch.

5) Relationship to the existing daily synthetic workflow (.github/workflows/live-page-synthetic.yml)
- Keep as-is for deep end-to-end coverage (Playwright-rendered, build-tag assertions). It remains a deploy gate and does not write to DB.
  - Grounding: schedule is daily at 06:00 UTC: "- cron: \"0 6 * * *\""; it uploads an artifact "live-page-synthetic-results" and prints JSON; no DB writes.
- Optional extension (non-blocking): We may add a secondary check_id with cadence_seconds=86400 that ingests the workflow’s artifact into monitoring.check_observations (not live_page_checks) via a small adapter, preserving the workflow’s independence and avoiding mixing JS-rendered semantics into minute-level HTTP checks. This will be proposed in a separate lane and requires approval.
- Rationale: The 60s producer provides continuous lightweight signal for heartbeat. The daily GA job is heavier, JS-rendered, and not suitable for minute cadence. They are complementary.

6) Approvals required from Jeremy before any implementation
- Production writes to public.live_page_checks (hard requirement in standing rules).
- The definitive verdict value set above, including exact strings and their semantics (ok, content_mismatch, timeout, dns_error, tls_error, connect_error, http_error).
- The initial CheckConfig inventory: which URLs, their check_type, latency_budget_ms, cadence/crons, and ownership metadata.
- The scheduler owner choice for production (default proposal: pg_cron) and the plan to update monitoring.scheduler_heartbeats from that runner.
- Any schema changes: adding url to monitoring.check_config; adjusting monitoring.v_check_observations to correctly map live_page_checks → Observation by joining on url and projecting Observation fields.
- Retention policy for live_page_checks (e.g., 14–30 days) and cost bounds.
- Any user-facing copy in alerts and dashboards; evaluator currently emits state_reason strings such as "failed run in window" and "latest ok run (healthy|degraded)" per 54ae7a0, but routing/audience and wording are Jeremy’s domain.

Caller mapping: live_page_checks → Observation (for the evaluator caller)
- Given a row r from public.live_page_checks, construct an Observation for compute_state(...):
  - run_at = r.checked_at (UTC timestamptz)
  - http_status = r.status_code (int|None)
  - latency_ms = r.response_ms (int|None)
  - Map verdict to (ok, content_ok, error_code):
    - ok → ok=True, content_ok=True (or None if check_type does not apply), error_code=None
    - content_mismatch → ok=True, content_ok=False, error_code=None
    - http_error → ok=False, content_ok=None, error_code="http"
    - timeout → ok=False, content_ok=None, error_code="timeout"
    - dns_error → ok=False, content_ok=None, error_code="dns"
    - tls_error → ok=False, content_ok=None, error_code="tls"
    - connect_error → ok=False, content_ok=None, error_code="connect"

Notes on mismatches and follow-ups
- The current monitoring.v_check_observations view in supabase/migrations/jeg339_monitoring_schema.sql selects evaluator-native columns (check_id, run_at, ok, latency_ms, http_status, content_ok, error_code) from public.live_page_checks, which per Roman has only (checked_at, url, status_code, response_ms, verdict). We will replace that view in a follow-up migration to:
  - Join monitoring.check_config on url (new column) to project check_id;
  - Project run_at := checked_at, ok/content_ok/error_code derived from verdict, latency_ms := response_ms, http_status := status_code.
- This change is part of the implementation lane, not this spec.

Operational checklist (non-implementation commitments in this spec)
- Minute cadence runner (single process) with best-effort single-flight per check via advisory lock. If a second runner exists, correctness holds; costs remain bounded.
- Producer writes only the five columns defined; no evaluator code reaches into live_page_checks directly. The evaluator caller composes Observation sequences by filtering rows to the relevant check_id/url.
- Timestamps are written in UTC by the producer; evaluator windows use tz-aware now, as shown in 54ae7a0 tests.

Appendix: direct quotes grounding evaluator semantics (54ae7a0)
- classify_observation: "if not obs.ok: return HeartbeatState.ERROR"; "and obs.content_ok is False → return HeartbeatState.ERROR"; "if degraded: return HeartbeatState.DEGRADED; return HeartbeatState.HEALTHY".
- Missed transition in compute_state: "gap since last_run exceeds grace and no run in current window" and reason string "no runs in window" with scheduler_down variant.
- Duplicate handling: "latest_observation returns whichever appears later ... the algorithm is stable and does not crash on duplicates."
- Ownership: "if cfg.active_ownership_count <= 0: return OwnershipStatus.UNKNOWN_OWNER; if >1: AMBIGUOUS; else OK" and platform audience page for ambiguous ownership.

Deliverable ends. This file is the contract; implementation will follow in a separate lane after approvals listed in section 6.
