## 2026-10-29 - JEG-1211 review context, fresh PR

Contract: closed PR #1055 (head `a7028a10`, stale Oct 28 base) held the
JEG-1211 review-context doc. Re-land its new files on current main, without
its AGENTS.md and HANDOFF.md edits, which its review found drop current rules.

### Verified (check named)
- Copied from #1055 unchanged: `.github/pull_request_template.md`,
  `docs/review-evidence/2026-10-28-jeg-1142-impact.md` and the two Oct 28
  claude-log entries (`git checkout a7028a10 -- <path>`).
- `docs/review-context.md` copied, with one change: the label paragraph now
  names the active labels from the Linear catalog (list_issue_labels, Jegabee,
  2026-10-29) instead of "only Bug, Feature and Improvement", since `claude`,
  `needs-jeremy` and the `review-*` labels are in use.
- `docs/README.md`: the two index rows from #1055 added on current main.
- The `<!-- preview-build -->` marker the doc cites is in
  `.github/workflows/preview.yml` (grep). No test or workflow reads the PR
  template's headings (grep for `## Testing`).
- `python3 -m unittest tests.test_doc_staleness`: 4 OK. `git diff --check`
  clean. Docs only.

### Claimed, not confirmed
- The 2026-10-28 label-taxonomy log says its instruction change sits on
  #1055; #1055 is closed and the AGENTS.md label rules land in #1171
  (JEG-1218) instead.
- "the labels AGENTS.md lists" in review-context.md is true once #1171 merges.
