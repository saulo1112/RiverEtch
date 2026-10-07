import itertools
import math
from pathlib import Path

import numpy as np
import pytest

from climate_pipeline.screening.config import SubreachConfig, load_screening_config
from climate_pipeline.screening.mask import (
    FrequencyStack,
    RiverGeometry,
    component,
    derive_geometry,
    dilate,
    erode,
    histogram,
    land_ring,
    place_subreaches,
    shortest_path,
    snap,
    upsample2,
)

CONFIG = load_screening_config(Path(__file__).parents[1] / "screening.yaml")
RES = 20.0


def draw(mask: np.ndarray, points: list[tuple[float, float]], half: int) -> None:
    """Thick polyline through (row, col) points."""
    for (r0, c0), (r1, c1) in itertools.pairwise(points):
        n = int(max(abs(r1 - r0), abs(c1 - c0))) + 1
        for t in np.linspace(0.0, 1.0, n):
            r, c = round(r0 + (r1 - r0) * t), round(c0 + (c1 - c0) * t)
            mask[max(0, r - half) : r + half + 1, max(0, c - half) : c + half + 1] = True


def meander(rows: int = 400, cols: int = 1000) -> list[tuple[float, float]]:
    """A sinuous centerline from the left edge to the right edge (~22 km at 20 m)."""
    cs = np.linspace(20, cols - 20, 200)
    return [(rows / 2 + 120 * math.sin(c / 90.0), float(c)) for c in cs]


def frequency(river: np.ndarray) -> np.ndarray:
    freq = np.where(river, 0.9, 0.05)
    freq[:5, :5] = np.nan
    return freq


def derive(
    freq: np.ndarray, up: tuple[int, int], down: tuple[int, int], **overrides: object
) -> RiverGeometry:
    args: dict[str, object] = {
        "resolution": RES,
        "thresholds": (0.5,),
        "upstream": up,
        "downstream": down,
        "center": up,
        "confluences": {},
        "excluded": None,
        "snap_radius_m": CONFIG.mask.snap_radius_m,
        "corridor_half_width_m": CONFIG.mask.corridor_half_width_m,
        "erosion_px_10m": 1,
        "land_ring_m": CONFIG.mask.land_ring_m,
        "subreach": CONFIG.subreach,
    }
    args.update(overrides)
    return derive_geometry(freq, **args)  # type: ignore[arg-type]


def test_frequency_stack_counts_water_among_clear_observations() -> None:
    stack = FrequencyStack((1, 4), CONFIG.scl)
    stack.update(np.array([[6, 6, 9, 0]], dtype=np.uint8))
    stack.update(np.array([[6, 5, 6, 0]], dtype=np.uint8))
    stack.update(np.array([[7, 5, 3, 0]], dtype=np.uint8))
    assert stack.valid.tolist() == [[3, 3, 1, 0]]
    assert stack.water.tolist() == [[2, 1, 1, 0]]
    freq = stack.frequency(min_observations=2)
    assert freq[0, 0] == pytest.approx(2 / 3)
    assert freq[0, 1] == pytest.approx(1 / 3)
    assert np.isnan(freq[0, 2]) and np.isnan(freq[0, 3])
    assert histogram(freq) == [0, 0, 0, 1, 0, 0, 1, 0, 0, 0]


def test_morphology_helpers() -> None:
    m = np.zeros((7, 7), dtype=bool)
    m[2:5, 2:5] = True
    assert erode(m, 1).sum() == 1
    assert dilate(m, 1).sum() == 25
    assert upsample2(m).shape == (14, 14) and upsample2(m).sum() == 36


def test_snap_finds_the_nearest_mask_pixel_within_the_radius() -> None:
    m = np.zeros((50, 50), dtype=bool)
    m[30, 10:40] = True
    assert snap(m, (20, 20), 15) == ((30, 20), 10.0)
    assert snap(m, (0, 0), 5) is None
    assert snap(m, (-100, -100), 5) is None


