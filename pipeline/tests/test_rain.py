import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
import pytest

from climate_pipeline.screening.rain import OpenMeteoClient, RainSeries, rain_context, rainy_months


def hourly_payload(start: datetime, hours: int, value: float | None = 1.0) -> dict[str, object]:
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)]
    return {"hourly": {"time": times, "precipitation": [value] * hours}}


def series(start: datetime, values: list[float]) -> RainSeries:
    ends = np.array(
        [
            np.datetime64((start + timedelta(hours=h + 1)).replace(tzinfo=None), "h")
            for h in range(len(values))
        ]
    )
    return RainSeries("center", -76.6, 5.7, ends, np.array(values, dtype=np.float64))


def test_client_requests_utc_hourly_rain_and_caches(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    start = datetime(2023, 1, 1, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=hourly_payload(start, 48))

    client = OpenMeteoClient(
        "https://archive.test/v1/archive",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_dir=tmp_path,
    )
    rain = client.hourly("center", -76.65, 5.69, date(2023, 1, 1), date(2023, 1, 2))
    again = client.hourly("center", -76.65, 5.69, date(2023, 1, 1), date(2023, 1, 2))
    assert len(seen) == 1
    params = dict(seen[0].url.params)
    assert params["hourly"] == "precipitation"
    assert params["timezone"] == "UTC"
    assert params["latitude"] == "5.69" and params["longitude"] == "-76.65"
    # Open-Meteo stamps the hour's start; the series stores the hour's end.
    assert str(rain.times[0]) == "2023-01-01T01"
    assert np.array_equal(rain.mm, again.mm)
    assert (
        json.loads(next(tmp_path.glob("*.json")).read_text())["hourly"]["time"][0]
        == "2023-01-01T00:00"
    )


def test_window_sums_end_at_the_acquisition_hour() -> None:
    start = datetime(2023, 1, 1, tzinfo=UTC)
    rain = series(start, [1.0] * 24 * 10)
    at = datetime(2023, 1, 8, 15, 36, tzinfo=UTC)
    assert rain.window_sum(at, 24) == 24
    assert rain.window_sum(at, 72) == 72
    # 15:36 UTC is 10:36 in Bogota: ten whole hours since local midnight.
    assert rain.same_day(at, "America/Bogota") == 10
    assert np.isnan(rain.window_sum(datetime(2023, 1, 1, 5, tzinfo=UTC), 24))


def test_missing_hours_make_a_window_unknown() -> None:
    start = datetime(2023, 1, 1, tzinfo=UTC)
    values = [1.0] * 100
    values[60:70] = [np.nan] * 10
    rain = series(start, values)
    assert np.isnan(rain.window_sum(start + timedelta(hours=72), 72))
    assert rain.window_sum(start + timedelta(hours=100), 24) == 24


def test_daily_totals_use_local_days() -> None:
    start = datetime(2023, 1, 1, 5, tzinfo=UTC)  # local midnight in Bogota
    rain = series(start, [1.0] * 48)
    daily = rain.daily("America/Bogota")
    assert daily == {date(2023, 1, 1): 24.0, date(2023, 1, 2): 24.0}


def test_rainy_months_are_those_above_the_median() -> None:
    daily = {}
    day = date(2022, 1, 1)
    while day <= date(2023, 12, 31):
        daily[day] = 10.0 if day.month in (4, 5, 10, 11) else 1.0
        day += timedelta(days=1)
    assert rainy_months(daily) == (4, 5, 10, 11)
    assert rainy_months({date(2022, 1, 1): 3.0}) == ()


def test_rain_context_takes_the_wettest_point() -> None:
    start = datetime(2023, 1, 1, tzinfo=UTC)
    center = series(start, [0.0] * 200)
    upstream = RainSeries("upstream", -76.5, 5.8, center.times, np.full(200, 0.5))
    ctx = rain_context([center, upstream], start + timedelta(hours=150), (24, 72), "America/Bogota")
    assert ctx.sums_mm["center"][72] == 0
    assert ctx.max_over_points(72) == pytest.approx(36)
