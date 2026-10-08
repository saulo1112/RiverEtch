"""Settings of the Urrá validation, pre-registered in ``docs/urra-validation/method.md``.

Every value lives in ``pipeline/urra-validation.yaml``; the thresholds the screening already fixed
(pixel guards, sub-reach geometry, the point rain rule) are read from ``pipeline/screening.yaml``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Window(_Frozen):
    """A period of days (inclusive)."""

    start: date
    end: date

    @model_validator(mode="after")
    def _check_order(self) -> Window:
        if self.start > self.end:
            raise ValueError(f"window starts after it ends: {self.start} > {self.end}")
        return self

    def contains(self, day: date) -> bool:
        """Whether a day falls in the window.

        Args:
            day: The day.

        Returns:
            True if ``start <= day <= end``.
        """
        return self.start <= day <= self.end


class SiteRoles(_Frozen):
    """Which screened reach plays which part."""

    target: str
    control: str
    reference: str


class ScreeningReference(_Frozen):
    """The screening outputs the validation must reproduce for 2022-2025."""

    results: str = Field(description="folder of the screening variant that is reproduced")
    evidence_sha256: dict[str, str] = Field(description="SHA-256 of the 2022-2025 item ids")
    events_sha256: str = Field(description="hash of the frozen event catalog")
    ndti_decimals: int = Field(default=4, ge=1)


BaselineKind = Literal["season-then-all", "season", "month-window", "day-window"]


class Variant(_Frozen):
    """One assumption variant: the screening rule (D0) with exactly one thing changed."""

    id: str = Field(pattern=r"^[A-Z][A-Z0-9.]*$")
    description: str
    baseline: BaselineKind
    season_min: int = Field(default=8, gt=1)
    all_min: int = Field(default=12, gt=1)
    window_min: int = Field(default=8, gt=1, description="month-window and day-window minimum")
    month_halfwidth: int = Field(default=1, ge=0, le=5)
    day_halfwidth: int = Field(default=182, gt=0)
    anomaly_z: float = Field(default=3.0, gt=0)
    swir16_max: float = Field(default=0.05, gt=0, description="pixel B11 glint limit")
    max_glint_share: float | None = Field(
        default=None, ge=0, le=1, description="drop scenes above this glint share"
    )
    distinct: bool = Field(description="counts in the report-only distinct-variant persistence")


class Criteria(_Frozen):
    """The two pre-registered criteria of a candidate signal."""

    persistence_min: int = Field(gt=0, description="variants a scene must be flagged in")
    episode_gap_days: int = Field(ge=0, description="anomalous scenes this close merge")
    min_episodes: int = Field(gt=0)
    share_ratio_min: float = Field(gt=0, description="target / control anomalous-scene share")
    zero_share_numerator: float = Field(
        gt=0, description="a control share of 0 counts as this many scenes over n"
    )


class CatchmentConfig(_Frozen):
    """The catchment rain rule and the grid it is computed on."""

    hydrobasins_url: str
    hydrobasins_layer: str
    anchor_tolerance_deg: float = Field(gt=0)
    spacings_deg: tuple[float, ...] = Field(min_length=1)
    points_min: int = Field(gt=0)
    points_max: int = Field(gt=0)
    windows_h: tuple[int, ...] = Field(min_length=1)
    statistics: tuple[Literal["mean", "max"], ...] = Field(min_length=1)
    percentile: float = Field(gt=0, lt=100)
    sample_hour_utc: int = Field(ge=0, le=23)
    grid_csv: str
    request_pause_s: float = Field(ge=0)
    max_attempts: int = Field(gt=0)

    @model_validator(mode="after")
    def _check(self) -> CatchmentConfig:
        if list(self.spacings_deg) != sorted(self.spacings_deg, reverse=True):
            raise ValueError("catchment spacings must go from coarsest to finest")
        if self.points_min > self.points_max:
            raise ValueError("catchment points_min > points_max")
        return self


class RainValidation(_Frozen):
    """Rain coincidence: the screening's point rule, the catchment rule and their union."""

    catchment: CatchmentConfig
    unknown_is_coincident: Literal[True] = Field(
        description="a scene whose rain cannot be computed counts as rain-coincident"
    )


class ChirpsConfig(_Frozen):
    """CHIRPS: probed and compared, never used in the criteria."""

    cog_url_template: str = Field(description="with {year} and {date} (YYYY.MM.DD)")
    probe_date: date
    days_before: int = Field(gt=0)


class PlaceboConfig(_Frozen):
    """Within-season shuffles of the target's scenes."""

    shuffles: int = Field(gt=0)
    seed: int


class EventTest(_Frozen):
    """Event windows and chance windows (report-only), on the frozen catalog."""

    catalog: str
    window_before_days: int = Field(ge=0)
    window_after_days: int = Field(ge=0)
    scored_precisions: tuple[str, ...]
    chance_windows: int = Field(gt=0)
    seed: int


class Outputs(_Frozen):
    """Where results go and how large committed files may be."""

    results: str
    case_json: str
    case_sample: str
    max_committed_bytes: int = Field(gt=0)


class ValidationConfig(_Frozen):
    """Everything in ``pipeline/urra-validation.yaml``."""

    screening_config: str
    method: str
    sites: SiteRoles
    mask_variant: Literal["post-hoc"]
    period: Window
    geometry_period: Window
    holdout: Window
    rainy_months: dict[str, tuple[int, ...]]
    screening_reference: ScreeningReference
    variants: tuple[Variant, ...]
    criteria: Criteria
    rain: RainValidation
    chirps: ChirpsConfig
    placebo: PlaceboConfig
    seasonality_halfwidth_days: int = Field(gt=0)
    events: EventTest
    outputs: Outputs

    @model_validator(mode="after")
    def _check(self) -> ValidationConfig:
        ids = [v.id for v in self.variants]
        if len(ids) != len(set(ids)) or "D0" not in ids:
            raise ValueError("variants need unique ids, one of them D0")
        if not self.criteria.persistence_min <= len(ids):
            raise ValueError("persistence_min exceeds the number of variants")
        roles = (self.sites.target, self.sites.control, self.sites.reference)
        if len(set(roles)) != 3 or set(roles) - set(self.rainy_months):
            raise ValueError("target, control and reference must differ and have rainy months")
        for site, months in self.rainy_months.items():
            if not months or not set(months) <= set(range(1, 13)):
                raise ValueError(f"{site}: rainy months must be 1-12")
        inside = (
            self.period.contains(self.geometry_period.start)
            and self.period.contains(self.geometry_period.end)
            and self.period.contains(self.holdout.start)
            and self.period.contains(self.holdout.end)
        )
        if not inside:
            raise ValueError("geometry and hold-out periods must lie inside the period")
        return self

    def variant(self, variant_id: str) -> Variant:
        """A variant by id.

        Args:
            variant_id: E.g. ``D0``.

        Returns:
            The variant.
        """
        return next(v for v in self.variants if v.id == variant_id)


def load_validation_config(path: Path) -> ValidationConfig:
    """Load and validate ``urra-validation.yaml``.

    Args:
        path: The file.

    Returns:
        The validated settings.
    """
    return ValidationConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
