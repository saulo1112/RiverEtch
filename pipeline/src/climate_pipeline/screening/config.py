"""Configuration of the site screening: global thresholds and one YAML file per candidate reach.

Nothing site-specific lives in code. ``screening.yaml`` holds every threshold, weight and source
setting (pre-registered in ``docs/site-screening/method.md``); ``sites/<id>.yaml`` describes one
reach with the sources its positions come from.
"""

from __future__ import annotations

import hashlib
import math
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal["A", "B", "C", "D"]
"""A: reservoir operations, B: mining benchmark, C: other pressure, D: control."""

CATEGORY_NAMES: dict[str, str] = {
    "A": "reservoir operations",
    "B": "mining benchmark",
    "C": "other pressure",
    "D": "control",
}


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ----------------------------------------------------------------------------------------------
# Sites
# ----------------------------------------------------------------------------------------------


class Point(_Frozen):
    """An approximate position in WGS84 degrees, with how it was obtained."""

    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    description: str
    basis: str = Field(description="'source-stated' or 'estimated-from-<named place>'")
    source_url: str = ""


class Citation(_Frozen):
    """A source and the fact it supports."""

    url: str
    title: str
    supports: str
    verification: str = Field(description="How the fact was checked, e.g. 'search summary only'")


class Confluence(_Frozen):
    """A tributary joining the river near the reach."""

    name: str
    point: Point


class RegimeChange(_Frozen):
    """A dated change in how a dam is operated (stage-2 baselines are split at these dates)."""

    date: date
    precision: Literal["day", "month", "year"]
    description: str
    source_url: str


class Polygon(_Frozen):
    """A polygon in WGS84 degrees, e.g. pits or floodplain lakes to keep out of the river mask."""

    description: str
    coordinates: tuple[tuple[float, float], ...] = Field(min_length=3)


class SiteConfig(_Frozen):
    """One candidate reach. Positions are approximate until corrected against the water mask."""

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    name: str
    river: str
    category: Category
    rationale: str
    center: Point
    aoi_bbox: tuple[float, float, float, float] = Field(description="west, south, east, north")
    upstream_anchor: Point
    downstream_anchor: Point
    feature: Point | None = Field(default=None, description="The dam or pressure, if any")
    corridor_half_width_m: float | None = Field(default=None, gt=0)
    erosion_px_10m: int | None = Field(default=None, ge=0, le=5)
    exclude_polygons: tuple[Polygon, ...] = ()
    confluences: tuple[Confluence, ...] = ()
    regime_changes: tuple[RegimeChange, ...] = ()
    rain_points: tuple[Point, ...] = Field(min_length=1)
    operator: str
    regulator: str
    backwater_note: str = ""
    river_width_note: str = ""
    climate_note: str = ""
    citations: tuple[Citation, ...] = Field(min_length=1)
    unverified: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check_geometry(self) -> SiteConfig:
        west, south, east, north = self.aoi_bbox
        if not (west < east and south < north):
            raise ValueError(f"{self.id}: aoi_bbox must be west < east and south < north")
        width_km = (east - west) * 111.32 * math.cos(math.radians((south + north) / 2))
        height_km = (north - south) * 110.57
        if not (3 <= width_km <= 60 and 3 <= height_km <= 60):
            raise ValueError(f"{self.id}: aoi_bbox is {width_km:.0f} x {height_km:.0f} km")
        for label, point in (
            ("center", self.center),
            ("upstream_anchor", self.upstream_anchor),
            ("downstream_anchor", self.downstream_anchor),
        ):
            if not (west <= point.lon <= east and south <= point.lat <= north):
                raise ValueError(f"{self.id}: {label} lies outside aoi_bbox")
        return self


# ----------------------------------------------------------------------------------------------
# Global screening configuration
# ----------------------------------------------------------------------------------------------


class Period(_Frozen):
    """The study period (inclusive)."""

    start: date
    end: date


class AssetKeys(_Frozen):
    """STAC asset keys of the bands the screening reads."""

    scl: str
    red: str
    green: str
    swir16: str


class StacSourceConfig(_Frozen):
    """One STAC API that serves Sentinel-2 L2A as cloud-optimized GeoTIFFs."""

    url: str
    collection: str
    assets: AssetKeys
    sas_token_url: str | None = None


class StacConfig(_Frozen):
    """STAC sources; ``source`` picks the default one."""

    source: str
    sources: dict[str, StacSourceConfig]
    page_size: int = Field(default=100, gt=0)

    @model_validator(mode="after")
    def _check_source(self) -> StacConfig:
        if self.source not in self.sources:
            raise ValueError(f"stac.source {self.source!r} is not one of {sorted(self.sources)}")
        return self


class SclConfig(_Frozen):
    """Scene classification classes."""

    nodata: tuple[int, ...]
    water: tuple[int, ...]
    invalid: tuple[int, ...]
    reported: tuple[int, ...]
    cloud: tuple[int, ...]


class MaskConfig(_Frozen):
    """River mask from the water frequency of the SCL stack."""

    @property
    def thresholds(self) -> tuple[float, ...]:
        """The pre-registered threshold followed by its fallbacks."""
        return (self.water_frequency_min, *self.water_frequency_fallbacks)

    water_frequency_min: float = Field(gt=0, lt=1)
    water_frequency_fallbacks: tuple[float, ...] = Field(
        default=(), description="lower thresholds tried, in order, if the anchors do not connect"
    )
    min_observations: int = Field(gt=0)
    snap_radius_m: float = Field(gt=0)
    corridor_half_width_m: float = Field(gt=0)
    erosion_px_10m: int = Field(ge=0, le=5)
    land_ring_m: tuple[float, float] = Field(description="inner and outer distance from the river")
    bridge_gap_px: int = Field(
        default=0, ge=0, le=5, description="close mask gaps up to 2x this (connectivity only)"
    )


