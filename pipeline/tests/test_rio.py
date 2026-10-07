from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from climate_pipeline.screening.rio import (
    AcquisitionReader,
    Grid,
    lonlat_rowcol,
    rasterize_polygon,
    read_to_grid,
    site_grid,
    to_projected,
    utm_epsg,
    write_geotiff,
)
from climate_pipeline.screening.stac import Acquisition, AssetRef, Scene

BBOX = (-76.70, 5.60, -76.55, 5.75)


class PassThrough:
    name = "local"

    def search(self, *args: object) -> list[Scene]:
        return []

    def sign(self, href: str) -> str:
        return href


def scene(item_id: str, scl_href: str) -> Scene:
    return Scene(
        item_id=item_id,
        datetime=datetime(2023, 1, 1, 15, tzinfo=UTC),
        platform="sentinel-2a",
        mgrs_tile=item_id,
        relative_orbit=25,
        processing_baseline=5.09,
        boa_offset_applied=True,
        cloud_cover=10.0,
        epsg=32618,
        bbox=BBOX,
        assets={"scl": AssetRef(scl_href, None, None, 0, 32618)},
    )


def test_utm_zone_of_colombian_points() -> None:
    assert utm_epsg(-76.65, 5.69) == 32618
    assert utm_epsg(-78.5, 1.0) == 32617
    assert utm_epsg(-70.0, -1.0) == 32719


def test_site_grid_covers_the_bbox_and_nests_a_10_m_grid() -> None:
    coarse = site_grid(BBOX)
    fine = site_grid(BBOX, resolution=10.0)
    assert coarse.epsg == 32618
    assert coarse.resolution == 20.0
    assert coarse.x0 % 20 == 0 and coarse.y0 % 20 == 0
    assert (fine.x0, fine.y0) == (coarse.x0, coarse.y0)
    assert fine.shape == (coarse.height * 2, coarse.width * 2)
    for lon in (BBOX[0], BBOX[2]):
        for lat in (BBOX[1], BBOX[3]):
            row, col = lonlat_rowcol(coarse, lon, lat)
            assert 0 <= row <= coarse.height and 0 <= col <= coarse.width


def test_with_resolution_rejects_uneven_steps() -> None:
    grid = Grid(32618, 20.0, 0.0, 100.0, 3, 5)
    with pytest.raises(ValueError):
        grid.with_resolution(15.0)


def test_round_trip_on_the_same_grid(tmp_path: Path) -> None:
    grid = site_grid(BBOX)
    data = (np.arange(grid.width * grid.height) % 11).reshape(grid.shape).astype(np.uint8)
    write_geotiff(tmp_path / "scl.tif", data, grid)
    assert np.array_equal(read_to_grid(str(tmp_path / "scl.tif"), grid), data)


def test_a_raster_in_another_utm_zone_lands_in_place(tmp_path: Path) -> None:
    grid = site_grid(BBOX)
    ((x, y),) = to_projected(32617, [-76.625], [5.675])
    other = Grid(32617, 20.0, round(x / 20) * 20 - 2000, round(y / 20) * 20 + 2000, 200, 200)
    data = np.zeros(other.shape, dtype=np.uint8)
    data[90:110, 90:110] = 6
    write_geotiff(tmp_path / "zone17.tif", data, other)
    out = read_to_grid(str(tmp_path / "zone17.tif"), grid)
    row, col = lonlat_rowcol(grid, -76.625, 5.675)
    assert out[row, col] == 6
    assert np.count_nonzero(out == 6) == pytest.approx(400, rel=0.15)


def test_rasterize_polygon_burns_the_inside() -> None:
    grid = site_grid(BBOX)
    ring = [(-76.66, 5.66), (-76.64, 5.66), (-76.64, 5.68), (-76.66, 5.68)]
    inside = rasterize_polygon(grid, ring)
    row, col = lonlat_rowcol(grid, -76.65, 5.67)
    assert inside[row, col]
    assert not inside[0, 0]
    assert 11_000 < inside.sum() < 13_500  # about 2.2 km x 2.2 km = 110 x 110 px at 20 m


