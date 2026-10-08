import math
from datetime import UTC, date, datetime, timedelta

import httpx
import numpy as np
import pytest

from climate_pipeline.screening.rain import RainSeries, rain_context
from climate_pipeline.validation.catchment import (
    CellSeries,
    catchment_flags,
    fetch_grid,
    hour_ends,
    point_flags,
    point_values,
    thresholds,
    union,
    window_sums,
)
from climate_pipeline.validation.config import Window

START = datetime(2023, 1, 1, tzinfo=UTC)


def series(values: list[float], label: str = "p") -> RainSeries:
    ends = np.array(
        [
            np.datetime64((START + timedelta(hours=h + 1)).replace(tzinfo=None), "h")
            for h in range(len(values))
        ]
    )
    return RainSeries(label, -76.0, 8.0, ends, np.array(values, dtype=np.float64))


def test_window_sums_match_the_screening_window_sum() -> None:
    rng = np.random.default_rng(1)
    values = list(rng.gamma(0.3, 2.0, 24 * 30))
    for k in range(200, 230):
        values[k] = math.nan  # a gap of 30 hours
    rain = series(values)
    moments = [START + timedelta(hours=h, minutes=37) for h in range(0, 24 * 30, 7)]
    ends = hour_ends(moments)
    for hours in (24, 72, 168):
        fast = window_sums(rain, ends, hours)
        slow = [rain.window_sum(m, hours) for m in moments]
        assert all(
            (math.isnan(a) and math.isnan(b)) or a == pytest.approx(b)
            for a, b in zip(fast, slow, strict=True)
        )


def test_the_point_rule_takes_the_wettest_point_and_keeps_unknowns() -> None:
    wet = series([1.0] * 200, "wet")
    dry = series([0.0] * 200, "dry")
    missing = series([math.nan] * 200, "gap")
    moments = [START + timedelta(hours=100), START + timedelta(hours=10)]
    values = point_values([dry, wet, missing], moments, 72)
    ctx = rain_context([dry, wet, missing], moments[0], (72,), "America/Bogota")
    assert values[0] == pytest.approx(ctx.max_over_points(72)) == pytest.approx(72.0)
    assert math.isnan(values[1])  # not enough hours before the series starts
    assert point_flags(values, 20.0) == [True, None]
    assert point_flags(np.array([20.0]), 20.0) == [False]


def cell(values: list[float], name: str) -> CellSeries:
    return CellSeries((name,), -76.0, 8.0, series(values, name))


def test_thresholds_are_percentiles_of_daily_values() -> None:
    hours = 24 * 40
    rng = np.random.default_rng(3)
    cells = [
        cell(list(rng.gamma(0.4, 1.5, hours)), "a"),
        cell(list(rng.gamma(0.4, 1.5, hours)), "b"),
    ]
    period = Window(start=date(2023, 1, 9), end=date(2023, 2, 8))
    limits = thresholds(cells, period, 15, (24, 72), ("mean", "max"), 90)
    assert set(limits.values) == {("mean", 24), ("max", 24), ("mean", 72), ("max", 72)}
    assert all(n == 31 for n in limits.days.values())
    daily = [START.replace(day=1) + timedelta(days=8 + d, hours=15) for d in range(31)]
    sums = np.vstack([window_sums(c.series, hour_ends(daily), 24) for c in cells])
    assert limits.values[("mean", 24)] == pytest.approx(np.percentile(sums.mean(axis=0), 90))
    assert 0.1 <= limits.day_share_flagged <= 0.4


