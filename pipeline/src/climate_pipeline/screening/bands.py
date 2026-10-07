"""Surface reflectance from an acquisition's items, each scaled with its own STAC metadata."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from functools import partial

import numpy as np
from numpy.typing import NDArray

from climate_pipeline.screening.rio import AcquisitionReader, Grid, read_to_grid
from climate_pipeline.screening.stac import Acquisition, ScalingError, reflectance_scaling

Reflectance = NDArray[np.float32]
"""Reflectance arrays are float32: a 10 m AOI band is tens of millions of values."""

read_average: Callable[[str, Grid], NDArray[np.generic]] = partial(
    read_to_grid, resampling="average"
)
"""Reads a band averaged onto a coarser grid (e.g. 10 m green onto the 20 m grid)."""


def to_reflectance(dn: NDArray[np.generic], scale: float, offset: float) -> Reflectance:
    """Digital numbers to reflectance (0 is no data and becomes NaN).

    Args:
        dn: Digital numbers.
        scale: From the item's ``raster:bands``.
        offset: From the item's ``raster:bands``.

    Returns:
        Reflectance.
    """
    values = dn.astype(np.float32) * np.float32(scale) + np.float32(offset)
    values[dn == 0] = np.nan
    return values


def read_reflectance(
    reader: AcquisitionReader,
    acquisition: Acquisition,
    asset: str,
    grid: Grid,
    read: Callable[[str, Grid], NDArray[np.generic]] = read_to_grid,
) -> tuple[Reflectance, list[str]]:
    """Read one band as reflectance, scaling each item with its own metadata before merging.

    Args:
        reader: Band reader.
        acquisition: The pass.
        asset: ``red``, ``green`` or ``swir16``.
        grid: Target grid.
        read: Function reading one href onto the grid (e.g. :data:`read_average`).

    Returns:
        Reflectance (NaN = no data) and the problems met (items without scaling).
    """
    merged = np.full(grid.shape, np.nan, dtype=np.float32)
    problems = []
    for scene in acquisition.scenes:
        try:
            scale, offset = reflectance_scaling(scene, asset)
        except ScalingError as error:
            problems.append(str(error))
            continue
        single = dataclasses.replace(acquisition, scenes=(scene,))
        dn, _ = reader.read(single, asset, grid, reader=read)
        values = to_reflectance(dn, scale, offset)
        gap = np.isnan(merged) & np.isfinite(values)
        merged[gap] = values[gap]
    return merged, problems
