"""Regression test: quantile mapping preserves source distinctions.

Jeremy caught this live on 2026-09-30: Jaxon Smith-Njigba (55.4), Ja'Marr Chase
(57.1), and Amon-Ra St. Brown (54.0) had distinct FantasyPros values but were all
flattened to 56.1 indexed. Two bugs caused this:

1. The comparison pipeline used the `value` field (overwritten with reindexed
   values by the bake) instead of `native_value` (raw published). The fixture's
   "natives" didn't match the snapshot's natives.

2. Isotonic PAVA pooled values when the source disagreed with ESPN's ordering.
   FP ordered Chase > JSN, ESPN ordered JSN > Chase, so PAVA averaged them.

This test verifies that quantile mapping preserves distinct source values as
distinct reindexed values, even when the source ordering disagrees with the anchor.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipelines"))

from reindex_comparison_section import quantile_map


def test_distinct_natives_stay_distinct():
    """The JSN/Chase/Amon-Ra case: distinct FP natives must map to distinct values."""
    # FP natives (source ordering: Amon-Ra < JSN < Chase)
    fp_natives = [54.0, 55.4, 57.1]
    # ESPN anchors (anchor ordering: Amon-Ra < Chase < JSN -- disagrees on Chase/JSN)
    espn_anchors = [37.6, 38.0, 40.4]
    
    mapped = [quantile_map(fp_natives, espn_anchors, x) for x in fp_natives]
    
    # All three must be distinct
    assert len(set(round(m, 2) for m in mapped)) == 3, (
        f"Quantile mapping flattened distinct natives: {fp_natives} -> {mapped}"
    )
    
    # Order must be preserved (FP's ordering, not ESPN's)
    assert mapped[0] < mapped[1] < mapped[2], (
        f"Quantile mapping broke source ordering: {fp_natives} -> {mapped}"
    )


def test_quantile_mapping_preserves_spacing():
    """Relative gaps in the source should be preserved proportionally."""
    xs = [10.0, 20.0, 30.0, 40.0]
    ys = [100.0, 200.0, 300.0, 400.0]
    
    # Midpoint of source should map to midpoint of anchor
    mid = quantile_map(xs, ys, 25.0)
    assert abs(mid - 250.0) < 0.01, f"Expected 250.0, got {mid}"
    
    # Endpoints clamp correctly
    assert quantile_map(xs, ys, 5.0) == 100.0
    assert quantile_map(xs, ys, 45.0) == 400.0


def test_quantile_mapping_monotone():
    """Output must be non-decreasing in input (the core reindexing invariant)."""
    import random
    random.seed(42)
    
    xs = sorted([random.uniform(0, 100) for _ in range(50)])
    ys = sorted([random.uniform(0, 70) for _ in range(50)])
    
    # Test with shuffled anchor (disagreements)
    random.shuffle(ys)
    ys_shuffled = ys[:]
    
    test_points = [x + random.uniform(-1, 1) for x in xs[::5]]
    mapped = [quantile_map(xs, ys_shuffled, x) for x in sorted(test_points)]
    
    for i in range(1, len(mapped)):
        assert mapped[i] >= mapped[i-1], (
            f"Quantile mapping not monotone: {mapped[i-1]} -> {mapped[i]}"
        )


if __name__ == "__main__":
    test_distinct_natives_stay_distinct()
    print("✓ distinct natives stay distinct")
    test_quantile_mapping_preserves_spacing()
    print("✓ spacing preserved")
    test_quantile_mapping_monotone()
    print("✓ monotone")
    print("\nAll regression tests passed!")
