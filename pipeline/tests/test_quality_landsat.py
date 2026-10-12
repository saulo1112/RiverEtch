import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from climate_pipeline.calibration.extract import Windows
from climate_pipeline.quality import landsat
from climate_pipeline.quality.config import load_quality_config
from climate_pipeline.screening.config import load_screening_config
from climate_pipeline.screening.rio import Grid
from climate_pipeline.screening.stac import Acquisition

PIPELINE = Path(__file__).parents[1]
CFG = load_quality_config(PIPELINE / "water-quality.yaml")
SCREENING = load_screening_config(PIPELINE / "screening.yaml")
SCALE, OFFSET = 2.75e-5, -0.2


def item(platform: str = "landsat-8", tier: str = "T1") -> dict[str, Any]:
    band = {"raster:bands": [{"scale": SCALE, "offset": OFFSET, "nodata": 0}]}
    return {
        "id": "LC08_L2SP_009055_20231002_02_T1", "bbox": [-75, 6, -73, 8],
        "properties": {"platform": platform, "landsat:collection_category": tier,
                       "landsat:wrs_path": 9, "landsat:wrs_row": 55, "proj:epsg": 32618,
                       "datetime": "2023-10-02T15:20:00Z", "eo:cloud_cover": 12.0,
                       "view:sun_elevation": 60.0},
        "assets": {k: {"href": f"https://x/{k}.tif", **band}
                   for k in ("qa_pixel", "blue", "green", "red", "nir08", "swir16", "swir22")},
    }  # fmt: skip


def test_only_landsat_8_and_9_tier_1_items_are_kept() -> None:
    scene = landsat.parse(item())
    assert scene is not None and scene.mgrs_tile == "WRS009055" and scene.relative_orbit == 9
    assert scene.assets["nir08"].scale == SCALE and scene.assets["red"].offset == OFFSET
    assert landsat.parse(item(tier="T2")) is None
    assert landsat.parse(item(platform="landsat-7")) is None


class FakeReader:
    """Serves a QA_PIXEL array and constant bands (as DN) on any grid."""

    def __init__(self, qa: np.ndarray, reflectance: dict[str, float]) -> None:
        self.qa, self.reflectance = qa, reflectance
        self.calls: list[str] = []
        self.errors: list[str] = []

    def read(self, acquisition: Acquisition, asset: str, grid: Grid,
             reader: Any = None) -> tuple[np.ndarray, dict[str, int]]:  # fmt: skip
        self.calls.append(asset)
        if asset == "qa_pixel":
            return self.qa, {}
        dn = round((self.reflectance[asset] - OFFSET) / SCALE)
        return np.full(self.qa.shape, dn, dtype=np.uint16), {}


def run(qa: np.ndarray, swir: float = 0.01) -> tuple[list[dict[str, Any]], FakeReader]:
    scene = landsat.parse(item())
    assert scene is not None
    acq = Acquisition("landsat-8_2023-10-02_R009", datetime(2023, 10, 2, 15, 20, tzinfo=UTC),
                      "landsat-8", 9, (scene,))  # fmt: skip
    mask = np.zeros(qa.shape, dtype=bool)
    mask[2:8, 2:8] = True
    windows = Windows(Grid(32618, 20.0, 0.0, 0.0, 10, 10), {"300m": mask, "core": mask})
    reader = FakeReader(qa, {"blue": 0.03, "green": 0.05, "red": 0.08, "nir08": 0.04,
                             "swir16": swir, "swir22": 0.005})  # fmt: skip
    rows = landsat.measure(acq, reader, windows, "s", {scene.item_id: 30.0}, CFG, SCREENING)  # type: ignore[arg-type]
    return rows, reader


def test_clear_water_gives_band_medians_in_the_sentinel_2_slots() -> None:
    rows, _ = run(np.full((10, 10), 1 << 7 | 1 << 6, dtype=np.uint16))  # clear water
    row = rows[0]
    assert row["valid_px"] == 36 and row["contamination"] == 0.0 and row["bands_read"] == 1.0
    assert math.isclose(row["B8A"], 0.04, abs_tol=1e-4) and math.isclose(row["B04"], 0.08,
                                                                          abs_tol=1e-4)  # fmt: skip
    assert math.isnan(row["B05"]) and row["b11_ok"] == 1.0 and row["sun_zenith"] == 30.0


def test_clouds_skip_the_bands_and_glint_leaves_the_medians() -> None:
    cloudy = np.full((10, 10), 1 << 3, dtype=np.uint16)
    rows, reader = run(cloudy)
    assert rows[0]["bands_read"] == 0.0 and rows[0]["contamination"] == 1.0
    assert reader.calls == ["qa_pixel"]
    glinted, _ = run(np.full((10, 10), 1 << 7 | 1 << 6, dtype=np.uint16), swir=0.2)
    assert glinted[0]["glint_share"] == 1.0 and glinted[0]["valid_px"] == 0.0
