import math
from pathlib import Path

from climate_pipeline.quality import gauged, site
from climate_pipeline.quality.config import load_quality_config

PIPELINE = Path(__file__).parents[1]
CFG = load_quality_config(PIPELINE / "water-quality.yaml")
GOOD = {"n": 60.0, "mdsa": 30.0, "sspb": 5.0, "null_mdsa": 100.0, "rho_low": 0.6}


def test_v5_accepts_a_conservative_interval_but_caps_its_width() -> None:
    wide = {**GOOD, "coverage90": 0.99, "interval_factor90": 2.0}
    assert site.site_level(wide, CFG, 3, "v4") == "indicative"  # v4's ceiling fails it
    assert site.site_level(wide, CFG, 3, "v5") == "validated"
    assert site.site_level({**wide, "interval_factor90": 2.8}, CFG, 3, "v5") == "estimated"
    assert site.site_level({**wide, "interval_factor90": 3.5}, CFG, 3, "v5") == "indicative"
    assert site.site_level({**wide, "coverage90": 0.7}, CFG, 3, "v5") == "indicative"


def test_the_demo_takes_the_best_levels_then_the_lowest_error() -> None:
    reaches = [
        {"slug": "a", "level": "estimated", "mdsa": 40.0, "n": 50},
        {"slug": "b", "level": "validated", "mdsa": 45.0, "n": 30},
        {"slug": "c", "level": "estimated", "mdsa": 35.0, "n": 25},
        {"slug": "d", "level": "indicative", "mdsa": 20.0, "n": 90},
        {"slug": "e", "level": "estimated", "mdsa": math.nan, "n": 99},
    ]
    assert gauged.demo(reaches) == ["b", "c"]
    assert gauged.demo(reaches, 4) == ["b", "c", "a", "e"]


def test_every_new_site_gets_turbidity_and_its_ssc_target() -> None:
    planned = gauged.runs(PIPELINE.parent, CFG)
    if not planned:  # the site list is committed with v5's snapshots
        return
    turbidity = {r.site for r, s in planned if s == "turbidity"}
    assert site.SITE not in turbidity and len(turbidity) == 10
    sources = {(r.site, s) for r, s in planned if r.target == "tss"}
    assert ("USGS-14144700", "surrogate") in sources and ("USGS-07381600", "ssc") in sources
    assert all(r.rule == "v5" for r, _ in planned)
    labs = {r.site: r.lab for r, _ in planned}
    assert labs["USGS-07020850"] == "no-mississippi" and labs["USGS-14246900"] == ""
