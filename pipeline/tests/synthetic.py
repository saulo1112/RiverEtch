"""Synthetic rivers and SCL scenes shared by the tests (no network, no real imagery)."""

import itertools
import math

import numpy as np
from numpy.typing import NDArray


def draw(mask: NDArray[np.bool_], points: list[tuple[float, float]], half: int) -> None:
    """Burn a thick polyline through (row, col) points into a mask."""
    for (r0, c0), (r1, c1) in itertools.pairwise(points):
        n = int(max(abs(r1 - r0), abs(c1 - c0))) + 1
        for t in np.linspace(0.0, 1.0, n):
            r, c = round(r0 + (r1 - r0) * t), round(c0 + (c1 - c0) * t)
            mask[max(0, r - half) : r + half + 1, max(0, c - half) : c + half + 1] = True


def meander(rows: int = 400, cols: int = 1000) -> list[tuple[float, float]]:
    """A sinuous centerline from the left edge to the right edge (~22 km at 20 m)."""
    cs = np.linspace(20, cols - 20, 200)
    return [(rows / 2 + 120 * math.sin(c / 90.0), float(c)) for c in cs]


def frequency(river: NDArray[np.bool_]) -> NDArray[np.float64]:
    """A water frequency that is high on the river and low elsewhere."""
    freq = np.where(river, 0.9, 0.05)
    freq[:5, :5] = np.nan
    return freq


def scl_scene(
    river: NDArray[np.bool_],
    *,
    river_class: int = 6,
    cloud: tuple[slice, slice] | None = None,
    cloud_class: int = 9,
    nodata_cols: slice | None = None,
) -> NDArray[np.uint8]:
    """An SCL array: vegetation (4) on land, ``river_class`` on the river, optional cloud/nodata."""
    scl = np.where(river, river_class, 4).astype(np.uint8)
    if cloud is not None:
        scl[cloud] = cloud_class
    if nodata_cols is not None:
        scl[:, nodata_cols] = 0
    return scl
