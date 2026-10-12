from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from climate_pipeline.calibration.config import load_calibration_config
from climate_pipeline.quality.config import QualityConfig, load_quality_config

PIPELINE = Path(__file__).parents[1]


def raw() -> dict[str, Any]:
    with (PIPELINE / "water-quality.yaml").open(encoding="utf-8") as handle:
        data: dict[str, Any] = yaml.safe_load(handle)
    return data


def test_the_committed_settings_load() -> None:
    cfg = load_quality_config(PIPELINE / "water-quality.yaml")
    assert cfg.stations.test_stream == "MAGDALENA"
    assert [c.id for c in cfg.candidates] == ["M0", "A1", "A2", "A3", "A4", "B1", "B2", "B3"]
    assert cfg.target("turbidity").bins == (30, 100, 300, 1000)
    assert cfg.levels.estimated.mdsa_max == 60 and cfg.levels.validated.mdsa_max == 50


def test_one_source_serves_each_date() -> None:
    cfg = load_quality_config(PIPELINE / "water-quality.yaml")
    assert cfg.imagery.source_for(date(2017, 6, 1)) == "planetary-computer"
    assert cfg.imagery.source_for(date(2018, 11, 30)) == "planetary-computer"
    assert cfg.imagery.source_for(date(2018, 12, 1)) == "earth-search"


def test_the_rules_called_unchanged_match_d15() -> None:
    cfg = load_quality_config(PIPELINE / "water-quality.yaml")
    d15 = load_calibration_config(PIPELINE / "calibration.yaml")
    for field in ("grid_half_size_m", "water_frequency_min", "min_observations", "mask_fallback",
                  "snap_radius_m", "width_search_m", "min_width_m", "quality_resource",
                  "quality_variables", "bucket", "catalog"):  # fmt: skip
        assert getattr(cfg.stations, field) == getattr(d15.stations, field), field
    for field in ("radius_m", "erosion_px", "min_valid_px", "max_contamination",
                  "abstain_glint_share"):  # fmt: skip
        assert getattr(cfg.window, field) == getattr(d15.window, field), field
    assert cfg.geometry_period == d15.geometry_period
    assert cfg.route_b.acolite_commit == "ca477dd91dfb5f8eb77333824b38cb0bcce5e083"
    assert cfg.window.as_calibration().min_valid_px == d15.window.min_valid_px


def test_range_bins_count_edges_below_the_value() -> None:
    target = load_quality_config(PIPELINE / "water-quality.yaml").target("turbidity")
    assert [target.bin_of(v) for v in (10, 30, 99.9, 300, 5000)] == [0, 1, 1, 3, 4]


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("levels", "estimated", "mdsa_max"), 40.0, "stricter than validated"),
        (("stations", "test_stream"), "RIN", "not among the streams"),
        (("targets", 0, "bins"), [100, 30], "strictly increasing"),
        (("candidates", 5, "route"), "A", "not a route A model"),
        (("usgs", "overpass_nearest_minutes"), 10, "narrower"),
        (("imagery", "split_date"), "2014-01-01", "split date"),
    ],
)
def test_inconsistent_settings_are_refused(path: tuple[Any, ...], value: Any, message: str) -> None:
    data = raw()
    node: Any = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(ValidationError, match=message):
        QualityConfig.model_validate(data)
