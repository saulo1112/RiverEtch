"""v7 and v7.1: oxygen saturation, the power law, the linear candidates and the levels."""

import math
from datetime import UTC, datetime

import pytest

from climate_pipeline.quality import v7


@pytest.mark.parametrize(("t_c", "expected"), [(0.0, 14.621), (10.0, 11.288), (20.0, 9.092),
                                               (30.0, 7.559)])  # fmt: skip
def test_saturation_matches_the_usgs_table_at_one_atmosphere(t_c: float, expected: float) -> None:
    assert v7.saturation(t_c, 1.0) == pytest.approx(expected, abs=0.01)


def test_saturation_falls_with_pressure_and_the_standard_atmosphere() -> None:
    assert v7.pressure_at(0.0) == pytest.approx(1.0)
    assert v7.pressure_at(1000.0) == pytest.approx(0.887, abs=0.002)
    assert v7.saturation(20.0, v7.pressure_at(330.0)) < v7.saturation(20.0, 1.0)


def _pair(
    year: int, month: int, f: float, value: float, approval: str = "Approved"
) -> v7.SurfacePair:
    return v7.SurfacePair(datetime(year, month, 15, 17, tzinfo=UTC), f, f, value, approval)


def test_the_power_law_recovers_a_rating_and_abstains_outside_its_range() -> None:
    pairs = [_pair(2020, m, f, 10.0 * f**2) for m, f in enumerate((0.2, 0.3, 0.4, 0.5, 0.6), 1)]
    fit = v7.fit_power(pairs, "scl", harmonic=False)
    assert fit is not None
    assert fit.coefficients[1] == pytest.approx(2.0)
    assert fit.smearing == pytest.approx(1.0)
    assert fit.predict(0.45, pairs[0].time) == pytest.approx(10.0 * 0.45**2)
    assert math.isnan(fit.predict(0.7, pairs[0].time))  # outside the fitted range
    assert math.isnan(fit.predict(0.0, pairs[0].time))


def test_leave_one_year_out_never_uses_the_year_it_estimates() -> None:
    pairs = [_pair(y, 6, f, 5.0 * f) for y in (2019, 2020, 2021) for f in (0.2, 0.4, 0.6)]
    est = v7.loyo_power(pairs, "scl", harmonic=False)
    assert all(e == pytest.approx(p.value) for e, p in zip(est, pairs, strict=True))
    lonely = [*pairs, _pair(2022, 6, 0.9, 4.5)]
    assert math.isnan(v7.loyo_power(lonely, "scl", harmonic=False)[-1])  # 0.9 is never in training


def test_the_split_keeps_approved_values_for_training_and_the_lock_box() -> None:
    pairs = [_pair(2020, 5, 0.3, 1.0), _pair(2020, 6, 0.3, 1.0, "Provisional"),
             _pair(2024, 5, 0.3, 1.0), _pair(2026, 3, 0.3, 1.0, "Provisional")]  # fmt: skip
    train, lock, later = v7._split(pairs)
    assert [p.time.year for p in train] == [2020] and train[0].approval == "Approved"
    assert [p.time.year for p in lock] == [2024]
    assert [p.time.year for p in later] == [2026]


def test_linear_candidates_and_their_abstention() -> None:
    train = [v7.LinearPair(datetime(2020, m, 1, tzinfo=UTC), x, 2.0 + 0.5 * x, "Approved")
             for m, x in enumerate((8.0, 9.0, 10.0, 11.0), 1)]  # fmt: skip
    probe = [v7.LinearPair(datetime(2024, 1, 1, tzinfo=UTC), 10.5, 0.0, "Approved"),
             v7.LinearPair(datetime(2024, 2, 1, tzinfo=UTC), 12.0, 0.0, "Approved")]  # fmt: skip
    assert v7.linear_predict("O1", train, probe)[0] == pytest.approx(10.5)
    assert v7.linear_predict("O2", train, probe)[0] == pytest.approx(2.0 + 0.5 * 10.5)
    assert math.isnan(v7.linear_predict("O2", train, probe)[1])  # outside the training range
    assert v7.linear_predict("O0", train, probe, null=lambda _: 7.0) == [7.0, 7.0]


def _lock(**kw: float) -> dict[str, float]:
    return {"n": 24.0, "mdsa": 20.0, "sspb": 5.0, "coverage90": 0.9, "rho_low": 0.6,
            "mae": 0.5, "bias": 0.1, **kw}  # fmt: skip


def test_ratio_levels_follow_the_preregistered_thresholds() -> None:
    levels = v7.DISCHARGE_LEVELS
    assert v7.ratio_level(_lock(), 2, 60.0, 1.8, levels) == "validated"
    assert v7.ratio_level(_lock(), 1, 60.0, 1.8, levels) == "estimated"  # one year: not validated
    assert v7.ratio_level(_lock(mdsa=40.0), 2, 45.0, 1.8, levels) == "estimated"  # ratio > 0.8
    assert v7.ratio_level(_lock(mdsa=40.0), 2, 39.0, 1.8, levels) == "indicative"  # null wins
    assert v7.ratio_level(_lock(coverage90=0.7), 2, 60.0, 1.8, levels) == "indicative"
    assert v7.ratio_level(_lock(rho_low=0.1, mdsa=80.0), 2, 60.0, 1.8, levels) == "none"


def test_absolute_levels_follow_the_preregistered_thresholds() -> None:
    levels = v7.OXYGEN_LEVELS
    assert v7.absolute_level(_lock(), 2, 1.0, 1.2, levels) == "validated"
    assert v7.absolute_level(_lock(mae=1.0), 2, 1.1, 2.0, levels) == "estimated"
    assert v7.absolute_level(_lock(mae=1.0), 2, 0.9, 2.0, levels) == "indicative"


def test_daily_null_takes_the_median_within_fifteen_days() -> None:
    rows = [
        {"site_id": "S", "parameter": "00060", "day": "2020-06-01", "value": "100",
         "approval": "Approved", "qualified": "0"},
        {"site_id": "S", "parameter": "00060", "day": "2021-06-10", "value": "300",
         "approval": "Approved", "qualified": "0"},
        {"site_id": "S", "parameter": "00060", "day": "2021-06-11", "value": "900",
         "approval": "Approved", "qualified": "1"},
        {"site_id": "S", "parameter": "00060", "day": "2021-09-01", "value": "50",
         "approval": "Approved", "qualified": "0"},
    ]  # fmt: skip
    null = v7.daily_null(rows, "S", "00060", scale=2.0)
    assert null(datetime(2024, 6, 5, tzinfo=UTC)) == pytest.approx(400.0)  # median of 200 and 600
    assert math.isnan(null(datetime(2024, 1, 5, tzinfo=UTC)))
