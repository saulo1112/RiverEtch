import math

import pytest

from climate_pipeline.validation.config import Criteria
from climate_pipeline.validation.verdict import (
    CANDIDATE,
    NO_SIGNAL,
    NOT_COMPUTABLE,
    binomial_tail,
    decide,
)

CRITERIA = Criteria(
    persistence_min=8,
    episode_gap_days=30,
    min_episodes=4,
    share_ratio_min=3.0,
    zero_share_numerator=0.5,
)


def test_both_criteria_give_a_candidate_signal() -> None:
    verdict = decide(4, (12, 50), (1, 41), True, CRITERIA)
    assert verdict.label == CANDIDATE and verdict.criterion_a and verdict.criterion_b
    assert verdict.ratio == pytest.approx((12 / 50) / (1 / 41))


def test_one_episode_short_is_no_robust_signal() -> None:
    verdict = decide(3, (12, 50), (1, 41), True, CRITERIA)
    assert verdict.label == NO_SIGNAL and verdict.criterion_a is False
    assert "3 episode(s)" in verdict.reasons[0]


def test_exactly_three_times_the_control_is_enough() -> None:
    verdict = decide(4, (3, 50), (1, 50), True, CRITERIA)
    assert verdict.ratio == pytest.approx(3.0) and verdict.criterion_b


def test_a_quiet_control_counts_as_half_a_scene() -> None:
    verdict = decide(4, (2, 40), (0, 50), True, CRITERIA)
    assert verdict.control_share == pytest.approx(0.5 / 50)
    assert verdict.ratio == pytest.approx((2 / 40) / 0.01) and verdict.label == CANDIDATE


@pytest.mark.parametrize(
    ("target", "control", "rain", "reason"),
    [
        ((0, 0), (1, 41), True, "the target has no scored scene"),
        ((5, 40), (0, 0), True, "the control has no scored scene"),
        ((5, 40), (1, 41), False, "rain is unavailable"),
    ],
)
def test_missing_inputs_are_not_computable(
    target: tuple[int, int], control: tuple[int, int], rain: bool, reason: str
) -> None:
    verdict = decide(9, target, control, rain, CRITERIA)
    assert verdict.label == NOT_COMPUTABLE and verdict.criterion_a is None
    assert any(reason in r for r in verdict.reasons)


@pytest.mark.parametrize(
    ("n", "k", "expected"),
    [
        (46, 4, 0.024),
        (60, 4, 0.056),
        (70, 4, 0.088),
        (46, 3, 0.098),
        (60, 3, 0.175),
        (70, 3, 0.237),
    ],
)
def test_binomial_tails_match_the_method(n: int, k: int, expected: float) -> None:
    assert binomial_tail(n, 0.024, k) == pytest.approx(expected, abs=0.0006)
    assert binomial_tail(n, 0.024, 0) == 1.0
    assert math.isnan(binomial_tail(n, 1.5, k))
