"""The water surface of a reach's active channel (preregistration v7, A).

Its area of interest is fixed once, from the frozen geometry: the corridor's pixels whose SCL water
frequency in the geometry period is at least 0.05, kept where they connect (8-connectivity) to the
river mask. That keeps the sand bars a braided river covers at high flow and drops the lakes that
do not join the channel. A pass is clear when at least 95 % of those pixels have data outside the
invalid SCL classes; its water fraction is then the share of clear pixels that are water, by SCL
class 6 and by MNDWI > 0.
"""

from __future__ import annotations

import math
from collections import deque

import numpy as np
from numpy.typing import NDArray

BoolArray = NDArray[np.bool_]

MIN_FREQUENCY = 0.05
MIN_CLEAR_SHARE = 0.95
INVALID_SCL = (1, 3, 8, 9, 10, 11)  # saturated, cloud shadow, cloud medium/high, cirrus, snow
WATER_SCL = 6
MNDWI_THRESHOLD = 0.0


def connected8(mask: BoolArray, seeds: BoolArray) -> BoolArray:
    """The 8-connected regions of ``mask`` that touch ``seeds``.

    Args:
        mask: Candidate pixels.
        seeds: Pixels to grow from (those outside the mask are ignored).

    Returns:
        The connected regions.
    """
    out = np.zeros_like(mask, dtype=bool)
    rows, cols = mask.shape
    start = np.argwhere(mask & seeds)
    queue = deque((int(r), int(c)) for r, c in start)
    for r, c in queue:
        out[r, c] = True
    while queue:
        r, c = queue.popleft()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and mask[nr, nc] and not out[nr, nc]:
                    out[nr, nc] = True
                    queue.append((nr, nc))
    return out


def active_channel(corridor: BoolArray, frequency: NDArray[np.floating],
                   river: BoolArray) -> BoolArray:  # fmt: skip
    """The area of interest: wet at least 5 % of the time, inside the corridor, joined to the river.

    Args:
        corridor: The frozen corridor (between the anchors).
        frequency: SCL water frequency of the geometry period (NaN: too few observations).
        river: The frozen river mask.

    Returns:
        The active channel.
    """
    freq = np.nan_to_num(np.asarray(frequency, dtype=float), nan=0.0)
    wet = corridor & (freq >= MIN_FREQUENCY)
    return connected8(wet, river & corridor)


def clear_pixels(scl: NDArray[np.integer], aoi: BoolArray) -> BoolArray:
    """The area of interest's pixels with data outside the invalid SCL classes.

    Args:
        scl: The pass's SCL on the site grid (0: no data).
        aoi: The area of interest.

    Returns:
        The clear pixels.
    """
    return np.asarray(aoi & (scl != 0) & ~np.isin(scl, INVALID_SCL), dtype=bool)


def is_clear(clear: BoolArray, aoi: BoolArray) -> bool:
    """Whether a pass is clear enough to measure (≥ 95 % of the area of interest).

    Args:
        clear: Its clear pixels.
        aoi: The area of interest.

    Returns:
        True when it passes the preregistered rule.
    """
    total = int(aoi.sum())
    return total > 0 and int(clear.sum()) >= MIN_CLEAR_SHARE * total


def mndwi(green: NDArray[np.floating], swir: NDArray[np.floating]) -> NDArray[np.float64]:
    """MNDWI = (green - SWIR) / (green + SWIR) (NaN where undefined).

    Args:
        green: B03 reflectance.
        swir: B11 reflectance.

    Returns:
        The index.
    """
    g = np.asarray(green, dtype=float)
    s = np.asarray(swir, dtype=float)
    total = g + s
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(total > 0, (g - s) / total, np.nan)
    return np.asarray(out, dtype=float)


def water_counts(scl: NDArray[np.integer], clear: BoolArray,
                 index: NDArray[np.floating] | None) -> tuple[int, int]:  # fmt: skip
    """Water pixels among the clear ones: by SCL class 6, and by MNDWI > 0.

    Args:
        scl: The pass's SCL.
        clear: Its clear pixels in the area of interest.
        index: Its MNDWI (None: not read).

    Returns:
        ``(scl_water, mndwi_water)``; the second is -1 when the index was not read.
    """
    scl_water = int((clear & (scl == WATER_SCL)).sum())
    if index is None:
        return scl_water, -1
    finite = np.isfinite(index)
    return scl_water, int((clear & finite & (index > MNDWI_THRESHOLD)).sum())


def fraction(water: int, clear: int) -> float:
    """The water fraction of the clear pixels (NaN when nothing is clear or the count is missing).

    Args:
        water: Water pixels (-1: missing).
        clear: Clear pixels.

    Returns:
        The fraction.
    """
    if clear <= 0 or water < 0:
        return math.nan
    return water / clear
