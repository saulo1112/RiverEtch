import math
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from climate_pipeline.sources import usgs

T0 = datetime(2023, 6, 1, 16, 30, tzinfo=UTC)


def reading(minutes: int, value: float, approval: str = "Approved",
            qualified: bool = False) -> usgs.Reading:  # fmt: skip
    return usgs.Reading(T0 + timedelta(minutes=minutes), value, approval, qualified)


def test_river_groups_from_site_names() -> None:
    assert usgs.river_group("Mississippi River at Baton Rouge, LA") == "MISSISSIPPI"
    assert usgs.river_group("MISS R AT AUX LOCK 14 (DS) AT PLEASANT VALLEY") == "MISSISSIPPI"
    assert usgs.river_group("KANSAS R AT WAMEGO, KS") == "KANSAS"
    assert usgs.river_group("RED RIVER OF THE NORTH AT GRAND FORKS, ND") == "RED"
    assert usgs.river_group("Platte River near Ashland, Nebr.") == "PLATTE"


def test_overpass_value_prefers_the_median_of_approved_values() -> None:
    readings = [reading(-15, 80.0), reading(0, 100.0), reading(15, 90.0), reading(5, 999.0,
                approval="Provisional"), reading(10, 999.0, qualified=True)]  # fmt: skip
    assert usgs.overpass_value(readings, T0, 30, 60) == (90.0, "median 30 min", 3)


def test_overpass_value_falls_back_to_the_nearest_within_an_hour() -> None:
    readings = [reading(-50, 70.0), reading(45, 60.0)]
    assert usgs.overpass_value(readings, T0, 30, 60) == (60.0, "nearest 60 min", 1)
    value, rule, n = usgs.overpass_value([reading(90, 1.0)], T0, 30, 60)
    assert math.isnan(value) and rule == "none" and n == 0


def test_parse_readings_and_samples() -> None:
    rows: list[dict[str, Any]] = [
        {"time": "2023-06-01T17:00:00+00:00", "value": "86.6", "approval_status": "Approved",
         "qualifier": None},
        {"time": "2023-06-01T17:15:00+00:00", "value": "x"},
    ]  # fmt: skip
    parsed = usgs.parse_readings(rows)
    assert len(parsed) == 1 and parsed[0].value == 86.6 and not parsed[0].qualified
    body = (b"Activity_StartDate,Activity_StartTime,Activity_StartTimeZone,Result_Measure,"
            b"Result_MeasureUnit,Result_MeasureStatusIdentifier\n"
            b"2023-02-01,10:00:00,CST,412,mg/L,Accepted\n"
            b"2023-03-01,10:00:00,CST,,mg/L,\n")  # fmt: skip
    assert usgs.parse_samples(body) == [{"date": "2023-02-01", "time": "10:00:00", "zone": "CST",
                                         "value": "412", "unit": "mg/L",
                                         "status": "Accepted"}]  # fmt: skip


def test_features_follow_next_links_and_retry_rate_limits() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0.01"})
        if "page=2" in str(request.url):
            return httpx.Response(200, json={"features": [{"id": 2}], "links": []})
        return httpx.Response(200, json={"features": [{"id": 1}], "links": [
            {"rel": "next", "href": "https://api.example/items?page=2"}]})  # fmt: skip

    client = httpx.Client(transport=httpx.MockTransport(handler))
    found, bodies = usgs.features(client, "https://api.example/items", {"limit": "1"})
    assert [f["id"] for f in found] == [1, 2] and len(bodies) == 2 and len(calls) == 3
