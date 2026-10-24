# JEG-974: research posts 6, 7, 8, 10 public-facing cleanup

Branch be/JEG-974. Docs-only; no code, data, fixtures or generated files touched.

## Changed
- Posts 6, 7, 8, 10 under docs/research/posts/: removed ticket IDs, PR numbers, paths, line references, draft markers and "copy rules" lines; replaced "Evidence links" with plain "Sources" tables; defined DDF Value, Rescaled and value above waivers; "Indexed" renamed "Rescaled".
- Post 6: compare-trade headline described as shipped; pending notes removed; "seven sources" changed to the three projection sources.
- Post 7: blend figures dropped, projections-only kept, one dated sentence about the earlier blend; framed as early evidence (weeks 2 to 7); re-run and future-plan lines removed.
- Post 8: blend figures dropped; "Toss-up" kept; High confidence tied to 3 of 4 charts; "Yes / Send it" described as a split and renamed "Value yes, market no".
- Post 10: "from now on" and "next step" wording, the storage schema code line, and the handback/decision lines removed.

## Verified
- grep of the four posts for JEG-, PR #, backticks, tools/, docs/, "Draft": no hits in public text.
- Every retained number was copied from the prior text, none recomputed.

## Claimed, not verified
- Retained projections-only figures are exactly as the prior posts stated them; not re-run against the data.
- Post 7: "about 45 percent" base rate for the Buy-list comparison was the blend-run base rate; the projections-only base rate was not stated.
- Post 8: statement that DDF Value and DDF Projections are now the same number, so "Medium" no longer occurs, comes from the post's own projections-only note, not a fresh check of the site.
- Post 8: "High needs at least three of four charts" is stated as what the evidence supports, not as a confirmed live rule.
- Post 6: confidence rules on the headline (one-source lowers a level, margin under 5% forces Low, fewer than three charts caps at Medium) were taken from post 8's rule list.
