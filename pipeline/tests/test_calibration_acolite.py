from typing import Any

from climate_pipeline.calibration.acolite import covers, datatake, l1c_item

SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
PRODUCT = "S2B_MSIL1C_20230128T152639_N0509_R025_T18NXP_20230128T184739.SAFE"


def item(item_id: str, platform: str, product: str, geometry: dict[str, Any]) -> dict[str, Any]:
    return {"id": item_id, "geometry": geometry,
            "properties": {"platform": platform, "s2:product_uri": product}}  # fmt: skip


def test_covers_needs_every_corner_inside_one_polygon() -> None:
    assert covers(SQUARE, (0.2, 0.2, 0.8, 0.8))
    assert not covers(SQUARE, (0.5, 0.5, 1.5, 0.8))
    multi = {"type": "MultiPolygon", "coordinates": [SQUARE["coordinates"],
             [[[2, 0], [3, 0], [3, 1], [2, 1], [2, 0]]]]}  # fmt: skip
    assert covers(multi, (2.2, 0.2, 2.8, 0.8))
    assert not covers(multi, (0.5, 0.2, 2.5, 0.8))  # straddles both parts


def test_l1c_item_matches_platform_orbit_and_footprint() -> None:
    box = (0.4, 0.4, 0.6, 0.6)
    half = {"type": "Polygon", "coordinates": [[[0, 0], [0.5, 0], [0.5, 1], [0, 1], [0, 0]]]}
    other_orbit = PRODUCT.replace("_R025_", "_R125_")
    items = [
        item("S2B_18NXQ_20230128_0_L1C", "sentinel-2b", PRODUCT, half),  # partial footprint
        item("S2A_18NXP_20230128_0_L1C", "sentinel-2a", PRODUCT, SQUARE),  # other satellite
        item("S2B_18NXR_20230128_0_L1C", "sentinel-2b", other_orbit, SQUARE),  # other orbit
        item("S2B_18NXP_20230128_0_L1C", "sentinel-2b", PRODUCT, SQUARE),
    ]
    chosen = l1c_item(items, "sentinel-2b_2023-01-28_R025", box)
    assert chosen is not None and chosen["id"] == "S2B_18NXP_20230128_0_L1C"
    assert l1c_item(items[:3], "sentinel-2b_2023-01-28_R025", box) is None


def test_datatake_ignores_the_processing_baseline() -> None:
    assert datatake(PRODUCT) == "S2B_MSIL1C_20230128T152639"
    reprocessed = "S2B_MSIL1C_20230128T152639_N0510_R025_T18NXP_20240810T065055.SAFE"
    assert datatake(reprocessed) == datatake(PRODUCT)
    assert datatake("not a product") == ""
