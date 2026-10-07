from collections import Counter
from pathlib import Path

import pytest

from climate_pipeline.screening.config import SiteConfig, load_sites
from climate_pipeline.screening.rio import lonlat_rowcol, site_grid

SITES = load_sites(Path(__file__).parents[1] / "sites")
# Observations only: the hand-written fields never attribute cause or blame.
FORBIDDEN = ("caused", "responsible for", "illegal", "ilegal", "blame", "culprit", "guilty")


def test_site_ids_are_unique_and_categories_known() -> None:
    assert SITES
    ids = [s.id for s in SITES]
    assert len(ids) == len(set(ids))
    assert set(Counter(s.category for s in SITES)) <= {"A", "B", "C", "D"}


@pytest.mark.parametrize("site", SITES, ids=lambda s: s.id)
def test_site_is_sourced_and_fits_its_grid(site: SiteConfig) -> None:
    assert site.citations
    assert all(c.url.startswith("http") for c in site.citations)
    assert all(r.source_url.startswith("http") for r in site.regime_changes)
    assert site.rain_points[0].description == "reach center"
    grid = site_grid(site.aoi_bbox)
    for point in (site.upstream_anchor, site.downstream_anchor, site.center):
        row, col = lonlat_rowcol(grid, point.lon, point.lat)
        assert 0 <= row < grid.height and 0 <= col < grid.width


@pytest.mark.parametrize("site", SITES, ids=lambda s: s.id)
def test_site_text_is_observational(site: SiteConfig) -> None:
    text = " ".join((site.rationale, site.operator, site.regulator)).lower()
    assert not [word for word in FORBIDDEN if word in text]
