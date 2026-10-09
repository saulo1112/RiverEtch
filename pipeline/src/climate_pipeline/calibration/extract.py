"""Imagery for the calibration validation: station geometry, window statistics, water extent.

Reads Sentinel-2 L2A COGs through the screening's reader, scaling each item with its own
metadata (``boa_offset_applied`` handled as in the screening). Bands beyond red, green, B11 and
SCL are added to each scene here, so :mod:`climate_pipeline.screening.stac` keeps its behaviour.
10 m bands are averaged onto the 20 m grid. Small windows are cached on disk, so a rerun reads
nothing new; every failed read is recorded by the reader and must be zero before results count.
"""

from __future__ import annotations

import dataclasses
import logging
import math
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

import numpy as np
from numpy.typing import NDArray

from climate_pipeline.calibration.config import CalibrationConfig
from climate_pipeline.calibration.stations import (
    Candidate,
    disk,
    largest_component,
    width_m,
    window_mask,
)
from climate_pipeline.screening.bands import read_average, read_reflectance
from climate_pipeline.screening.config import AssetKeys, ScreeningConfig
from climate_pipeline.screening.mask import FrequencyStack, snap
from climate_pipeline.screening.rio import (
    AcquisitionReader,
    Grid,
    lonlat_rowcol,
    read_to_grid,
    site_grid,
)
from climate_pipeline.screening.stac import (
    Acquisition,
    extra_assets,
    group_acquisitions,
    parse_item,
    search_items,
)
from climate_pipeline.screening.stage1 import mndwi_frequency

log = logging.getLogger(__name__)
BoolArray = NDArray[np.bool_]
CORE = AssetKeys(scl="scl", red="red", green="green", swir16="swir16")
TEN_M = ("blue", "green", "red", "nir")
BAND_ORDER = ("B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12")


def bbox_around(lon: float, lat: float, half_m: float) -> tuple[float, float, float, float]:
    """A WGS84 box of +-``half_m`` around a point.

    Args:
        lon: Longitude.
        lat: Latitude.
        half_m: Half size in meters.

    Returns:
        West, south, east, north.
    """
    dlat = half_m / 111_320
    dlon = half_m / (111_320 * math.cos(math.radians(lat)))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


def search(
    cfg: CalibrationConfig,
    collection: str,
    bbox: tuple[float, float, float, float],
    start: date,
    end: date,
) -> list[Acquisition]:
    """Acquisitions of a collection over a box, every configured band attached.

    Args:
        cfg: Settings.
        collection: E.g. ``sentinel-2-l2a``.
        bbox: West, south, east, north.
        start: First day.
        end: Last day.

    Returns:
        Acquisitions sorted by time (newest processing per tile).
    """
    keys = {k: k for k in cfg.imagery.assets if k not in ("scl", "red", "green", "swir16")}
    scenes = []
    for item in search_items(cfg.imagery.url, collection, bbox, start, end, 100):
        try:
            scene = parse_item(item, CORE)
        except (KeyError, TypeError, ValueError) as error:
            log.warning("skipping item %s: %s", item.get("id", "?"), error)
            continue
        scenes.append(
            dataclasses.replace(scene, assets={**scene.assets, **extra_assets(item, keys)})
        )
    return group_acquisitions(scenes)


def family(acquisition: Acquisition) -> str:
    """The processing-baseline family of an acquisition (``02.xx``; the newest of its items).

    Args:
        acquisition: The pass.

    Returns:
        The family, or ``unknown``.
    """
    values = [s.processing_baseline for s in acquisition.scenes if s.processing_baseline]
    return f"{int(max(values)):02d}.xx" if values else "unknown"


@dataclass(frozen=True)
class StationGeometry:
    """Where a station sits on the river, and whether it is selected."""

    station_id: str
    grid: Grid
    main: BoolArray
    snapped: tuple[int, int] | None
    snap_m: float
    width_m: float
    mask_source: str
    selected: bool
    reason: str


def _parallel(
    acquisitions: Sequence[Acquisition], work: Callable[[Acquisition], object], workers: int
) -> list[object]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(work, acquisitions))


