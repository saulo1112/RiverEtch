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
