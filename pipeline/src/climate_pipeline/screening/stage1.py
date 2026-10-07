"""Stage 1: how often each candidate reach can be observed, from SCL only.

Pass 1 reads every acquisition's SCL onto the site grid and accumulates the water frequency;
the river, centerline and sub-reaches are derived from it. Pass 2 re-reads the cached SCL and
measures each sub-reach per acquisition. Two scene rules are reported:

* clear (the brief's rule, used in the score): each sub-reach has at least ``min_valid_px_10m``
  pixels SCL classifies as water, under ``max_contamination`` invalid pixels and at least
  ``min_data_coverage`` of its pixels with data;
* observable (used by stage 2): the same, but counting river-mask pixels that are not invalid,
  whatever class SCL gives them, because SCL often labels very turbid water as soil or
  "unclassified" and the clear rule would drop exactly the scenes that matter.
"""

from __future__ import annotations

import itertools
import logging
import math
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
from numpy.typing import NDArray

from climate_pipeline.screening.config import ScreeningConfig, SiteConfig
from climate_pipeline.screening.mask import FrequencyStack, RiverGeometry, derive_geometry
from climate_pipeline.screening.rain import OpenMeteoClient, RainSeries, rainy_months
from climate_pipeline.screening.rio import (
    AcquisitionReader,
    Grid,
    lonlat_rowcol,
    rasterize_polygon,
    rowcol_lonlat,
    site_grid,
)
from climate_pipeline.screening.stac import (
    Acquisition,
    SceneSource,
    evidence_hash,
    group_acquisitions,
)

log = logging.getLogger(__name__)

RAIN_LEAD_DAYS = 8
"""Rain is fetched from this many days before the period so the first 7-day windows are full."""


@dataclass(frozen=True)
class SubreachMetrics:
    """One sub-reach in one acquisition (pixel counts in 10 m equivalents)."""

    data_coverage: float
    water_px_10m: int
    valid_px_10m: int
    contamination: float
    class_shares: dict[int, float]
    river_cloud_share: float
    land_cloud_share: float
    suspect_turbid_as_cloud: bool


@dataclass(frozen=True)
class SceneMetrics:
    """One acquisition over one site."""

    key: str
    datetime: datetime
    platform: str
    relative_orbit: int | None
    tiles: tuple[str, ...]
    tiles_with_data: int
    scaling: tuple[str, ...]
    sub: dict[str, SubreachMetrics]
    clear: bool
    observable: bool
    full_coverage: bool
    has_data: bool


@dataclass
class Stage1Result:
    """Everything stage 1 learned about one site."""

    site: SiteConfig
    grid: Grid
    acquisitions: list[Acquisition]
    geometry: RiverGeometry
    scenes: list[SceneMetrics]
    rain: list[RainSeries]
    rainy_months: tuple[int, ...]
    summary: dict[str, object] = field(default_factory=dict)


def measure_scene(
    scl: NDArray[np.generic], geometry: RiverGeometry, cfg: ScreeningConfig
) -> dict[str, SubreachMetrics]:
    """Measure each sub-reach in one SCL array.

    Args:
        scl: SCL classes on the 20 m grid (0 = no data).
        geometry: The site's derived sub-reaches.
        cfg: Screening settings.

    Returns:
        Metrics per sub-reach name.
    """
    nodata = np.isin(scl, cfg.scl.nodata)
    invalid = np.isin(scl, cfg.scl.invalid)
    water = np.isin(scl, cfg.scl.water)
    cloud = np.isin(scl, cfg.scl.cloud)
    out = {}
    for sub in geometry.subreaches:
        total = int(sub.mask.sum())
        has_data = sub.mask & ~nodata
        data = int(has_data.sum())
        n_invalid = int((has_data & invalid).sum())
        ring = sub.land_ring & ~nodata
        ring_n = int(ring.sum())
        river_cloud = float((has_data & cloud).sum()) / data if data else 0.0
        land_cloud = float((ring & cloud).sum()) / ring_n if ring_n else 1.0
        out[sub.name] = SubreachMetrics(
            data_coverage=data / total if total else 0.0,
            water_px_10m=4 * int((has_data & water).sum()),
            valid_px_10m=4 * (data - n_invalid),
            contamination=n_invalid / data if data else 1.0,
            class_shares={
                c: float((has_data & (scl == c)).sum()) / data if data else 0.0
                for c in cfg.scl.reported
            },
            river_cloud_share=river_cloud,
            land_cloud_share=land_cloud,
            suspect_turbid_as_cloud=(
                data > 0
                and river_cloud >= cfg.clear.suspect_river_cloud_min
                and land_cloud <= cfg.clear.suspect_land_cloud_max
            ),
        )
    return out


