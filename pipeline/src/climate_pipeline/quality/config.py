"""Settings of the water-quality validation v2 (``pipeline/water-quality.yaml``), checked."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from climate_pipeline.calibration.config import Period, WindowSettings

BANDS = ("B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12")
SourceName = Literal["earth-search", "planetary-computer"]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(_Frozen):
    """One STAC source of Sentinel-2 L2A."""

    url: str
    collection: str
    sun: Literal["view:sun_elevation", "s2:mean_solar_zenith"]
    assets: dict[str, str] = Field(description="asset key -> band name")
    sas_token_url: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Source:
        if missing := {*BANDS, "SCL"} - set(self.assets.values()):
            raise ValueError(f"source assets miss bands: {sorted(missing)}")
        return self

    def band_asset(self, band: str) -> str:
        """The asset key holding a band.

        Args:
            band: E.g. ``B8A``.

        Returns:
            The asset key, e.g. ``nir08``.
        """
        return next(k for k, v in self.assets.items() if v == band)


class Sensitivity(_Frozen):
    """A collection read only as a sensitivity."""

    source: SourceName
    collection: str


class SourceCheck(_Frozen):
    """Planetary Computer against Earth Search on dates both hold."""

    start: date
    end: date
    max_scenes: int = Field(gt=0)
    shift_sigma: float = Field(gt=0)


class Imagery(_Frozen):
    """The sources, which dates each serves, and the read grid."""

    split_date: date = Field(description="Planetary Computer before it, Earth Search from it on")
    resolution_m: float = Field(gt=0)
    read_half_size_m: float = Field(gt=0)
    sources: dict[SourceName, Source]
    sensitivity: Sensitivity
    source_check: SourceCheck

    @model_validator(mode="after")
    def _check(self) -> Imagery:
        if set(self.sources) != {"earth-search", "planetary-computer"}:
            raise ValueError("both Earth Search and Planetary Computer must be configured")
        if self.sources["planetary-computer"].sas_token_url is None:
            raise ValueError("planetary-computer needs sas_token_url")
        return self

    def source_for(self, day: date) -> SourceName:
        """The one source that serves a date.

        Args:
            day: The acquisition's date (UTC).

        Returns:
            ``planetary-computer`` before the split date, else ``earth-search``.
        """
        return "planetary-computer" if day < self.split_date else "earth-search"


class Stations(_Frozen):
    """The metadata-only selection of Colombian stations (D15's rule, more streams)."""

    streams: tuple[str, ...] = Field(min_length=1)
    test_stream: str
    quality_resource: str
    quality_variables: tuple[str, ...] = Field(min_length=1)
    samples_since: date
    bucket: str
    catalog: str
    flow_labels: tuple[str, ...]
    flow_search_km: float = Field(gt=0)
    report_labels: tuple[str, ...]
    grid_half_size_m: float = Field(gt=0)
    water_frequency_min: float = Field(gt=0, le=1)
    min_observations: int = Field(gt=0)
    mask_fallback: Literal["mndwi"]
    snap_radius_m: float = Field(gt=0)
    width_search_m: float = Field(gt=0)
    min_width_m: float = Field(gt=0)

    @model_validator(mode="after")
    def _check(self) -> Stations:
        if len(set(self.streams)) != len(self.streams):
            raise ValueError("streams must be unique")
        if self.test_stream not in self.streams:
            raise ValueError(f"the test stream {self.test_stream} is not among the streams")
        return self


class Usgs(_Frozen):
    """The USGS pilot sites and how their values meet the scenes."""

    api: str
    turbidity_parameter: str
    ssc_parameter: str
    min_drainage_area_sq_mi: float = Field(gt=0)
    period: Period
    max_cloud_cover: float = Field(gt=0, le=100)
    max_clear_scenes_per_site: int = Field(gt=0)
    approval: Literal["Approved"]
    exclude_qualified: bool
    overpass_median_minutes: int = Field(gt=0)
    overpass_nearest_minutes: int = Field(gt=0)

    @model_validator(mode="after")
    def _check(self) -> Usgs:
        if self.overpass_nearest_minutes < self.overpass_median_minutes:
            raise ValueError("the nearest-value window must not be narrower than the median one")
        return self


class Window(_Frozen):
    """The station window (D15's primary window) and the core window."""

    radius_m: float = Field(gt=0)
    erosion_px: int = Field(ge=0)
    core_min_distance_m: float = Field(gt=0)
    min_valid_px: int = Field(gt=0)
    max_contamination: float = Field(ge=0, le=1)
    abstain_glint_share: float = Field(ge=0, le=1)

    def as_calibration(self) -> WindowSettings:
        """The same guards in D15's type, for its scene and abstention rules.

        Returns:
            D15's window settings (no 1 km sensitivity window here).
        """
        return WindowSettings(
            radius_m=self.radius_m, sensitivity_radius_m=self.radius_m,
            erosion_px=self.erosion_px, min_valid_px=self.min_valid_px,
            max_contamination=self.max_contamination,
            abstain_glint_share=self.abstain_glint_share,
        )  # fmt: skip


class Matchups(_Frozen):
    """How Colombian samples meet scenes."""

    primary_days: int = Field(ge=0)
    sensitivity_days: int = Field(ge=0)
    stable_max_abs_log_q: float = Field(gt=0)
    stable_max_level_m: float = Field(gt=0)
    replicates: Literal["median"]
    censored: Literal["exclude_from_fits"]


class Target(_Frozen):
    """One in-situ variable, its USGS counterpart and its range bins."""

    id: Literal["turbidity", "tss"]
    variable: str
    unit: str
    usgs_parameter: str
    usgs_unit: str
    bins: tuple[float, ...] = Field(min_length=1, description="upper edges, increasing")

    @model_validator(mode="after")
    def _check(self) -> Target:
        if any(b <= 0 for b in self.bins) or list(self.bins) != sorted(set(self.bins)):
            raise ValueError(f"{self.id}: bins must be positive and strictly increasing")
        return self

    def bin_of(self, value: float) -> int:
        """The range bin of a value (0 below the first edge, len(bins) above the last).

        Args:
            value: A positive value in the target's unit.

        Returns:
            The bin index.
        """
        return sum(1 for edge in self.bins if value >= edge)


class Features(_Frozen):
    """The feature set F of Route A."""

    log_bands: tuple[str, ...]
    log_ratios: tuple[str, ...]
    linear: tuple[str, ...]
    floor: float = Field(gt=0)
    geometry: tuple[Literal["sun_zenith", "log_width_m", "core_share"], ...]

    @model_validator(mode="after")
    def _check(self) -> Features:
        used = set(self.log_bands)
        for ratio in self.log_ratios:
            used |= set(ratio.split("/"))
        for item in self.linear:
            used |= set(item.split("-"))
        if unknown := used - set(BANDS):
            raise ValueError(f"features use unknown bands: {sorted(unknown)}")
        return self


class Candidate(_Frozen):
    """One predeclared model, evaluated on the test set once."""

    id: str
    route: Literal["A", "B"]
    model: Literal[
        "null_median", "loglog", "ridge_log", "gbm", "dogliotti2015_turbidity", "nechad", "mdn_tss"
    ]
    features: tuple[str, ...] | Literal["F"] | None = None
    fit: Literal["colombia", "usgs_then_adjust"] | None = None

    @model_validator(mode="after")
    def _check(self) -> Candidate:
        route_b = {"dogliotti2015_turbidity", "nechad", "mdn_tss"}
        if (self.model in route_b) != (self.route == "B"):
            raise ValueError(f"{self.id}: model {self.model} is not a route {self.route} model")
        if self.model in ("loglog", "ridge_log", "gbm") and (not self.features or not self.fit):
            raise ValueError(f"{self.id}: a fitted model names its features and fit")
        return self


class Gbm(_Frozen):
    """The gradient-boosting grid (trained in the separate lab environment)."""

    num_leaves: tuple[int, ...] = Field(min_length=1)
    min_data_in_leaf: tuple[int, ...] = Field(min_length=1)
    n_estimators: tuple[int, ...] = Field(min_length=1)
    learning_rate: float = Field(gt=0)
    threads: Literal[1]


class Selection(_Frozen):
    """How the product model is chosen, on training rivers only."""

    outer: Literal["loro_colombia"]
    inner: Literal["loro_usgs"]
    simpler_within_mdsa: float = Field(ge=0)
    ridge_lambdas: tuple[float, ...] = Field(min_length=1)
    adjustment_lambdas: tuple[float, ...] = Field(min_length=1)
    adjustment_min_pairs: int = Field(gt=0)
    gbm: Gbm
    bootstrap_resamples: int = Field(gt=0)
    confidence: float = Field(gt=0, lt=1)


class Intervals(_Frozen):
    """Prediction intervals."""

    method: Literal["mondrian_split_conformal_log"]
    coverages: tuple[float, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Intervals:
        if any(not 0 < c < 1 for c in self.coverages):
            raise ValueError("coverages must lie in (0, 1)")
        return self


class Criteria(_Frozen):
    """The test-set criteria of a level."""

    mdsa_max: float = Field(gt=0)
    sspb_abs_max: float = Field(gt=0)
    null_ratio_max: float = Field(gt=0)
    coverage_90: tuple[float, float]
    min_pairs: int | None = None
    min_stations: int | None = None


class Indicative(_Frozen):
    """The rank-only level."""

    lower_bound_min: float = Field(gt=-1, lt=1)


class Levels(_Frozen):
    """The levels a target and range can reach."""

    min_bin_pairs: int = Field(gt=0)
    min_test_pairs: int = Field(gt=0)
    validated: Criteria
    estimated: Criteria
    indicative: Indicative

    @model_validator(mode="after")
    def _check(self) -> Levels:
        v, e = self.validated, self.estimated
        if v.min_pairs is None or v.min_stations is None:
            raise ValueError("validated names its minimum pairs and stations")
        if (e.mdsa_max < v.mdsa_max or e.sspb_abs_max < v.sspb_abs_max
                or e.null_ratio_max < v.null_ratio_max):  # fmt: skip
            raise ValueError("estimated must not be stricter than validated")
        return self


class Adjacency(_Frozen):
    """When Route B confirms adjacency (both must hold)."""

    rho_min: float = Field(gt=0, lt=1)
    narrow_width_m: float = Field(gt=0)


class RouteB(_Frozen):
    """The physics check: ACOLITE (DSF, RAdCor) and the MDN."""

    acolite_commit: str = Field(min_length=40, max_length=40)
    dsf_settings: str
    radcor_settings: str
    radcor_time_box_h: float = Field(gt=0)
    radcor_fallback_limit_deg: float = Field(gt=0)
    mdn_commit: str = Field(min_length=40, max_length=40)
    mdn_bands_nm: tuple[int, ...] = Field(min_length=1)
    mdn_setup_time_box_h: float = Field(gt=0)
    adjacency: Adjacency


class Landsat(_Frozen):
    """The optional Landsat 8/9 stage."""

    source: Literal["planetary-computer"]
    collection: str
    start: date
    end: date
    min_width_m: float = Field(gt=0)


class Doi(_Frozen):
    """A dataset reference."""

    doi: str


class ZenodoRecord(_Frozen):
    """A Zenodo record."""

    zenodo: str


class OptionalStages(_Frozen):
    """Stages run only if chosen at the checkpoint."""

    landsat: Landsat
    gloria: Doi
    dethier: ZenodoRecord


class NetworkBudget(_Frozen):
    """Network caps per stage, in GB."""

    colombia: float = Field(gt=0)
    usgs: float = Field(gt=0)
    reach_baseline: float = Field(gt=0)
    landsat: float = Field(gt=0)


class Budgets(_Frozen):
    """Disk and network budgets."""

    keep_free_gb: float = Field(gt=0)
    min_usgs_pairs: int = Field(gt=0)
    network_gb: NetworkBudget


class Outputs(_Frozen):
    """Where snapshots and results go."""

    inputs: str
    results: str


class QualityConfig(_Frozen):
    """Everything in ``pipeline/water-quality.yaml``."""

    title: str
    preregistration: str
    screening_config: str
    calibration_config: str
    seed: int
    period: Period
    geometry_period: Period
    timezone: str
    imagery: Imagery
    stations: Stations
    usgs: Usgs
    window: Window
    matchups: Matchups
    targets: tuple[Target, ...] = Field(min_length=1)
    features: Features
    candidates: tuple[Candidate, ...] = Field(min_length=1)
    selection: Selection
    intervals: Intervals
    levels: Levels
    route_b: RouteB
    optional: OptionalStages
    budgets: Budgets
    outputs: Outputs

    @model_validator(mode="after")
    def _check(self) -> QualityConfig:
        ids = [c.id for c in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate ids must be unique")
        if not (
            self.period.contains(self.geometry_period.start)
            and self.period.contains(self.geometry_period.end)
        ):
            raise ValueError("the geometry period must lie inside the period")
        if not self.period.contains(self.imagery.split_date):
            raise ValueError("the source split date must lie inside the period")
        return self

    def target(self, target_id: str) -> Target:
        """A target by id.

        Args:
            target_id: E.g. ``tss``.

        Returns:
            The target.
        """
        return next(t for t in self.targets if t.id == target_id)


def load_quality_config(path: Path) -> QualityConfig:
    """Load and validate the settings file.

    Args:
        path: ``pipeline/water-quality.yaml``.

    Returns:
        The settings.
    """
    with path.open(encoding="utf-8") as handle:
        return QualityConfig.model_validate(yaml.safe_load(handle))
