# Working agreements for AI sessions in this repo

Read this first. It is short on purpose.

## Log what you did before you finish

**Any session that changes anything in this repo writes its own log entry
before it ends.** Create `docs/claude-log/YYYY-MM-DD-<short-slug>.md` (e.g.
`docs/claude-log/2026-10-08-fix-coverage-gate.md`). Not just code changes — an
investigation that concluded something, a claim about what is broken, a number
you measured. The format and the rules are in `docs/claude-log/README.md`.

`docs/claude-log.md` is the frozen archive of entries from before 2026-10-07;
do not append to it. New entries go only in the `docs/claude-log/` directory.

The rule that matters: separate what you **verified** (and name the check) from
what you **claimed** without confirming. A previous session's unverified
assertion, inherited as fact, is worse than no note at all — it gets built on.
If you find an earlier entry was wrong, add a new entry saying so rather than
editing the old one.

Durable issues go in `docs/risk-register.md` as well; that is the standing issue
list, while the log is the record of who checked what.

Do not leave durable gaps only in chat or only in `docs/claude-log/`. If a
session discovers a real open issue, stale document, missing validation path, or
fixed correctness defect that future sessions would otherwise rediscover, add or
update its row in `docs/risk-register.md` before finishing.

## Standing constraints

These are the user's, stated directly. They are not suggestions.

- **Commit and push by default after validation.** When the user asks for a fix,
  refresh, deploy repair, or other repo/site outcome, finish the work end to end:
  commit, push to `main`, wait for GitHub Actions, and verify the live site when
  the change affects published output. The user no longer needs to say the exact
  word "Push" or "Publish". Stop short only when the user explicitly says not to
  push/publish, validation is red, the change would require a force push or
  destructive history edit, or another approval gate below applies.
- **Every regression guard must prove it catches the bug it names.** Negative-test
  it against a simulated broken state. A guard that asserts current behaviour is
  correct, without checking which state is right, is worse than no guard.
- **Never display unvalidated values. Never publish on a known flaw.** If
  `make validate` is red, that is a stop, not a warning — it is also the deploy's
  own gate, so a red local run means a failed deploy.
- **Do not adjust tests to go green.** If a test fails, the default assumption is
  that the code is wrong. Changing a pinned assertion is legitimate only when the
  assertion itself was wrong, and the entry in the log must say why.
- **Muse owns nothing here except as a last resort** (2026-10-06). Claude owns
  merges, deploys, production QA and scheduled jobs; route to Muse only when a
  step truly can't be done elsewhere and Jeremy asks.
- **Prefer Supabase tools over GitHub** for schedules, checks and orchestration
  (pg_cron, Edge Functions, `monitoring` schema). GitHub Actions only for what
  Supabase can't do (site build/deploy, repo tests), scheduled from pg_cron.
- **`make sync` is the single publish path** and stamps the build tag. Do not
  re-add `dist/static`, `dist/server`, `space.json` or `deploy.sh`.
- **Do not touch `~/Projects/"fantasy tools"`** on the user's machine beyond the
  `Claude outputs/` folder. It holds `data/raw` — 33MB, gitignored, and the only
  copy of the player-news pipeline's inputs.

## Copy rules (user-facing text)

- The market side is always **"Vegas"**, never "the market".
- The brand is **Data Driven Football** only. No FantasyPros, Muse, or Meta
  branding anywhere user-facing.
- The locked user-facing term is **"VORP vs waivers"** (decision copy-vorp-001,
  2026-10-06; it replaced "value above waivers"). That exact phrase is the only
  allowed user-facing use of "VORP" — no "Raw VORP", bare "VORP", or other
  wording. (`espn_vorp` as an internal data key is exempt;
  `tests/test_public_copy_no_vorp.py` enforces this.)

## Before changing the trade-value chart

Run the 12-combo headless sweep (3 scorings × 4 league sizes) against the built
`dist/`, and check `fixedPieIndexed` and `sourceScaleAgreement` in
`TradeValueCurveDiagnostics` for each.

Pie totals agreeing across sources proves nothing about curve shape. In
September 2026 the ESPN curve was a completely different valuation model from
every other line on the chart, with an RB peak of 99.1 against the published
charts' 75–80 — and every pie total matched to a rounding error, so every guard
stayed green. Compare the thing a reader actually looks at: where each
position's curve starts.
