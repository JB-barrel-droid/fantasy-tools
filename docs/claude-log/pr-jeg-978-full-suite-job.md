## 2026-10-23 - JEG-978: full test suite in its own preview job (laptop-2)

### Finding

The red `preview` checks were not timeouts. The informational `make test-unit`
step died 1.5 to 3 minutes in with "runner has received a shutdown signal" or
"The hosted runner lost communication with the server" (runs 40014037799,
39994927317, 40010847396, 40008330849). The cause was a test that exhausted
memory: `fc_grain_check`'s cycle walk never ended (JEG-979, fixed in #872).
When the runner itself is lost, the whole job fails and step-level
`continue-on-error` cannot help, so the ticket's first suggestion would not
have worked. Every other red preview run checked today was a real
`make validate` failure.

### Change

- `.github/workflows/preview.yml`: the suite moves to its own `full-suite`
  job with job-level `continue-on-error` and a 45-minute timeout. It gets the
  setup it had as the preview job's last step (Playwright browser,
  rendered_gate `npm ci`, `RENDER_TESTS_REQUIRED=1`, `make sync`). Steps use
  multi-line `run:` blocks so the pages.yml parity guard ignores them.
- `tests/test_preview_workflow_matches_pages.py`: `check_preview` now requires
  `make test-unit` to be in the full-suite job with job-level continue-on-error,
  and never in the preview job.

### Verified (named checks)
- `tests.test_preview_workflow_matches_pages`, `tests.test_workflow_no_event_interpolation`,
  `tests.test_retired_extras`: OK.
- Against origin/main's preview.yml (simulated broken state),
  `test_real_preview_matches_production` fails with both new messages.
- CI proof runs: see the PR description.
