# JEG-1531 incident reader

Trusted coordinator command and publication-window drill. Status: implemented offline; human App setup and live acceptance pending (2026-11-05).

The administrator must create/install a **separate** repository-limited GitHub App with Actions, Checks, Commit statuses and Pull requests read permissions, plus metadata. No writer or dispatch permissions. The secret owner provisions `INCIDENT_GITHUB_APP_ID`, `INCIDENT_GITHUB_INSTALLATION_ID`, and PEM `INCIDENT_GITHUB_PRIVATE_KEY` in the trusted coordinator environment, names a rotation/revocation owner, and keeps these variables out of ordinary jobs and PR execution. Purpose checks are routing guards, not a sandbox against code already holding the environment.

Install `pipelines/requirements-incident.txt` in that environment. Run from this worktree:

```sh
python3 -m pipelines.incident_reader OWNER/REPO PR --required preview --required v2-render
python3 scripts/incident_reader_drill.py OWNER/REPO PR --required preview --required v2-render > incident-drill.jsonl
```

Replace required names with the human-confirmed required-check contract; this command does not read branch protection settings. Exit 0 means complete green evidence for that explicit contract, 2 means unknown/deadline. The command never merges or deploys. Routine clients take only an explicit routine token; no fallback selects App credentials. Minting restricts the token to the named repository and read permissions. Tokens remain in memory; they expire per GitHub's returned expiry, and App JWTs expire after nine minutes.

A process registry and a worktree-local POSIX lock serialize observers per repo/PR (stricter than per head). All coordinators must route through this single trusted checkout; the lock is not distributed across hosts. Each sample discovers current runs so newly started workflows cannot be missed, caches their workflow/run IDs for job routing, and invalidates IDs when the head changes. Discovery pages are deliberately refreshed rather than cached as green. Pagination consumes the same ten-request budget, including minting. A second PR read fences green against a changed head. Unknown evidence never inherits prior success. Polls are 60–65 seconds apart; rate headers can extend delays but never the 30-minute observer deadline. In-flight HTTP operations have a 15-second timeout.

The drill runs at least 65 minutes, rotating bounded observers after 30 minutes, and injects routine exhaustion for the first 15 minutes without sending routine requests. It retains live samples and sanitized rate headers, checks rolling 30-minute request totals, reserve, 403/429 counts and reset changes. It uses the same observer lock. It does not claim full acceptance from synthetic routine exhaustion alone.

Human acceptance procedure (SOURCE.md section 5):

1. Approve App scope and endpoint probes; record distinct installation identity/budget versus routine bot and main-writer, without credential values.
2. Capture baseline and protected morning counters for bot and Actions consumers, including unattributed spend, while usual scheduled jobs and several fix PRs run. Confirm actual legacy sweep/QA enablement and token bindings without restarting disabled routines.
3. Run the drill over a full reset boundary. Complete the test PR's checks during the injected 15-minute routine outage. Record the completion timestamp externally and compare the first current-head GREEN sample: latency must be <=120 seconds. Push a new head mid-drill and verify no stale-head green. Repeat with many-check/paginated evidence; bounded UNKNOWN is expected when pages exceed the cap.
4. Require <=300 protected REST requests per rolling 30 minutes, >=1,000 remaining, no protected 403/429, and observed reset boundaries. Review JSONL against external completion evidence; a script threshold pass alone is insufficient.
5. For real publication retain PR/head/check evidence, Pages run/deployed SHA and live build verification. None of those gates is replaced by this reader.

Rollback: disable command routing and have the secret owner revoke installation tokens/key. Preserve UNKNOWN on the exhausted routine path. No automated credential transfer, scheduler changes, deployment or credential revocation is performed here.
