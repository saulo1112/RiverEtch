"""The turbidity value beside its class (preregistration-values.md): the file frozen before anything
runs, an ungauged class carrying the value it was made from (never an interval, never while
abstaining), the schema allowing exactly that, and the along-river index showing each pass's
latest record with its values."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import pytest

from climate_pipeline.contract import observation_v2 as v2
from climate_pipeline.quality.config import load_quality_config
from climate_pipeline.reach import along, records
from climate_pipeline.reach.config import load_reach_config

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "pipeline"
QUALITY = load_quality_config(PIPELINE / "water-quality.yaml")
WINDOW = QUALITY.window.as_calibration()
TURBIDITY = QUALITY.target("turbidity")
REACH = load_reach_config(PIPELINE / "reach.yaml")
SCHEMA = json.loads((ROOT / "docs/schema/observation-record.v2.schema.json").read_text("utf-8"))
STATS = {"valid_px": 50.0, "contamination": 0.0, "b11_ok": 1.0, "glint_share": 0.0,
         "bands_read": 1.0}  # fmt: skip
ITEM = records.Item("S2A_18NXP_20260110_0_L2A", "https://x/item.json", "05.11", True)


def test_the_preregistration_is_frozen_before_anything_runs() -> None:
    frozen = [json.loads(t) for t in (ROOT / "docs/ledgers/frozen-artifacts.jsonl")
              .read_text(encoding="utf-8").splitlines() if t.strip()]  # fmt: skip
    listed = {x["path"]: x["sha256"] for x in frozen}
    path = ROOT / records.VALUES_PREREGISTRATION
    assert listed[records.VALUES_PREREGISTRATION] == hashlib.sha256(path.read_bytes()).hexdigest()


def _card(basis: str = v2.UNGAUGED) -> dict[str, Any]:
    # 300 r^2 FNU for a ratio r (test_reach_records' card), shown as a class.
    return {
        "modelId": "A1:turbidity:core", "version": "1", "target": "turbidity", "unit": "FNU",
        "parameters": {"kind": "loglog", "features": ["B8A/B04"],
                       "coefficients": [math.log(300.0), 2.0]},
        "adjustment": None, "featureRange": {"B8A/B04": [0.1, 2.0]},
        "targetRange": [5.0, 2000.0], "basis": basis, "levels": [], "display": "class",
    }  # fmt: skip


def _measure(ratio: float) -> records.Measure:
    return records.Measure(
        key="k", day=date(2026, 1, 10), items=(ITEM,), exclusion="",
        ndti={"upstream": 0.1, "downstream": 0.1}, nir_red={"upstream": 0.5, "downstream": 0.5},
        window={"B8A/B04": ratio}, stats=STATS,
    )  # fmt: skip


def _estimate(card: dict[str, Any], ratio: float, with_value: bool) -> v2.Estimate:
    return records.estimate(card, "ab" * 32, TURBIDITY, _measure(ratio), [], WINDOW, Path(),
                            with_value)  # fmt: skip


def test_an_ungauged_class_carries_its_value_only_when_asked() -> None:
    before = _estimate(_card(), 0.5, with_value=False)
    assert before.fnu_class is not None and before.value is None
    after = _estimate(_card(), 0.5, with_value=True)
    assert after.fnu_class == before.fnu_class and after.value == pytest.approx(75.0)
    assert after.interval is None and after.level == "unvalidated"
    outside = _estimate(_card(v2.OUTSIDE), 0.2, with_value=True)
    assert outside.basis == v2.OUTSIDE and outside.value == pytest.approx(12.0)
    # An abstaining estimate has neither class nor value.
    far = _estimate(_card(), 5.0, with_value=True)
    assert far.fnu_class is None and far.value is None and far.abstain_reason is not None


def test_the_contract_and_the_schema_allow_a_value_only_beside_a_class() -> None:
    e = _estimate(_card(), 0.5, with_value=True).model_dump(mode="json", by_alias=True)
    validator = jsonschema.Draft202012Validator(SCHEMA["$defs"]["Estimate"]
                                                | {"$defs": SCHEMA["$defs"]})  # fmt: skip
    validator.validate(e)
    no_class = {k: v for k, v in e.items() if k != "fnuClass"}
    assert list(validator.iter_errors(no_class)), "a value without a class"
    with pytest.raises(ValueError, match="a class, has a value"):
        v2.Estimate.model_validate(no_class)
    with_interval = {**e, "interval": {"low": 50.0, "high": 110.0, "coverage": 0.9,
                                       "method": "mondrian_split_conformal_log"}}  # fmt: skip
    with pytest.raises(ValueError, match="has an interval"):
        v2.Estimate.model_validate(with_interval)
    assert list(validator.iter_errors(with_interval))


def test_the_along_index_shows_each_passs_latest_record_with_its_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "along"
    (out / "records").mkdir(parents=True)
    monkeypatch.setattr(along, "folder", lambda cfg, root, site: out)
    docs: list[dict[str, Any]] = [
        {"schema": along.SCHEMA, "sceneId": "x:a", "date": "2026-01-01",
         "windows": [{"id": "w01", "fnuClass": "under_30"}, {"id": "w02", "abstainReason": "r"}]},
        {"schema": along.SCHEMA, "sceneId": "x:b", "date": "2026-01-05",
         "windows": [{"id": "w01", "fnuClass": "30_to_50"}, {"id": "w02", "fnuClass": "under_30"}]},
        {"schema": along.SCHEMA_V2, "sceneId": "x:a", "date": "2026-01-01", "replaces": "s0",
         "windows": [{"id": "w01", "fnuClass": "under_30", "fnuValue": 12.34},
                     {"id": "w02", "abstainReason": "r"}]},
    ]  # fmt: skip
    for k, doc in enumerate(docs):
        doc["recordSha256"] = f"s{k}"
        file = f"records/{k}.json"
        (out / file).write_text(json.dumps(doc), encoding="utf-8")
        line = {"sceneId": doc["sceneId"], "date": doc["date"],
                "recordSha256": doc["recordSha256"], "file": file}  # fmt: skip
        with (out / "ledger.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line) + "\n")
    rows = along.series(REACH, tmp_path, "x")
    assert [(r["sceneId"], r["recordSha256"]) for r in rows] == [("x:a", "s2"), ("x:b", "s1")]
    assert rows[0]["values"] == [12.34, None] and rows[0]["classes"] == ["under_30", None]
    assert rows[1]["values"] == [None, None], "a v1 record has no values"
