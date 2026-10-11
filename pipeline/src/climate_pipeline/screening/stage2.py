"""Stage 2: NDTI series, robust baselines and anomalies on the selected sites.

NDTI = (red - green) / (red + green) on surface reflectance. It is a relative index: its level
is not comparable between sites, only changes within one sub-reach mean anything, and it is never
converted to turbidity units. Reflectance is DN * scale + offset with each item's own scale and
offset; a scene whose water is not near 0 in B11 and small and positive in red and green is
excluded and listed.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np
from numpy.typing import NDArray

from climate_pipeline.screening.bands import Reflectance, read_reflectance
from climate_pipeline.screening.config import ScreeningConfig, SiteConfig
from climate_pipeline.screening.mask import erode, upsample2
from climate_pipeline.screening.rain import rain_context
from climate_pipeline.screening.rio import AcquisitionReader
from climate_pipeline.screening.stac import Acquisition
from climate_pipeline.screening.stage1 import Stage1Result

log = logging.getLogger(__name__)

SIGNALS = ("upstream", "downstream", "delta")
"""Anomaly signals: each sub-reach's NDTI and the downstream-minus-upstream difference."""

MAD_TO_SIGMA = 1.4826

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class SubreachNdti:
    """NDTI statistics of one sub-reach in one scene (NaN when too few pixels)."""

    pixels: int
    ndti: float
    red: float
    green: float
    swir16: float
    class6_share: float
    glint_share: float


@dataclass
class Stage2Scene:
    """One observable acquisition in stage 2."""

    key: str
    datetime: datetime
    platform: str
    scaling: tuple[str, ...]
    exclusion: str
    sub: dict[str, SubreachNdti]
    rain_mm: dict[int, float] = field(default_factory=dict)
    rain_same_day_mm: float = math.nan
    rain_coincident: bool = False
    z: dict[str, float] = field(default_factory=dict)
    baseline: dict[str, str] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        """Not excluded."""
        return not self.exclusion

    @property
    def values(self) -> dict[str, float]:
        """NDTI per signal (the difference only when both sub-reaches are valid)."""
        up = self.sub["upstream"].ndti if "upstream" in self.sub else math.nan
        down = self.sub["downstream"].ndti if "downstream" in self.sub else math.nan
        return {"upstream": up, "downstream": down, "delta": down - up}

    def anomalous(self, threshold: float) -> tuple[str, ...]:
        """Signals whose robust z reaches the threshold.

        Args:
            threshold: |z| threshold.

        Returns:
            Signal names.
        """
        return tuple(s for s in SIGNALS if abs(self.z.get(s, math.nan)) >= threshold)


# ----------------------------------------------------------------------------------------------
# Pixels to NDTI
# ----------------------------------------------------------------------------------------------


def repeat2(array: NDArray[np.generic]) -> NDArray[np.generic]:
    """A 20 m array on the nested 10 m grid.

    Args:
        array: Array on the 20 m grid.

    Returns:
        Each value repeated over its 2 x 2 block.
    """
    return np.repeat(np.repeat(array, 2, axis=0), 2, axis=1)


def subreach_ndti(
    red: Reflectance,
    green: Reflectance,
    swir16_20m: Reflectance,
    scl_20m: NDArray[np.generic],
    subreach_20m: NDArray[np.bool_],
    erosion_px_10m: int,
    cfg: ScreeningConfig,
) -> SubreachNdti:
    """NDTI median over one sub-reach's usable water pixels.

    Usable: inside the eroded sub-reach, SCL not invalid or no data (whatever class SCL gives the
    water), red, green and B11 all present, red + green above a floor, and B11 at or below the
    glint threshold.

    Args:
        red: Red reflectance on the 10 m grid.
        green: Green reflectance on the 10 m grid.
        swir16_20m: B11 reflectance on the 20 m grid.
        scl_20m: SCL on the 20 m grid.
        subreach_20m: The sub-reach on the 20 m grid.
        erosion_px_10m: Bank erosion at 10 m.
        cfg: Settings.

    Returns:
        The statistics (NaN values with fewer than ``min_valid_px_10m`` pixels).
    """
    limit = cfg.stage2.swir16_max
    return subreach_ndti_variants(
        red, green, swir16_20m, scl_20m, subreach_20m, erosion_px_10m, cfg, (limit,)
    )[limit]


