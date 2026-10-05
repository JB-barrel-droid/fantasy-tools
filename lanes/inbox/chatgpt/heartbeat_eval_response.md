HEARTBEAT-EVAL — 60s wiring recommendation (lane chatgpt/heartbeat-eval)

What I found (repo-verified, with citations)
- There is a daily CI synthetic gate, not a DB cron, for the live page. In .github/workflows/live-page-synthetic.yml the schedule is explicitly daily at 06:00 UTC:
  - "schedule:\n    - cron: \"0 6 * * *\"" (lines 7–11 of the workflow header)
  - The job runs a Node script (not Python): "node tests/rendered_gate/live.mjs … --out output/live-page-synthetic.json" (lines ~68–76). This produces an artifact file for a monitor bridge step; it does not populate a DB.
- The monitor bridge explicitly copes with producer schema and fails closed on ambiguity. In .github/workflows/live-page-synthetic.yml:
  - The fixed reader is: "raw_ts = data.get('generatedAt', data.get('generated_at'))\nif not raw_ts:\n    raise SystemExit('live-page-synthetic.json has neither generatedAt nor generated_at')\ngenerated_at = datetime.fromisoformat(str(raw_ts).replace('Z', '+00:00'))" (lines ~131–159). The exact failure addressed is documented in tests/test_live_page_synthetic_workflow.py (see below).
- The workflow behaviour is tested in tests/test_live_page_synthetic_workflow.py and confirms the producer/consumer wiring is artifact-based, not DB-based:
  - "producer writes camelCase `generatedAt`, the bridge read snake_case `generated_at`" (docstring lines 7–13)
  - The guard for missing timestamp: "raise SystemExit('live-page-synthetic.json has neither generatedAt nor generated_at')" (around line 106) and the corresponding test "test_missing_timestamp_fails_closed" (lines ~128–136).
- I could not find pipelines/heartbeat_evaluator.py or any tests named tests/test_heartbeat_state_machine.py in this worktree. Grepping pipelines/ for "heartbeat" and the exact filename returns no hits. That indicates the evaluator module exists conceptually (per ticket) but is not present/landed in this lane yet; any production wiring must treat the callable and its entrypoints as to-be-landed.
- Supabase inventory (read-only) shows a table named live_page_checks with columns {checked_at, url, status_code, response_ms, verdict}, but no rows at present (db_describe/db_select from the test harness, zero rows observed). Given the ticket’s context statement “There is NO live_page_checks table … (verified against the live API)”, treat this as an environment discrepancy and do not rely on it existing in production without explicit approval/migration.
- I found no pg_cron DDL in sql/ (grep for pg_cron/cron.schedule returned empty). The only scheduler evidence in-repo is GitHub Actions cron (the daily synthetic gate above) and our own scheduler slip tooling (pipelines/measure_scheduler_slip.py) which is GH Actions–oriented.

Implications
- The evaluator is a pure-Python, hermetic state machine that “reads CheckConfig + Observation rows (filtered by the caller — it must NOT touch live_page_checks itself) and writes a Heartbeat snapshot. It also has plan_pages() for paging decisions.” There is currently no landed Python entry point to call it, no confirmed observation producer in production, and no consumer of Heartbeat snapshots in-repo.
- pg_cron cannot execute Python. The sibling proposal to run the evaluator from pg_cron every 60s is infeasible without a SQL/PL/pgSQL port of the state machine.

Option analysis
A) VM-side scheduler every 60s invoking a small Python driver that loads observations, calls the evaluator, and writes the Heartbeat snapshot
- Build cost
  - Low to moderate. Work to land:
    - A tiny driver module (e.g., pipelines/heartbeat_driver.py) that:
      - Loads a CheckConfig and a bounded window of Observation rows (from a caller-owned source — e.g., a spool directory of NDJSON dropped by the observation producer, or a vetted Supabase view if/when approved).
      - Calls the evaluator (evaluate/check()/whatever the landed API is) and optionally plan_pages() for page decisions.
      - Writes a Heartbeat snapshot artifact (JSON) and, if/when approved, persists to a Supabase table via a single RPC or REST write. No writes without explicit approval.
    - A wrapper shell that ensures single-flight execution (flock) and bounded runtime.
    - systemd unit + timer to run every 60s on the VM.