def test_reader_merges_tiles_and_caches(tmp_path: Path) -> None:
    grid = site_grid(BBOX)
    left = np.zeros(grid.shape, dtype=np.uint8)
    right = np.zeros(grid.shape, dtype=np.uint8)
    half = grid.width // 2
    left[:, :half] = 4
    right[:, half - 10 :] = 6
    write_geotiff(tmp_path / "left.tif", left, grid)
    write_geotiff(tmp_path / "right.tif", right, grid)
    acq = Acquisition(
        "sentinel-2a_2023-01-01_R025",
        datetime(2023, 1, 1, 15, tzinfo=UTC),
        "sentinel-2a",
        25,
        (scene("A", str(tmp_path / "left.tif")), scene("B", str(tmp_path / "right.tif"))),
    )
    reader = AcquisitionReader(PassThrough(), tmp_path / "cache")
    merged, filled = reader.read(acq, "scl", grid)
    assert np.all(merged[:, :half] == 4)
    assert np.all(merged[:, half:] == 6)
    assert filled == {"A": half * grid.height, "B": (grid.width - half) * grid.height}

    def must_not_read(href: str, g: Grid) -> np.ndarray:
        raise AssertionError("cache miss")

    cached, cached_filled = reader.read(acq, "scl", grid, reader=must_not_read)
    assert np.array_equal(cached, merged)
    assert cached_filled == filled


def test_a_failing_tile_is_skipped_recorded_and_not_cached(tmp_path: Path) -> None:
    grid = site_grid(BBOX)
    data = np.full(grid.shape, 6, dtype=np.uint8)
    write_geotiff(tmp_path / "ok.tif", data, grid)
    acq = Acquisition(
        "sentinel-2a_2023-01-01_R025",
        datetime(2023, 1, 1, 15, tzinfo=UTC),
        "sentinel-2a",
        25,
        (scene("bad", str(tmp_path / "missing.tif")), scene("good", str(tmp_path / "ok.tif"))),
    )
    reader = AcquisitionReader(PassThrough(), tmp_path / "cache")
    merged, filled = reader.read(acq, "scl", grid)
    assert np.all(merged == 6)
    assert filled["bad"] == -1 and filled["good"] > 0
    assert len(reader.errors) == 1 and reader.errors[0].startswith("bad scl")
    assert not list((tmp_path / "cache").rglob("*.npz"))


def test_a_corrupt_cache_file_is_read_again(tmp_path: Path) -> None:
    grid = site_grid(BBOX)
    write_geotiff(tmp_path / "ok.tif", np.full(grid.shape, 6, dtype=np.uint8), grid)
    acq = Acquisition(
        "sentinel-2a_2023-01-01_R025",
        datetime(2023, 1, 1, 15, tzinfo=UTC),
        "sentinel-2a",
        25,
        (scene("good", str(tmp_path / "ok.tif")),),
    )
    reader = AcquisitionReader(PassThrough(), tmp_path / "cache")
    reader.read(acq, "scl", grid)
    (cached,) = (tmp_path / "cache").rglob("*.npz")
    cached.write_bytes(b"truncated")
    merged, _ = reader.read(acq, "scl", grid)
    assert np.all(merged == 6)


def test_only_listed_assets_are_cached(tmp_path: Path) -> None:
    grid = site_grid(BBOX)
    write_geotiff(tmp_path / "ok.tif", np.full(grid.shape, 6, dtype=np.uint8), grid)
    acq = Acquisition(
        "sentinel-2a_2023-01-01_R025",
        datetime(2023, 1, 1, 15, tzinfo=UTC),
        "sentinel-2a",
        25,
        (scene("good", str(tmp_path / "ok.tif")),),
    )
    reader = AcquisitionReader(PassThrough(), tmp_path / "cache", cache_assets=())
    reader.read(acq, "scl", grid)
    assert not (tmp_path / "cache").exists()