def subreach_ndti_variants(
    red: Reflectance,
    green: Reflectance,
    swir16_20m: Reflectance,
    scl_20m: NDArray[np.generic],
    subreach_20m: NDArray[np.bool_],
    erosion_px_10m: int,
    cfg: ScreeningConfig,
    swir16_limits: Sequence[float],
) -> dict[float, SubreachNdti]:
    """NDTI medians over one sub-reach for several pixel glint limits, from one set of arrays.

    Everything but the glint guard is shared: the plausibility medians use every water pixel
    before the darkness and glint guards, and the glint share of a limit is the share of guarded
    pixels above it.

    Args:
        red: Red reflectance on the 10 m grid.
        green: Green reflectance on the 10 m grid.
        swir16_20m: B11 reflectance on the 20 m grid.
        scl_20m: SCL on the 20 m grid.
        subreach_20m: The sub-reach on the 20 m grid.
        erosion_px_10m: Bank erosion at 10 m.
        cfg: Settings.
        swir16_limits: B11 glint limits (the screening's is ``cfg.stage2.swir16_max``).

    Returns:
        The statistics by glint limit.
    """
    scl, swir, water, base = _guarded(
        red, green, swir16_20m, scl_20m, subreach_20m, erosion_px_10m, cfg
    )
    # The plausibility medians use every water pixel, before the darkness and glint guards, so
    # a wrong offset that makes water dark or negative is reported instead of filtered away.
    enough = int(water.sum()) >= cfg.clear.min_valid_px_10m
    red_median = float(np.median(red[water])) if enough else math.nan
    green_median = float(np.median(green[water])) if enough else math.nan
    with_swir = water & np.isfinite(swir)
    enough_swir = int(with_swir.sum()) >= cfg.clear.min_valid_px_10m
    swir_median = float(np.median(swir[with_swir])) if enough_swir else math.nan
    n_base = int(base.sum())
    out: dict[float, SubreachNdti] = {}
    for limit in swir16_limits:
        glint = base & (swir > limit)
        use = base & ~glint
        n = int(use.sum())
        glint_share = float(glint.sum()) / n_base if n_base else math.nan
        if n < cfg.clear.min_valid_px_10m:
            out[limit] = SubreachNdti(
                n, math.nan, red_median, green_median, swir_median, math.nan, glint_share
            )
            continue
        r, g = red[use], green[use]
        ndti = (r - g) / (r + g)
        out[limit] = SubreachNdti(
            pixels=n,
            ndti=float(np.median(ndti)),
            red=red_median,
            green=green_median,
            swir16=swir_median,
            class6_share=float(np.isin(scl[use], cfg.scl.water).mean()),
            glint_share=glint_share,
        )
    return out


def _guarded(
    red: Reflectance,
    green: Reflectance,
    swir16_20m: Reflectance,
    scl_20m: NDArray[np.generic],
    subreach_20m: NDArray[np.bool_],
    erosion_px_10m: int,
    cfg: ScreeningConfig,
) -> tuple[NDArray[np.generic], Reflectance, NDArray[np.bool_], NDArray[np.bool_]]:
    """SCL and B11 on the 10 m grid, the water pixels, and those passing the darkness guard."""
    area = erode(upsample2(subreach_20m), erosion_px_10m)
    scl = repeat2(scl_20m)
    swir = repeat2(swir16_20m).astype(np.float32, copy=False)
    excluded = np.array(sorted(set(cfg.scl.invalid) | set(cfg.scl.nodata)))
    water = area & ~np.isin(scl, excluded) & np.isfinite(red) & np.isfinite(green)
    base = water & np.isfinite(swir) & ((red + green) > cfg.stage2.rg_floor)
    return scl, swir, water, base


def subreach_nir_red(
    red: Reflectance,
    green: Reflectance,
    nir08_20m: Reflectance,
    swir16_20m: Reflectance,
    scl_20m: NDArray[np.generic],
    subreach_20m: NDArray[np.bool_],
    erosion_px_10m: int,
    cfg: ScreeningConfig,
) -> float:
    """NIR/red (B8A/B04) of one sub-reach: the median B8A over the median red.

    The pixels are those :func:`subreach_ndti` takes its median over, with B8A present. It is a
    ratio of medians, as the water-quality features (D16) compute B8A/B04 in a window. Like NDTI
    it is a relative index, never a unit.

    Args:
        red: Red reflectance on the 10 m grid.
        green: Green reflectance on the 10 m grid.
        nir08_20m: B8A reflectance on the 20 m grid.
        swir16_20m: B11 reflectance on the 20 m grid.
        scl_20m: SCL on the 20 m grid.
        subreach_20m: The sub-reach on the 20 m grid.
        erosion_px_10m: Bank erosion at 10 m.
        cfg: Settings.

    Returns:
        The ratio (NaN with fewer than ``min_valid_px_10m`` pixels or a red median at or below 0).
    """
    _, swir, _, base = _guarded(red, green, swir16_20m, scl_20m, subreach_20m, erosion_px_10m, cfg)
    nir = repeat2(nir08_20m).astype(np.float32, copy=False)
    use = base & ~(swir > cfg.stage2.swir16_max) & np.isfinite(nir)
    if int(use.sum()) < cfg.clear.min_valid_px_10m:
        return math.nan
    red_median = float(np.median(red[use]))
    return float(np.median(nir[use])) / red_median if red_median > 0 else math.nan


