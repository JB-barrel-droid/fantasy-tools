# Working agreements for AI sessions in this repo

Read this first. It is short on purpose.

## Log what you did before you finish

**Any session that changes anything in this repo appends an entry to
`docs/claude-log.md` before it ends.** Not just code changes — an investigation
that concluded something, a claim about what is broken, a number you measured.
The format and the reasoning behind it are at the top of that file.

The rule that matters: separate what you **verified** (and name the check) from
what you **claimed** without confirming. A previous session's unverified
assertion, inherited as fact, is worse than no note at all — it gets built on.
If you find an earlier entry was wrong, add a new entry saying so rather than
editing the old one.

Durable issues go in `docs/risk-register.md` as well; that is the standing issue
list, while the log is the record of who checked what.

## Standing constraints

These are the user's, stated directly. They are not suggestions.

- **Stage only.** Nothing is committed, merged, pushed, or published without the
  explicit word "Push" or "Publish". Staging work and reporting is the default.
- **Every regression guard must prove it catches the bug it names.** Negative-test
  it against a simulated broken state. A guard that asserts current behaviour is
  correct, without checking which state is right, is worse than no guard.
- **Never display unvalidated values. Never publish on a known flaw.** If
  `make validate` is red, that is a stop, not a warning — it is also the deploy's
  own gate, so a red local run means a failed deploy.
- **Do not adjust tests to go green.** If a test fails, the default assumption is
  that the code is wrong. Changing a pinned assertion is legitimate only when the
  assertion itself was wrong, and the entry in the log must say why.
- **`make sync` is the single publish path** and stamps the build tag. Do not
  re-add `dist/static`, `dist/server`, `space.json` or `deploy.sh`.
- **Do not touch `~/Projects/"fantasy tools"`** on the user's machine beyond the
  `Claude outputs/` folder. It holds `data/raw` — 33MB, gitignored, and the only
  copy of the player-news pipeline's inputs.

## Copy rules (user-facing text)

- The market side is always **"Vegas"**, never "the market".
- The brand is **Data Driven Football** only. No FantasyPros, Muse, or Meta
  branding anywhere user-facing.
- Never say **VORP** in user-facing copy. The locked term is **"value above
  waivers"**. (`espn_vorp` as an internal data key is exempt; there is a test
  enforcing this.)

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