def classify_scene(
    sub: dict[str, SubreachMetrics], cfg: ScreeningConfig
) -> tuple[bool, bool, bool]:
    """Apply the clear, observable and full-coverage rules to a scene's sub-reach metrics.

    Args:
        sub: Metrics per sub-reach.
        cfg: Screening settings.

    Returns:
        ``(clear, observable, full_coverage)``.
    """
    if not sub:
        return False, False, False
    c = cfg.clear

    def ok(m: SubreachMetrics, px: int) -> bool:
        return (
            px >= c.min_valid_px_10m
            and m.contamination < c.max_contamination
            and m.data_coverage >= c.min_data_coverage
        )

    clear = all(ok(m, m.water_px_10m) for m in sub.values())
    observable = all(ok(m, m.valid_px_10m) for m in sub.values())
    full = all(m.data_coverage >= cfg.score.full_coverage for m in sub.values())
    return clear, observable, full


# ----------------------------------------------------------------------------------------------
# Summary statistics
# ----------------------------------------------------------------------------------------------


def month_keys(start: date, end: date) -> list[str]:
    """``YYYY-MM`` keys of every month in a period.

    Args:
        start: First day.
        end: Last day.

    Returns:
        Month keys in order.
    """
    keys, year, month = [], start.year, start.month
    while (year, month) <= (end.year, end.month):
        keys.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return keys


def longest_gap_days(days: Iterable[date], start: date, end: date) -> int:
    """Longest stretch without a qualifying scene, counting the period's edges.

    Args:
        days: Days with a qualifying scene.
        start: Period start.
        end: Period end.

    Returns:
        The longest gap in days.
    """
    marks = sorted({d for d in days if start <= d <= end})
    edges = [start - timedelta(days=1), *marks, end + timedelta(days=1)]
    return max((b - a).days - 1 for a, b in itertools.pairwise(edges))


def monthly_counts(scenes: list[SceneMetrics], start: date, end: date) -> dict[str, dict[str, int]]:
    """Acquisitions, observable and clear scenes per month.

    Args:
        scenes: The site's scenes.
        start: Period start.
        end: Period end.

    Returns:
        Counts per ``YYYY-MM``.
    """
    table = {
        key: {"acquisitions": 0, "observable": 0, "clear": 0} for key in month_keys(start, end)
    }
    for scene in scenes:
        key = scene.datetime.strftime("%Y-%m")
        if key in table:
            table[key]["acquisitions"] += 1
            table[key]["observable"] += scene.observable
            table[key]["clear"] += scene.clear
    return table