def station_geometry(
    cand: Candidate,
    acquisitions: Sequence[Acquisition],
    reader: AcquisitionReader,
    cfg: CalibrationConfig,
    screening: ScreeningConfig,
    workers: int,
) -> StationGeometry:
    """Main channel, snap and width of one station (the preregistered selection rule).

    Args:
        cand: The candidate.
        acquisitions: The geometry period's acquisitions over the station grid.
        reader: Band reader.
        cfg: Settings.
        screening: The screening's settings (SCL classes, MNDWI rule).
        workers: Parallel reads.

    Returns:
        The geometry and the selection outcome.
    """
    st = cfg.stations
    grid = site_grid(bbox_around(cand.lon, cand.lat, st.grid_half_size_m))
    res = grid.resolution
    stack = FrequencyStack(grid.shape, screening.scl)

    def scl(acq: Acquisition) -> object:
        return reader.read(acq, "scl", grid)[0]

    for layer in _parallel(acquisitions, scl, workers):
        stack.update(np.asarray(layer))
    freq = stack.frequency(st.min_observations)
    source = "scl"
    main = largest_component(np.nan_to_num(freq, nan=0.0) >= st.water_frequency_min)
    if not main.any():
        mfreq, _ = mndwi_frequency(list(acquisitions), reader, grid, screening.posthoc(), workers)
        main = largest_component(np.nan_to_num(mfreq, nan=0.0) >= st.water_frequency_min)
        source = "mndwi"
    if not main.any():
        return StationGeometry(
            cand.station_id, grid, main, None, math.nan, math.nan, source, False, "no water"
        )
    rc = lonlat_rowcol(grid, cand.lon, cand.lat)
    snapped = snap(main, rc, st.snap_radius_m / res)
    if snapped is None:
        return StationGeometry(
            cand.station_id, grid, main, None, math.nan, math.nan, source, False,
            f"no main channel within {st.snap_radius_m:g} m",
        )  # fmt: skip
    pixel, dist = snapped
    width = width_m(main, pixel, st.width_search_m / res, res)
    ok = width >= st.min_width_m
    return StationGeometry(
        cand.station_id, grid, main, pixel, dist * res, width, source, ok,
        "" if ok else f"main channel {width:.0f} m wide, {st.min_width_m:g} m needed",
    )  # fmt: skip


def sub_grid(grid: Grid, center: tuple[int, int], half_px: int) -> tuple[Grid, tuple[int, int]]:
    """A smaller grid, aligned with ``grid``, around a pixel (clipped to the grid).

    Args:
        grid: The station grid.
        center: Centre pixel.
        half_px: Half size in pixels.

    Returns:
        The sub-grid and its top-left offset in ``grid``.
    """
    r0, c0 = max(0, center[0] - half_px), max(0, center[1] - half_px)
    r1 = min(grid.height, center[0] + half_px + 1)
    c1 = min(grid.width, center[1] + half_px + 1)
    sub = Grid(
        grid.epsg, grid.resolution, grid.x0 + c0 * grid.resolution,
        grid.y0 - r0 * grid.resolution, c1 - c0, r1 - r0,
    )  # fmt: skip
    return sub, (r0, c0)


@dataclass(frozen=True)
class Windows:
    """The masks measured at one station, on its small read grid."""

    grid: Grid
    masks: Mapping[str, BoolArray]  # e.g. "300m", "1000m", "extent"


def station_windows(geometry: StationGeometry, cfg: CalibrationConfig) -> Windows:
    """The station's window masks (300 m, 1 km) and the 2 km extent disk, on one small grid.

    Args:
        geometry: A selected station.
        cfg: Settings.

    Returns:
        The windows.

    Raises:
        ValueError: If the station did not snap.
    """
    if geometry.snapped is None:
        raise ValueError(f"{geometry.station_id}: not snapped")
    res = geometry.grid.resolution
    radius = cfg.climate.width.window_radius_m
    half = math.ceil(max(radius, cfg.window.sensitivity_radius_m) / res) + 2
    grid, (r0, c0) = sub_grid(geometry.grid, geometry.snapped, half)
    main = geometry.main[r0 : r0 + grid.height, c0 : c0 + grid.width]
    center = (geometry.snapped[0] - r0, geometry.snapped[1] - c0)
    w = cfg.window
    return Windows(
        grid,
        {
            "300m": window_mask(main, center, w.radius_m / res, w.erosion_px),
            "1000m": window_mask(main, center, w.sensitivity_radius_m / res, w.erosion_px),
            "extent": disk(grid.shape, center, radius / res),
        },
    )


def _median(values: NDArray[np.floating]) -> float:
    finite = values[np.isfinite(values)]
    return float(np.median(finite)) if finite.size else math.nan