def reflectance_problem(sub: dict[str, SubreachNdti], cfg: ScreeningConfig) -> str:
    """Why a scene's water reflectance is implausible (empty if it is fine).

    Water absorbs SWIR, so its B11 reflectance is near 0: a median far below 0 means the BOA
    offset was applied twice, far above it that the offset is missing (or strong glint). Water
    should also be dark: small and positive in red and green. Negative or large values there
    point to a wrong offset, cloud or haze the SCL missed, or a misplaced mask.

    Args:
        sub: Statistics per sub-reach.
        cfg: Settings.

    Returns:
        A reason, or an empty string.
    """
    low, high = cfg.stage2.water_swir16_range
    for name, s in sub.items():
        if math.isfinite(s.swir16) and not (low <= s.swir16 <= high):
            cause = "offset applied twice?" if s.swir16 < low else "glint or a missing offset"
            return (
                f"{name} median B11 water reflectance {s.swir16:.3f} outside [{low}, {high}]"
                f" ({cause})"
            )
    top = cfg.stage2.water_reflectance_max
    for name, s in sub.items():
        for band, value in (("red", s.red), ("green", s.green)):
            if math.isfinite(value) and not (0 < value <= top):
                return f"{name} median {band} reflectance {value:.3f} outside (0, {top}]"
    return ""


# ----------------------------------------------------------------------------------------------
# Baselines
# ----------------------------------------------------------------------------------------------


def robust_z(
    values: Sequence[float],
    days: Sequence[date],
    rainy: set[int],
    regimes: Sequence[date],
    cfg: ScreeningConfig,
) -> tuple[list[float], list[str]]:
    """Leave-one-out robust z-scores with seasonal and regime-aware baselines.

    For each value the baseline is the first group, in this order, with enough other values:
    same regime and season, same regime, same season, all. Season groups need ``min_season_n``
    values, the others ``min_baseline_n``; otherwise the score is NaN ("insufficient").
    sigma = max(1.4826 * MAD, mad_floor).

    Args:
        values: One value per scene (NaN allowed).
        days: The scenes' days.
        rainy: Rainy-season months.
        regimes: Dates where a dam's operating regime changed (sorted).
        cfg: Settings.

    Returns:
        z-scores and the baseline group used for each value.
    """
    s2 = cfg.stage2
    x = np.array(values, dtype=np.float64)
    season = np.array(["rainy" if d.month in rainy else "dry" for d in days])
    regime = np.array([sum(1 for r in regimes if d >= r) for d in days])
    finite = np.isfinite(x)
    zs: list[float] = []
    groups: list[str] = []
    for i, value in enumerate(x):
        if not finite[i]:
            zs.append(math.nan)
            groups.append("")
            continue
        others = finite.copy()
        others[i] = False
        options = [
            (
                "regime+season",
                others & (regime == regime[i]) & (season == season[i]),
                s2.min_season_n,
            ),
            ("regime", others & (regime == regime[i]), s2.min_baseline_n),
            ("season", others & (season == season[i]), s2.min_season_n),
            ("all", others, s2.min_baseline_n),
        ]
        if not regimes:
            options = [options[2], options[3]]
        for label, sel, minimum in options:
            if int(sel.sum()) >= minimum:
                ref = x[sel]
                median = float(np.median(ref))
                mad = float(np.median(np.abs(ref - median)))
                sigma = max(MAD_TO_SIGMA * mad, s2.mad_floor)
                zs.append((float(value) - median) / sigma)
                groups.append(label)
                break
        else:
            zs.append(math.nan)
            groups.append("insufficient")
    return zs, groups


# ----------------------------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------------------------


def measure_acquisition(
    result: Stage1Result,
    acquisition: Acquisition,
    reader: AcquisitionReader,
    cfg: ScreeningConfig,
) -> Stage2Scene:
    """NDTI per sub-reach for one acquisition, with the empirical reflectance check.

    Args:
        result: The site's stage-1 result (grid, geometry).
        acquisition: The pass.
        reader: Cached band reader.
        cfg: Settings.

    Returns:
        The scene (``exclusion`` explains a rejection).
    """
    limit = cfg.stage2.swir16_max
    return measure_acquisition_variants(result, acquisition, reader, cfg, (limit,))[limit]