def test_component_ignores_diagonal_only_links() -> None:
    m = np.zeros((10, 10), dtype=bool)
    m[2, 0:5] = True  # river
    m[3, 5] = True  # pit touching the river diagonally only
    m[4, 5:9] = True
    region = component(m, (2, 0))
    assert region.sum() == 5
    assert not region[3, 5]


def test_shortest_path_does_not_cut_land_corners() -> None:
    m = np.zeros((5, 5), dtype=bool)
    m[0, 0:3] = True
    m[0:5, 2] = True
    path = shortest_path(m, (0, 0), (4, 2))
    assert path is not None
    assert path[0] == (0, 0) and path[-1] == (4, 2)
    for (r0, c0), (r1, c1) in itertools.pairwise(path):
        if r0 != r1 and c0 != c1:
            assert m[r1, c0] or m[r0, c1]


def test_meandering_river_gets_sub_reaches_5_to_15_km_apart() -> None:
    river = np.zeros((400, 1000), dtype=bool)
    line = meander()
    draw(river, line, half=4)  # 9 px = 180 m wide
    up = (round(line[0][0]) + 20, round(line[0][1]))  # 400 m off the channel
    down = (round(line[-1][0]), round(line[-1][1]))
    geom = derive(frequency(river), up, down)
    assert geom.failed is None
    assert geom.reach_length_m > 19_000
    assert 0 < geom.anchor_shifts_m["upstream_anchor"] <= 400  # snapped onto the channel
    assert geom.placement is not None
    assert 5_000 <= geom.placement.separation_m <= 15_000
    assert geom.placement.upstream[0] == pytest.approx(CONFIG.subreach.start_offset_m)
    up_sub, down_sub = geom.subreaches
    assert up_sub.mask.any() and down_sub.mask.any()
    assert not (up_sub.mask & down_sub.mask).any()
    assert not (up_sub.land_ring & river).any()
    # 9 px at 20 m = 18 px at 10 m; one-pixel erosion on each bank leaves about 16.
    assert geom.width_px_10m_raw["upstream"] == pytest.approx(19, rel=0.25)
    assert geom.width_px_10m["upstream"] < geom.width_px_10m_raw["upstream"]


def test_corridor_keeps_both_branches_of_a_braid_but_not_distant_lakes() -> None:
    river = np.zeros((400, 1000), dtype=bool)
    draw(river, [(200, 10), (200, 990)], half=3)
    draw(river, [(200, 300), (215, 350), (215, 500), (200, 550)], half=2)  # second branch
    river[205:211, 352:498] = False  # island between the branches
    river[340:380, 600:700] = True
    draw(river, [(203, 650), (360, 650)], half=1)  # a lake joined by a long channel
    geom = derive(frequency(river), (200, 12), (200, 988))
    assert geom.failed is None
    assert geom.corridor is not None
    assert geom.corridor[215, 420]  # other branch, ~300 m from the centerline
    assert not geom.corridor[360, 650]  # lake 3 km away


def test_corridor_drops_water_joined_to_the_river_only_outside_the_band() -> None:
    river = np.zeros((400, 1000), dtype=bool)
    draw(river, [(200, 10), (200, 990)], half=3)
    river[220:227, 400:461] = True  # a pit ~400-500 m from the centerline
    # Its only link to the river is a ditch that loops 1.2 km away before rejoining.
    draw(river, [(226, 430), (260, 430), (260, 560), (203, 560)], half=0)
    geom = derive(frequency(river), (200, 12), (200, 988))
    assert geom.failed is None and geom.corridor is not None
    assert not geom.corridor[223, 430]  # inside the band, but not main channel
    assert geom.corridor[215, 560]  # the ditch next to the river still joins inside the band
    assert geom.corridor[200, 430]


