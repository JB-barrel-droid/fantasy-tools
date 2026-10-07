# Claude session log — per-PR directory

New entries go here as individual files, one per PR or session.

## Naming convention

```
docs/claude-log/YYYY-MM-DD-<short-slug>.md
```

Where `<short-slug>` is a 2–5 word kebab-case label matching the PR topic or
Linear issue (e.g. `log-per-pr`, `qb2-hold-fix`, `sleeper-identity-dedup`).
Files sort chronologically by name; no shared index file is required or
maintained.

## Entry format

```markdown
## YYYY-MM-DD - <topic / Linear issue>

Contract: one or two sentences — what was the session's goal?

### Verified (check named)
- Bullet per thing confirmed. Name the test, script, or observation that
  confirmed it. Do not write "Verified: it works." Name the check.

### Claimed, not confirmed
- Bullet per thing asserted without a live check. A future session can
  promote a claimed item to Verified by naming its check.
```

## Rules (same as the old docs/claude-log.md preamble)

- **Separate verified from claimed.** An unverified assertion inherited as fact
  is worse than no note at all.
- **Corrections are new entries, never edits.** If an earlier entry was wrong,
  add a new file saying so. Never modify a past entry in place.
- **Name the check.** "It passed" with no check named is a claim, not a
  verification.
- **Durable issues also go in `docs/risk-register.md`.** The log is the record
  of who checked what; the risk register is the standing issue list.

## Archive

`docs/claude-log.md` is the frozen archive of entries from before 2026-10-07.
Its format is identical; read it for historical context but do not append to it.
