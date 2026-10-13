import json
from pathlib import Path

import pytest

from climate_pipeline.contract import thermal as contract
from climate_pipeline.reach import thermal

CARD = {
    "modelId": "W1:water_temperature:core:platte-louisville", "version": "1",
    "basis": "preregistered_lockbox_site", "parameters": {"a": 0.0, "b": 1.0},
    "halfWidth90": 2.5, "minWaterPixels": 10,
    "levels": [{"predicted_range": "all", "level": "estimated"}],
}  # fmt: skip


def test_an_estimated_card_gives_a_value_with_its_interval() -> None:
    e = thermal.estimate(CARD, 300.15)
    assert e.value == pytest.approx(27.0)
    assert e.interval is not None and (e.interval.low, e.interval.high) == (24.5, 29.5)
    assert e.unit == "°C" and e.level == "estimated"


def test_an_indicative_card_gives_no_value() -> None:
    card = {**CARD, "levels": [{"predicted_range": "all", "level": "indicative"}]}
    e = thermal.estimate(card, 300.15)
    assert e.value is None and e.interval is None


def record() -> contract.ThermalRecordV1:
    return contract.seal(contract.ThermalRecordV1.model_validate({
        "reachId": "platte-louisville", "date": "2026-08-02",
        "datetimeUtc": "2026-08-02T17:05:47+00:00",
        "sceneId": "platte-louisville:landsat-9_2026-08-02_R028", "platform": "landsat-9",
        "window": {"pixels": 109, "waterPixels": 83, "surfaceTemperatureK": 300.722},
        "estimate": thermal.estimate(CARD, 300.722),
        "provenance": {"stacItems": [{"id": "LC09", "url": "https://x"}], "codeCommit": "abc",
                       "processingParamsSha256": "def"},
    }))  # fmt: skip


def test_a_temperature_record_is_sealed_and_an_edit_breaks_the_seal() -> None:
    rec = record()
    assert contract.is_sealed(rec)
    data = json.loads(rec.model_dump_json(by_alias=True))
    data["estimate"]["value"] = 30.0
    assert not contract.is_sealed(contract.ThermalRecordV1.model_validate(data))


def test_the_series_lists_the_records_by_date(tmp_path: Path) -> None:
    rec = record()
    (tmp_path / "records").mkdir()
    (tmp_path / "records" / "2026-08-02_landsat-9_2026-08-02_R028.json").write_text(
        rec.model_dump_json(by_alias=True), encoding="utf-8"
    )
    thermal.write_series(tmp_path)
    series = json.loads((tmp_path / "series.json").read_text(encoding="utf-8"))
    assert series[0]["estimate"]["value"] == pytest.approx(27.57)
    assert series[0]["recordSha256"] == rec.record_sha256
