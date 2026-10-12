"""One scene of a reach: NDTI and NIR/red per sub-reach, and the estimate station's window.

The sub-reaches are the screening's, from the water frequency of the frozen geometry period; the
scene is read only over the box around them. The estimate station's 300 m and core windows are
the water-quality validation's (D15's station geometry), so the model cards see the features they
were fitted on.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
from numpy.typing import NDArray

from climate_pipeline.calibration import extract
from climate_pipeline.calibration.config import CalibrationConfig
from climate_pipeline.calibration.matchups import SceneRow, candidate_values
from climate_pipeline.contract.observation import item_json_url
from climate_pipeline.quality import features, values
from climate_pipeline.quality.config import QualityConfig
from climate_pipeline.quality.route_a import STAT_NAMES
from climate_pipeline.reach.records import Item, Measure
from climate_pipeline.screening import stage1
from climate_pipeline.screening.bands import read_reflectance
from climate_pipeline.screening.config import ScreeningConfig
from climate_pipeline.screening.rio import AcquisitionReader, Grid, read_to_grid
from climate_pipeline.screening.stac import Acquisition
from climate_pipeline.screening.stage1 import Stage1Result
from climate_pipeline.screening.stage2 import measure_acquisition, subreach_nir_red

BANDS = ("B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12")


class MemoReader(AcquisitionReader):
    """A reader that keeps a scene's arrays in memory until :meth:`forget` (each band read once)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Create the reader (same arguments as :class:`AcquisitionReader`).

        Args:
            *args: Positional arguments of the reader.
            **kwargs: Keyword arguments of the reader.
        """
        super().__init__(*args, **kwargs)
        self._memo: dict[tuple[str, str, str], tuple[NDArray[np.generic], dict[str, int]]] = {}

    def read(
        self,
        acquisition: Acquisition,
        asset: str,
        grid: Grid,
        reader: Callable[[str, Grid], NDArray[np.generic]] = read_to_grid,
    ) -> tuple[NDArray[np.generic], dict[str, int]]:
        """Read once per scene, asset and grid (see :meth:`AcquisitionReader.read`).

        Args:
            acquisition: The pass.
            asset: Logical asset name.
            grid: Target grid.
            reader: Function reading one href onto the grid.

        Returns:
            The merged array and the pixels each item filled.
        """
        key = ("|".join(s.item_id for s in acquisition.scenes), asset, grid.key())
        if key not in self._memo:
            self._memo[key] = super().read(acquisition, asset, grid, reader)
        return self._memo[key]

    def forget(self, acquisition: Acquisition) -> None:
        """Drop the arrays of one acquisition's items.

        Args:
            acquisition: The pass.
        """
        ids = {s.item_id for s in acquisition.scenes}
        for key in [k for k in self._memo if set(k[0].split("|")) <= ids]:
            del self._memo[key]


def corridor(result: Stage1Result, margin_px: int = 8) -> Stage1Result:
    """The stage-1 result cropped to the box around its sub-reaches, plus a margin.

    The margin exceeds the bank erosion, so every sub-reach measures the same pixels as on the
    full grid; only fewer COG blocks are read.

    Args:
        result: The reach's stage-1 result (20 m grid).
        margin_px: Margin in 20 m pixels.

    Returns:
        The cropped result.
    """
    union = np.zeros(result.grid.shape, dtype=bool)
    for s in result.geometry.subreaches:
        union |= s.mask
    rows, cols = np.nonzero(union)
    g = result.grid
    r0, c0 = max(0, int(rows.min()) - margin_px), max(0, int(cols.min()) - margin_px)
    r1 = min(g.height, int(rows.max()) + margin_px + 1)
    c1 = min(g.width, int(cols.max()) + margin_px + 1)
    grid = Grid(g.epsg, g.resolution, g.x0 + c0 * g.resolution, g.y0 - r0 * g.resolution,
                c1 - c0, r1 - r0)  # fmt: skip
    subreaches = tuple(
        dataclasses.replace(s, mask=s.mask[r0:r1, c0:c1], land_ring=s.land_ring[r0:r1, c0:c1])
        for s in result.geometry.subreaches
    )
    geometry = dataclasses.replace(result.geometry, subreaches=subreaches,
                                   river_mask=result.geometry.river_mask[r0:r1, c0:c1],
                                   corridor=None)  # fmt: skip
    return dataclasses.replace(result, grid=grid, geometry=geometry, frequency=None)


def observable(acquisition: Acquisition, reader: AcquisitionReader, result: Stage1Result,
               screening: ScreeningConfig) -> bool:  # fmt: skip
    """The screening's observable rule on the scene's SCL (read first, and cached).

    Args:
        acquisition: The pass.
        reader: Reader caching SCL.
        result: The reach's stage-1 result (full grid).
        screening: Screening settings.

    Returns:
        Whether stage 2 measures it.
    """
    scl, _ = reader.read(acquisition, "scl", result.grid)
    return stage1.classify_scene(stage1.measure_scene(scl, result.geometry, screening),
                                 screening)[1]  # fmt: skip


def items(acquisition: Acquisition) -> tuple[Item, ...]:
    """The STAC items behind a scene.

    Args:
        acquisition: The pass.

    Returns:
        One item per tile.
    """
    return tuple(
        Item(s.item_id, item_json_url(s.item_id),
             f"{s.processing_baseline:05.2f}" if s.processing_baseline is not None else "unknown",
             s.boa_offset_applied)
        for s in acquisition.scenes
    )  # fmt: skip


def nir_red(result: Stage1Result, acquisition: Acquisition, reader: AcquisitionReader,
            screening: ScreeningConfig) -> dict[str, float]:  # fmt: skip
    """NIR/red per sub-reach (the bands NDTI read come from the reader's memory).

    Args:
        result: The cropped stage-1 result.
        acquisition: The pass.
        reader: The scene's reader.
        screening: Screening settings.

    Returns:
        Sub-reach -> B8A/B04.
    """
    grid20 = result.grid
    grid10 = grid20.with_resolution(10.0)
    erosion = (result.site.erosion_px_10m if result.site.erosion_px_10m is not None
               else screening.mask.erosion_px_10m)  # fmt: skip
    scl, _ = reader.read(acquisition, "scl", grid20)
    red, _ = read_reflectance(reader, acquisition, "red", grid10)
    green, _ = read_reflectance(reader, acquisition, "green", grid10)
    swir, _ = read_reflectance(reader, acquisition, "swir16", grid20)
    nir, _ = read_reflectance(reader, acquisition, "nir08", grid20)
    return {s.name: subreach_nir_red(red, green, nir, swir, scl, s.mask, erosion, screening)
            for s in result.geometry.subreaches}  # fmt: skip


@dataclass(frozen=True)
class Station:
    """The estimate station: its windows and main-channel width."""

    station_id: str
    width_m: float
    windows: extract.Windows


def scene_rows(rows: list[dict[str, Any]], station: Station, quality: QualityConfig
               ) -> dict[str, SceneRow]:  # fmt: skip
    """The station's window rows as scenes with the feature set F.

    Args:
        rows: One row per window (from :func:`values.measure`).
        station: The station.
        quality: The v2 settings.

    Returns:
        Window -> scene.
    """
    scenes: dict[str, list[SceneRow]] = {}
    for row in rows:
        bands = {b: float(row.get(b, math.nan)) for b in BANDS}
        stats = {k: float(row.get(k, math.nan)) for k in STAT_NAMES}
        scenes[str(row["window"])] = [SceneRow(
            station=station.station_id, collection=str(row["source"]), key=str(row["key"]),
            day=date.fromisoformat(str(row["local_date"])), family=str(row["family"]),
            stats=stats, bands=bands, features=candidate_values(bands, None),
        )]  # fmt: skip
    if set(scenes) != {"300m", "core"}:
        return {}
    full = features.with_features(quality.features, scenes, {station.station_id: station.width_m})
    return {w: s[0] for w, s in full.items()}


def measure(acquisition: Acquisition, reader: MemoReader, result: Stage1Result,
            station: Station | None, window: str, sun: Mapping[str, float],
            quality: QualityConfig, d15: CalibrationConfig,
            screening: ScreeningConfig) -> Measure:  # fmt: skip
    """Everything a record needs from one observable scene.

    Args:
        acquisition: The pass.
        reader: The scene's reader (Earth Search, every band).
        result: The cropped stage-1 result.
        station: The estimate station (None: no estimate).
        window: The model cards' window (``300m`` or ``core``).
        sun: Item id -> sun zenith.
        quality: The v2 settings.
        d15: D15's settings (window guards).
        screening: Screening settings.

    Returns:
        The measure.
    """
    scene = measure_acquisition(result, acquisition, reader, screening)
    ratio = nir_red(result, acquisition, reader, screening) if not scene.exclusion else {}
    row: Mapping[str, float] = {}
    stats: Mapping[str, float] = {}
    problem = "no estimate station"
    if station is not None:
        try:
            rows = values.measure(acquisition, "earth-search", reader, station.windows,
                                  station.station_id, sun, d15, screening,
                                  quality.timezone)  # fmt: skip
            scenes = scene_rows(rows, station, quality)
            problem = "" if window in scenes else "the station's windows were not measured"
            if window in scenes:
                row, stats = scenes[window].features, scenes[window].stats
        except Exception as error:  # a failed window read is an abstention, not a failed run
            problem = f"window read failed: {error}"
    reader.forget(acquisition)
    return Measure(
        key=acquisition.key, day=extract.local_date(acquisition, quality.timezone),
        items=items(acquisition), exclusion=scene.exclusion,
        ndti={name: s.ndti for name, s in scene.sub.items()}, nir_red=ratio,
        window=row, stats=stats, window_problem=problem,
    )  # fmt: skip
