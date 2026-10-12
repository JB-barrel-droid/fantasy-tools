# Research post drafts (JEG-544, JEG-557, JEG-545)

Date: 2026-10-12
Tickets: JEG-544, JEG-557, JEG-545

## What changed

Drafted six research posts in `docs/research/posts/`:

1. **01-bench-player-value.md** (JEG-544): "How much is a bench player worth?" Academic-paper structure per Jeremy's review feedback. Uses verified facts from JEG-551 (fill-in rates), JEG-553 (bench-slots effect), JEG-593 (readout). Numbers pending JEG-562 (tier-basis convention) marked as pending.
2. **02-how-many-backups.md** (JEG-557): "How many backups should a fantasy roster hold?" From bench-rule-research.md and ticket description. Links to `pipelines/derive_market_bench.py` for draft data. Analysis scripts pending JEG-566.
3. **03-why-ddf-value.md** (JEG-545 post 1): "Why DDF Value is the core." From methodology.md VP-3 through VP-6.
4. **04-how-we-rescale-trade-charts.md** (JEG-545 post 2): "How we rescale trade charts." From methodology.md VP-6.4, JEG-482 decision.
5. **05-missing-zero-one-source.md** (JEG-545 post 3): "Missing = 0 and the one-source rule." From methodology.md "Published Charts On The Rows" and VP-6.2/6.3.
6. **06-trade-confidence.md** (JEG-545 post 4): "Trade confidence." Partially gated on JEG-505 (compare trade headline). One-source rule documented; agreement threshold marked pending.

Updated `docs/research/README.md` with a post drafts table.

## Verified

- Every claim links to a methodology section, research doc, or ticket.
- Numbers from JEG-551, JEG-553, JEG-593 are cited with verification status.
- JEG-562-gated numbers are marked "Pending JEG-562" throughout.
- JEG-505-gated content in post 6 is marked "Pending JEG-505."
- Copy rules followed: no named players in bench posts (rank-based), no title abbreviations, no vanity stats.

## Not verified (claimed)

- The exact post structure matches Jeremy's approved Google Doc feedback (the draft follows the same structure but is a fresh write, not a diff against the Doc).
- Posts 3-5 translate methodology correctly; no independent cross-check against the engine code was run.