def test_threshold_fallback_reconnects_a_river_scl_rarely_calls_water() -> None:
    river = np.zeros((300, 1000), dtype=bool)
    draw(river, [(150, 10), (150, 990)], half=3)
    freq = frequency(river)
    freq[:, 480:520] = np.where(river[:, 480:520], 0.3, 0.05)
    assert (
        derive(freq, (150, 12), (150, 988)).failed == "anchors are not connected by the river mask"
    )
    geom = derive(freq, (150, 12), (150, 988), thresholds=(0.5, 0.35, 0.25))
    assert geom.failed is None
    assert geom.threshold == 0.25


def test_short_reach_and_missing_anchor_fail_with_a_reason() -> None:
    river = np.zeros((200, 400), dtype=bool)
    draw(river, [(100, 10), (100, 390)], half=3)  # 7.6 km
    assert "too short" in str(derive(frequency(river), (100, 12), (100, 388)).failed)
    assert "upstream anchor" in str(derive(frequency(river), (10, 12), (100, 388)).failed)


def test_excluded_polygons_are_removed_from_the_river() -> None:
    river = np.zeros((300, 1000), dtype=bool)
    draw(river, [(150, 10), (150, 990)], half=3)
    excluded = np.zeros_like(river)
    excluded[100:200, 495:505] = True
    geom = derive(frequency(river), (150, 12), (150, 988), excluded=excluded)
    assert geom.failed == "anchors are not connected by the river mask"


def test_confluences_are_kept_out_of_the_sub_reaches() -> None:
    cfg = CONFIG.subreach
    default = place_subreaches(20_000, [], cfg)
    assert default is not None and not default.confluence_inside
    inside_default_up = (default.upstream[0] + default.upstream[1]) / 2
    moved = place_subreaches(20_000, [inside_default_up], cfg)
    assert moved is not None
    assert not moved.confluence_inside
    assert moved.upstream != default.upstream
    unavoidable = place_subreaches(
        9_000,
        [x * 250.0 for x in range(40)],
        SubreachConfig(**{**cfg.model_dump(), "confluence_buffer_m": 0}),
    )
    assert unavoidable is not None and unavoidable.confluence_inside


def test_confluence_chainage_is_reported() -> None:
    river = np.zeros((300, 1000), dtype=bool)
    draw(river, [(150, 10), (150, 990)], half=3)
    draw(river, [(10, 600), (150, 600)], half=2)
    geom = derive(frequency(river), (150, 12), (150, 988), confluences={"tributary": (140, 600)})
    assert geom.confluence_chainage_m["tributary"] == pytest.approx(588 * RES, abs=100)
    assert geom.placement is not None and not geom.placement.confluence_inside


def test_anchors_snap_to_the_region_that_connects_them() -> None:
    river = np.zeros((300, 1000), dtype=bool)
    draw(river, [(150, 10), (150, 990)], half=3)
    river[100:120, 0:30] = True  # a pond nearer to the upstream anchor than the river
    river[100:120, 970:1000] = True  # and another near the downstream anchor
    geom = derive(frequency(river), (110, 35), (110, 965))
    assert geom.failed is None
    assert geom.centerline[0][0] in range(147, 154)


def test_land_ring_is_euclidean() -> None:
    sub = np.zeros((60, 60), dtype=bool)
    sub[30, 30] = True
    ring = land_ring(sub, np.zeros_like(sub), 5.0, 20.0)
    rr, cc = np.nonzero(ring)
    dist = np.hypot(rr - 30, cc - 30)
    assert dist.min() >= 5 and dist.max() <= 20
    assert ring[30, 50] and not ring[50, 50]  # 20 px along an axis, 28 px on the diagonal


def test_a_bridge_does_not_break_the_channel_but_is_not_water() -> None:
    river = np.zeros((300, 1000), dtype=bool)
    draw(river, [(150, 10), (150, 990)], half=4)
    river[:, 500:502] = False  # a 40 m bridge across the river
    assert derive(frequency(river), (150, 12), (150, 988)).failed is not None
    geom = derive(frequency(river), (150, 12), (150, 988), bridge_gap_px=1)
    assert geom.failed is None
    assert geom.corridor is not None and not geom.corridor[:, 500:502].any()
