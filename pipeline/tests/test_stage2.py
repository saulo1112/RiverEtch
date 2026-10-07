import math
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from synthetic import draw, frequency

from climate_pipeline.screening.bands import to_reflectance
from climate_pipeline.screening.config import load_screening_config
from climate_pipeline.screening.mask import derive_geometry
from climate_pipeline.screening.stage2 import (
    reflectance_problem,
    robust_z,
    subreach_ndti,
)

CONFIG = load_screening_config(Path(__file__).parents[1] / "screening.yaml")


def geometry() -> tuple[np.ndarray, list[np.ndarray]]:
    river = np.zeros((300, 1000), dtype=bool)
    draw(river, [(150, 10), (150, 990)], half=4)
    geom = derive_geometry(
        frequency(river), resolution=20.0, thresholds=(0.5,), upstream=(150, 12),
        downstream=(150, 988), center=(150, 500), confluences={}, excluded=None,
        snap_radius_m=1500, corridor_half_width_m=600, erosion_px_10m=1,
        land_ring_m=(100, 400), subreach=CONFIG.subreach,
    )  # fmt: skip
    return river, [s.mask for s in geom.subreaches]


def bands(river: np.ndarray, red: float, green: float, swir: float) -> tuple[np.ndarray, ...]:
    fine = np.repeat(np.repeat(river, 2, axis=0), 2, axis=1)
    r = np.where(fine, red, 0.05).astype(np.float32)
    g = np.where(fine, green, 0.08).astype(np.float32)
    s = np.where(river, swir, 0.2).astype(np.float32)
    scl = np.where(river, 6, 4).astype(np.uint8)
    return r, g, s, scl


def test_reflectance_uses_the_items_scale_and_offset() -> None:
    dn = np.array([0, 1400, 10000], dtype=np.uint16)
    values = to_reflectance(dn, 1e-4, -0.1)
    assert math.isnan(values[0])
    assert values[1] == pytest.approx(0.04) and values[2] == pytest.approx(0.9)


def test_ndti_median_and_guards() -> None:
    river, subs = geometry()
    red, green, swir, scl = bands(river, 0.04, 0.055, 0.01)
    stats = subreach_ndti(red, green, swir, scl, subs[0], 1, CONFIG)
    assert stats.ndti == pytest.approx((0.04 - 0.055) / 0.095, abs=1e-4)
    assert stats.class6_share == 1 and stats.glint_share == 0
    glinted = subreach_ndti(
        red, green, np.where(river, 0.2, 0.2).astype(np.float32), scl, subs[0], 1, CONFIG
    )
    assert math.isnan(glinted.ndti) and glinted.glint_share == 1
    no_b11 = subreach_ndti(red, green, np.full_like(swir, np.nan), scl, subs[0], 1, CONFIG)
    assert math.isnan(no_b11.ndti) and no_b11.pixels == 0


def test_implausible_water_reflectance_is_reported() -> None:
    river, subs = geometry()
    red, green, swir, scl = bands(river, -0.02, 0.03, 0.01)
    stats = {"upstream": subreach_ndti(red, green, swir, scl, subs[0], 1, CONFIG)}
    assert "outside" in reflectance_problem(stats, CONFIG)


def test_robust_z_is_leave_one_out_with_a_mad_floor() -> None:
    days = [date(2023, 1, 1 + i) for i in range(20)]
    values = [0.1] * 19 + [0.5]
    zs, groups = robust_z(values, days, set(), [], CONFIG)
    assert zs[-1] == pytest.approx((0.5 - 0.1) / CONFIG.stage2.mad_floor)
    assert zs[0] == pytest.approx(0.0)
    assert set(groups) == {"season"}


def test_robust_z_reports_an_insufficient_baseline() -> None:
    days = [date(2023, 1, 1 + i) for i in range(5)]
    zs, groups = robust_z([0.1, 0.2, 0.1, 0.3, 0.1], days, set(), [], CONFIG)
    assert all(math.isnan(z) for z in zs)
    assert set(groups) == {"insufficient"}


def test_robust_z_splits_at_regime_changes() -> None:
    days = [date(2022, 1, 1) + (date(2022, 1, 2) - date(2022, 1, 1)) * i * 10 for i in range(60)]
    regime = date(2022, 11, 1)
    values = [0.0 if d < regime else 0.2 for d in days]
    zs, groups = robust_z(values, days, set(), [regime], CONFIG)
    assert all(abs(z) < 1e-9 for z in zs)
    assert set(groups) <= {"regime+season", "regime"}
