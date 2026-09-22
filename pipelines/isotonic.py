"""Isotonic regression (non-decreasing), PAVA. Repo-owned port.

This is the fixed-pie translation math the repo uses to map a source's native
published values onto the canonical chart scale: a non-decreasing (isotonic)
fit preserves each source's rank order and within-position relative shape while
moving values onto the anchor's scale. Standard Pool Adjacent Violators
Algorithm; stdlib only, no dependencies.

Predict clamps at the ends of the fitted range and linearly interpolates
between fitted points, so predictions are monotone in the input.
"""

from __future__ import annotations


def isotonic_fit(xs: list[float], ys: list[float]) -> tuple[list[float], list[float]]:
    """Fit a non-decreasing function mapping xs -> ys.

    Returns (fit_x, fit_y): the fitted step values, one (x, y) pair per input
    point, sorted by x, with y non-decreasing. Requires at least one point.

    Tied x values are pooled FIRST (their y values averaged): a fit must be
    a function, so equal inputs share one fitted value. Without this, tied
    inputs with increasing y never trigger a PAVA violation and receive
    different fitted values -- inventing a distinction the data didn't make
    and breaking sum preservation (the fixed-pie invariant).
    """
    if not xs or len(xs) != len(ys):
        raise ValueError("isotonic_fit needs non-empty xs and ys of equal length")
    pts = sorted(zip(xs, ys))
    # Pre-pool tied x values: one block per distinct x.
    pooled: list[list] = []  # [x, weight, y_sum]
    for x, y in pts:
        if pooled and pooled[-1][0] == x:
            pooled[-1][1] += 1.0
            pooled[-1][2] += y
        else:
            pooled.append([x, 1.0, y])
    # Each block: [x_sum, weight, y_sum, [x values in block]]
    blocks: list[list] = []
    for x, w, y_sum in pooled:
        blocks.append([x * w, w, y_sum, [x] * int(w)])
        while len(blocks) >= 2 and blocks[-2][2] / blocks[-2][1] > blocks[-1][2] / blocks[-1][1]:
            b2 = blocks.pop()
            b1 = blocks.pop()
            blocks.append([b1[0] + b2[0], b1[1] + b2[1], b1[2] + b2[2], b1[3] + b2[3]])
    out_x: list[float] = []
    out_y: list[float] = []
    for _x_sum, w, y_sum, x_list in blocks:
        v = y_sum / w
        for x in x_list:
            out_x.append(x)
            out_y.append(v)
    return out_x, out_y


def isotonic_predict(fit_x: list[float], fit_y: list[float], x: float) -> float:
    """Predict y for x under a fitted isotonic map.

    Clamps to the fitted range at the ends; linearly interpolates between
    fitted points. Monotone non-decreasing in x.
    """
    if not fit_x:
        raise ValueError("isotonic_predict needs a non-empty fit")
    if x <= fit_x[0]:
        return fit_y[0]
    if x >= fit_x[-1]:
        return fit_y[-1]
    lo, hi = 0, len(fit_x) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if fit_x[mid] <= x:
            lo = mid
        else:
            hi = mid
    t = (x - fit_x[lo]) / (fit_x[hi] - fit_x[lo]) if fit_x[hi] != fit_x[lo] else 0.0
    return fit_y[lo] + t * (fit_y[hi] - fit_y[lo])