def measure_acquisition_variants(
    result: Stage1Result,
    acquisition: Acquisition,
    reader: AcquisitionReader,
    cfg: ScreeningConfig,
    swir16_limits: Sequence[float],
) -> dict[float, Stage2Scene]:
    """NDTI per sub-reach for one acquisition and several pixel glint limits, from one read.

    Args:
        result: The site's stage-1 result (grid, geometry).
        acquisition: The pass.
        reader: Cached band reader.
        cfg: Settings.
        swir16_limits: B11 glint limits.

    Returns:
        The scene by glint limit (``exclusion`` explains a rejection).
    """
    grid20 = result.grid
    grid10 = grid20.with_resolution(10.0)
    erosion = (
        result.site.erosion_px_10m
        if result.site.erosion_px_10m is not None
        else cfg.mask.erosion_px_10m
    )
    scl, _ = reader.read(acquisition, "scl", grid20)
    red, p1 = read_reflectance(reader, acquisition, "red", grid10)
    green, p2 = read_reflectance(reader, acquisition, "green", grid10)
    swir, p3 = read_reflectance(reader, acquisition, "swir16", grid20)
    scaling = tuple(s.scaling_status() for s in acquisition.scenes)
    per_subreach = {
        s.name: subreach_ndti_variants(red, green, swir, scl, s.mask, erosion, cfg, swir16_limits)
        for s in result.geometry.subreaches
    }
    read_problems = "; ".join(sorted(set(p1 + p2 + p3)))
    flagged = sorted({status for status in scaling if status in ("conflict", "missing")})
    scenes = {}
    for limit in swir16_limits:
        sub = {name: by_limit[limit] for name, by_limit in per_subreach.items()}
        exclusion = read_problems
        if not exclusion and flagged:
            # A wrong offset of +0.1 keeps water reflectance plausible but pulls NDTI toward 0,
            # so a scene whose metadata disagree is never used: it is listed instead.
            exclusion = f"scaling {'/'.join(flagged)} in item metadata"
        if not exclusion:
            exclusion = reflectance_problem(sub, cfg)
        # A sub-reach with too few pixels is missing for this scene; the scene goes only if
        # both are.
        if not exclusion and all(math.isnan(s.ndti) for s in sub.values()):
            exclusion = "too few usable water pixels in both sub-reaches after the pixel guards"
        scenes[limit] = Stage2Scene(
            key=acquisition.key,
            datetime=acquisition.datetime,
            platform=acquisition.platform,
            scaling=scaling,
            exclusion=exclusion,
            sub=sub,
        )
    return scenes


@dataclass
class Stage2Result:
    """Stage-2 output for one site."""

    site: SiteConfig
    scenes: list[Stage2Scene]
    truncated: int = 0

    def usable(self) -> list[Stage2Scene]:
        """Scenes that passed every check."""
        return [s for s in self.scenes if s.usable]

    def scores_by_day(self) -> dict[date, dict[str, float]]:
        """Largest |z| per signal and day (for event matching).

        Returns:
            Per day, z by signal (sign kept from the most extreme scene).
        """
        out: dict[date, dict[str, float]] = {}
        for scene in self.usable():
            day = scene.datetime.date()
            current = out.setdefault(day, {})
            for signal, z in scene.z.items():
                if math.isfinite(z) and (signal not in current or abs(z) > abs(current[signal])):
                    current[signal] = z
        return out


def observable_acquisitions(
    result: Stage1Result, cfg: ScreeningConfig
) -> tuple[list[Acquisition], int]:
    """The acquisitions stage 2 measures: the observable ones, up to the per-site cap.

    Args:
        result: The site's stage-1 result.
        cfg: Settings.

    Returns:
        The acquisitions, and how many observable ones the cap skipped.
    """
    observable_keys = {s.key for s in result.scenes if s.observable}
    chosen = [a for a in result.acquisitions if a.key in observable_keys]
    truncated = max(0, len(chosen) - cfg.stage2.max_scenes_per_site)
    if truncated:
        log.warning(
            "%s: %d observable scenes beyond the cap are skipped", result.site.id, truncated
        )
        chosen = chosen[: cfg.stage2.max_scenes_per_site]
    return chosen, truncated