class SubreachConfig(_Frozen):
    """Upstream and downstream sub-reaches along the derived centerline."""

    length_m: float = Field(gt=0)
    start_offset_m: float = Field(ge=0)
    separation_target_m: float = Field(gt=0)
    separation_min_m: float = Field(gt=0)
    separation_max_m: float = Field(gt=0)
    confluence_buffer_m: float = Field(ge=0)

    @model_validator(mode="after")
    def _check_separation(self) -> SubreachConfig:
        if not (
            self.separation_min_m <= self.separation_target_m <= self.separation_max_m
            and self.length_m < self.separation_min_m
        ):
            raise ValueError("subreach: need length < separation_min <= target <= max")
        return self


class ClearConfig(_Frozen):
    """When a scene counts as clear over both sub-reaches."""

    min_valid_px_10m: int = Field(gt=0)
    max_contamination: float = Field(ge=0, le=1)
    min_data_coverage: float = Field(ge=0, le=1)
    suspect_river_cloud_min: float = Field(ge=0, le=1)
    suspect_land_cloud_max: float = Field(ge=0, le=1)


class WidthConfig(_Frozen):
    """Width adequacy for NDTI at 10 m."""

    unreliable_below_px_10m: float = Field(gt=0)
    adequate_at_px_10m: float = Field(gt=0)


class Stage2Config(_Frozen):
    """NDTI extraction, baselines and anomalies."""

    anomaly_z: float = Field(gt=0)
    mad_floor: float = Field(gt=0)
    min_baseline_n: int = Field(gt=1)
    min_season_n: int = Field(gt=1)
    rg_floor: float = Field(ge=0, description="minimum red + green reflectance per pixel")
    swir16_max: float = Field(gt=0, description="pixels above this B11 reflectance are dropped")
    water_reflectance_max: float = Field(gt=0)
    max_scenes_per_site: int = Field(gt=0)


class RainConfig(_Frozen):
    """Open-Meteo archive and the rain-coincidence rule."""

    url: str
    windows_h: tuple[int, ...]
    coincident_window_h: int
    coincident_mm: float = Field(ge=0)
    timezone: str


class EventConfig(_Frozen):
    """Matching of catalog events to clear scenes."""

    window_before_days: int = Field(ge=0)
    window_after_days: int = Field(ge=0)
    scored_precisions: tuple[str, ...]
    chance_shifts: int = Field(gt=0)
    seed: int


class ScoreWeights(_Frozen):
    """Weights of the pre-registered score (they sum to 1)."""

    coverage: float = Field(ge=0)
    width: float = Field(ge=0)
    tile_integrity: float = Field(ge=0)
    contrast_feasibility: float = Field(ge=0)
    events: float = Field(ge=0)

    @model_validator(mode="after")
    def _check_sum(self) -> ScoreWeights:
        total = sum(self.model_dump().values())
        if abs(total - 1) > 1e-9:
            raise ValueError(f"score weights sum to {total}, not 1")
        return self


class ScoreConfig(_Frozen):
    """Score anchors, weights, gates and the stage-2 selection rule."""

    weights: ScoreWeights
    clear_per_year_full: float = Field(gt=0)
    feasibility_px_full: float = Field(gt=0)
    events_full: int = Field(gt=0)
    min_clear_total: int = Field(ge=0)
    full_coverage: float = Field(gt=0, le=1)
    stage2_top: int = Field(gt=0)
    stage2_max_benchmarks: int = Field(ge=0)


class ScreeningConfig(_Frozen):
    """Everything the screening reads from ``screening.yaml``."""

    period: Period
    stac: StacConfig
    scl: SclConfig
    mask: MaskConfig
    subreach: SubreachConfig
    clear: ClearConfig
    width: WidthConfig
    stage2: Stage2Config
    rain: RainConfig
    events: EventConfig
    score: ScoreConfig


# ----------------------------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------------------------


def load_screening_config(path: Path) -> ScreeningConfig:
    """Load and validate ``screening.yaml``.

    Args:
        path: Path to the YAML file.

    Returns:
        The validated configuration.
    """
    return ScreeningConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_site(path: Path) -> SiteConfig:
    """Load and validate one site file; its ``id`` must match the file name.

    Args:
        path: Path to ``sites/<id>.yaml``.

    Returns:
        The validated site.

    Raises:
        ValueError: If the id does not match the file name.
    """
    site = SiteConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if site.id != path.stem:
        raise ValueError(f"{path}: id {site.id!r} does not match the file name")
    return site


def load_sites(directory: Path, only: tuple[str, ...] = ()) -> list[SiteConfig]:
    """Load every site file in a directory, sorted by id.

    Args:
        directory: The ``sites/`` directory.
        only: If given, the ids to keep (unknown ids are an error).

    Returns:
        The validated sites.

    Raises:
        ValueError: If a requested id has no file.
    """
    sites = [load_site(path) for path in sorted(directory.glob("*.yaml"))]
    if only:
        missing = set(only) - {site.id for site in sites}
        if missing:
            raise ValueError(f"unknown site ids: {sorted(missing)}")
        sites = [site for site in sites if site.id in only]
    return sites


def config_hash(paths: list[Path]) -> str:
    """Hash configuration files so outputs record exactly which settings produced them.

    Args:
        paths: Files to hash, in a stable order.

    Returns:
        The hex SHA-256 of the files' names and contents.
    """
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()
