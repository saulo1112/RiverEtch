import copy
import json
import math
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import pytest
from pydantic import ValidationError

from climate_pipeline.contract import observation as obs

ROOT = Path(__file__).parents[2]
SCHEMA_FILE = ROOT / "docs" / "schema" / "observation-record.v1.schema.json"
FIXTURE = Path(__file__).parent / "fixtures" / "observation-records.sample.json"
ITEM = "S2B_18NXP_20200106_0_L2A"


def schema() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    return data


def fixture() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


def validator() -> Any:
    return jsonschema.Draft202012Validator(schema())


def test_the_committed_schema_matches_the_models() -> None:
    # Compared as data, so formatting (Prettier) cannot cause a false drift.
    assert schema() == obs.json_schema()
    jsonschema.Draft202012Validator.check_schema(schema())


def test_the_fixture_validates_and_is_sealed() -> None:
    records = fixture()
    assert len(records) == 5
    v = validator()
    for data in records:
        assert list(v.iter_errors(data)) == []
        record = obs.ObservationRecord.model_validate(data)
        assert obs.is_sealed(record)
        assert record.calibration.status == "none" and record.calibration.value is None
        assert record.climate_context.label == "not_evaluated"
    anomaly = next(r for r in records if r["date"] == "2020-08-26")
    assert anomaly["verdict"] == {
        "rule": "D0", "threshold": 3.0, "anomalous": True, "signals": ["delta"]
    }  # fmt: skip


def record(**changes: Any) -> dict[str, Any]:
    data = copy.deepcopy(fixture()[0])
    for path, value in changes.items():
        target = data
        keys = path.split(".")
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value
    return data


def passed_calibration(**extra: Any) -> dict[str, Any]:
    base = {
        "status": "passed", "modelId": "tss-loglog-B8A/B04", "version": "1",
        "parametersHash": "0" * 64, "target": "tss", "unit": "mg/L", "value": 120.0,
        "uncertainty": {"low": 80.0, "high": 180.0, "kind": "loo_mdsa_band"},
        "validRange": [20.0, 900.0], "abstainReason": None,
    }  # fmt: skip
    return {**base, **extra}


@pytest.mark.parametrize(
    ("changes", "accepted"),
    [
        ({"calibration.value": 12.0}, False),
        ({"calibration.status": "failed"}, True),
        ({"calibration": passed_calibration()}, True),
        ({"calibration": passed_calibration(value=None)}, False),
        ({"calibration": passed_calibration(value=None, uncertainty=None,
                                            abstainReason="feature outside the training range")},
         True),
        ({"calibration": passed_calibration(abstainReason="glint share above 0.5")}, False),
        ({"calibration": passed_calibration(modelId=None)}, False),
        ({"climateContext.label": "explained_by_climate"}, False),
        ({"climateContext.label": "unexplained"}, False),
        ({"climateContext.expected": 0.05}, False),
        ({"climateContext.status": "weak"}, True),
    ],
)  # fmt: skip
def test_conditional_rules_hold_in_the_model_and_the_schema(
    changes: dict[str, Any], accepted: bool
) -> None:
    data = record(**changes)
    data["recordSha256"] = None
    schema_ok = not list(validator().iter_errors(data))
    try:
        obs.ObservationRecord.model_validate(data)
        model_ok = True
    except ValidationError:
        model_ok = False
    assert model_ok == accepted
    # The schema expresses the same rules, except the ones it cannot (named model fields).
    if accepted:
        assert schema_ok


def test_a_passed_climate_label_names_its_model_and_residual() -> None:
    good = {
        "status": "passed", "signal": "delta", "modelId": "5a-delta", "expected": 0.001,
        "residual": -0.047, "residualZ": -4.2, "label": "unexplained",
        "rule": "|residual z| >= 3 on a D0-anomalous scene", "dischargePercentile": 0.4,
        "ensoPhase": "neutral",
    }  # fmt: skip
    obs.ClimateContext.model_validate(good)
    with pytest.raises(ValidationError):
        obs.ClimateContext.model_validate({**good, "residualZ": None})
    with pytest.raises(ValidationError):
        obs.ClimateContext.model_validate({**good, "label": "not_evaluated"})
    with pytest.raises(ValidationError):
        obs.ClimateContext.model_validate({**good, "dischargePercentile": 1.5})


def test_the_verdict_follows_from_the_z_scores_only() -> None:
    data = record(**{"verdict.anomalous": True, "verdict.signals": ["upstream"]})
    with pytest.raises(ValidationError, match="verdict must follow"):
        obs.ObservationRecord.model_validate(data)
    # A climate or calibration field can never move the verdict.
    sealed = obs.ObservationRecord.model_validate(fixture()[0])
    other = sealed.model_copy(
        update={"calibration": obs.Calibration.model_validate(passed_calibration())}
    )
    assert other.verdict == sealed.verdict
    z = obs.ZScores(upstream=math.nan, downstream=None, delta=-3.0)
    assert obs.verdict_from_z(z, 3.0).signals == ["delta"]
    assert obs.verdict_from_z(z, 3.5).anomalous is False


def test_the_hash_covers_every_field_and_ignores_key_order() -> None:
    sealed = obs.ObservationRecord.model_validate(fixture()[1])
    assert obs.is_sealed(sealed)
    shuffled = dict(reversed(list(fixture()[1].items())))
    assert obs.record_hash(obs.ObservationRecord.model_validate(shuffled)) == sealed.record_sha256
    changed = sealed.model_copy(update={"date": "2020-08-27"})
    assert obs.record_hash(changed) != sealed.record_sha256 and not obs.is_sealed(changed)
    assert '"recordSha256"' not in obs.canonical_json(sealed)


def test_records_from_a_case_file() -> None:
    case = {
        "manifest": {"commit": "abc", "configSha256": "f" * 64},
        "ui": {
            "scenes": [
                {"date": "2020-01-01", "excluded": True, "stacItemIds": ["X"], "ndti": {},
                 "z": {"D0": {}}, "rain": {"point": None, "catchment": None, "union": "unknown"}},
                {"date": "2020-01-06", "excluded": False, "stacItemIds": [ITEM],
                 "ndti": {"upstream": 0.05, "downstream": None, "delta": None},
                 "z": {"D0": {"upstream": 3.2, "downstream": None, "delta": None}},
                 "rain": {"point": True, "catchment": None, "union": "yes"}},
            ]
        },
    }  # fmt: skip
    meta = obs.ItemMeta("u", "1" * 64, "2026-10-09T00:00:00+00:00", True, "02.14")
    records = obs.records_from_case(case, "reach", "sentinel-2-l2a", {ITEM: meta}, 3.0)
    assert len(records) == 1
    r = records[0]
    assert r.index.reach == 0.05 and r.verdict.signals == ["upstream"]
    assert r.provenance.processing_baseline == ["02.14"] and obs.is_sealed(r)


def test_item_json_urls_follow_the_bucket_layout() -> None:
    assert obs.item_json_url("S2A_18NXP_20181205_0_L2A") == (
        "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/"
        "18/N/XP/2018/12/S2A_18NXP_20181205_0_L2A/S2A_18NXP_20181205_0_L2A.json"
    )
    assert "/2022/3/" in obs.item_json_url("S2A_18NXP_20220309_0_L2A")
    meta = obs.item_meta_from_json(
        "u", json.dumps({"properties": {"s2:processing_baseline": "05.00"}}).encode(), "t"
    )
    assert meta.boa_offset_applied is None and meta.processing_baseline == "05.00"
