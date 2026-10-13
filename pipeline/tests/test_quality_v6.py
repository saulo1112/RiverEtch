import math
from datetime import UTC, datetime, timedelta

import pytest

from climate_pipeline.quality import v6, variables


def test_a_sample_time_turns_its_local_zone_into_utc() -> None:
    row = {"date": "2024-07-02", "time": "10:30:00", "zone": "CDT"}
    assert variables.sample_time(row) == datetime(2024, 7, 2, 15, 30, tzinfo=UTC)
    assert variables.sample_time({**row, "zone": "XYZ"}) is None
    assert variables.sample_time({**row, "time": ""}) is None


def test_the_hydrological_year_starts_in_december() -> None:
    assert v6.hydro_year(datetime(2023, 12, 1, tzinfo=UTC)) == 2024
    assert v6.hydro_year(datetime(2024, 11, 30, tzinfo=UTC)) == 2024


def pair(k: int, turbidity: float, ssc: float, discharge: float = math.nan) -> v6.RatingPair:
    when = datetime(2019, 1, 1, tzinfo=UTC) + timedelta(days=200 * k)
    return v6.RatingPair("S", when, ssc, turbidity, discharge)


def test_a_power_rating_is_recovered_with_no_smearing_for_exact_data() -> None:
    pairs = [pair(k, t, 2.0 * t**1.1) for k, t in enumerate([5, 10, 20, 40, 80, 160])]
    rating = v6.fit_rating(pairs, with_discharge=False)
    assert rating is not None
    assert rating.coefficients[1] == pytest.approx(1.1)
    assert rating.smearing == pytest.approx(1.0)
    assert rating.predict(30.0) == pytest.approx(2.0 * 30**1.1)
    assert math.isnan(rating.predict(0.0))
    assert v6.fit_rating(pairs[:2], with_discharge=False) is None


def test_leave_one_year_out_never_sees_the_estimated_year() -> None:
    pairs = [pair(k, t, 2.0 * t) for k, t in enumerate([5, 10, 20, 40, 80, 160, 320, 640])]
    est = v6.loyo(pairs, with_discharge=False)
    assert all(e == pytest.approx(p.ssc) for e, p in zip(est, pairs, strict=True))


def test_the_chain_sums_both_links_errors() -> None:
    q05, q95 = v6.chain_quantiles([0.0], [-0.2, 0.0, 0.2])
    assert q05 == pytest.approx(-0.18) and q95 == pytest.approx(0.18)
    assert all(math.isnan(q) for q in v6.chain_quantiles([], [0.1]))


def lock(**over: float) -> dict[str, float]:
    return {"n": 30.0, "mdsa": 20.0, "sspb": 5.0, "rho_low": 0.6, **over}


def test_the_ssc_chain_is_estimated_at_best_and_needs_a_good_turbidity_card() -> None:
    assert v6.ssc_level("validated", lock(), 2, 60.0, 2.0) == "estimated"
    assert v6.ssc_level("indicative", lock(), 2, 60.0, 2.0) == "indicative"
    assert v6.ssc_level("validated", lock(mdsa=40.0), 2, 60.0, 2.0) == "indicative"
    assert v6.ssc_level("validated", lock(), 2, 60.0, 3.5) == "indicative"
    assert v6.ssc_level("validated", lock(n=10.0, rho_low=0.1), 2, 60.0, 2.0) == "none"


def temp(**over: float) -> dict[str, float]:
    return {"n": 40.0, "mae": 1.0, "bias": 0.3, "coverage90": 0.9, "rho_low": 0.9, **over}


def test_water_temperature_levels_follow_the_preregistered_thresholds() -> None:
    assert v6.temperature_level(temp(), 3, 3.0, 2.5) == "validated"
    assert v6.temperature_level(temp(mae=2.0), 3, 3.0, 2.5) == "estimated"
    assert v6.temperature_level(temp(mae=2.0), 3, 1.9, 2.5) == "indicative"
    assert v6.temperature_level(temp(coverage90=0.7), 3, 3.0, 2.5) == "indicative"
    assert v6.temperature_level(temp(), 3, 3.0, 5.0) == "indicative"
    assert v6.temperature_level(temp(n=5.0, rho_low=0.1), 3, 3.0, 2.5) == "none"


def test_the_climatology_wraps_around_the_new_year() -> None:
    train = [v6.ThermalPair(datetime(2020, 12, 28, tzinfo=UTC), 1.0, 2.0, 20),
             v6.ThermalPair(datetime(2021, 7, 1, tzinfo=UTC), 25.0, 26.0, 20)]  # fmt: skip
    assert v6.climatology(train, datetime(2022, 1, 5, tzinfo=UTC)) == pytest.approx(2.0)
    assert math.isnan(v6.climatology(train, datetime(2022, 4, 1, tzinfo=UTC)))
    est = v6.thermal_predict("W1", train, train)
    assert est == [1.0, 25.0]
