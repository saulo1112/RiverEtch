from datetime import date
from pathlib import Path

import numpy as np
import pytest
from synthetic import draw, frequency, scl_scene

from climate_pipeline.screening.config import load_screening_config
from climate_pipeline.screening.mask import RiverGeometry, derive_geometry
from climate_pipeline.screening.stage1 import (
    classify_scene,
    longest_gap_days,
    measure_scene,
    month_keys,
)

CONFIG = load_screening_config(Path(__file__).parents[1] / "screening.yaml")


def straight_river() -> tuple[np.ndarray, RiverGeometry]:
    river = np.zeros((300, 1000), dtype=bool)
    draw(river, [(150, 10), (150, 990)], half=4)
    geom = derive_geometry(
        frequency(river),
        resolution=20.0,
        thresholds=(0.5,),
        upstream=(150, 12),
        downstream=(150, 988),
        center=(150, 500),
        confluences={},
        excluded=None,
        snap_radius_m=1500,
        corridor_half_width_m=600,
        erosion_px_10m=1,
        land_ring_m=(100, 400),
        subreach=CONFIG.subreach,
    )
    assert geom.failed is None
    return river, geom


def test_clean_scene_is_clear_and_observable() -> None:
    river, geom = straight_river()
    sub = measure_scene(scl_scene(river), geom, CONFIG)
    assert set(sub) == {"upstream", "downstream"}
    m = sub["upstream"]
    # 2 km x 9 px of 20 m = ~900 px of 20 m = ~3600 10 m pixels.
    assert m.water_px_10m == pytest.approx(3600, rel=0.1)
    assert m.valid_px_10m == m.water_px_10m
    assert m.contamination == 0 and m.data_coverage == 1
    assert classify_scene(sub, CONFIG) == (True, True, True)


def test_turbid_water_labelled_soil_is_observable_but_not_clear() -> None:
    river, geom = straight_river()
    sub = measure_scene(scl_scene(river, river_class=5), geom, CONFIG)
    assert sub["upstream"].water_px_10m == 0
    assert classify_scene(sub, CONFIG) == (False, True, True)


def test_cloud_over_the_river_only_is_flagged_as_possibly_turbid_water() -> None:
    river, geom = straight_river()
    flagged = scl_scene(river, river_class=9)  # "cloud" exactly on the river, land clear
    m = measure_scene(flagged, geom, CONFIG)["upstream"]
    assert m.suspect_turbid_as_cloud and m.contamination == 1
    cloudy = scl_scene(river, cloud=(slice(0, 300), slice(0, 1000)))
    assert not measure_scene(cloudy, geom, CONFIG)["upstream"].suspect_turbid_as_cloud


def test_partial_coverage_fails_the_coverage_rule() -> None:
    river, geom = straight_river()
    up = geom.subreaches[0]
    cols = np.nonzero(up.mask.any(axis=0))[0]
    half = slice(int(cols[0]), int((cols[0] + cols[-1]) // 2))
    sub = measure_scene(scl_scene(river, nodata_cols=half), geom, CONFIG)
    assert sub["upstream"].data_coverage == pytest.approx(0.5, abs=0.05)
    assert classify_scene(sub, CONFIG) == (False, False, False)


def test_cloud_contamination_over_20_percent_is_not_clear() -> None:
    river, geom = straight_river()
    up = geom.subreaches[0]
    _, cols = np.nonzero(up.mask)
    cut = int(np.percentile(cols, 30))
    scl = scl_scene(river, cloud=(slice(0, 300), slice(int(cols.min()), cut)))
    sub = measure_scene(scl, geom, CONFIG)
    assert sub["upstream"].contamination > 0.2
    assert classify_scene(sub, CONFIG)[0] is False


def test_gap_and_month_helpers() -> None:
    start, end = date(2022, 1, 1), date(2022, 12, 31)
    assert longest_gap_days([], start, end) == 365
    assert longest_gap_days([date(2022, 1, 1), date(2022, 12, 31)], start, end) == 363
    assert longest_gap_days([date(2022, 3, 1)], start, end) == 305
    keys = month_keys(date(2022, 1, 1), date(2025, 12, 31))
    assert len(keys) == 48 and keys[0] == "2022-01" and keys[-1] == "2025-12"