def measure_window(
    acquisition: Acquisition,
    reader: AcquisitionReader,
    windows: Windows,
    names: Sequence[str],
    cfg: CalibrationConfig,
    screening: ScreeningConfig,
) -> dict[str, dict[str, float]]:
    """Per-window statistics and band medians of one acquisition.

    Valid pixels are window pixels whose SCL class is neither no-data nor invalid. Pixels with
    B11 above the screening's guard are glint and leave the medians. The scene's water-B11 check
    uses the median B11 of the valid pixels.

    Args:
        acquisition: The pass.
        reader: Band reader.
        windows: The station's windows.
        names: Which windows to measure (``300m``, ``1000m``).
        cfg: Settings.
        screening: Screening settings.

    Returns:
        Window name -> statistics and band medians.
    """
    grid = windows.grid
    scl = np.asarray(reader.read(acquisition, "scl", grid)[0])
    bands: dict[str, NDArray[np.float32]] = {}
    for asset, band in cfg.imagery.assets.items():
        if asset == "scl":
            continue
        read = read_average if asset in TEN_M else read_to_grid
        bands[band], _ = read_reflectance(reader, acquisition, asset, grid, read=read)
    invalid = np.isin(scl, screening.scl.invalid)
    data = ~np.isin(scl, screening.scl.nodata)
    low, high = screening.stage2.water_swir16_range
    out = {}
    for name in names:
        window = windows.masks[name]
        pixels = window & data
        valid = pixels & ~invalid
        b11 = bands["B11"]
        glint = valid & (b11 > screening.stage2.swir16_max)
        water = valid & ~glint
        for band in BAND_ORDER:
            water &= np.isfinite(bands[band])
        n_pixels, n_valid = int(pixels.sum()), int(valid.sum())
        b11_median = _median(b11[valid])
        red, green = bands["B04"][water], bands["B03"][water]
        rg = red + green
        keep = rg >= screening.stage2.rg_floor
        row = {
            "window_px": float(window.sum()),
            "data_px": float(n_pixels),
            "valid_px": float(int(water.sum())),
            "contamination": float((pixels & invalid).sum() / n_pixels) if n_pixels else math.nan,
            "glint_share": float(glint.sum() / n_valid) if n_valid else math.nan,
            "b11_median": b11_median,
            "b11_ok": float(low <= b11_median <= high) if math.isfinite(b11_median) else 0.0,
            "ndti_px_median": _median((red[keep] - green[keep]) / rg[keep]),
        }
        for band in BAND_ORDER:
            row[band] = _median(bands[band][water])
        out[name] = row
    return out


def measure_extent(
    acquisition: Acquisition,
    reader: AcquisitionReader,
    windows: Windows,
    screening: ScreeningConfig,
) -> dict[str, float]:
    """Water extent in the 2 km disk: MNDWI > 0 among valid pixels.

    Args:
        acquisition: The pass.
        reader: Band reader.
        windows: The station's windows.
        screening: Screening settings.

    Returns:
        ``valid_fraction``, ``water_px``, ``extent_km2`` and ``b11_ok`` (0 when the darkest B11
        values suggest an offset applied twice, as the screening's MNDWI rule checks).
    """
    grid = windows.grid
    area = windows.masks["extent"]
    scl = np.asarray(reader.read(acquisition, "scl", grid)[0])
    green, _ = read_reflectance(reader, acquisition, "green", grid, read=read_average)
    swir, _ = read_reflectance(reader, acquisition, "swir16", grid)
    excluded = np.isin(scl, sorted(set(screening.scl.invalid) | set(screening.scl.nodata)))
    valid = area & ~excluded & np.isfinite(green) & np.isfinite(swir)
    with np.errstate(divide="ignore", invalid="ignore"):
        index = (green - swir) / (green + swir)
    water = valid & (index > 0)
    lowest = screening.stage2.water_swir16_range[0]
    b11_ok = not (valid.any() and float(np.percentile(swir[valid], 0.5)) < lowest)
    res = grid.resolution
    return {
        "valid_fraction": float(valid.sum() / area.sum()) if area.any() else math.nan,
        "water_px": float(water.sum()),
        "extent_km2": float(water.sum() * res * res / 1e6),
        "b11_ok": float(b11_ok),
    }


def local_date(acquisition: Acquisition, timezone: str) -> date:
    """The acquisition's local date.

    Args:
        acquisition: The pass.
        timezone: IANA name.

    Returns:
        The date in that zone.
    """
    return acquisition.datetime.astimezone(ZoneInfo(timezone)).date()
