import numpy as np

from climate_pipeline.reach import render


def test_ndti_bytes_span_the_range_and_keep_zero_for_no_value() -> None:
    low, high = render.NDTI_RANGE
    out = render.ndti_bytes(np.array([low, 0.0, high, high + 1.0, np.nan]))
    assert out.tolist() == [1, 128, 255, 255, 0]


def test_a_map_packs_ndti_place_sub_reach_and_inside() -> None:
    ndti = np.array([[0.0, 0.3, 0.1], [np.nan, -0.3, 0.2]])
    up = np.array([[True, True, False], [False, False, False]])
    down = np.array([[False, False, True], [False, True, True]])
    usable = np.array([[True, False, True], [False, True, True]])
    progress = np.array([[0.0, 0.5, 1.0], [0.0, 0.25, 1.0]])
    rgba = render.encode(ndti, {"upstream": up, "downstream": down},
                         {"upstream": up & usable, "downstream": down & usable},
                         progress)  # fmt: skip
    assert rgba[..., 3].tolist() == [[255, 255, 255], [0, 255, 255]]
    assert rgba[..., 2].tolist() == [[1, 1 + render.UNUSABLE, 2], [0, 2, 2]]
    assert rgba[0, 1, 0] == 0  # an unusable pixel carries no NDTI
    assert rgba[0, 0, 0] == 128 and rgba[1, 1, 0] == 1
    assert rgba[..., 1].tolist() == [[0, 128, 255], [0, 64, 255]]