def summarize(result: Stage1Result, cfg: ScreeningConfig) -> dict[str, object]:
    """The per-site stage-1 summary (one row of the summary table).

    Args:
        result: Stage-1 results of the site.
        cfg: Screening settings.

    Returns:
        Summary fields.
    """
    start, end = cfg.period.start, cfg.period.end
    years = ((end - start).days + 1) / 365.25
    scenes = result.scenes
    geom = result.geometry
    clear = [s for s in scenes if s.clear]
    observable = [s for s in scenes if s.observable]
    months = monthly_counts(scenes, start, end)
    with_data = [s for s in scenes if s.has_data]
    weaker = [min(m.water_px_10m for m in s.sub.values()) for s in clear]
    rainy = set(result.rainy_months)
    by_season: dict[str, list[SceneMetrics]] = {"rainy": [], "dry": []}
    for s in scenes:
        by_season["rainy" if s.datetime.month in rainy else "dry"].append(s)
    center_daily = result.rain[0].daily(cfg.rain.timezone) if result.rain else {}
    clear_rain = [center_daily[d] for d in {s.datetime.date() for s in clear} if d in center_daily]
    all_rain = [mm for d, mm in center_daily.items() if start <= d <= end]
    width = min(geom.width_px_10m.values()) if geom.width_px_10m else math.nan
    width_raw = min(geom.width_px_10m_raw.values()) if geom.width_px_10m_raw else math.nan
    center_lonlat: tuple[float, float] | None = None
    if geom.corridor is not None and geom.centerline:
        mid = geom.centerline[len(geom.centerline) // 2]
        center_lonlat = rowcol_lonlat(result.grid, mid[0], mid[1])
    platforms = Counter(s.platform for s in scenes)
    scaling = Counter(status for s in scenes for status in s.scaling)
    summary: dict[str, object] = {
        "site_id": result.site.id,
        "category": result.site.category,
        "river": result.site.river,
        "geometry_failed": geom.failed or "",
        "water_frequency_threshold": geom.threshold,
        "frequency_histogram": " ".join(str(c) for c in geom.frequency_histogram),
        "reach_length_km": round(geom.reach_length_m / 1000, 2),
        "separation_km": round(geom.placement.separation_m / 1000, 2)
        if geom.placement
        else math.nan,
        "confluence_inside": bool(geom.placement and geom.placement.confluence_inside),
        "confluence_between": bool(geom.placement and geom.placement.confluence_between),
        "anchor_shift_up_m": round(geom.anchor_shifts_m.get("upstream_anchor", math.nan)),
        "anchor_shift_down_m": round(geom.anchor_shifts_m.get("downstream_anchor", math.nan)),
        "center_shift_m": round(geom.anchor_shifts_m.get("center", math.nan))
        if math.isfinite(geom.anchor_shifts_m.get("center", math.nan))
        else math.nan,
        "centerline_mid_lon": round(center_lonlat[0], 5) if center_lonlat else math.nan,
        "centerline_mid_lat": round(center_lonlat[1], 5) if center_lonlat else math.nan,
        "width_px_10m": round(width, 1),
        "width_px_10m_before_erosion": round(width_raw, 1),
        "ndti_unreliable_width": bool(width < cfg.width.unreliable_below_px_10m)
        if width == width
        else True,
        "items": sum(len(a.scenes) for a in result.acquisitions),
        "acquisitions": len(scenes),
        "platforms": " ".join(f"{p}:{n}" for p, n in sorted(platforms.items())),
        "clear": len(clear),
        "observable": len(observable),
        "clear_per_year": round(len(clear) / years, 2),
        "observable_per_year": round(len(observable) / years, 2),
        "months_with_clear_pct": round(
            100 * sum(1 for m in months.values() if m["clear"]) / len(months), 1
        ),
        "months_with_observable_pct": round(
            100 * sum(1 for m in months.values() if m["observable"]) / len(months), 1
        ),
        "longest_gap_clear_days": longest_gap_days((s.datetime.date() for s in clear), start, end),
        "longest_gap_observable_days": longest_gap_days(
            (s.datetime.date() for s in observable), start, end
        ),
        "rainy_months": " ".join(str(m) for m in sorted(rainy)),
        "clear_share_rainy": _share(by_season["rainy"], lambda s: s.clear),
        "clear_share_dry": _share(by_season["dry"], lambda s: s.clear),
        "rain_mean_mm_clear_days": round(float(np.mean(clear_rain)), 2) if clear_rain else math.nan,
        "rain_mean_mm_all_days": round(float(np.mean(all_rain)), 2) if all_rain else math.nan,
        "tiles": " ".join(sorted({t for s in scenes for t in s.tiles})),
        "relative_orbits": " ".join(
            str(o)
            for o in sorted({s.relative_orbit for s in scenes if s.relative_orbit is not None})
        ),
        "multi_tile_share": _share(with_data, lambda s: s.tiles_with_data > 1),
        "tile_integrity": _share(with_data, lambda s: s.full_coverage),
        "suspect_turbid_as_cloud": sum(
            any(m.suspect_turbid_as_cloud for m in s.sub.values()) for s in scenes
        ),
        "median_weaker_subreach_water_px_10m": float(np.median(weaker)) if weaker else 0.0,
        "scaling_status": " ".join(f"{k}:{v}" for k, v in sorted(scaling.items())),
        "evidence_sha256": evidence_hash(result.acquisitions),
    }
    return summary


def _share(items: list[SceneMetrics], test: Callable[[SceneMetrics], bool]) -> float:
    return round(sum(1 for s in items if test(s)) / len(items), 3) if items else math.nan


# ----------------------------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------------------------


def run_stage1(
    site: SiteConfig,
    cfg: ScreeningConfig,
    source: SceneSource,
    reader: AcquisitionReader,
    rain: OpenMeteoClient | None,
    workers: int = 8,
    period: tuple[date, date] | None = None,
) -> Stage1Result:
    """Run stage 1 for one site.

    Args:
        site: The site.
        cfg: Screening settings.
        source: STAC source.
        reader: Reads (and caches) acquisition bands onto the grid.
        rain: Open-Meteo client, or None to skip rain context.
        workers: Parallel reads.
        period: Override of the configured period (e.g. a short re-run).

    Returns:
        The stage-1 result with its summary filled in.
    """
    start, end = period or (cfg.period.start, cfg.period.end)
    grid = site_grid(site.aoi_bbox)
    log.info("%s: searching scenes %s..%s", site.id, start, end)
    acquisitions = group_acquisitions(source.search(site.aoi_bbox, start, end))
    log.info("%s: %d acquisitions", site.id, len(acquisitions))

    stack = FrequencyStack(grid.shape, cfg.scl)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for scl, _ in pool.map(lambda a: reader.read(a, "scl", grid), acquisitions):
            stack.update(scl)
    geometry = derive_site_geometry(site, cfg, grid, stack)
    log.info("%s: geometry %s", site.id, geometry.failed or "ok")

    rain_series = fetch_rain(site, rain, start, end) if rain else []
    scenes: list[SceneMetrics] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        reads = pool.map(lambda a: reader.read(a, "scl", grid), acquisitions)
        for acquisition, (scl, filled) in zip(acquisitions, reads, strict=True):
            sub = measure_scene(scl, geometry, cfg) if geometry.failed is None else {}
            clear, observable, full = classify_scene(sub, cfg)
            scenes.append(
                SceneMetrics(
                    key=acquisition.key,
                    datetime=acquisition.datetime,
                    platform=acquisition.platform,
                    relative_orbit=acquisition.relative_orbit,
                    tiles=acquisition.tiles,
                    tiles_with_data=sum(1 for n in filled.values() if n > 0),
                    scaling=tuple(s.scaling_status() for s in acquisition.scenes),
                    sub=sub,
                    clear=clear,
                    observable=observable,
                    full_coverage=full,
                    has_data=any(m.data_coverage > 0 for m in sub.values()),
                )
            )
    result = Stage1Result(
        site=site,
        grid=grid,
        acquisitions=acquisitions,
        geometry=geometry,
        scenes=scenes,
        rain=rain_series,
        rainy_months=rainy_months(rain_series[0].daily(cfg.rain.timezone)) if rain_series else (),
    )
    result.summary = summarize(result, cfg)
    return result


def derive_site_geometry(
    site: SiteConfig, cfg: ScreeningConfig, grid: Grid, stack: FrequencyStack
) -> RiverGeometry:
    """Derive the river geometry of a site from its accumulated SCL counts.

    Args:
        site: The site (anchors, confluences, exclusions, overrides).
        cfg: Screening settings.
        grid: The 20 m site grid.
        stack: Accumulated counts.

    Returns:
        The geometry.
    """
    excluded = None
    for polygon in site.exclude_polygons:
        burned = rasterize_polygon(grid, polygon.coordinates)
        excluded = burned if excluded is None else excluded | burned
    return derive_geometry(
        stack.frequency(cfg.mask.min_observations),
        resolution=grid.resolution,
        thresholds=cfg.mask.thresholds,
        upstream=lonlat_rowcol(grid, site.upstream_anchor.lon, site.upstream_anchor.lat),
        downstream=lonlat_rowcol(grid, site.downstream_anchor.lon, site.downstream_anchor.lat),
        center=lonlat_rowcol(grid, site.center.lon, site.center.lat),
        confluences={
            c.name: lonlat_rowcol(grid, c.point.lon, c.point.lat) for c in site.confluences
        },
        excluded=excluded,
        snap_radius_m=cfg.mask.snap_radius_m,
        corridor_half_width_m=site.corridor_half_width_m or cfg.mask.corridor_half_width_m,
        erosion_px_10m=site.erosion_px_10m
        if site.erosion_px_10m is not None
        else cfg.mask.erosion_px_10m,
        land_ring_m=cfg.mask.land_ring_m,
        subreach=cfg.subreach,
    )


def fetch_rain(
    site: SiteConfig, client: OpenMeteoClient, start: date, end: date
) -> list[RainSeries]:
    """Hourly rain at each of a site's rain points (the first is the center).

    Args:
        site: The site.
        client: Open-Meteo client.
        start: Period start.
        end: Period end.

    Returns:
        One series per rain point.
    """
    first = start - timedelta(days=RAIN_LEAD_DAYS)
    return [client.hourly(p.description, p.lon, p.lat, first, end) for p in site.rain_points]


def scene_rows(result: Stage1Result) -> list[dict[str, object]]:
    """Per-acquisition rows for ``pipeline/out/screening_stage1.csv``.

    Args:
        result: Stage-1 result of one site.

    Returns:
        One row per acquisition.
    """
    rows = []
    for s in result.scenes:
        row: dict[str, object] = {
            "site_id": result.site.id,
            "acquisition": s.key,
            "datetime_utc": s.datetime.isoformat(),
            "platform": s.platform,
            "relative_orbit": s.relative_orbit,
            "tiles": " ".join(s.tiles),
            "tiles_with_data": s.tiles_with_data,
            "scaling": " ".join(s.scaling),
            "clear": s.clear,
            "observable": s.observable,
            "full_coverage": s.full_coverage,
        }
        for name, m in s.sub.items():
            row |= {
                f"{name}_coverage": round(m.data_coverage, 3),
                f"{name}_water_px_10m": m.water_px_10m,
                f"{name}_valid_px_10m": m.valid_px_10m,
                f"{name}_contamination": round(m.contamination, 3),
                **{f"{name}_class{c}_share": round(v, 3) for c, v in m.class_shares.items()},
                f"{name}_river_cloud": round(m.river_cloud_share, 3),
                f"{name}_land_cloud": round(m.land_cloud_share, 3),
                f"{name}_suspect_turbid_as_cloud": m.suspect_turbid_as_cloud,
            }
        rows.append(row)
    return rows
