"""Thin typed adapter around rasterio, the only module that imports it.

Every scene is read onto one fixed grid per site (the site's UTM zone, 20 m for SCL and B11,
10 m for red and green), so tiles from different MGRS squares or UTM zones line up pixel for
pixel. Reads go through a ``WarpedVRT`` over the cloud-optimized GeoTIFF, which fetches only the
blocks the window needs.
"""

from __future__ import annotations

import hashlib
import math
import os
import threading
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np
import rasterio
from numpy.typing import NDArray
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform as warp_transform

from climate_pipeline.screening.stac import Acquisition, SceneSource

GDAL_ENV: dict[str, str | int | bool] = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "AWS_NO_SIGN_REQUEST": "YES",
    "AWS_REGION": "us-west-2",
    "GDAL_HTTP_MAX_RETRY": 5,
    "GDAL_HTTP_RETRY_DELAY": 2,
    "GDAL_HTTP_TIMEOUT": 120,
    "GDAL_HTTP_CONNECTTIMEOUT": 30,
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_MULTIPLEX": "YES",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF,.tiff",
    "VSI_CACHE": "TRUE",
}


@dataclass(frozen=True)
class Grid:
    """A north-up raster grid in a projected CRS (meters)."""

    epsg: int
    resolution: float
    x0: float
    y0: float
    width: int
    height: int

    @property
    def shape(self) -> tuple[int, int]:
        """Rows and columns."""
        return (self.height, self.width)

    def affine(self) -> Affine:
        """The rasterio affine transform of the grid."""
        return Affine(self.resolution, 0.0, self.x0, 0.0, -self.resolution, self.y0)

    def with_resolution(self, resolution: float) -> Grid:
        """The same extent at another resolution that divides the current one evenly.

        Args:
            resolution: New pixel size in meters.

        Returns:
            The finer or coarser grid.

        Raises:
            ValueError: If the extent is not a whole number of new pixels.
        """
        factor = self.resolution / resolution
        width, height = self.width * factor, self.height * factor
        if not (width.is_integer() and height.is_integer()):
            raise ValueError(f"{resolution} m does not divide the {self.resolution} m grid")
        return Grid(self.epsg, resolution, self.x0, self.y0, int(width), int(height))

    def key(self) -> str:
        """A short stable identifier of the grid (for cache file names)."""
        text = f"{self.epsg}|{self.resolution}|{self.x0}|{self.y0}|{self.width}|{self.height}"
        return hashlib.sha256(text.encode()).hexdigest()[:12]

    def rowcol(self, x: float, y: float) -> tuple[int, int]:
        """The pixel containing a projected point (may fall outside the grid)."""
        return (
            math.floor((self.y0 - y) / self.resolution),
            math.floor((x - self.x0) / self.resolution),
        )


