from pathlib import Path

import numpy as np
from synthetic import draw, frequency

from climate_pipeline.reach import measure as m
from climate_pipeline.screening.config import load_screening_config, load_site
from climate_pipeline.screening.mask import derive_geometry
from climate_pipeline.screening.rio import Grid
from climate_pipeline.screening.stage1 import Stage1Result
from climate_pipeline.screening.stage2 import subreach_ndti, subreach_nir_red

PIPELINE = Path(__file__).parents[1]
CONFIG = load_screening_config(PIPELINE / "screening.yaml")
SITE = load_site(PIPELINE / "sites" / "magdalena-puerto-wilches.yaml")


def result() -> Stage1Result:
    river = np.zeros((300, 1000), dtype=bool)
    draw(river, [(150, 10), (120, 500), (150, 990)], half=4)
    geom = derive_geometry(
        frequency(river), resolution=20.0, thresholds=(0.5,), upstream=(150, 12),
        downstream=(150, 988), center=(120, 500), confluences={}, excluded=None,
        snap_radius_m=1500, corridor_half_width_m=600, erosion_px_10m=1,
        land_ring_m=(100, 400), subreach=CONFIG.subreach,
    )  # fmt: skip
    grid = Grid(32618, 20.0, 500_000.0, 900_000.0, 1000, 300)
    return Stage1Result(SITE, grid, [], geom, [], [], ())


def test_the_corridor_measures_the_same_pixels_as_the_full_grid() -> None:
    full = result()
    assert full.geometry.subreaches
    cut = m.corridor(full)
    assert cut.grid.width * cut.grid.height < full.grid.width * full.grid.height / 3
    r0 = round((full.grid.y0 - cut.grid.y0) / 20.0)
    c0 = round((cut.grid.x0 - full.grid.x0) / 20.0)
    rng = np.random.default_rng(0)
    red = rng.uniform(0.03, 0.08, (600, 2000)).astype(np.float32)
    green = rng.uniform(0.04, 0.09, (600, 2000)).astype(np.float32)
    nir = rng.uniform(0.01, 0.06, (300, 1000)).astype(np.float32)
    swir = np.full((300, 1000), 0.01, dtype=np.float32)
    scl = np.full((300, 1000), 6, dtype=np.uint8)
    h, w = cut.grid.height, cut.grid.width

    def fine(a: np.ndarray) -> np.ndarray:
        return a[2 * r0 : 2 * (r0 + h), 2 * c0 : 2 * (c0 + w)]

    def coarse(a: np.ndarray) -> np.ndarray:
        return a[r0 : r0 + h, c0 : c0 + w]

    for whole, part in zip(full.geometry.subreaches, cut.geometry.subreaches, strict=True):
        assert whole.mask.sum() == part.mask.sum()
        a = subreach_ndti(red, green, swir, scl, whole.mask, 1, CONFIG)
        b = subreach_ndti(fine(red), fine(green), coarse(swir), coarse(scl), part.mask, 1, CONFIG)
        assert a == b
        assert subreach_nir_red(red, green, nir, swir, scl, whole.mask, 1, CONFIG) == (
            subreach_nir_red(fine(red), fine(green), coarse(nir), coarse(swir), coarse(scl),
                             part.mask, 1, CONFIG))  # fmt: skip
