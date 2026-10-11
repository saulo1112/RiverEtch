import copy
import json
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import pytest
from pydantic import ValidationError

from climate_pipeline.contract import observation_v2 as v2

ROOT = Path(__file__).parents[2]
SCHEMA_FILE = ROOT / "docs" / "schema" / "observation-record.v2.schema.json"
ITEM = "S2B_18NXP_20200106_0_L2A"


def schema() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    return data


def estimate(level: str = "estimated", **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "target": "turbidity", "unit": "NTU", "level": level, "value": 180.0,
        "interval": {"low": 90.0, "high": 360.0, "coverage": 0.9,
                     "method": "mondrian_split_conformal_log"},
        "modelId": "A3:turbidity:core", "modelVersion": "1", "modelCardSha256": "ab" * 32,
        "validRange": [20.0, 1500.0], "rangeMdsa": 48.0,
        "atmosphericCorrection": {"processor": "sen2cor", "collection": "sentinel-2-l2a",
                                  "processingBaseline": ["05.10"]},
    }  # fmt: skip
    return {**base, **over}


def record(estimates: list[dict[str, Any]] | None = None, **over: Any) -> dict[str, Any]:
    z = {"rule": "D0", "upstream": 0.4, "downstream": 3.2, "delta": 2.9}
    base: dict[str, Any] = {
        "schemaVersion": 2, "reachId": "magdalena-puerto-wilches", "date": "2020-01-06",
        "sceneId": "magdalena-puerto-wilches:2020-01-06", "stacItemIds": [ITEM],
        "indices": {
            "ndti": {"upstream": 0.1, "downstream": 0.2, "reach": 0.15, "delta": 0.1, "zScore": z},
            "nirRed": {"upstream": 0.6, "downstream": 0.7, "reach": 0.65, "delta": 0.1,
                       "zScore": {"rule": "D0", "upstream": 0.1, "downstream": 0.2,
                                  "delta": 0.1}},
        },
        "verdict": {"rule": "D0", "threshold": 3.0, "anomalous": True, "signals": ["downstream"]},
        "rain": {"point": False, "catchment": None, "union": "unknown"},
        "estimates": estimates if estimates is not None else [estimate()],
        "climateContext": {"status": "not_run", "label": "not_evaluated",
                           "rule": "climate context not run"},
        "provenance": {"collection": "sentinel-2-l2a",
                       "stacItems": [{"id": ITEM, "url": "https://x/item.json"}],
                       "codeCommit": "abc", "processingParamsSha256": "def",
                       "boaOffsetApplied": [None], "processingBaseline": ["02.14"]},
    }  # fmt: skip
    return {**base, **over}


def test_the_committed_schema_matches_the_models() -> None:
    assert schema() == v2.json_schema()
    jsonschema.Draft202012Validator.check_schema(schema())


def test_a_valid_record_validates_against_both_and_seals() -> None:
    model = v2.seal(v2.ObservationRecordV2.model_validate(record()))
    assert v2.is_sealed(model) and model.record_sha256 == v2.record_hash(model)
    jsonschema.Draft202012Validator(schema()).validate(model.model_dump(mode="json", by_alias=True))
    tampered = model.model_copy(update={"date": "2020-01-07"})
    assert not v2.is_sealed(tampered)


@pytest.mark.parametrize(
    ("estimates", "message"),
    [
        ([estimate("indicative")], "only a validated or estimated level"),
        ([estimate("none", value=None, interval=None, relativeClass="high")], "relative class"),
        ([estimate(interval=None)], "carries value, interval, range"),
        ([estimate(value=1000.0)], "inside its interval"),
        ([estimate(modelCardSha256=None)], "names its model"),
        ([estimate(), estimate()], "one estimate per target"),
        ([estimate(abstainReason="glint share above 0.5")], "not abstaining"),
    ],
)
def test_the_rules_refuse_dishonest_estimates(estimates: list[dict[str, Any]],
                                              message: str) -> None:  # fmt: skip
    with pytest.raises(ValidationError, match=message):
        v2.ObservationRecordV2.model_validate(record(estimates))


def test_the_schema_refuses_a_value_below_the_estimated_level() -> None:
    data = record([estimate("indicative", relativeClass="high")])
    data["estimates"][0]["value"] = 12.0
    errors = list(jsonschema.Draft202012Validator(schema()).iter_errors(data))
    assert errors


def test_indicative_and_none_levels_carry_no_value() -> None:
    lean = [
        estimate("indicative", value=None, interval=None, relativeClass="medium"),
        {"target": "tss", "unit": "mg/L", "level": "none"},
    ]
    model = v2.ObservationRecordV2.model_validate(record(lean))
    assert [e.level for e in model.estimates] == ["indicative", "none"]
    jsonschema.Draft202012Validator(schema()).validate(model.model_dump(mode="json", by_alias=True))


def test_the_verdict_follows_from_the_ndti_z_scores_alone() -> None:
    data = copy.deepcopy(record())
    data["verdict"] = {"rule": "D0", "threshold": 3.0, "anomalous": False, "signals": []}
    with pytest.raises(ValidationError, match="NDTI D0 z-scores"):
        v2.ObservationRecordV2.model_validate(data)
