from dataclasses import replace
from pathlib import Path

import pytest

from climate_pipeline.screening.config import load_screening_config
from climate_pipeline.screening.score import (
    SiteInputs,
    score_sites,
    select_stage2,
    site_terms,
    weighted,
)

CONFIG = load_screening_config(Path(__file__).parents[1] / "screening.yaml")

BASE = SiteInputs(
    site_id="a",
    category="A",
    geometry_failed="",
    clear=60,
    clear_per_year=15.0,
    months_with_clear_pct=50.0,
    observable_per_year=20.0,
    months_with_observable_pct=60.0,
    width_px_10m=10.0,
    tile_integrity=0.8,
    median_weaker_subreach_water_px_10m=200.0,
    confluence_inside=False,
    events_with_clear_window=2,
)


def test_terms_are_anchored_in_absolute_units() -> None:
    terms = site_terms(BASE, CONFIG)
    assert terms["coverage"] == pytest.approx(0.5 * 15 / 24 + 0.5 * 0.5)
    assert terms["width"] == pytest.approx(0.5)
    assert terms["tile_integrity"] == pytest.approx(0.8)
    assert terms["contrast_feasibility"] == pytest.approx(0.5)
    assert terms["events"] == pytest.approx(2 / 3)
    capped = site_terms(
        replace(BASE, clear_per_year=99, width_px_10m=40, confluence_inside=True), CONFIG
    )
    assert capped["width"] == 1
    assert capped["contrast_feasibility"] == pytest.approx(0.25)


def test_weighted_score_and_dropping_a_term() -> None:
    terms = {
        "coverage": 1.0,
        "width": 0.0,
        "tile_integrity": 1.0,
        "contrast_feasibility": 1.0,
        "events": 1.0,
    }
    assert weighted(terms, CONFIG.score.weights) == pytest.approx(0.8)
    assert weighted(terms, CONFIG.score.weights, drop="width") == pytest.approx(1.0)


def test_gates_exclude_whatever_the_score() -> None:
    narrow = replace(BASE, site_id="narrow", width_px_10m=4.0, events_with_clear_window=9)
    failed = replace(BASE, site_id="failed", geometry_failed="anchors are not connected")
    cloudy = replace(BASE, site_id="cloudy", clear=10)
    ranked = score_sites([narrow, failed, cloudy, BASE], CONFIG)
    assert ranked[0].site_id == "a" and ranked[0].eligible
    gated = {s.site_id: s.gates for s in ranked[1:]}
    assert "width" in gated["narrow"][0]
    assert "mask failed" in gated["failed"][0]
    assert "clear scenes" in gated["cloudy"][0]


def test_stage2_selection_caps_benchmarks_and_adds_the_control() -> None:
    sites = [
        replace(BASE, site_id="mine1", category="B", events_with_clear_window=3, clear_per_year=24),
        replace(BASE, site_id="mine2", category="B", events_with_clear_window=3, clear_per_year=23),
        replace(BASE, site_id="dam1", category="A"),
        replace(BASE, site_id="dam2", category="A", width_px_10m=8.0),
        replace(BASE, site_id="dredge", category="C", width_px_10m=6.0),
        replace(BASE, site_id="control", category="D", events_with_clear_window=0),
    ]
    ranked = score_sites(sites, CONFIG)
    assert select_stage2(ranked, CONFIG) == ["mine1", "dam1", "dam2", "control"]
    assert set(ranked[0].ranks_without) == {
        "coverage",
        "width",
        "tile_integrity",
        "contrast_feasibility",
        "events",
        "observable_coverage",
    }


def test_gated_control_is_left_out() -> None:
    sites = [BASE, replace(BASE, site_id="control", category="D", clear=3)]
    assert select_stage2(score_sites(sites, CONFIG), CONFIG) == ["a"]


def test_recommendation_skips_benchmarks_and_flags_fragile_rankings() -> None:
    from climate_pipeline.screening.score import recommend

    sites = [
        replace(BASE, site_id="mine", category="B", clear_per_year=24, events_with_clear_window=3),
        replace(BASE, site_id="dam1", category="A", events_with_clear_window=3, width_px_10m=6),
        replace(BASE, site_id="dam2", category="A", events_with_clear_window=0, width_px_10m=15),
        replace(BASE, site_id="control", category="D"),
    ]
    rec = recommend(score_sites(sites, CONFIG))
    assert rec.recommended == "dam1" and rec.runner_up == "dam2"
    assert rec.fragile and any("without events: dam2" in c for c in rec.changes)
    assert recommend(score_sites([replace(BASE, category="B")], CONFIG)).recommended is None