def run_stage2_variants(
    result: Stage1Result,
    reader: AcquisitionReader,
    cfg: ScreeningConfig,
    swir16_limits: Sequence[float],
    workers: int = 8,
) -> dict[float, Stage2Result]:
    """NDTI of a site's observable acquisitions for several pixel glint limits, read once.

    The scenes carry no rain context and no z-scores: callers add the baselines they need.

    Args:
        result: The site's stage-1 result.
        reader: Cached band reader.
        cfg: Settings.
        swir16_limits: B11 glint limits.
        workers: Parallel reads.

    Returns:
        One stage-2 result per glint limit, with the same acquisitions in the same order.
    """
    chosen, truncated = observable_acquisitions(result, cfg)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        measured = list(
            pool.map(
                lambda a: measure_acquisition_variants(result, a, reader, cfg, swir16_limits),
                chosen,
            )
        )
    return {
        limit: Stage2Result(result.site, [m[limit] for m in measured], truncated)
        for limit in swir16_limits
    }


def run_stage2(
    result: Stage1Result,
    reader: AcquisitionReader,
    cfg: ScreeningConfig,
    workers: int = 8,
) -> Stage2Result:
    """Run stage 2 on one site's observable acquisitions.

    Args:
        result: The site's stage-1 result.
        reader: Cached band reader.
        cfg: Settings.
        workers: Parallel reads.

    Returns:
        Scenes with NDTI, rain context and robust z-scores.
    """
    limit = cfg.stage2.swir16_max
    second = run_stage2_variants(result, reader, cfg, (limit,), workers)[limit]
    scenes = second.scenes
    for scene in scenes:
        if result.rain:
            ctx = rain_context(result.rain, scene.datetime, cfg.rain.windows_h, cfg.rain.timezone)
            scene.rain_mm = {h: ctx.max_over_points(h) for h in cfg.rain.windows_h}
            scene.rain_same_day_mm = next(iter(ctx.same_day_mm.values()), math.nan)
            scene.rain_coincident = (
                scene.rain_mm.get(cfg.rain.coincident_window_h, math.nan) > cfg.rain.coincident_mm
            )
    usable = [s for s in scenes if s.usable]
    regimes = sorted(r.date for r in result.site.regime_changes if r.precision == "day")
    rainy = set(result.rainy_months)
    days = [s.datetime.date() for s in usable]
    for signal in SIGNALS:
        zs, groups = robust_z([s.values[signal] for s in usable], days, rainy, regimes, cfg)
        for scene, z, group in zip(usable, zs, groups, strict=True):
            scene.z[signal] = z
            scene.baseline[signal] = group
    return Stage2Result(result.site, scenes, second.truncated)


def false_alarm_rate(result: Stage2Result, threshold: float) -> tuple[float, int]:
    """Share of usable scenes with any anomalous signal (meant for the control site).

    Args:
        result: A site's stage-2 result.
        threshold: |z| threshold.

    Returns:
        The rate and the number of scenes with at least one z-score.
    """
    scored = [s for s in result.usable() if any(math.isfinite(z) for z in s.z.values())]
    if not scored:
        return math.nan, 0
    return sum(1 for s in scored if s.anomalous(threshold)) / len(scored), len(scored)


def ndti_map(
    result: Stage1Result,
    acquisition: Acquisition,
    reader: AcquisitionReader,
    cfg: ScreeningConfig,
) -> FloatArray:
    """NDTI over the whole eroded corridor at 10 m (NaN off the river or where a guard fails).

    Args:
        result: The site's stage-1 result.
        acquisition: The pass.
        reader: Cached band reader.
        cfg: Settings.

    Returns:
        The NDTI map on the 10 m grid.
    """
    grid20 = result.grid
    grid10 = grid20.with_resolution(10.0)
    corridor = result.geometry.corridor
    if corridor is None:
        return np.full(grid10.shape, np.nan)
    erosion = (
        result.site.erosion_px_10m
        if result.site.erosion_px_10m is not None
        else cfg.mask.erosion_px_10m
    )
    scl, _ = reader.read(acquisition, "scl", grid20)
    red, _ = read_reflectance(reader, acquisition, "red", grid10)
    green, _ = read_reflectance(reader, acquisition, "green", grid10)
    swir, _ = read_reflectance(reader, acquisition, "swir16", grid20)
    area = erode(upsample2(corridor & result.geometry.river_mask), erosion)
    excluded = np.array(sorted(set(cfg.scl.invalid) | set(cfg.scl.nodata)))
    use = area & ~np.isin(repeat2(scl), excluded) & np.isfinite(red) & np.isfinite(green)
    use &= (red + green) > cfg.stage2.rg_floor
    swir10 = repeat2(swir).astype(np.float32, copy=False)
    use &= np.isfinite(swir10) & (swir10 <= cfg.stage2.swir16_max)
    out = np.full(grid10.shape, np.nan)
    out[use] = (red[use] - green[use]) / (red[use] + green[use])
    return out
