# JEG-1458 Actions egress rollup

Prepare a measured week from the existing Python shim counter. This is a response-body meter, not a Supabase billing meter. Status: draft implementation, 2026-10-31; review and merge pending.

Each exiting shim process emits its workflow, script basename, optional non-secret `SUPABASE_BYTES_CALLER`, run ID, attempt, job, and step summary filename (or explicit `SUPABASE_BYTES_STEP`). Actions does not expose a native step ID to Python. Never put secrets in either optional label. UTC timestamps and process event IDs allow filtering and duplicate removal. The health build also copies all counter log lines to its summary rather than relying on its 25-line tail.

Every workflow job installing the shim uploads `supabase-bytes-<job>-<attempt>` artifacts, retained 14 days. Failed runs are included when available. Abrupt termination can prevent exit counters; missing artifacts, days and callers mean unmeasured, never zero. Existing pre-change summaries lack script/time context and are skipped with an explicit count. New artifacts and summary copies carry identical event IDs and are counted once.

Read-only collection and rollup (requires gh authentication with Actions read access):

```sh
python3 pipelines/rollup_supabase_bytes.py output/egress-week --days 7 --download JB-barrel-droid/fantasy-tools
```

This discovers the checked-out workflows using the shim, paginates runs/artifacts and downloads only counter artifacts, including previous run attempts. It stops on the first API failure, including rate limiting; no retry loops. Use a fresh output directory per collection. The first real collection can wait for quota. No importers or write-capable measurement jobs should be launched.

For already exported step summaries or downloaded/extracted artifacts, place `.md` files below a directory and omit `--download`. A reproducible offline example:

```sh
python3 pipelines/rollup_supabase_bytes.py tests/fixtures/supabase-bytes --days 2 --until 2026-11-01T00:00:00+00:00
```

The checked-in sample records use representative counter output with fixed test attribution, not measured production usage. Output groups requests, decoded bytes and wire body bytes per UTC day, workflow, script, caller and table. Top five reads aggregate GET/HEAD wire bytes over the full window. RPC POSTs have unknown read/write semantics and are excluded from that ranking. Boundary days may be partial: collect seven full UTC days using an explicit midnight `--until` after the week has elapsed. Do not infer that a workflow with no records used no bandwidth; check its runs/artifacts and exit status separately.

get-values and site traffic are **not covered and must not be read as zero**. Leave get-values unchanged: a future shared response wrapper could count UTF-8 application response bytes including errors, but requires a deploy and Jeremy's explicit yes. Site delivery/browser Supabase calls need separate host/endpoint accounting. Wire here excludes headers, transport overhead and request payloads; compare against provider egress before any plan or trim decision. This patch starts no schedule and makes no plan/trim recommendation.
