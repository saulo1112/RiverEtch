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


def test_a_failed_site_still_gets_a_summary() -> None:
    from climate_pipeline.screening.config import load_site
    from climate_pipeline.screening.stage1 import failed_stage1

    site = load_site(Path(__file__).parents[1] / "sites" / "cauca-salvajina.yaml")
    result = failed_stage1(site, CONFIG, "error: OSError: unreachable")
    assert result.summary["geometry_failed"] == "error: OSError: unreachable"
    assert result.summary["acquisitions"] == 0


def test_posthoc_mndwi_mask_recovers_a_river_scl_calls_soil(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    from climate_pipeline.screening.config import Citation, Point, SiteConfig
    from climate_pipeline.screening.rio import AcquisitionReader, rowcol_lonlat, site_grid
    from climate_pipeline.screening.rio import write_geotiff as write
    from climate_pipeline.screening.stac import AssetRef, Scene
    from climate_pipeline.screening.stage1 import run_stage1

    bbox = (-76.70, 5.60, -76.57, 5.66)
    grid = site_grid(bbox)
    river = np.zeros(grid.shape, dtype=bool)
    draw(river, [(grid.height // 2, 8), (grid.height // 2, grid.width - 8)], half=4)
    fine = np.repeat(np.repeat(river, 2, axis=0), 2, axis=1)
    write(tmp_path / "scl.tif", np.where(river, 5, 4).astype(np.uint8), grid)
    # Turbid water: green 0.09 well above SWIR 0.01 (MNDWI > 0); land: SWIR above green. The
    # pixels already carry the BOA offset, as Earth Search's flagged items do.
    green = np.where(fine, 0.09, 0.07)
    swir = np.where(river, 0.01, 0.25)
    write(tmp_path / "green.tif", (green / 1e-4).astype(np.uint16), grid.with_resolution(10.0))
    write(tmp_path / "swir.tif", (swir / 1e-4).astype(np.uint16), grid)
    epsg = grid.epsg

    class Source:
        name = "local"
        flagged = True

        def search(self, *args: object) -> list[Scene]:
            return [
                Scene(
                    item_id=f"S2A_X_{k}",
                    datetime=datetime(2022, 1, 5, 15, tzinfo=UTC) + timedelta(days=10 * k),
                    platform="sentinel-2a",
                    mgrs_tile="18NUL",
                    relative_orbit=25,
                    processing_baseline=5.09,
                    boa_offset_applied=self.flagged,
                    cloud_cover=0.0,
                    epsg=epsg,
                    bbox=bbox,
                    assets={
                        "scl": AssetRef(str(tmp_path / "scl.tif"), None, None, 0, epsg),
                        "green": AssetRef(str(tmp_path / "green.tif"), 1e-4, -0.1, 0, epsg),
                        "swir16": AssetRef(str(tmp_path / "swir.tif"), 1e-4, -0.1, 0, epsg),
                    },
                )
                for k in range(25)
            ]

        def sign(self, href: str) -> str:
            return href

    mid = grid.height // 2

    def pt(col: int, text: str) -> Point:
        lon, lat = rowcol_lonlat(grid, mid, col)
        return Point(lon=lon, lat=lat, description=text, basis="synthetic")

    site = SiteConfig(
        id="synth-soil", name="Synthetic", river="Synthetic", category="A", rationale="test",
        center=pt(grid.width // 2, "center"), aoi_bbox=bbox,
        upstream_anchor=pt(10, "up"), downstream_anchor=pt(grid.width - 11, "down"),
        rain_points=(pt(grid.width // 2, "reach center"),), operator="none", regulator="none",
        citations=(Citation(url="https://example.test", title="t", supports="s",
                            verification="v"),),
    )  # fmt: skip
    reader = AcquisitionReader(Source(), tmp_path / "cache")
    primary = run_stage1(site, CONFIG, Source(), reader, None, workers=2)
    assert primary.geometry.failed is not None and primary.mask_source == "scl"
    posthoc = run_stage1(site, CONFIG.posthoc(), Source(), reader, None, workers=2)
    assert posthoc.geometry.failed is None and posthoc.mask_source == "mndwi"
    assert posthoc.summary["clear"] == 0 and posthoc.summary["observable"] == 25
    assert posthoc.summary["mndwi_skipped_b11"] == 0

    # Unflagged items get the listed -0.1 a second time: water B11 turns about -0.09, MNDWI
    # flips sign over water, and the B11 check skips every acquisition instead of using it.
    unflagged = Source()
    unflagged.flagged = False
    twice = run_stage1(site, CONFIG.posthoc(), unflagged, reader, None, workers=2)
    assert twice.summary["mndwi_skipped_b11"] == 25 and twice.geometry.failed is not None