- Failure modes
  - VM restart: mitigated with systemd timer Persistent=true so missed intervals are queued; OnBootSec adds a post-boot delay.
  - Overlap: prevented by flock in the wrapper; log and skip if a prior run is still active.
  - Jitter: systemd OnUnitActiveSec=60s is monotonic; RandomizedDelaySec=2s optional to avoid phase alignment with other minute jobs.
  - Observation starvation: if the producer is down, the driver emits a snapshot with no new observations; the evaluator must treat this as degraded and never fabricate green.
  - IO/network failure (if reading from Supabase once approved): treat as a hard failure, emit red or no snapshot; never guess.
- Reversibility
  - Fully reversible by disabling the timer; no DB DDL required to ship the driver + units. Rolling back the driver code is a normal deploy.
- VM restart/pg_cron jitter
  - Independent of Postgres; no pg_cron interaction at all.

B) SQL/PL/pgSQL port of the evaluator run via pg_cron every 60s
- Build cost
  - High to very high. Porting a Python state machine (plus plan_pages()) into SQL/PL language risks semantic drift and creates two sources of truth for testability. The tests named in the ticket (tests/test_heartbeat_state_machine.py) are Python; they would not cover a SQL port.
- Failure modes
  - Complexity-induced bugs; difficult local iteration; hard to hermetically unit-test.
- Reversibility
  - Requires DDL, function bodies, and grant wiring; rolling back is more complex and touches production.
- VM restart/pg_cron jitter
  - pg_cron can jitter and coalesce missed runs; also, it cannot reach Python, so any hybrid requires FDW/external.
- Verdict
  - Not recommended.

C) Don’t schedule yet — prerequisite wiring is missing
- Facts supporting this
  - No evaluator module present in this worktree (pipelines/heartbeat_evaluator.py not found); no callers; no DB consumers for Heartbeat snapshots; observation producer unclear.
  - The only scheduled “live page” job is the CI synthetic gate that writes a GitHub artifact, not a DB table. Quotes:
    - ".github/workflows/live-page-synthetic.yml: schedule: - cron: \"0 6 * * *\"" (daily)
    - "node tests/rendered_gate/live.mjs … --out output/live-page-synthetic.json" (artifact, no DB write)
- Pros
  - Honest: we avoid deploying a heartbeat of nothing that fabricates green.
- Cons
  - No telemetry until the rest of the pipeline lands.
- Reversibility
  - N/A — we simply wait to flip the switch when producers/consumers exist.

D) Event-driven instead of polled (evaluate on observation write)
- Build cost
  - Medium to high and depends on platform:
    - Postgres NOTIFY/LISTEN: needs a long-lived worker anyway (back to A, but event-driven wakeups).
    - Supabase Edge Functions/Realtime: evaluator is Python; Edge Functions are TypeScript/Deno — would need a port or a service bridge.
- Failure modes
  - Backpressure/duplicate events; at-least-once semantics demand idempotency guards anyway.
- Reversibility
  - Tighter coupling to producer makes reverting trickier; also platform-dependent infrastructure.
- Verdict
  - Worth revisiting once an observation producer exists. Today, premature.

Recommendation (one clear path)
- Choose A: systemd timer on the VM, running a small Python driver every 60 seconds.
- Ship the wiring but gate activation on two prerequisites: (1) the evaluator module is landed with a stable callable API; (2) an observation producer is defined and accepted (source of CheckConfig + Observation rows), and a consumer for Heartbeat snapshots is approved. Until then, the units can sit disabled and the driver can be exercised in staging with file-based fixtures.

Concrete next steps (sequenced, fail-closed)
0) Land the evaluator and its tests in-repo
- File: pipelines/heartbeat_evaluator.py (export: plan_pages(), and a pure function that takes List[Observation], CheckConfig and returns a Heartbeat snapshot — exact names per the module).
- Tests: tests/test_heartbeat_state_machine.py. The lane’s worktree currently lacks both; reviewers will block wiring changes until they exist.

1) Define the observation interface and a staging source
- Pick one of:
  - File-spool: a directory (e.g., /var/spool/heartbeat/observations/) where the producer drops NDJSON observations. Driver reads last N seconds and advances a cursor file. Easiest to test; no DB writes; hermetic.
  - Supabase view (approved): a read-only view v_live_observations that exposes the last 2–5 minutes of observations for whitelisted checks. The driver reads this view and never writes; it remains hermetic at the evaluator layer. This requires explicit schema approval (not included here).
- Codify CheckConfig discovery (static JSON under config/heartbeat_checks.json or a read-only view v_heartbeat_check_config). Do not couple the evaluator to live tables; the driver owns filtering and shaping.

