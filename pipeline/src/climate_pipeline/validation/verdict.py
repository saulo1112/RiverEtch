"""The mechanical verdict of the pre-registered criteria, and the binomial chance level."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from climate_pipeline.validation.config import Criteria

CANDIDATE = "candidate signal"
NO_SIGNAL = "no robust signal"
NOT_COMPUTABLE = "not computable"


@dataclass(frozen=True)
class Verdict:
    """The verdict and every number it rests on."""

    label: str
    episodes: int
    episodes_needed: int
    criterion_a: bool | None
    target_anomalous: int
    target_scored: int
    control_anomalous: int
    control_scored: int
    target_share: float
    control_share: float  # as used: 0.5 / n when the control had no anomaly
    ratio: float
    ratio_needed: float
    criterion_b: bool | None
    reasons: list[str] = field(default_factory=list)


def decide(
    episodes: int,
    target: tuple[int, int],
    control: tuple[int, int],
    target_rain_available: bool,
    criteria: Criteria,
) -> Verdict:
    """Apply criteria (a) and (b).

    Args:
        episodes: Criterion-(a) episodes of the target.
        target: The target's D0 ``(anomalous, scored)`` scenes.
        control: The control's D0 ``(anomalous, scored)`` scenes.
        target_rain_available: False when the target's point-rule rain is unknown for every scene.
        criteria: The pre-registered criteria.

    Returns:
        The verdict: "candidate signal" when both hold, "no robust signal" otherwise, and
        "not computable" when an input is missing.
    """
    a_n, a_scored = target
    c_n, c_scored = control
    reasons = []
    if a_scored == 0:
        reasons.append("the target has no scored scene under D0")
    if c_scored == 0:
        reasons.append("the control has no scored scene under D0")
    if not target_rain_available:
        reasons.append("the target's point-rule rain is unavailable for every scene")
    target_share = a_n / a_scored if a_scored else math.nan
    if c_scored == 0:
        control_share = math.nan
    elif c_n == 0:
        control_share = criteria.zero_share_numerator / c_scored
    else:
        control_share = c_n / c_scored
    ratio = (
        target_share / control_share
        if control_share and control_share == control_share
        else math.nan
    )
    if reasons:
        return Verdict(
            NOT_COMPUTABLE,
            episodes,
            criteria.min_episodes,
            None,
            a_n,
            a_scored,
            c_n,
            c_scored,
            target_share,
            control_share,
            ratio,
            criteria.share_ratio_min,
            None,
            reasons,
        )
    crit_a = episodes >= criteria.min_episodes
    crit_b = ratio >= criteria.share_ratio_min
    label = CANDIDATE if crit_a and crit_b else NO_SIGNAL
    if not crit_a:
        reasons.append(f"{episodes} episode(s), fewer than {criteria.min_episodes}")
    if not crit_b:
        reasons.append(f"share ratio {ratio:.2f}, below {criteria.share_ratio_min:g}")
    return Verdict(
        label,
        episodes,
        criteria.min_episodes,
        crit_a,
        a_n,
        a_scored,
        c_n,
        c_scored,
        target_share,
        control_share,
        ratio,
        criteria.share_ratio_min,
        crit_b,
        reasons,
    )


def binomial_tail(n: int, p: float, k: int) -> float:
    """P(X >= k) for X ~ Binomial(n, p).

    Args:
        n: Trials.
        p: Success probability.
        k: Threshold.

    Returns:
        The tail probability (NaN for an invalid p).
    """
    if not 0 <= p <= 1:
        return math.nan
    if k <= 0:
        return 1.0
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))
