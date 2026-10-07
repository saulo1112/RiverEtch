import copy
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from climate_pipeline.screening import stac
from climate_pipeline.screening.config import AssetKeys, StacSourceConfig
from climate_pipeline.screening.stac import (
    EarthSearchSource,
    PlanetaryComputerSource,
    ScalingError,
    evidence_hash,
    group_acquisitions,
    parse_baseline,
    parse_item,
    reflectance_scaling,
)

FIXTURE = Path(__file__).parent / "fixtures" / "earth_search_item.json"
ES_KEYS = AssetKeys(scl="scl", red="red", green="green", swir16="swir16")


def item(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text())
    data = copy.deepcopy(data)
    for key, value in changes.items():
        if key in ("id", "bbox"):
            data[key] = value
        else:
            data["properties"][key] = value
    return data


def set_offsets(data: dict[str, Any], offset: float | None) -> dict[str, Any]:
    for name in ("red", "green", "swir16"):
        band = data["assets"][name]["raster:bands"][0]
        if offset is None:
            band.pop("offset", None)
            band.pop("scale", None)
        else:
            band["offset"] = offset
    return data


def test_parse_item_reads_identity_projection_and_scaling() -> None:
    scene = parse_item(item(), ES_KEYS)
    assert scene.item_id == "S2B_18NUL_20230807_0_L2A"
    assert scene.datetime == datetime(2023, 8, 7, 15, 36, 41, 157000, tzinfo=UTC)
    assert scene.platform == "sentinel-2b"
    assert scene.mgrs_tile == "18NUL"
    assert scene.relative_orbit == 25
    assert scene.processing_baseline == pytest.approx(5.09)
    assert scene.epsg == 32618
    assert set(scene.assets) == {"scl", "red", "green", "swir16"}
    assert scene.assets["red"].href.endswith("/B04.tif")
    assert reflectance_scaling(scene, "red") == (0.0001, -0.1)
    assert scene.scaling_status() == "ok"


def test_parse_item_reads_proj_code_and_mgrs_from_the_id() -> None:
    data = item()
    del data["properties"]["proj:epsg"]
    data["properties"]["proj:code"] = "EPSG:32617"
    for key in ("grid:code", "mgrs:utm_zone", "mgrs:latitude_band", "mgrs:grid_square"):
        del data["properties"][key]
    scene = parse_item(data, ES_KEYS)
    assert scene.epsg == 32617
    assert scene.mgrs_tile == "18NUL"


def test_pre_2022_baseline_without_offset_is_consistent() -> None:
    data = set_offsets(item(**{"s2:processing_baseline": "03.01"}), 0.0)
    assert parse_item(data, ES_KEYS).scaling_status() == "ok"


def test_offset_that_disagrees_with_the_baseline_is_flagged() -> None:
    newer_without_offset = set_offsets(item(), 0.0)
    older_with_offset = item(**{"s2:processing_baseline": "03.01"})
    assert parse_item(newer_without_offset, ES_KEYS).scaling_status() == "conflict"
    assert parse_item(older_with_offset, ES_KEYS).scaling_status() == "conflict"


def test_missing_scaling_is_never_guessed() -> None:
    scene = parse_item(set_offsets(item(), None), ES_KEYS)
    assert scene.scaling_status() == "missing"
    with pytest.raises(ScalingError):
        reflectance_scaling(scene, "red")


def test_unknown_baseline_is_reported() -> None:
    data = item()
    del data["properties"]["s2:processing_baseline"]
    assert parse_item(data, ES_KEYS).scaling_status() == "unknown-baseline"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("05.10", 5.10), ("N0400", 4.0), ("0301", 3.01), (None, None), ("x", None)],
)
def test_parse_baseline(raw: object, expected: float | None) -> None:
    assert parse_baseline(raw) == (pytest.approx(expected) if expected is not None else None)


def test_scl_asset_is_required() -> None:
    data = item()
    del data["assets"]["scl"]
    with pytest.raises(KeyError):
        parse_item(data, ES_KEYS)


