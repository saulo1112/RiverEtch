"""Settings of the calibration validation (``pipeline/calibration.yaml``), validated on load."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Period(_Frozen):
    """A period of days (inclusive)."""

    start: date
    end: date

    @model_validator(mode="after")
    def _check(self) -> Period:
        if self.start > self.end:
            raise ValueError(f"period starts after it ends: {self.start} > {self.end}")
        return self

    def contains(self, day: date) -> bool:
        """Whether a day lies in the period.

        Args:
            day: The day.

        Returns:
            True when ``start <= day <= end``.
        """
        return self.start <= day <= self.end


class Imagery(_Frozen):
    """The STAC source, the collections and the bands read."""

    source: Literal["earth-search"]
    url: str
    primary: str
    sensitivity: str
    resolution_m: float = Field(gt=0)
    assets: dict[str, str] = Field(description="Earth Search asset key -> band name")

    @model_validator(mode="after")
    def _check(self) -> Imagery:
        needed = {"scl", "red", "green", "swir16", "nir08", "blue", "rededge1"}
        if missing := needed - set(self.assets):
            raise ValueError(f"imagery assets missing: {sorted(missing)}")
        return self

    def band_asset(self, band: str) -> str:
        """The asset key holding a band.

        Args:
            band: E.g. ``B8A``.

        Returns:
            The asset key, e.g. ``nir08``.
        """
        return next(k for k, v in self.assets.items() if v == band)


class Stations(_Frozen):
    """The metadata-only station selection rule."""

    stream: str
    quality_resource: str
    quality_variables: tuple[str, ...] = Field(min_length=1)
    samples_since: date
    bucket: str
    catalog: str
    variables_catalog: str
    daily_labels: tuple[str, ...]
    monthly_labels: tuple[str, ...]
    grid_half_size_m: float = Field(gt=0)
    water_frequency_min: float = Field(gt=0, le=1)
    min_observations: int = Field(gt=0)
    mask_fallback: Literal["mndwi"]
    snap_radius_m: float = Field(gt=0)
    width_search_m: float = Field(gt=0)
    min_width_m: float = Field(gt=0)


class WindowSettings(_Frozen):
    """The station extraction window."""

    radius_m: float = Field(gt=0)
    sensitivity_radius_m: float = Field(gt=0)
    erosion_px: int = Field(ge=0)
    min_valid_px: int = Field(gt=0)
    max_contamination: float = Field(ge=0, le=1)
    abstain_glint_share: float = Field(ge=0, le=1)


class Matchups(_Frozen):
    """How samples meet scenes, and the hold-out."""

    primary_days: int = Field(ge=0)
    sensitivity_days: int = Field(ge=0)
    daily_target_days: int = Field(ge=0)
    replicates: Literal["median"]
    censored: Literal["exclude_from_fits"]
    holdout_share: float = Field(gt=0, lt=1)
    quality_states: Literal["all"]


class Candidate(_Frozen):
    """One band or ratio tested against the targets."""

    id: str
    formula: str


class Target(_Frozen):
    """One in-situ variable."""

    id: Literal["turbidity", "tss", "cm_d"]
    kind: Literal["sample", "daily"]
    unit: str
    variable: str | None = None
    label: str | None = None
    note: str | None = None


class Stage1(_Frozen):
    """Band diagnostic criteria."""

    min_train: int = Field(gt=2)
    rho_min: float = Field(gt=0, lt=1)
    lower_bound_min: float = Field(gt=-1, lt=1)
    resamples: int = Field(gt=0)
    confidence: float = Field(gt=0, lt=1)
    top_per_target: int = Field(gt=0)


class Acolite(_Frozen):
    """The ACOLITE sensitivity (Stage 2c)."""

    repository: str
    time_box_h: float = Field(gt=0)
    l1c_dir: str


class Stage2(_Frozen):
    """Processing homogeneity checks."""

    family_min_scenes: int = Field(gt=0)
    homogeneity_p: float = Field(gt=0, lt=1)
    shift_sigma: float = Field(gt=0)
    acolite: Acolite


class Stage3(_Frozen):
    """Calibration criteria."""

    min_holdout: int = Field(gt=0)
    mdsa_max: float = Field(gt=0)
    sspb_abs_max: float = Field(gt=0)
    null_ratio_max: float = Field(gt=0)
    ridge_min_per_feature: int = Field(gt=0)
    ridge_lambdas: tuple[float, ...] = Field(min_length=1)


class Stage4(_Frozen):
    """Transfer of published models (report-only)."""

    models: tuple[str, ...]
    coefficients_source: Literal["acolite"]


class Width(_Frozen):
    """Water extent against discharge (5b)."""

    window_radius_m: float = Field(gt=0)
    valid_fraction_min: float = Field(gt=0, le=1)
    water_rule: Literal["mndwi_gt_0"]
    rho_min: float = Field(gt=0, lt=1)
    lower_bound_min: float = Field(gt=-1, lt=1)
    report_lags_days: tuple[int, ...]
    resamples: int = Field(gt=0)


class Enso(_Frozen):
    """Known climate periods (5c)."""

    oni_url: str
    threshold: float = Field(gt=0)
    min_consecutive_seasons: int = Field(gt=0)
    permutations: int = Field(gt=0)
    alpha: float = Field(gt=0, lt=1)
    magnitude_sigma: float = Field(gt=0)


class Climate(_Frozen):
    """Climate and hydrology (Stage 5)."""

    reach: str
    reach_scenes: str
    signals: tuple[Literal["upstream", "downstream", "delta"], ...]
    rain_grid: str
    open_meteo: str
    chirps_template: str
    harmonics: int = Field(gt=0)
    rain_windows_days: tuple[int, ...] = Field(min_length=1)
    hydrological_year_start_month: int = Field(ge=1, le=12)
    skill_min: float
    label_z: float = Field(gt=0)
    width: Width
    enso: Enso


class Outputs(_Frozen):
    """Where snapshots and results go."""

    inputs: str
    results: str
    observations_sample: str
    max_committed_bytes: int = Field(gt=0)


class CalibrationConfig(_Frozen):
    """Everything in ``pipeline/calibration.yaml``."""

    title: str
    preregistration: str
    screening_config: str
    seed: int
    period: Period
    geometry_period: Period
    timezone: str
    imagery: Imagery
    stations: Stations
    window: WindowSettings
    matchups: Matchups
    candidates: tuple[Candidate, ...] = Field(min_length=1)
    targets: tuple[Target, ...] = Field(min_length=1)
    stage1: Stage1
    stage2: Stage2
    stage3: Stage3
    stage4: Stage4
    climate: Climate
    outputs: Outputs

    @model_validator(mode="after")
    def _check(self) -> CalibrationConfig:
        ids = [c.id for c in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate ids must be unique")
        for target in self.targets:
            if target.kind == "sample" and not target.variable:
                raise ValueError(f"{target.id}: a sample target names its variable")
            if target.kind == "daily" and not target.label:
                raise ValueError(f"{target.id}: a daily target names its bucket label")
        if not (
            self.period.contains(self.geometry_period.start)
            and self.period.contains(self.geometry_period.end)
        ):
            raise ValueError("the geometry period must lie inside the period")
        return self

    def target(self, target_id: str) -> Target:
        """A target by id.

        Args:
            target_id: E.g. ``tss``.

        Returns:
            The target.
        """
        return next(t for t in self.targets if t.id == target_id)


def load_calibration_config(path: Path) -> CalibrationConfig:
    """Load and validate the settings file.

    Args:
        path: ``pipeline/calibration.yaml``.

    Returns:
        The settings.
    """
    with path.open(encoding="utf-8") as handle:
        return CalibrationConfig.model_validate(yaml.safe_load(handle))
