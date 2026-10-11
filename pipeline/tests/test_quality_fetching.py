import math
from pathlib import Path

import pytest

from climate_pipeline.calibration.stations import Candidate
from climate_pipeline.quality.fetching import DiskBudgetError, check_disk, distance_km, flow_link

LABELS = ("Q_MEDIA_D", "NV_MEDIA_D")
CATALOG = [
    {"Codigo": "0023187010", "Longitud": "-73.89", "Latitud": "7.35"},  # the point's own station
    {"Codigo": "0023187060", "Longitud": "-73.90", "Latitud": "7.40"},  # 5.6 km north
    {"Codigo": "0023207040", "Longitud": "-73.90", "Latitud": "7.47"},  # 13 km north
]


def point(name: str, lon: float = -73.90, lat: float = 7.35) -> Candidate:
    return Candidate("x", name, lon, lat, "quality point", quality_point=name)


def test_distance_is_great_circle() -> None:
    assert round(distance_km(-74.0, 7.0, -74.0, 8.0), 1) == 111.2


def test_a_point_prefers_its_own_discharge_then_its_own_level() -> None:
    files = {"Q_MEDIA_D": {"0023187010": 10}, "NV_MEDIA_D": {"0023187010": 10}}
    link = flow_link(point("PTO. WILCHES [23187010]"), CATALOG, files, LABELS, 10)
    assert (link.code, link.label, link.km) == ("0023187010", "Q_MEDIA_D", 0.0)
    level_only = {"NV_MEDIA_D": {"0023187010": 10}}
    assert flow_link(point("PTO [23187010]"), CATALOG, level_only, LABELS, 10).label == "NV_MEDIA_D"


def test_without_its_own_series_the_nearest_station_within_reach_is_used() -> None:
    files = {"NV_MEDIA_D": {"0023187060": 1}, "Q_MEDIA_D": {"0023207040": 1}}
    link = flow_link(point("NO CODE"), CATALOG, files, LABELS, 10)
    assert link.code == "0023187060" and link.label == "NV_MEDIA_D" and 5 < link.km < 6
    far = flow_link(point("NO CODE"), CATALOG, {"Q_MEDIA_D": {"0023207040": 1}}, LABELS, 10)
    assert far.code == "" and math.isnan(far.km)


def test_the_disk_guard_refuses_to_go_on_under_the_budget(tmp_path: Path) -> None:
    assert check_disk(tmp_path, 0.001) > 0
    with pytest.raises(DiskBudgetError, match="must stay free"):
        check_disk(tmp_path, 1e9)


def test_streams_are_queried_by_every_accented_spelling() -> None:
    import httpx

    from climate_pipeline.quality.fetching import stream_points, stream_spellings

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        where = request.url.params.get("$where", "")
        seen.append(where)
        if "corriente in" not in where:
            return httpx.Response(200, json=[{"corriente": "SINÚ", "n": "5"},
                                             {"corriente": "Sinu ", "n": "1"},
                                             {"corriente": "MAGDALENA", "n": "9"}])  # fmt: skip
        return httpx.Response(200, json=[
            {"nombre_del_punto_de_monitoreo": "P", "corriente": "SINÚ", "n": "3"},
            {"nombre_del_punto_de_monitoreo": "Q", "corriente": "SINU VIEJO", "n": "2"},
        ])  # fmt: skip

    client = httpx.Client(transport=httpx.MockTransport(handler))
    spellings, _ = stream_spellings(client, "https://soda.example", "2015-07-01")
    assert spellings["SINU"] == ["SINÚ", "Sinu "] and spellings["MAGDALENA"] == ["MAGDALENA"]
    rows, _ = stream_points(client, "https://soda.example", ["TURBIDEZ"], "2015-07-01", "SINU",
                            spellings["SINU"])  # fmt: skip
    assert [r["nombre_del_punto_de_monitoreo"] for r in rows] == ["P"]
    assert "corriente in ('SINÚ', 'Sinu ')" in seen[-1]
    assert stream_points(client, "https://soda.example", ["T"], "x", "NECHI", []) == ([], b"[]")
