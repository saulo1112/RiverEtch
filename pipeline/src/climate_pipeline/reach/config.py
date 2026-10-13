"""Settings of the reach runs (``pipeline/reach.yaml``), checked."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Reach(_Frozen):
    """One published reach."""

    site: str = Field(description="site id")
    site_file: str | None = Field(
        default=None,
        description="the site file, relative to the root (default: pipeline/sites/<site>.yaml); "
        "a reach outside the screening keeps its file elsewhere so the screening never reads it",
    )
    estimate_station: str = Field(description="the station whose window the models read")
    station_source: Literal["ideam", "usgs"] = Field(
        default="ideam", description="the station list: IDEAM (stations.csv) or the USGS pilot"
    )
    timezone: str = Field(default="America/Bogota", description="local dates and rain")
    targets: tuple[str, ...] = Field(default=("turbidity", "tss"), min_length=1)
    cards: dict[str, str] = Field(
        default_factory=dict,
        description="target -> model card, relative to the root (default: the models folder)",
    )
    rainy_months: tuple[int, ...] = Field(min_length=1)
    geometry_start: date = Field(description="the water mask is built from these scenes only")
    geometry_end: date
    ndti_scenes: str | None = Field(
        default=None,
        description="frozen NDTI per scene (a validation's scenes.csv); without it the baseline "
        "measures NDTI itself on its usable scenes from baseline_start",
    )
    baseline_start: date | None = Field(default=None, description="first day of a baseline")
    nir_red_baseline: str = Field(description="NIR/red per historical scene, written once")
    baseline_end: date = Field(description="last day of the frozen baselines")
    baseline_max_gb: float | None = Field(default=None, gt=0, description="this reach's cap")

    @model_validator(mode="after")
    def _check(self) -> Reach:
        if self.ndti_scenes is None and self.baseline_start is None:
            raise ValueError(f"{self.site}: a reach without ndti_scenes needs baseline_start")
        if self.baseline_start is not None and self.baseline_start > self.baseline_end:
            raise ValueError(f"{self.site}: baseline_start is after baseline_end")
        return self

    def site_path(self, root: Path) -> Path:
        """The site file.

        Args:
            root: Repository root.

        Returns:
            Its path.
        """
        return root / (self.site_file or f"pipeline/sites/{self.site}.yaml")


class Budgets(_Frozen):
    """Per-run caps."""

    max_gb: float = Field(gt=0, description="estimated network per run")
    keep_free_gb: float = Field(ge=0, description="stop when free disk falls under this")
    baseline_max_gb: float = Field(gt=0, description="network cap of the one-off NIR/red baseline")


class ReachConfig(_Frozen):
    """The settings file."""

    title: str
    screening_config: str
    quality_config: str
    calibration_config: str
    models: str = Field(description="folder of the product's model cards")
    threshold: float = Field(gt=0, description="D0 |z| threshold (the screening's)")
    lookback_days: int = Field(ge=1, description="default first day of a run, before today")
    reaches: tuple[Reach, ...] = Field(min_length=1)
    budgets: Budgets
    out: str

    def reach(self, site: str) -> Reach:
        """A reach by site id.

        Args:
            site: E.g. ``magdalena-puerto-wilches``.

        Returns:
            The reach.

        Raises:
            KeyError: For a site that is not configured.
        """
        for r in self.reaches:
            if r.site == site:
                return r
        raise KeyError(f"no reach {site!r} in the settings")


def load_reach_config(path: Path) -> ReachConfig:
    """Load and validate the settings file.

    Args:
        path: ``pipeline/reach.yaml``.

    Returns:
        The settings.
    """
    with path.open(encoding="utf-8") as handle:
        return ReachConfig.model_validate(yaml.safe_load(handle))
