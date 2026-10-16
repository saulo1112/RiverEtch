"""The active channel and the water fraction (preregistration v7, A)."""

import math

import numpy as np

from climate_pipeline.quality import surface


def test_connected8_keeps_diagonal_neighbours_and_drops_detached_patches() -> None:
    mask = np.array([
        [1, 0, 0, 0, 1],
        [0, 1, 0, 0, 1],
        [0, 0, 1, 0, 0],
    ], dtype=bool)  # fmt: skip
    seeds = np.zeros_like(mask)
    seeds[0, 0] = True
    out = surface.connected8(mask, seeds)
    assert out[1, 1] and out[2, 2]  # diagonal steps join
    assert not out[0, 4] and not out[1, 4]  # a separate patch (a sand-pit lake) stays out


def test_active_channel_needs_the_frequency_the_corridor_and_the_river() -> None:
    corridor = np.ones((3, 6), dtype=bool)
    corridor[:, 5] = False
    frequency = np.array([
        [0.9, 0.9, 0.9, 0.0, 0.9, 0.9],
        [0.04, 0.5, 0.06, 0.0, 0.9, 0.9],
        [np.nan, 0.2, 0.0, 0.0, 0.9, 0.9],
    ])  # fmt: skip
    river = np.zeros_like(corridor)
    river[0, 0:3] = True
    aoi = surface.active_channel(corridor, frequency, river)
    assert aoi[0, 0:3].all() and aoi[1, 1] and aoi[1, 2] and aoi[2, 1]
    assert not aoi[1, 0]  # wet only 4 % of the time
    assert not aoi[2, 0]  # too few observations
    assert not aoi[:, 4].any()  # wet, but not joined to the river (a lake)
    assert not aoi[:, 5].any()  # outside the corridor


def test_a_pass_is_clear_at_95_percent_of_the_area_of_interest() -> None:
    aoi = np.ones((4, 5), dtype=bool)
    scl = np.full((4, 5), 6)
    assert surface.is_clear(surface.clear_pixels(scl, aoi), aoi)
    scl[0, 0] = 9  # one cloudy pixel of 20: 95 % clear
    assert surface.is_clear(surface.clear_pixels(scl, aoi), aoi)
    scl[0, 1] = 0  # and one without data: 90 %
    assert not surface.is_clear(surface.clear_pixels(scl, aoi), aoi)


def test_water_counts_by_scl_and_by_mndwi() -> None:
    aoi = np.ones((2, 3), dtype=bool)
    scl = np.array([[6, 6, 5], [5, 4, 6]])
    clear = surface.clear_pixels(scl, aoi)
    index = surface.mndwi(np.array([[0.1, 0.1, 0.3], [0.1, 0.0, 0.2]]),
                          np.array([[0.05, 0.2, 0.1], [0.1, 0.0, 0.1]]))  # fmt: skip
    assert surface.water_counts(scl, clear, None) == (3, -1)
    # MNDWI > 0 at (0,0), (0,2) and (1,2); (1,1) is undefined; (1,0) is zero.
    assert surface.water_counts(scl, clear, index) == (3, 3)
    assert surface.fraction(3, 6) == 0.5
    assert math.isnan(surface.fraction(-1, 6)) and math.isnan(surface.fraction(0, 0))
