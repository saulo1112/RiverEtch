import json
from datetime import UTC, date, datetime

import numpy as np
import pytest
from pydantic import ValidationError

from climate_pipeline.screening.events import CatalogEvent
from climate_pipeline.screening.mask import RiverGeometry, Subreach
from climate_pipeline.screening.rio import site_grid
from climate_pipeline.screening.stage2 import Stage2Scene, SubreachNdti
from climate_pipeline.validation.case import (
    CaseFile,
    Context,
    ContextSource,
    Manifest,
    Permit,
    Rain,
    Ui,
    ValidationSummary,
    build_reach,
    case_events,
    case_scene,
    names_outside_context,
    reach_label,
)

GRID = site_grid((-76.23, 7.99, -76.1, 8.14))


def geometry() -> RiverGeometry:
    path = [(400, c) for c in range(100, 400)]
    mask = np.zeros(GRID.shape, dtype=bool)
    subs = (
        Subreach("upstream", (200.0, 2200.0), mask, mask),
        Subreach("downstream", (4000.0, 5980.0), mask, mask),
    )
    return RiverGeometry(20.0, 0.25, [], None, mask, mask, path, 5980.0, subreaches=subs)


def scene(usable: bool = True) -> Stage2Scene:
    sub = SubreachNdti(812, -0.1234, 0.03, 0.04, 0.012, 0.9, 0.05)
    return Stage2Scene(
        key="sentinel-2a_2024-01-16_R068",
        datetime=datetime(2024, 1, 16, 15, 40, tzinfo=UTC),
        platform="sentinel-2a",
        scaling=("offset-in-pixels",),
        exclusion=""
        if usable
        else "upstream median B11 water reflectance -0.050 outside [-0.03, 0.08]",
        sub={"upstream": sub, "downstream": sub},
    )


EVENT = CatalogEvent(
    "sinu-urra-01",
    "sinu-urra",
    date(2022, 11, 28),
    date(2022, 11, 30),
    "week",
    "Río Sinú",
    "flow_increase",
    "Higher discharges from the Urrá I reservoir were announced",
    "https://news.test/1",
    "news",
    "medium",
    "v",
    "",
)


def case(ui_name: str = "Río Sinú near Tierralta, Córdoba") -> CaseFile:
    reach, subreaches = build_reach(ui_name, GRID, geometry())
    z = {"D0": {"upstream": 0.1, "downstream": 3.4, "delta": float("nan")}}
    entry = case_scene(
        scene(),
        ["S2A_18NUP_20240116_0_L2A"],
        ["05.10"],
        z,
        {"D0": True},
        9,
        Rain(point=False, catchment=None, union="unknown"),
    )
    return CaseFile(
        ui=Ui(
            reach_label=ui_name,
            reach=reach,
            subreaches=subreaches,
            scenes=[entry],
            events=case_events([EVENT]),
            permit=Permit(note="illustrative"),
            validation=ValidationSummary(
                verdict="no robust signal",
                episodes=2,
                episodes_needed=4,
                share_ratio=None,
                share_ratio_needed=3.0,
            ),
            note="NDTI is relative",
        ),
        context=Context(
            sources=[
                ContextSource(title=EVENT.event_id, url=EVENT.source_url, text=EVENT.description)
            ]
        ),
        manifest=Manifest(
            commit="abc", config_sha256="d", method_blob="e", item_ids_sha256={"full": "f"}
        ),
    )


def test_the_case_file_uses_the_web_contract_and_camel_case() -> None:
    data = json.loads(case().to_json())
    reach = data["ui"]["reach"]
    assert reach["type"] == "Feature" and reach["geometry"]["type"] == "LineString"
    assert (
        set(reach["properties"]) == {"name", "lengthM"} and reach["properties"]["lengthM"] == 5980
    )
    lon, lat = reach["geometry"]["coordinates"][0]
    assert -77 < lon < -76 and 7.9 < lat < 8.2  # [lng, lat] order
    assert all(len(str(v).split(".")[-1]) <= 5 for p in reach["geometry"]["coordinates"] for v in p)
    # About one vertex per 100 m along 6 km, ends kept.
    assert 55 <= len(reach["geometry"]["coordinates"]) <= 62
    assert [s["name"] for s in data["ui"]["subreaches"]] == ["upstream", "downstream"]
    scene_json = data["ui"]["scenes"][0]
    assert scene_json["stacItemIds"] == ["S2A_18NUP_20240116_0_L2A"]
    assert scene_json["z"]["D0"]["delta"] is None and scene_json["variantFlags"] == {"D0": True}
    assert scene_json["rain"] == {"point": False, "catchment": None, "union": "unknown"}
    assert scene_json["validWaterPx"] == {"upstream": 812, "downstream": 812}
    assert data["ui"]["permit"] == {
        "simulated": True,
        "holder": "simulated permit holder",
        "label": "illustrative limit, not the real licence",
        "note": "illustrative",
    }
    assert data["context"]["label"] == "public-source context, not an accusation"
    assert "candidate_human_pressure" not in json.dumps(data)


def test_real_names_appear_only_in_the_context_block() -> None:
    assert names_outside_context(case()) == []
    assert "Urrá" in case().context.model_dump_json()
    assert names_outside_context(case("Río Sinú below Urrá I")) == ["urrá"]
    assert case_events([EVENT])[0].summary == "reported rise in river flow"


def test_the_label_names_the_river_and_the_place_only() -> None:
    assert reach_label("Río Sinú", "Río Sinú below Urrá I dam (Tierralta, Córdoba)") == (
        "Río Sinú near Tierralta, Córdoba"
    )
    assert reach_label("Río Meta", "Río Meta") == "Río Meta"


def test_the_permit_cannot_be_made_real() -> None:
    with pytest.raises(ValidationError):
        Permit(note="x", holder="URRÁ S.A. E.S.P.")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Permit(note="x", simulated=False)  # type: ignore[arg-type]


def test_an_excluded_scene_keeps_its_reason() -> None:
    entry = case_scene(
        scene(usable=False), [], [], {}, {}, 0, Rain(point=None, catchment=None, union="unknown")
    )
    assert entry.excluded and "B11" in entry.exclusion_reason