def test_acquisitions_merge_tiles_of_one_pass_and_keep_the_newest_processing() -> None:
    a = parse_item(item(), ES_KEYS)
    neighbour = parse_item(
        item(id="S2B_18NVL_20230807_0_L2A", **{"grid:code": "MGRS-18NVL"}), ES_KEYS
    )
    reprocessed = parse_item(
        item(id="S2B_18NUL_20230807_1_L2A", **{"s2:processing_baseline": "05.10"}), ES_KEYS
    )
    other_pass = parse_item(
        item(
            id="S2A_18NUL_20230812_0_L2A",
            datetime="2023-08-12T15:36:41Z",
            platform="sentinel-2a",
            **{"sat:relative_orbit": 25},
        ),
        ES_KEYS,
    )
    acquisitions = group_acquisitions([other_pass, a, neighbour, reprocessed])
    assert [acq.key for acq in acquisitions] == [
        "sentinel-2b_2023-08-07_R025",
        "sentinel-2a_2023-08-12_R025",
    ]
    first = acquisitions[0]
    assert first.tiles == ("18NUL", "18NVL")
    assert {s.item_id for s in first.scenes} == {
        "S2B_18NUL_20230807_1_L2A",
        "S2B_18NVL_20230807_0_L2A",
    }


def test_evidence_hash_depends_only_on_the_item_ids() -> None:
    a = group_acquisitions([parse_item(item(), ES_KEYS)])
    b = group_acquisitions([parse_item(item(), ES_KEYS)])
    c = group_acquisitions([parse_item(item(id="S2B_18NUL_20230807_1_L2A"), ES_KEYS)])
    assert evidence_hash(a) == evidence_hash(b) != evidence_hash(c)


def test_earth_search_source_parses_search_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, ...]] = []

    def fake_search(*args: Any) -> list[dict[str, Any]]:
        calls.append(args)
        return [item()]

    monkeypatch.setattr(stac, "_search_dicts", fake_search)
    config = StacSourceConfig(
        url="https://example.test/v1", collection="sentinel-2-l2a", assets=ES_KEYS
    )
    source = EarthSearchSource(config, page_size=50)
    scenes = source.search((-76.7, 5.6, -76.6, 5.7), date(2022, 1, 1), date(2025, 12, 31))
    assert [s.item_id for s in scenes] == ["S2B_18NUL_20230807_0_L2A"]
    assert calls[0][0] == "https://example.test/v1"
    assert calls[0][-1] == 50
    assert source.sign("https://x/y.tif") == "https://x/y.tif"


def test_planetary_computer_appends_and_caches_the_sas_token() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(
            200, json={"token": "sv=1&sig=abc", "msft:expiry": "2999-01-01T00:00:00Z"}
        )

    config = StacSourceConfig(
        url="https://pc.test/api/stac/v1",
        collection="sentinel-2-l2a",
        assets=AssetKeys(scl="SCL", red="B04", green="B03", swir16="B11"),
        sas_token_url="https://pc.test/token/sentinel-2-l2a",
    )
    source = PlanetaryComputerSource(
        config, 100, http=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert source.sign("https://blob/a.tif") == "https://blob/a.tif?sv=1&sig=abc"
    assert source.sign("https://blob/b.tif?x=1") == "https://blob/b.tif?x=1&sv=1&sig=abc"
    assert requests == ["https://pc.test/token/sentinel-2-l2a"]


def test_relative_orbit_falls_back_to_the_product_name() -> None:
    data = item()
    del data["properties"]["sat:relative_orbit"]
    data["properties"]["s2:product_uri"] = (
        "S2B_MSIL2A_20230807T153619_N0509_R025_T18NUL_20230807T195442.SAFE"
    )
    assert parse_item(data, ES_KEYS).relative_orbit == 25


def test_split_granules_with_the_same_baseline_are_both_kept() -> None:
    first = parse_item(item(), ES_KEYS)
    second = parse_item(item(id="S2B_18NUL_20230807_1_L2A"), ES_KEYS)
    (acquisition,) = group_acquisitions([first, second])
    assert {s.item_id for s in acquisition.scenes} == {first.item_id, second.item_id}


def test_malformed_items_are_skipped() -> None:
    broken = item()
    del broken["assets"]["scl"]
    scenes = stac.parse_items([broken, item(id="S2B_18NUL_20230807_1_L2A")], ES_KEYS)
    assert [s.item_id for s in scenes] == ["S2B_18NUL_20230807_1_L2A"]
