"""Settings of the reach runs (``pipeline/reach.yaml``), checked."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Reach(_Frozen):
    """One published reach."""

    site: str = Field(description="site id in pipeline/sites/")
    estimate_station: str = Field(description="the D15 station whose window the models read")
    rainy_months: tuple[int, ...] = Field(min_length=1)
    geometry_start: date = Field(description="the water mask is built from these scenes only")
    geometry_end: date
    ndti_scenes: str = Field(description="frozen NDTI per scene (the validation's scenes.csv)")
    nir_red_baseline: str = Field(description="NIR/red per historical scene, written once")
    baseline_end: date = Field(description="last day of the frozen baselines")


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
