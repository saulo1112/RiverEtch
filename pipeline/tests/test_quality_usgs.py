import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from climate_pipeline.calibration.fetching import _csv
from climate_pipeline.quality import usgs
from climate_pipeline.quality import usgs as usgs_pilot
from climate_pipeline.sources import usgs as usgs_source


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


def test_a_checkpoint_round_trips_window_rows_and_skips_a_cut_line(tmp_path: Path) -> None:
    rows = [{"station": "USGS-1", "key": "k1", "window": "300m", "valid_px": 42,
             "b11_median": 0.0123456789, "glint_share": math.nan, "bands_read": 1.0,
             "b11_ok": 1.0, "selected": True, "B04": 0.25}]  # fmt: skip
    path = tmp_path / "USGS-1-windows.jsonl"
    path.write_text(json.dumps({"key": "k1", "rows": rows}, default=str) + '\n{"key": "k2", "ro',
                    encoding="utf-8")  # fmt: skip
    kept = usgs_pilot.checkpoint(path)
    assert list(kept) == ["k1"]
    columns = list(rows[0])
    assert _csv(kept["k1"], columns) == _csv(rows, columns)


def test_cached_turbidity_bodies_parse_like_fresh_ones(tmp_path: Path) -> None:
    body = json.dumps({"features": [{"properties": {
        "time": "2024-01-01T16:00:00+00:00", "value": "12.5", "approval_status": "Approved",
        "qualifier": None}}]}).encode()  # fmt: skip
    saved = tmp_path / "k.json"
    usgs_pilot.keep_bodies(saved, [body])
    cached = usgs_pilot.cached_bodies(saved)
    assert cached == [body]
    assert usgs_source.readings_from_bodies(cached)[0].value == 12.5
    saved.write_text('["cut', encoding="utf-8")
    assert usgs_pilot.cached_bodies(saved) is None


def test_an_overpass_file_can_point_to_its_batch_response(tmp_path: Path) -> None:
    body = b'{"features": []}'
    usgs_pilot.keep_bodies(tmp_path / "batch-1.json", [body])
    (tmp_path / "k.json").write_text(json.dumps({"batch": "batch-1.json"}), encoding="utf-8")
    assert usgs_pilot.cached_bodies(tmp_path / "k.json") == [body]
    (tmp_path / "lost.json").write_text(json.dumps({"batch": "gone.json"}), encoding="utf-8")
    assert usgs_pilot.cached_bodies(tmp_path / "lost.json") is None
