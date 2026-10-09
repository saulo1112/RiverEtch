import math

import numpy as np
import pytest

from climate_pipeline.calibration import stats


def test_mdsa_and_sspb_are_symmetric_in_log_space() -> None:
    observed = [10.0, 10.0, 10.0]
    assert stats.mdsa([20.0, 20.0, 20.0], observed) == pytest.approx(100.0)
    assert stats.mdsa([5.0, 5.0, 5.0], observed) == pytest.approx(100.0)  # halving = doubling
    assert stats.sspb([20.0, 20.0, 20.0], observed) == pytest.approx(100.0)
    assert stats.sspb([5.0, 5.0, 5.0], observed) == pytest.approx(-100.0)
    assert stats.mape([5.0], [10.0]) == pytest.approx(50.0)  # MAPE is not symmetric
    assert math.isnan(stats.mdsa([0.0, -1.0], [1.0, 1.0]))


def test_rho_needed_reproduces_the_preregistered_table() -> None:
    expected = {15: 0.739, 20: 0.685, 30: 0.618, 33: 0.603, 40: 0.577}
    for n, rho in expected.items():
        assert stats.rho_needed(n, 0.3) == pytest.approx(rho, abs=0.001)
    assert math.isnan(stats.rho_needed(3, 0.3))


def test_block_bootstrap_is_reproducible_and_wider_than_the_pair_bootstrap() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(size=40)
    y = x + rng.normal(scale=0.8, size=40)
    # Duplicate every pair four times, as if one scene matched four samples.
    xs, ys = np.repeat(x, 4).tolist(), np.repeat(y, 4).tolist()
    clusters = np.repeat(np.arange(40), 4).tolist()
    a = stats.block_bootstrap_spearman(xs, ys, clusters, 500, 7)
    assert a == stats.block_bootstrap_spearman(xs, ys, clusters, 500, 7)
    naive = stats.block_bootstrap_spearman(xs, ys, list(range(160)), 500, 7)
    assert (a[1] - a[0]) > (naive[1] - naive[0])
    assert math.isnan(stats.block_bootstrap_spearman([1, 2], [1, 2], [0, 1], 10, 0)[0])


def test_chi2_and_kruskal_wallis_match_known_values() -> None:
    assert stats.chi2_sf(3.841459, 1) == pytest.approx(0.05, abs=1e-5)
    assert stats.chi2_sf(5.991465, 2) == pytest.approx(0.05, abs=1e-5)
    assert stats.chi2_sf(0.0, 3) == 1.0
    # Textbook example (three groups): H = 7.2 with no ties at n = 9 -> p = exp(-3.6).
    h, p = stats.kruskal_wallis([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    assert h == pytest.approx(7.2) and p == pytest.approx(math.exp(-3.6))
    assert math.isnan(stats.kruskal_wallis([[1.0, 2.0]])[0])


def test_partial_spearman_removes_a_common_driver() -> None:
    rng = np.random.default_rng(3)
    driver = rng.normal(size=300)
    x = driver + rng.normal(scale=0.3, size=300)
    y = driver + rng.normal(scale=0.3, size=300)
    assert stats.spearman(x.tolist(), y.tolist()) > 0.8
    assert abs(stats.partial_spearman(x.tolist(), y.tolist(), driver.tolist())) < 0.15


def test_block_permutation_detects_a_shift_and_respects_the_direction() -> None:
    blocks = [year for year in range(12) for _ in range(5)]
    labels = ["wet" if year % 2 else "dry" for year in blocks]
    values = [3.0 + 0.1 * k if label == "wet" else 0.1 * k for k, label in enumerate(labels)]
    diff, p = stats.block_permutation_p(values, labels, blocks, "wet", "dry", 999, 1, "greater")
    assert diff > 0 and p < 0.05
    _, p_less = stats.block_permutation_p(values, labels, blocks, "wet", "dry", 999, 1, "less")
    assert p_less > 0.5
    assert math.isnan(stats.block_permutation_p([1.0], ["a"], [0], "a", "b", 10, 0)[0])


def test_the_fast_spearman_equals_the_reference_with_ties() -> None:
    rng = np.random.default_rng(11)
    for _ in range(50):
        n = int(rng.integers(3, 60))
        x = rng.integers(0, 6, size=n).astype(float).tolist()
        y = (rng.integers(0, 4, size=n) + rng.normal(size=n).round(1)).tolist()
        fast, slow = stats.spearman(x, y), stats.spearman_reference(x, y)
        assert (math.isnan(fast) and math.isnan(slow)) or fast == pytest.approx(slow, abs=1e-12)
