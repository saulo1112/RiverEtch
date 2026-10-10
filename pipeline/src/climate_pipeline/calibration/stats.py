"""Statistics of the calibration validation (numpy only, deterministic with a seed).

Every interval here resamples the unit that is independent: acquisitions (clusters) for matchups,
calendar months for daily series, hydrological years for climate phases. Resampling pairs would
give intervals that are too narrow when one scene pairs with several samples.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Sequence

import numpy as np

from climate_pipeline.validation.insitu import spearman as spearman_reference

__all__ = [
    "block_bootstrap_spearman",
    "block_permutation_p",
    "chi2_sf",
    "kruskal_wallis",
    "mape",
    "mdsa",
    "partial_spearman",
    "rho_needed",
    "spearman",
    "spearman_reference",
    "sspb",
]


def average_ranks(values: np.ndarray) -> np.ndarray:
    """Ranks from 1, ties sharing their average rank (vectorized).

    Args:
        values: 1-D array.

    Returns:
        The ranks.
    """
    sorter = np.argsort(values, kind="mergesort")
    inverse = np.empty(sorter.size, dtype=np.intp)
    inverse[sorter] = np.arange(sorter.size)
    ordered = values[sorter]
    first = np.r_[True, ordered[1:] != ordered[:-1]]
    dense = first.cumsum()[inverse]
    bounds = np.r_[np.nonzero(first)[0], first.size]
    return np.asarray(0.5 * (bounds[dense] + bounds[dense - 1] + 1), dtype=np.float64)


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman's rho with average ranks for ties (same definition as the validation's).

    Args:
        x: Values.
        y: Paired values.

    Returns:
        rho, NaN with fewer than three pairs or a constant series.
    """
    a, b = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    if a.size < 3:
        return math.nan
    ra, rb = average_ranks(a), average_ranks(b)
    if ra.std() == 0 or rb.std() == 0:
        return math.nan
    return float(np.corrcoef(ra, rb)[0, 1])


