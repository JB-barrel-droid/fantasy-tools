## 2026-10-28 - Monitor failure handling / JEG-1200

Contract: repair draft PR #1042's false success on alert-delivery failure and
false resolution with unknown served weeks. Preserve the #1022 dependency,
Wednesday-noon deadline and warning-only source lateness.

Judgments: an unknown publication week means the check is incomplete, not
that the source is late or current. Preserve existing alerts and fail that
monitoring run. An explicit unknown in published history overrides a chain
attempt; retain the existing fallback for sources absent from history. Fail
on GitHub delivery errors too, without claiming that a partially completed
multi-request update left the issue unchanged. No source holds or value rules
change.

### Verified (check named)

- Refreshed PR/Linear ownership. Head `6c5f589` remained an open draft while
  Linear said Done. Claimed `session:be`, In Progress, T1 deep.
- Merged current main `032cee07` into `be/jeg-1200-source-late` without conflicts.
- Refreshed main again before push and merged `1bd85f76` (connector fit labels);
  it does not change the source-health files.
- Four new regression methods failed before the implementation fix (nine
  failing subcases), including the exact unknown-week close and exit-0
  delivery failures from review.
- `python3 -m unittest tests.test_source_lateness tests.test_source_probe
  tests.test_monitoring_coverage tests.test_gha_schedules_pg_cron
  tests.test_timestamps`: 128 passed after the final mixed-state test.
- Final `python3 -m unittest tests.test_source_lateness`: 32 passed. Covers
  missing/null/malformed metadata, known-current resolution, mixed known and
  unknown states, connection failure and HTTP 403/429/503. Network calls mocked.
- The existing late-source exit-0 test now supplies known publication metadata:
  unknown publication is intentionally a monitoring error under this repair,
  while missing probe state still produces ordinary lateness warnings.

### Claimed, not confirmed

- Full validate/render CI and independent review on the repaired head.
- Scheduled main execution and real issue creation/update/resolution after
  the parent's eventual merge. No live alerts or Supabase writes were made.