def test_catchment_flags_are_unknown_only_when_nothing_is_flagged() -> None:
    hours = 24 * 20
    storm = [0.0] * hours
    for h in range(300, 310):
        storm[h] = 10.0
    cells = [cell(storm, "a"), cell([0.0] * (hours - 100) + [math.nan] * 100, "b")]
    period = Window(start=date(2023, 1, 9), end=date(2023, 1, 14))
    limits = thresholds(cells, period, 15, (24,), ("max",), 90)
    moments = [
        START + timedelta(hours=305),
        START + timedelta(hours=200),
        START + timedelta(hours=470),
    ]
    flags, stats = catchment_flags(cells, moments, limits, (24,), ("max",))
    assert flags[1] is False
    assert math.isnan(stats[("max", 24)][2]) and flags[2] is None
    # The storm's 24-hour maximum (50 mm) reaches the threshold (the 90th percentile of the
    # daily values 0, 0, 0, 0, 40 and 60 mm is 50 mm).
    assert limits.values[("max", 24)] == pytest.approx(50.0)
    assert flags[0] is True


def test_the_union_rule() -> None:
    assert union(True, False, True) == "yes"
    assert union(False, True, True) == "yes"
    assert union(False, None, True) == "unknown"
    assert union(None, False, True) == "unknown"
    assert union(False, False, True) == "no"
    assert union(False, None, False) == "no"  # grid unbuildable: point rule only


def open_meteo(calls: list[httpx.Request], fail_first: int = 0) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) <= fail_first:
            return httpx.Response(429, headers={"retry-after": "7"})
        lat = float(request.url.params["latitude"])
        lon = float(request.url.params["longitude"])
        times = [(START + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(48)]
        return httpx.Response(
            200,
            json={
                "latitude": round(lat * 4) / 4,
                "longitude": round(lon * 4) / 4,
                "hourly": {"time": times, "precipitation": [0.5] * 48},
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_grid_points_in_one_open_meteo_cell_are_merged(tmp_path: object) -> None:
    calls: list[httpx.Request] = []
    sleeps: list[float] = []
    points = [("g01", -76.25, 7.25), ("g02", -76.20, 7.27), ("g03", -76.0, 7.5)]
    cells = fetch_grid(
        points,
        "https://archive.test",
        date(2023, 1, 1),
        date(2023, 1, 2),
        None,
        2.0,
        6,
        http=open_meteo(calls, fail_first=1),
        sleep=sleeps.append,
    )
    assert [c.point_ids for c in cells] == [("g01", "g02"), ("g03",)]
    assert (cells[0].cell_lon, cells[0].cell_lat) == (-76.25, 7.25)
    assert sleeps[0] == 7.0  # the server's Retry-After after a 429
    assert sleeps.count(2.0) == 3 and len(calls) == 4


def test_cached_responses_are_not_requested_again(tmp_path: object) -> None:
    from pathlib import Path

    cache = Path(str(tmp_path))
    calls: list[httpx.Request] = []
    sleeps: list[float] = []
    for _ in range(2):
        fetch_grid(
            [("g01", -76.25, 7.25)],
            "https://archive.test",
            date(2023, 1, 1),
            date(2023, 1, 2),
            cache,
            2.0,
            6,
            http=open_meteo(calls),
            sleep=sleeps.append,
        )
    assert len(calls) == 1 and sleeps == [2.0]


def test_prefetched_rain_is_what_the_stage1_client_reads(tmp_path: object) -> None:
    from pathlib import Path

    from climate_pipeline.screening.rain import OpenMeteoClient
    from climate_pipeline.validation.catchment import fetch_hourly

    cache = Path(str(tmp_path))
    calls: list[httpx.Request] = []
    fetch_hourly(
        open_meteo(calls),
        "https://archive.test",
        -76.16783,
        8.06216,
        date(2023, 1, 1),
        date(2023, 1, 2),
        cache,
        3,
    )

    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the stage-1 client should read the cache")

    client = OpenMeteoClient(
        "https://archive.test",
        http=httpx.Client(transport=httpx.MockTransport(refuse)),
        cache_dir=cache,
    )
    rain = client.hourly("center", -76.16783, 8.06216, date(2023, 1, 1), date(2023, 1, 2))
    assert len(calls) == 1 and rain.mm.size == 48
