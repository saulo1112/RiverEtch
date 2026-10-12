"""Imagery of the water-quality validation v2: two L2A sources, small station windows.

One source serves each date: Planetary Computer before the split date, Earth Search from it on.
Both are read through D15's reader and window statistics (``calibration.extract``), so each source's
assets are renamed to the logical names D15 reads (``red``, ``nir08``…). Planetary Computer items
carry no ``raster:bands``; their reflectance follows ESA's L2A definition (DN x 1e-4, with the
-0.1 BOA offset from processing baseline 04.00), and the water-B11 check catches a wrong offset.
Windows sit on a +-400 m grid: the 300 m window is D15's (same snap, erosion and radius), the core
window erodes the main channel to 60 m from land.
"""

from __future__ import annotations

import dataclasses
import logging
import math
from collections.abc import Mapping
from datetime import UTC, date
from pathlib import Path
from typing import Any

from climate_pipeline.calibration import extract
from climate_pipeline.calibration.extract import StationGeometry, Windows
from climate_pipeline.calibration.stations import window_mask
from climate_pipeline.quality.config import QualityConfig, Source, SourceName
from climate_pipeline.screening.config import AssetKeys, ScreeningConfig
from climate_pipeline.screening.rio import AcquisitionReader
from climate_pipeline.screening.stac import (
    Acquisition,
    AssetRef,
    Scene,
    extra_assets,
    group_acquisitions,
    make_source,
    parse_item,
    search_items,
)

log = logging.getLogger(__name__)
LOGICAL = {"B02": "blue", "B03": "green", "B04": "red", "B05": "rededge1", "B06": "rededge2",
           "B07": "rededge3", "B08": "nir", "B8A": "nir08", "B11": "swir16", "B12": "swir22",
           "SCL": "scl"}  # fmt: skip
CORE = ("scl", "red", "green", "swir16")
ESA_SCALE = 1e-4
ESA_OFFSET = -0.1  # BOA_ADD_OFFSET of -1000 DN, from processing baseline 04.00
OFFSET_BASELINE = 4.0


def logical_keys(source: Source) -> dict[str, str]:
    """Logical band name -> the source's asset key.

    Args:
        source: The source settings (asset key -> band).

    Returns:
        E.g. ``{"red": "B04", "nir08": "B8A", ...}`` for Planetary Computer.
    """
    return {LOGICAL[band]: key for key, band in source.assets.items() if band in LOGICAL}


def esa_scaled(ref: AssetRef, baseline: float | None) -> AssetRef:
    """An asset without ``raster:bands`` scaled by ESA's L2A definition.

    Args:
        ref: The asset.
        baseline: The item's processing baseline (e.g. 2.12).

    Returns:
        The asset with scale and offset (unchanged when the item already carried them).
    """
    if ref.scale is not None and ref.offset is not None:
        return ref
    offset = ESA_OFFSET if baseline is not None and baseline >= OFFSET_BASELINE else 0.0
    return dataclasses.replace(ref, scale=ESA_SCALE, offset=offset)


def sun_zenith(props: Mapping[str, Any]) -> float:
    """The sun zenith angle from either source's item properties.

    Args:
        props: Item properties.

    Returns:
        Degrees (NaN when absent).
    """
    if isinstance(props.get("s2:mean_solar_zenith"), int | float):
        return float(props["s2:mean_solar_zenith"])
    if isinstance(props.get("view:sun_elevation"), int | float):
        return 90.0 - float(props["view:sun_elevation"])
    return math.nan


def parse(item: Mapping[str, Any], name: SourceName, source: Source) -> Scene:
    """One item as a scene whose assets carry D15's logical names (and a scale).

    Args:
        item: The STAC item.
        name: Its source.
        source: The source settings.

    Returns:
        The scene.
    """
    keys = logical_keys(source)
    scene = parse_item(item, AssetKeys(scl=keys["scl"], red=keys["red"], green=keys["green"],
                                       swir16=keys["swir16"]))  # fmt: skip
    assets = {**scene.assets, **extra_assets(item, {k: v for k, v in keys.items()
                                                    if k not in CORE})}  # fmt: skip
    if name == "planetary-computer":
        assets = {k: (v if k == "scl" else esa_scaled(v, scene.processing_baseline))
                  for k, v in assets.items()}  # fmt: skip
    return dataclasses.replace(scene, assets=assets)


def search(
    cfg: QualityConfig, name: SourceName, bbox: tuple[float, float, float, float], start: date,
    end: date,
) -> tuple[list[Acquisition], dict[str, float]]:  # fmt: skip
    """Acquisitions of one source over a box, and the sun zenith of each item.

    Args:
        cfg: The v2 settings.
        name: The source.
        bbox: West, south, east, north.
        start: First day.
        end: Last day.

    Returns:
        Acquisitions (newest processing per tile) and item id -> sun zenith.
    """
    source = cfg.imagery.sources[name]
    scenes, sun = [], {}
    for item in search_items(source.url, source.collection, bbox, start, end, 100):
        try:
            scenes.append(parse(item, name, source))
        except (KeyError, TypeError, ValueError) as error:
            log.warning("skipping item %s: %s", item.get("id", "?"), error)
            continue
        sun[str(item["id"])] = sun_zenith(item.get("properties", {}))
    return group_acquisitions(scenes), sun


def acquisition_sun(acquisition: Acquisition, sun: Mapping[str, float]) -> float:
    """The mean sun zenith of an acquisition's items.

    Args:
        acquisition: The pass.
        sun: Item id -> sun zenith.

    Returns:
        Degrees (NaN when unknown).
    """
    values = [
        sun[s.item_id] for s in acquisition.scenes if math.isfinite(sun.get(s.item_id, math.nan))
    ]
    return sum(values) / len(values) if values else math.nan


def reader(screening: ScreeningConfig, name: SourceName, cache: Path) -> AcquisitionReader:
    """A band reader for one source; only SCL windows are cached (they are small).

    Args:
        screening: Screening settings (STAC sources, signing).
        name: The source.
        cache: Cache folder.

    Returns:
        The reader.
    """
    source = make_source(name, screening.stac.sources, screening.stac.page_size)
    return AcquisitionReader(source, cache / "quality-bands" / name, ("scl",))


def small_windows(geometry: StationGeometry, cfg: QualityConfig) -> Windows:
    """The 300 m window (D15's) and the core window, on a +-400 m grid.

    Args:
        geometry: A selected station.
        cfg: The v2 settings.

    Returns:
        The windows.

    Raises:
        ValueError: If the station did not snap.
    """
    if geometry.snapped is None:
        raise ValueError(f"{geometry.station_id}: not snapped")
    res = geometry.grid.resolution
    half = math.ceil(cfg.imagery.read_half_size_m / res) + 2
    grid, (r0, c0) = extract.sub_grid(geometry.grid, geometry.snapped, half)
    main = geometry.main[r0 : r0 + grid.height, c0 : c0 + grid.width]
    center = (geometry.snapped[0] - r0, geometry.snapped[1] - c0)
    w = cfg.window
    radius = w.radius_m / res
    return Windows(grid, {
        "300m": window_mask(main, center, radius, w.erosion_px),
        "core": window_mask(main, center, radius, math.ceil(w.core_min_distance_m / res)),
    })  # fmt: skip


def utc_date(acquisition: Acquisition) -> date:
    """The acquisition's UTC date (the source split is on UTC dates).

    Args:
        acquisition: The pass.

    Returns:
        The date.
    """
    return acquisition.datetime.astimezone(UTC).date()
