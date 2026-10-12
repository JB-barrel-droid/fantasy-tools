## 2026-10-12 - JEG-619 docs index

Contract: add docs/README.md with naming conventions and a one-line description per doc (JEG-596 decision: keep .md in GitHub plus an easy-to-browse index).

### Verified (check named)
- Every top-level docs/*.md appears in the index: shell loop comparing `docs/*.md` names against README links.

### Claimed, not confirmed
- Status labels (Maintained / Record) are judged from titles and first lines, not from a full read; the JEG-597..605 passes will correct them.
- Hosted index artifact is a separate step (see ticket comment).
