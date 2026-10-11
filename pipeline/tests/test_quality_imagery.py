import math
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from climate_pipeline.calibration import extract
from climate_pipeline.calibration.config import load_calibration_config
from climate_pipeline.calibration.extract import StationGeometry
from climate_pipeline.quality import imagery
from climate_pipeline.quality.config import load_quality_config
from climate_pipeline.quality.values import Budget, near
from climate_pipeline.screening.rio import Grid
from climate_pipeline.screening.stac import AssetRef

PIPELINE = Path(__file__).parents[1]
CFG = load_quality_config(PIPELINE / "water-quality.yaml")


def pc_item(baseline: str) -> dict[str, Any]:
    assets = {band: {"href": f"https://example.blob/{band}.tif"}
              for band in ("B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12",
                           "SCL")}  # fmt: skip
    return {
        "id": "S2A_MSIL2A_20171230T152631_R025_T18NXP_20201014T172021",
        "bbox": [-74.0, 7.0, -73.0, 8.0],
        "properties": {
            "datetime": "2017-12-30T15:26:31Z",
            "platform": "Sentinel-2A",
            "s2:processing_baseline": baseline,
            "proj:epsg": 32618,
            "s2:mgrs_tile": "18NXP",
            "sat:relative_orbit": 25,
            "s2:mean_solar_zenith": 37.3,
        },
        "assets": assets,
    }


def test_planetary_computer_assets_take_d15s_logical_names() -> None:
    keys = imagery.logical_keys(CFG.imagery.sources["planetary-computer"])
    assert keys["red"] == "B04" and keys["nir08"] == "B8A" and keys["scl"] == "SCL"
    assert imagery.logical_keys(CFG.imagery.sources["earth-search"])["nir08"] == "nir08"


def test_esa_scaling_adds_the_offset_from_baseline_four() -> None:
    bare = AssetRef("h", None, None, 0, 32618)
    assert (imagery.esa_scaled(bare, 2.12).scale, imagery.esa_scaled(bare, 2.12).offset) == (
        1e-4, 0.0)  # fmt: skip
    assert imagery.esa_scaled(bare, 4.0).offset == -0.1
    carried = AssetRef("h", 2e-4, 0.5, 0, 32618)
    assert imagery.esa_scaled(carried, 5.1) is carried


def test_parse_scales_every_band_but_scl() -> None:
    scene = imagery.parse(pc_item("02.12"), "planetary-computer",
                          CFG.imagery.sources["planetary-computer"])  # fmt: skip
    assert set(scene.assets) >= {"red", "nir08", "swir16", "blue", "scl"}
    assert scene.assets["nir08"].scale == 1e-4 and scene.assets["nir08"].offset == 0.0
    assert scene.assets["scl"].scale is None
    assert scene.relative_orbit == 25 and scene.mgrs_tile == "18NXP"


def test_sun_zenith_reads_either_source() -> None:
    assert imagery.sun_zenith({"s2:mean_solar_zenith": 37.5}) == 37.5
    assert imagery.sun_zenith({"view:sun_elevation": 61.0}) == 29.0
    assert math.isnan(imagery.sun_zenith({}))


def test_the_small_300m_window_is_d15s_window() -> None:
    d15 = load_calibration_config(PIPELINE / "calibration.yaml")
    grid = Grid(32618, 20.0, 600000.0, 900000.0, 301, 301)
    main = np.zeros(grid.shape, dtype=bool)
    main[140:160, :] = True  # a 400 m wide river crossing the grid
    main[100:140, 150:154] = True  # a narrow side channel, eroded away
    geo = StationGeometry("s", grid, main, (150, 150), 0.0, 400.0, "scl", True, "")
    small = imagery.small_windows(geo, CFG)
    big = extract.station_windows(geo, d15)

    def absolute(windows: extract.Windows, name: str) -> set[tuple[float, float]]:
        rows, cols = np.nonzero(windows.masks[name])
        g = windows.grid
        return {
            (g.x0 + c * g.resolution, g.y0 - r * g.resolution)
            for r, c in zip(rows, cols, strict=True)
        }

    assert absolute(small, "300m") == absolute(big, "300m")
    assert absolute(small, "core") < absolute(small, "300m")


def test_scene_selection_and_network_budget() -> None:
    days = {date(2020, 1, 10)}
    assert near(date(2020, 1, 13), days, 3) and not near(date(2020, 1, 14), days, 3)
    budget = Budget(0.005)
    budget.add([{"source": "earth-search", "bands_read": 0.0}])
    assert math.isclose(budget.mb, 0.2) and not budget.spent
    budget.add([{"source": "planetary-computer", "bands_read": 1.0}, {"bands_read": 0.0}])
    assert math.isclose(budget.mb, 4.4) and not budget.spent
    budget.add([{"source": "earth-search", "bands_read": 1.0}])
    assert math.isclose(budget.mb, 13.1) and budget.spent
