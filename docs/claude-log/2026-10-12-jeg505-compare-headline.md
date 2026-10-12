## 2026-10-12 - JEG-505 compare-a-trade headline

Contract: the verdict card opens with "Should you propose or accept?" (DDF Value) and "Will they accept?" (published charts), each with a High / Medium / Low confidence (CT-02). Jeremy, 2026-10-09: DDF net under 5% of the value traded reads Low.

### Verified (check named)
- `tests.test_v2_headlines`: nine constructed trades (unanimous, split, one-source, razor-thin, 4% and exactly 5% margin, two charts only, a missing chart, a missing DDF value) equal a Python recomputation from the raw values, and hand-checked anchors; six mutations (thin rule dropped, 3% threshold, low-confidence ignored, other-manager flip, High threshold, few-sources cap) are caught.
- `tests.test_v2_compare_render`: both lines render with their question, a symbol and a confidence word; line 1's answer equals the sign of the DDF net recomputed from `getAllRows()`; a flipped-answer build is caught. `tests.test_v2_contract_render` still passes.

### Claimed, not confirmed
- The 60% / 75% agreement bands, the 2/3 and 1/3 Likely/Unlikely cut-offs, the "fewer than 3 sources caps at Medium" rule and "a one-source DDF Value lowers line 1 only" are my choices, documented in docs/v2-design-notes.md; Jeremy has only decided the 5% rule.
- No screenshot review of the card at phone width.
