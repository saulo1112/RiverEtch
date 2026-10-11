from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from climate_pipeline.quality import usgs


@dataclass(frozen=True)
class Acq:
    key: str
    datetime: datetime


def test_candidate_sites_join_series_and_large_locations() -> None:
    series = [
        {"properties": {"monitoring_location_id": "USGS-1", "begin": "2010-01-01",
                        "end": "2020-06-30"}},
        {"properties": {"monitoring_location_id": "USGS-1", "begin": "2021-01-01",
                        "end": "2026-01-01"}},
        {"properties": {"monitoring_location_id": "USGS-2", "begin": "2001-01-01",
                        "end": "2015-01-01"}},  # ends before the period
    ]  # fmt: skip
    locations: list[dict[str, Any]] = [
        {"properties": {"id": "USGS-1", "monitoring_location_name": "MISS R AT X",
                        "drainage_area": 90000.0},
         "geometry": {"coordinates": [-91.0, 30.0]}},
        {"properties": {"id": "USGS-2", "monitoring_location_name": "Ohio River at Y"},
         "geometry": {"coordinates": [-85.0, 38.0]}},
    ]  # fmt: skip
    rows = usgs.candidate_sites(series, locations, date(2018, 12, 1), date(2026, 9, 30))
    assert [r["site_id"] for r in rows] == ["USGS-1"]
    assert rows[0]["river"] == "MISSISSIPPI" and rows[0]["series_begin"] == "2010-01-01"
    assert rows[0]["series_end"] == "2026-01-01" and rows[0]["lon"] == -91.0


def test_the_draw_takes_one_acquisition_of_each_year_in_turn() -> None:
    acqs = [Acq(f"k{y}{m}", datetime(y, m, 1, tzinfo=UTC)) for y in (2019, 2020, 2021)
            for m in (1, 2, 3)]  # fmt: skip
    order = usgs.draw_order(acqs, 7)  # type: ignore[arg-type]
    assert [a.datetime.year for a in order] == [2019, 2020, 2021] * 3
    assert sorted(a.key for a in order) == sorted(a.key for a in acqs)
    assert order == usgs.draw_order(list(reversed(acqs)), 7)  # type: ignore[arg-type]
    assert order != usgs.draw_order(acqs, 8)  # type: ignore[arg-type]


def test_a_clear_scene_passes_every_guard_of_its_300m_window() -> None:
    good = {"window": "300m", "bands_read": 1.0, "valid_px": 40.0, "contamination": 0.1,
            "b11_ok": 1.0}  # fmt: skip
    assert usgs.clear([{"window": "core", "bands_read": 0.0}, good], 20, 0.2)
    assert not usgs.clear([{**good, "valid_px": 10.0}], 20, 0.2)
    assert not usgs.clear([{**good, "b11_ok": 0.0}], 20, 0.2)
    assert not usgs.clear([{**good, "bands_read": 0.0}], 20, 0.2)
    assert not usgs.clear([{**good, "window": "core"}], 20, 0.2)
