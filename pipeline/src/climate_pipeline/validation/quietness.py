"""How often the detector flags a reach, with Wilson intervals, and whether the reach is quiet."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from climate_pipeline.validation.config import QuietnessConfig, Variant
from climate_pipeline.validation.variants import VariantScene, share


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """The Wilson score interval of a proportion.

    Args:
        k: Successes (here: anomalous scenes).
        n: Trials (scored scenes).
        z: Normal quantile (1.96 for 95 %).

    Returns:
        ``(low, high)``, NaN for ``n == 0``.
    """
    if n == 0:
        return math.nan, math.nan
    p = k / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def share_rows(
    site_id: str,
    corridor: str,
    evaluations: dict[str, list[VariantScene]],
    variants: Sequence[Variant],
    z: float,
) -> list[dict[str, object]]:
    """The anomalous-scene share of every variant, with its Wilson interval.

    Args:
        site_id: The reach.
        corridor: Label of the geometry the scenes were measured on.
        evaluations: Variant id -> evaluation.
        variants: The variants, in order.
        z: Normal quantile of the interval.

    Returns:
        One row per variant.
    """
    rows = []
    for variant in variants:
        k, n = share(evaluations[variant.id])
        low, high = wilson(k, n, z)
        rows.append(
            {
                "site_id": site_id,
                "corridor": corridor,
                "variant": variant.id,
                "scored": n,
                "anomalous": k,
                "share": round(k / n, 4) if n else math.nan,
                "wilson_low": round(low, 4),
                "wilson_high": round(high, 4),
            }
        )
    return rows


@dataclass(frozen=True)
class Quietness:
    """The pre-registered quietness reading of the target, next to the control."""

    k: int
    n: int
    low: float
    high: float
    worst_variant: str
    worst_share: float
    quiet: bool
    control_k: int
    control_n: int
    control_low: float
    control_high: float
    comparison: str  # "lower than the control", "higher than the control", "not distinguishable"
    reasons: tuple[str, ...]


def assess(
    target: dict[str, list[VariantScene]],
    control: dict[str, list[VariantScene]] | None,
    variants: Sequence[Variant],
    cfg: QuietnessConfig,
) -> Quietness:
    """Apply the quietness criterion to the frozen-geometry evaluations.

    The reach is quiet when the Wilson upper bound of its D0 share is at most
    ``max_upper_bound`` and no variant's share exceeds ``max_variant_share``.

    Args:
        target: The target's evaluations by variant id.
        control: The control's evaluations (None if unavailable).
        variants: The variants.
        cfg: The criterion.

    Returns:
        The reading.
    """
    k, n = share(target["D0"])
    low, high = wilson(k, n, cfg.wilson_z)
    shares = []
    for variant in variants:
        vk, vn = share(target[variant.id])
        shares.append((vk / vn if vn else math.nan, variant.id))
    finite = [(s, v) for s, v in shares if math.isfinite(s)]
    worst_share, worst = max(finite, key=lambda p: p[0]) if finite else (math.nan, "")  # first max
    reasons = []
    if not high <= cfg.max_upper_bound:
        reasons.append(f"D0 upper bound {high:.3f} above {cfg.max_upper_bound:g}")
    if not worst_share <= cfg.max_variant_share:
        reasons.append(f"variant {worst} share {worst_share:.3f} above {cfg.max_variant_share:g}")
    ck, cn = share(control["D0"]) if control else (0, 0)
    c_low, c_high = wilson(ck, cn, cfg.wilson_z)
    if cn == 0:
        comparison = "control unavailable"
    elif high < c_low:
        comparison = "lower than the control"
    elif low > c_high:
        comparison = "higher than the control"
    else:
        comparison = "not distinguishable from the control"
    return Quietness(
        k, n, low, high, worst, worst_share, not reasons, ck, cn, c_low, c_high, comparison,
        tuple(reasons),
    )  # fmt: skip