2) Implement the driver (no production writes without approval)
- New file: pipelines/heartbeat_driver.py (CLI entry point)
  - Inputs: --checks <json|path>, --observations <ndjson|spool|supabase>, --out <path>, --window-sec 120
  - Behaviour: read CheckConfig + recent Observations; call evaluator; write a snapshot JSON with generated_at and deterministic content. Exit nonzero on any ambiguity (missing inputs, parse errors). Never fabricate green.
  - Optional: write a single structured log row to pipeline_cron_log (table exists) once writes are permitted; until then, log to stdout/journald only.
- Wrapper: bin/heartbeat-eval (bash)
  - Use flock to guarantee single-flight: exec flock -n /run/heartbeat-eval.lock -c "python3 -m pipelines.heartbeat_driver …"

3) Systemd units (ops-managed; examples here for production host)
- /etc/systemd/system/heartbeat-eval.service
  - [Unit]
    Description=Heartbeat evaluator (60s)
    After=network-online.target
  - [Service]
    Type=exec
    WorkingDirectory=/srv/fantasy-tools
    EnvironmentFile=-/etc/sysconfig/fantasy-tools
    ExecStart=/usr/bin/flock -n /run/heartbeat-eval.lock \ 
              /usr/bin/env bash -lc 'venv/bin/python -m pipelines.heartbeat_driver \
                --checks config/heartbeat_checks.json \
                --observations spool:/var/spool/heartbeat/observations \
                --out /var/spool/heartbeat/snapshots/last.json \
                --window-sec 120'
    Restart=always
    RestartSec=5s
    TimeoutStartSec=20s
    TimeoutStopSec=10s
    SyslogIdentifier=heartbeat-eval
  - [Install]
    WantedBy=multi-user.target
- /etc/systemd/system/heartbeat-eval.timer
  - [Unit]
    Description=Run heartbeat-eval every 60s
  - [Timer]
    OnBootSec=30s
    OnUnitActiveSec=60s
    AccuracySec=1s
    Persistent=true
    RandomizedDelaySec=2s
  - [Install]
    WantedBy=timers.target
- Operational notes
  - Enable with: systemctl enable --now heartbeat-eval.timer (only after 0–2 are complete and approved).
  - Logs: journalctl -u heartbeat-eval -f; ensure the driver’s JSON summary logs one line per run for easy scraping.
  - Overlap policy: if a run exceeds 60s, the next tick will skip (flock) and log a soft error; you’ll see wall-time > 60s, which is a backpressure signal.

4) Consumer/monitoring (deferred until approved)
- Once a Heartbeat snapshot table and/or monitor hooks are approved:
  - Add a writer to persist snapshots (one row per generated_at; idempotent on unique generated_at) and a tiny view for “latest per check”.
  - Wire alerts to read the latest snapshot and page on red/stale according to policy. Until then, rely on journald and dashboard rendering of the JSON artifact if desired.

Why not B/C/D today?
- B (SQL port) is an overreach: we lose the hermetic Python tests, double the maintenance surface, and still need a runner.
- C (don’t schedule) is honest but leaves us blind. The correct compromise is to land A’s code paths and enable the timer only when producers/consumers exist.
- D (event-driven) is attractive once we have a clear producer with event hooks; today we do not.

Acceptance checks you (Jeremy) can apply to the driver before enabling
- A lane-level dry run with file-spool fixtures: point --observations to a temp dir populated with known-good NDJSON, verify the evaluator snapshot matches tests and never fabricates green when you remove inputs.
- Kill -STOP the driver mid-run; verify the next minute logs a lock-skipped tick rather than overlapping runs.
- Reboot the VM; confirm the timer fires after ~30s and catches up once (Persistent=true).

Explicit blockers to flip the switch
- pipelines/heartbeat_evaluator.py must be landed in this repo, with a stable callable signature exercised by tests/test_heartbeat_state_machine.py.
- A blessed observation producer and a consumer for Heartbeat snapshots must be named and approved. Until then, keep the service disabled.

References (quotes)
- .github/workflows/live-page-synthetic.yml
  - "schedule:\n    - cron: \"0 6 * * *\""
  - "node tests/rendered_gate/live.mjs … --out output/live-page-synthetic.json"
  - "raise SystemExit('live-page-synthetic.json has neither generatedAt nor generated_at')"
- tests/test_live_page_synthetic_workflow.py
  - "producer writes camelCase `generatedAt`, the bridge read snake_case `generated_at`"
- Supabase catalog (read-only from test harness)
  - live_page_checks(checked_at, url, status_code, response_ms, verdict): present but empty; do not rely on this without production confirmation.