def utm_epsg(lon: float, lat: float) -> int:
    """The WGS84 UTM zone EPSG code of a point.

    Args:
        lon: Longitude in degrees.
        lat: Latitude in degrees.

    Returns:
        326zz north of the equator, 327zz south of it.
    """
    zone = min(int((lon + 180) // 6) + 1, 60)
    return (32600 if lat >= 0 else 32700) + zone


def to_projected(
    epsg: int, lons: Sequence[float], lats: Sequence[float]
) -> list[tuple[float, float]]:
    """Project WGS84 points into a CRS.

    Args:
        epsg: Target EPSG code.
        lons: Longitudes in degrees.
        lats: Latitudes in degrees.

    Returns:
        ``(x, y)`` pairs in meters.
    """
    xs, ys = warp_transform("EPSG:4326", f"EPSG:{epsg}", list(lons), list(lats))
    return [(float(x), float(y)) for x, y in zip(xs, ys, strict=True)]


def site_grid(bbox: tuple[float, float, float, float], resolution: float = 20.0) -> Grid:
    """The analysis grid covering a WGS84 bounding box, in its center's UTM zone.

    Args:
        bbox: West, south, east, north in degrees.
        resolution: Pixel size in meters (the extent is snapped to 20 m so a 10 m grid nests).

    Returns:
        The grid.
    """
    west, south, east, north = bbox
    epsg = utm_epsg((west + east) / 2, (south + north) / 2)
    steps = 16
    lons = [west + (east - west) * i / steps for i in range(steps + 1)]
    lats = [south + (north - south) * i / steps for i in range(steps + 1)]
    edge = (
        [(lon, south) for lon in lons]
        + [(lon, north) for lon in lons]
        + [(west, lat) for lat in lats]
        + [(east, lat) for lat in lats]
    )
    points = to_projected(epsg, [p[0] for p in edge], [p[1] for p in edge])
    snap = 20.0
    x0 = math.floor(min(p[0] for p in points) / snap) * snap
    x1 = math.ceil(max(p[0] for p in points) / snap) * snap
    y0 = math.ceil(max(p[1] for p in points) / snap) * snap
    y1 = math.floor(min(p[1] for p in points) / snap) * snap
    coarse = Grid(epsg, snap, x0, y0, int((x1 - x0) / snap), int((y0 - y1) / snap))
    return coarse if resolution == snap else coarse.with_resolution(resolution)


def lonlat_rowcol(grid: Grid, lon: float, lat: float) -> tuple[int, int]:
    """The grid pixel containing a WGS84 point.

    Args:
        grid: The grid.
        lon: Longitude in degrees.
        lat: Latitude in degrees.

    Returns:
        Row and column (may fall outside the grid).
    """
    ((x, y),) = to_projected(grid.epsg, [lon], [lat])
    return grid.rowcol(x, y)


def rowcol_lonlat(grid: Grid, row: int, col: int) -> tuple[float, float]:
    """The WGS84 position of a grid pixel's center.

    Args:
        grid: The grid.
        row: Row.
        col: Column.

    Returns:
        Longitude and latitude in degrees.
    """
    x = grid.x0 + (col + 0.5) * grid.resolution
    y = grid.y0 - (row + 0.5) * grid.resolution
    lons, lats = warp_transform(f"EPSG:{grid.epsg}", "EPSG:4326", [x], [y])
    return float(lons[0]), float(lats[0])


def rasterize_polygon(grid: Grid, ring: Sequence[tuple[float, float]]) -> NDArray[np.bool_]:
    """Burn a WGS84 polygon (lon, lat ring) into a boolean grid.

    Args:
        grid: The grid.
        ring: Polygon vertices as ``(lon, lat)``.

    Returns:
        True inside the polygon.
    """
    points = to_projected(grid.epsg, [p[0] for p in ring], [p[1] for p in ring])
    if points[0] != points[-1]:
        points.append(points[0])
    geometry = {"type": "Polygon", "coordinates": [points]}
    burned = rasterize(
        [(geometry, 1)], out_shape=grid.shape, transform=grid.affine(), fill=0, dtype="uint8"
    )
    return cast(NDArray[np.uint8], burned).astype(bool)


def read_to_grid(href: str, grid: Grid, nodata: float = 0) -> NDArray[np.generic]:
    """Read band 1 of a raster onto a grid (nearest neighbour), filling gaps with ``nodata``.

    Args:
        href: URL or path of the raster.
        grid: Target grid.
        nodata: Value for pixels the raster does not cover (and its own nodata).

    Returns:
        A ``grid.shape`` array in the raster's data type.
    """
    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as src:
        src_nodata = src.nodata if src.nodata is not None else nodata
        with WarpedVRT(
            src,
            crs=f"EPSG:{grid.epsg}",
            transform=grid.affine(),
            width=grid.width,
            height=grid.height,
            resampling=Resampling.nearest,
            src_nodata=src_nodata,
            nodata=nodata,
        ) as vrt:
            return cast(NDArray[np.generic], vrt.read(1))


def write_geotiff(
    path: Path, data: NDArray[np.generic], grid: Grid, nodata: float | None = 0
) -> None:
    """Write a single-band GeoTIFF on a grid (used for synthetic test scenes).

    Args:
        path: Output file.
        data: ``grid.shape`` array.
        grid: The grid the array is on.
        nodata: Nodata value to record, if any.
    """
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=grid.width,
        height=grid.height,
        count=1,
        dtype=str(data.dtype),
        crs=f"EPSG:{grid.epsg}",
        transform=grid.affine(),
        nodata=nodata,
        tiled=True,
        blockxsize=256,
        blockysize=256,
        compress="deflate",
    ) as dst:
        dst.write(data, 1)


class AcquisitionReader:
    """Reads one band of an acquisition onto a grid, merging its tiles, with an on-disk cache."""

    def __init__(
        self,
        source: SceneSource,
        cache_dir: Path | None,
        cache_assets: tuple[str, ...] = ("scl",),
    ) -> None:
        """Create the reader.

        Args:
            source: Signs asset URLs before reading.
            cache_dir: Where to keep compressed reads (None disables caching).
            cache_assets: Assets worth caching on disk (SCL is read twice; 10 m bands are large).
        """
        self._source = source
        self._cache_dir = cache_dir
        self._cache_assets = cache_assets
        self._lock = threading.Lock()
        self.errors: list[str] = []

    def read(
        self,
        acquisition: Acquisition,
        asset: str,
        grid: Grid,
        reader: Callable[[str, Grid], NDArray[np.generic]] = read_to_grid,
    ) -> tuple[NDArray[np.generic], dict[str, int]]:
        """Read and merge the acquisition's tiles for one asset (first tile with data wins).

        A tile that fails twice is skipped (its pixels stay no data) and recorded in ``errors``,
        so one bad file cannot abort a multi-hour run.

        Args:
            acquisition: The pass.
            asset: Logical asset name (``scl``, ``red``, ``green``, ``swir16``).
            grid: Target grid.
            reader: Function reading one href onto the grid (injectable for tests).

        Returns:
            The merged array (0 = no data) and, per item id, how many pixels it filled (-1 when
            the read failed).
        """
        cache = self._cache_path(acquisition, asset, grid)
        if cache is not None and cache.exists():
            try:
                with np.load(cache) as stored:
                    data = cast(NDArray[np.generic], stored["data"])
                    filled = {
                        str(k): int(v) for k, v in zip(stored["ids"], stored["counts"], strict=True)
                    }
                return data, filled
            except (OSError, ValueError, KeyError, zipfile.BadZipFile):
                cache.unlink(missing_ok=True)
        merged: NDArray[np.generic] | None = None
        filled = {}
        for scene in acquisition.scenes:
            ref = scene.assets.get(asset)
            if ref is None:
                continue
            tile = self._read_with_retry(scene.item_id, asset, ref.href, grid, reader)
            if tile is None:
                filled[scene.item_id] = -1
                continue
            if merged is None:
                merged = tile.copy()
                filled[scene.item_id] = int(np.count_nonzero(tile))
                continue
            gap = (merged == 0) & (tile != 0)
            merged[gap] = tile[gap]
            filled[scene.item_id] = int(np.count_nonzero(gap))
        failed = any(v < 0 for v in filled.values())
        if merged is None:
            merged = np.zeros(grid.shape, dtype=np.uint16)
        if cache is not None and not failed:
            cache.parent.mkdir(parents=True, exist_ok=True)
            # Write then rename, so a killed run never leaves a truncated cache file behind.
            partial = cache.with_suffix(f".{threading.get_ident()}.tmp.npz")
            np.savez_compressed(
                partial,
                data=merged,
                ids=np.array(list(filled), dtype=str),
                counts=np.array(list(filled.values()), dtype=np.int64),
            )
            os.replace(partial, cache)
        return merged, filled

    def _read_with_retry(
        self,
        item_id: str,
        asset: str,
        href: str,
        grid: Grid,
        reader: Callable[[str, Grid], NDArray[np.generic]],
    ) -> NDArray[np.generic] | None:
        for attempt in range(2):
            try:
                return reader(self._source.sign(href), grid)
            except Exception as error:  # GDAL/network errors: retried once, then recorded
                if attempt == 1:
                    with self._lock:
                        self.errors.append(f"{item_id} {asset}: {error}")
                    return None
        return None

    def _cache_path(self, acquisition: Acquisition, asset: str, grid: Grid) -> Path | None:
        if self._cache_dir is None or asset not in self._cache_assets:
            return None
        items = hashlib.sha256("|".join(s.item_id for s in acquisition.scenes).encode()).hexdigest()
        return self._cache_dir / grid.key() / f"{acquisition.key}_{items[:8]}_{asset}.npz"