def block_bootstrap_spearman(
    x: Sequence[float],
    y: Sequence[float],
    blocks: Sequence[Hashable],
    resamples: int,
    seed: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Percentile interval of Spearman's rho, resampling whole blocks (clusters) with replacement.

    Args:
        x: Values.
        y: Paired values.
        blocks: The block of each pair (an acquisition, a month, ...).
        resamples: Bootstrap draws.
        seed: Random seed.
        confidence: Interval coverage.

    Returns:
        ``(low, high)``; NaN when fewer than 3 pairs or 2 blocks, or no draw gives a finite rho.
    """
    a, b = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    keys = list(dict.fromkeys(blocks))
    if len(a) < 3 or len(keys) < 2:
        return math.nan, math.nan
    index = {k: i for i, k in enumerate(keys)}
    block_of = np.array([index[k] for k in blocks], dtype=np.intp)
    rng = np.random.default_rng(seed)
    chosen = np.stack([rng.integers(0, len(keys), size=len(keys)) for _ in range(resamples)])
    # A resample is a multiplicity per original pair: how often its block was drawn.
    rows = np.repeat(np.arange(resamples), len(keys))
    counts = np.bincount(rows * len(keys) + chosen.ravel(), minlength=resamples * len(keys))
    weights = counts.reshape(resamples, len(keys))[:, block_of].astype(np.float64)
    rho = _weighted_spearman(a, b, weights)
    values = rho[np.isfinite(rho)]
    if not values.size:
        return math.nan, math.nan
    tail = (1 - confidence) / 2 * 100
    return float(np.percentile(values, tail)), float(np.percentile(values, 100 - tail))


def _weighted_ranks(values: np.ndarray, weights: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Average ranks of each value inside every resample (a row of multiplicities).

    A value drawn ``m`` times occupies ``m`` tied positions, so in a resample its average rank is
    (the draws of smaller values) + (the draws of equal values + 1) / 2.

    Returns:
        The ranks (resamples x values) and whether each resample has two distinct values.
    """
    order = np.argsort(values, kind="mergesort")
    ordered = values[order]
    first = np.r_[True, ordered[1:] != ordered[:-1]]
    group = first.cumsum() - 1
    equal = np.add.reduceat(weights[:, order], np.flatnonzero(first), axis=1)
    less = np.cumsum(equal, axis=1) - equal
    ranks = np.empty_like(weights)
    ranks[:, order] = (less + (equal + 1) / 2)[:, group]
    return ranks, (equal > 0).sum(axis=1) > 1


def _weighted_spearman(a: np.ndarray, b: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """:func:`spearman` of every resample at once (NaN as there: < 3 draws or a constant)."""
    ra, varied_a = _weighted_ranks(a, weights)
    rb, varied_b = _weighted_ranks(b, weights)
    n = weights.sum(axis=1)
    da = ra - (weights * ra).sum(axis=1, keepdims=True) / n[:, None]
    db = rb - (weights * rb).sum(axis=1, keepdims=True) / n[:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        rho = (weights * da * db).sum(axis=1) / np.sqrt(
            (weights * da * da).sum(axis=1) * (weights * db * db).sum(axis=1)
        )
    ok = (n >= 3) & varied_a & varied_b
    return np.where(ok, np.clip(rho, -1.0, 1.0), np.nan)


def _log_ratios(predicted: Sequence[float], observed: Sequence[float]) -> np.ndarray:
    p, o = np.asarray(predicted, dtype=np.float64), np.asarray(observed, dtype=np.float64)
    ok = np.isfinite(p) & np.isfinite(o) & (p > 0) & (o > 0)
    return np.log(p[ok] / o[ok])


def mdsa(predicted: Sequence[float], observed: Sequence[float]) -> float:
    """Median symmetric accuracy, percent: 100 x (exp(median |ln(p/o)|) - 1) (Morley et al. 2018).

    Args:
        predicted: Predictions (positive).
        observed: Observations (positive).

    Returns:
        MdSA in percent (NaN without valid pairs).
    """
    q = _log_ratios(predicted, observed)
    return float(100 * (math.exp(float(np.median(np.abs(q)))) - 1)) if q.size else math.nan


def sspb(predicted: Sequence[float], observed: Sequence[float]) -> float:
    """Symmetric signed percentage bias: 100 x sign(m) x (exp(|m|) - 1), m = median ln(p/o).

    Args:
        predicted: Predictions (positive).
        observed: Observations (positive).

    Returns:
        SSPB in percent (NaN without valid pairs).
    """
    q = _log_ratios(predicted, observed)
    if not q.size:
        return math.nan
    m = float(np.median(q))
    return float(100 * math.copysign(math.exp(abs(m)) - 1, m))


def mape(predicted: Sequence[float], observed: Sequence[float]) -> float:
    """Mean absolute percentage error (secondary metric; asymmetric for log-normal data).

    Args:
        predicted: Predictions.
        observed: Observations (non-zero).

    Returns:
        MAPE in percent (NaN without valid pairs).
    """
    p, o = np.asarray(predicted, dtype=np.float64), np.asarray(observed, dtype=np.float64)
    ok = np.isfinite(p) & np.isfinite(o) & (o != 0)
    return float(100 * np.mean(np.abs((p[ok] - o[ok]) / o[ok]))) if ok.any() else math.nan


def rho_needed(n: int, lower_bound: float, z: float = 1.959964) -> float:
    """The Spearman rho whose approximate 95 % lower bound equals ``lower_bound`` at size ``n``.

    Fisher z with the Bonett-Wright standard error sqrt((1 + rho^2 / 2) / (n - 3)). The criterion
    itself uses the bootstrap; this only shows the bar in advance.

    Args:
        n: Pairs.
        lower_bound: The bound to exceed.
        z: Normal quantile.

    Returns:
        rho (NaN for n <= 3).
    """
    if n <= 3:
        return math.nan

    def low(r: float) -> float:
        return math.tanh(math.atanh(r) - z * math.sqrt((1 + r * r / 2) / (n - 3)))

    a, b = lower_bound, 0.999999
    if low(b) <= lower_bound:
        return math.nan
    for _ in range(100):
        m = (a + b) / 2
        a, b = (m, b) if low(m) <= lower_bound else (a, m)
    return b


def _ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=np.float64)
    ranks[order] = np.arange(1, len(values) + 1, dtype=np.float64)
    for value in np.unique(values):
        tied = values == value
        if tied.sum() > 1:
            ranks[tied] = ranks[tied].mean()
    return ranks


def partial_spearman(x: Sequence[float], y: Sequence[float], z: Sequence[float]) -> float:
    """Spearman correlation of x and y given z (the Pearson partial correlation of the ranks).

    Args:
        x: Values.
        y: Paired values.
        z: The controlled variable.

    Returns:
        The partial rho (NaN with fewer than 4 complete triples or a degenerate series).
    """
    a, b, c = (np.asarray(v, dtype=np.float64) for v in (x, y, z))
    ok = np.isfinite(a) & np.isfinite(b) & np.isfinite(c)
    if ok.sum() < 4:
        return math.nan
    ra, rb, rc = _ranks(a[ok]), _ranks(b[ok]), _ranks(c[ok])
    r = np.corrcoef(np.vstack([ra, rb, rc]))
    if not np.all(np.isfinite(r)):
        return math.nan
    rxy, rxz, ryz = r[0, 1], r[0, 2], r[1, 2]
    denominator = math.sqrt(max((1 - rxz**2) * (1 - ryz**2), 0.0))
    return float((rxy - rxz * ryz) / denominator) if denominator > 0 else math.nan


def _gammainc_upper_regularized(s: float, x: float) -> float:
    # Q(s, x): series for x < s + 1, continued fraction otherwise (Numerical Recipes 6.2).
    if x <= 0:
        return 1.0
    gln = math.lgamma(s)
    if x < s + 1:
        term = total = 1.0 / s
        a = s
        for _ in range(1000):
            a += 1
            term *= x / a
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return 1.0 - total * math.exp(-x + s * math.log(x) - gln)
    b = x + 1 - s
    c = 1.0 / 1e-300
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - s)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    return math.exp(-x + s * math.log(x) - gln) * h


def chi2_sf(x: float, k: int) -> float:
    """Upper tail probability of a chi-square distribution.

    Args:
        x: Statistic.
        k: Degrees of freedom.

    Returns:
        P(X >= x).
    """
    return _gammainc_upper_regularized(k / 2, x / 2)


def kruskal_wallis(groups: Sequence[Sequence[float]]) -> tuple[float, float]:
    """Kruskal-Wallis H test with the tie correction (chi-square approximation).

    Args:
        groups: Values per group (groups with no finite value are ignored).

    Returns:
        ``(H, p)``; NaN with fewer than 2 groups.
    """
    clean = [np.asarray([v for v in g if math.isfinite(v)], dtype=np.float64) for g in groups]
    clean = [g for g in clean if g.size]
    if len(clean) < 2:
        return math.nan, math.nan
    allv = np.concatenate(clean)
    ranks = _ranks(allv)
    n = allv.size
    h, start = 0.0, 0
    for g in clean:
        r = ranks[start : start + g.size]
        h += r.sum() ** 2 / g.size
        start += g.size
    h = 12 / (n * (n + 1)) * h - 3 * (n + 1)
    _, counts = np.unique(allv, return_counts=True)
    ties = 1 - float(np.sum(counts**3 - counts)) / (n**3 - n)
    if ties <= 0:
        return math.nan, math.nan
    h /= ties
    return float(h), chi2_sf(float(h), len(clean) - 1)


def block_permutation_p(
    values: Sequence[float],
    labels: Sequence[str],
    blocks: Sequence[Hashable],
    first: str,
    second: str,
    permutations: int,
    seed: int,
    alternative: str = "two-sided",
) -> tuple[float, float]:
    """Permutation test of mean(values | first) - mean(values | second), shuffling block labels.

    Every value of a block shares its block's label; the labels of whole blocks are permuted, so
    serial correlation within a block is kept.

    Args:
        values: Values (one per observation).
        labels: The label of each observation (constant within a block).
        blocks: The block of each observation.
        first: Label whose mean comes first.
        second: Label whose mean is subtracted.
        permutations: Draws.
        seed: Random seed.
        alternative: ``greater`` (first > second), ``less`` or ``two-sided``.

    Returns:
        The observed difference and its p-value (NaN when a label is missing).
    """
    v = np.asarray(values, dtype=np.float64)
    keys = list(dict.fromkeys(blocks))
    block_label: dict[Hashable, str] = {}
    for k, label in zip(blocks, labels, strict=True):
        block_label.setdefault(k, label)
    index = np.array([keys.index(k) for k in blocks])
    base = np.array([block_label[k] for k in keys])

    def diff(block_labels: np.ndarray) -> float:
        lab = block_labels[index]
        a, b = v[lab == first], v[lab == second]
        a, b = a[np.isfinite(a)], b[np.isfinite(b)]
        return float(a.mean() - b.mean()) if a.size and b.size else math.nan

    observed = diff(base)
    if not math.isfinite(observed):
        return math.nan, math.nan
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(permutations):
        d = diff(rng.permutation(base))
        if not math.isfinite(d):
            continue
        if alternative == "greater":
            hits += d >= observed
        elif alternative == "less":
            hits += d <= observed
        else:
            hits += abs(d) >= abs(observed)
    return observed, (1 + hits) / (1 + permutations)
