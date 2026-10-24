# Research posts 2, 4, 5: public-facing cleanup (JEG-973)

Branch be/JEG-973, docs-only. Files: docs/research/posts/02-how-many-backups.md,
04-how-we-rescale-trade-charts.md, 05-missing-zero-one-source.md.

## Verified

- Removed ticket IDs, script and config paths, relative links, evidence tables,
  and the draft header lines from all three posts (grep for JEG, backticks,
  `.py`, `.md`, `](`, "Draft" returns nothing in these files apart from the
  word "drafts" meaning fantasy drafts).
- Reader text uses Rescaled (not Indexed), Value above waivers (not VORP),
  DDF Value (no "blend"), and spells out positions and league terms at first use.
- Post 5 no longer says chart zeros or fill-in values count in DDF Value.
  Checked against docs/methodology.md line 33 and line 66: DDF Value is the
  equal-weight mean of the projection sources' Adjusted values (ESPN, CBS rest
  of season, Razzball) since the change merged as #814. The post-5 table,
  the "one source" section and the worked example were rewritten to match, and
  the post title no longer says "Missing = 0".
- Post 4 now defines DDF Value as the projection-only mean for the same reason.

## Claimed, not checked

- Every number is carried over unchanged from the earlier posts. I did not
  re-run the bench research or the 15,000 inversions count against the engine.
- Post 4 still says the factor matches the DDF Value total over shared players,
  as the methodology (VP-6.4) states; not re-derived from code.
- Post 2 line about "a different set of inputs" replaces "a blend of seven
  sources", since DDF Value is no longer a seven-source blend; the 22.6% and
  12% figures are unchanged.
- No tests run: docs only, no test reads these files (grep of tests/ and Makefile).
