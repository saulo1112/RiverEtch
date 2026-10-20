import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import pytest

from climate_pipeline.contract import observation_v2 as v2
from climate_pipeline.contract.observation import RainFlags
from climate_pipeline.quality import cards
from climate_pipeline.quality.config import load_quality_config
from climate_pipeline.reach import records
from climate_pipeline.screening.config import load_screening_config

PIPELINE = Path(__file__).parents[1]
CFG = load_quality_config(PIPELINE / "water-quality.yaml")
SCREENING = load_screening_config(PIPELINE / "screening.yaml")
WINDOW = CFG.window.as_calibration()
TURBIDITY = CFG.target("turbidity")
SCHEMA = json.loads(
    (PIPELINE.parent / "docs" / "schema" / "observation-record.v2.schema.json").read_text("utf-8")
)
STATS = {"valid_px": 50.0, "contamination": 0.0, "b11_ok": 1.0, "glint_share": 0.0,
         "bands_read": 1.0}  # fmt: skip
ITEM = records.Item("S2A_18NXP_20260110_0_L2A", "https://x/item.json", "05.11", True)


def card(overall: str = "estimated") -> dict[str, Any]:
    return {
        "modelId": "A1:turbidity:core", "version": "1", "target": "turbidity",
        "parameters": {"kind": "loglog", "features": ["B8A/B04"],
                       "coefficients": [math.log(300.0), 2.0]},
        "adjustment": None, "featureRange": {"B8A/B04": [0.1, 2.0]},
        "targetRange": [5.0, 2000.0],
        "intervals": {"edges": [100.0, 300.0], "q": {"0.8": [0.3] * 3, "0.9": [0.5] * 3},
                      "pooled": []},
        "levels": [{"predicted_range": "all", "level": overall, "mdsa": 40.0},
                   {"predicted_range": "<30", "level": "indicative", "mdsa": 90.0}],
    }  # fmt: skip


def measure(ratio: float = 1.0, **over: Any) -> records.Measure:
    base: dict[str, Any] = {
        "key": "k", "day": date(2026, 1, 10), "items": (ITEM,), "exclusion": "",
        "ndti": {"upstream": 0.1, "downstream": 0.1}, "nir_red": {"upstream": 0.5,
                                                                  "downstream": 0.5},
        "window": {"B8A/B04": ratio}, "stats": STATS,
    }  # fmt: skip
    return records.Measure(**{**base, **over})


def estimate(c: dict[str, Any] | None, m: records.Measure, history: list[float] | None = None
             ) -> v2.Estimate:  # fmt: skip
    return records.estimate(c, "ab" * 32, TURBIDITY, m, history or [], WINDOW, Path())


def test_an_estimated_level_carries_value_and_interval() -> None:
    e = estimate(card(), measure())
    assert e.level == "estimated" and e.value == pytest.approx(300.0)
    assert e.interval is not None and e.interval.coverage == 0.9
    assert e.interval.low == pytest.approx(300 * math.exp(-0.5), abs=0.01)
    assert e.valid_range == (5.0, 2000.0) and e.range_mdsa == 40.0 and e.abstain_reason is None


def test_the_window_guards_and_training_range_make_an_estimate_abstain() -> None:
    glinted = estimate(card(), measure(stats={**STATS, "glint_share": 0.9}))
    assert glinted.value is None and glinted.abstain_reason == "glint share above 0.5"
    assert glinted.level == "estimated" and glinted.model_card_sha256 == "ab" * 32
    far = estimate(card(), measure(ratio=5.0))
    assert far.value is None and "outside the training range" in str(far.abstain_reason)
    excluded = estimate(card(), measure(exclusion="too few usable water pixels"))
    assert excluded.abstain_reason == "too few usable water pixels"


def test_an_indicative_range_gives_a_relative_class_from_the_station_history() -> None:
    low = measure(ratio=0.2)  # 12 NTU: the <30 range, rated indicative
    history = [float(v) for v in range(5, 65, 5)]  # 12 values, terciles at ~23 and ~43
    e = estimate(card(), low, history)
    assert e.level == "indicative" and e.relative_class == "low" and e.value is None
    short = estimate(card(), low, history[:5])
    assert short.relative_class is None and "too short" in str(short.abstain_reason)


def test_without_a_model_or_with_level_none_the_estimate_is_bare() -> None:
    assert estimate(None, measure()) == v2.Estimate(target="turbidity", unit="NTU", level="none")
    assert estimate(card("none"), measure()).level == "none"


def ungauged_card(display: str = "class") -> dict[str, Any]:
    return {**card(), "unit": "FNU", "basis": v2.UNGAUGED, "levels": [], "display": display}


def test_an_ungauged_reach_shows_a_class_in_fnu_never_a_value() -> None:
    # The card gives 300 r^2 for a ratio r: 12, 75 and 300 FNU.
    found = [estimate(ungauged_card(), measure(ratio=r)) for r in (0.2, 0.5, 1.0)]
    assert [e.fnu_class for e in found] == ["under_30", "30_to_100", "100_and_over"]
    e = found[0]
    assert e.level == "unvalidated" and e.basis == v2.UNGAUGED and e.unit == "FNU"
    assert e.value is None and e.interval is None and e.relative_class is None
    assert e.model_card_sha256 == "ab" * 32 and e.range_mdsa is None
    far = estimate(ungauged_card(), measure(ratio=5.0))
    assert far.fnu_class is None and "outside the training range" in str(far.abstain_reason)
    # The pooled transfer result did not reach indicative: relative indices only.
    assert estimate(ungauged_card("none"), measure()).level == "none"


def test_the_fnu_class_is_left_out_of_the_json_when_empty() -> None:
    bare = v2.Estimate(target="turbidity", unit="FNU", level="none")
    assert "fnuClass" not in bare.model_dump(by_alias=True)
    assert "fnuClass" not in json.loads(bare.model_dump_json(by_alias=True))
    e = estimate(ungauged_card(), measure())
    dump = e.model_dump(mode="json", by_alias=True)
    assert dump["fnuClass"] == "100_and_over"
    with pytest.raises(ValueError, match="unvalidated level only"):
        v2.Estimate.model_validate({**dump, "level": "indicative"})
    with pytest.raises(ValueError, match="ungauged reach's, and only its"):
        v2.Estimate.model_validate({**dump, "basis": "preregistered_test"})
    with pytest.raises(ValueError, match="ungauged reach's, and only its"):
        v2.Estimate.model_validate({**estimate(card(), measure()).model_dump(by_alias=True),
                                    "basis": v2.UNGAUGED})  # fmt: skip
    jsonschema.Draft202012Validator(SCHEMA["$defs"]["Estimate"] | {"$defs": SCHEMA["$defs"]}
                                    ).validate(dump)  # fmt: skip


def test_a_record_compares_the_scene_with_the_frozen_baseline_only() -> None:
    days = tuple(date(2024, 1, 1) + timedelta(days=15 * k) for k in range(24))
    flat = [0.10 + 0.002 * (k % 3) for k in range(24)]
    baseline = records.Baseline(
        days, {"upstream": flat, "downstream": flat, "delta": [0.0] * 24},
        {"upstream": [0.5] * 24, "downstream": [0.5] * 24, "delta": [0.0] * 24},
    )  # fmt: skip
    turbid = measure(ndti={"upstream": 0.1, "downstream": 0.3})
    rain = RainFlags(point=False, catchment=None, union="unknown")
    rec = records.record("magdalena-puerto-wilches", turbid, baseline,
                         [estimate(card(), turbid), v2.Estimate(target="tss", unit="mg/L",
                                                                level="none")],
                         rain, {4, 5, 6, 8, 10, 11}, SCREENING, 3.0, "abc", "def")  # fmt: skip
    assert rec.verdict.anomalous and rec.verdict.signals == ["downstream", "delta"]
    assert rec.indices.ndti.reach == pytest.approx(0.2) and rec.indices.nir_red is not None
    assert v2.is_sealed(rec) and rec.scene_id == "magdalena-puerto-wilches:k"
    jsonschema.Draft202012Validator(SCHEMA).validate(rec.model_dump(mode="json", by_alias=True))


def test_two_passes_on_one_day_are_two_scenes() -> None:
    days = tuple(date(2024, 1, 1) + timedelta(days=15 * k) for k in range(24))
    flat = [0.10 + 0.002 * (k % 3) for k in range(24)]
    baseline = records.Baseline(
        days, {"upstream": flat, "downstream": flat, "delta": [0.0] * 24},
        {"upstream": [0.5] * 24, "downstream": [0.5] * 24, "delta": [0.0] * 24},
    )  # fmt: skip
    rain = RainFlags(point=False, catchment=None, union="unknown")
    ids = {
        records.record("mississippi-belle-chasse", measure(key=key), baseline, [], rain, set(),
                       SCREENING, 3.0, "abc", "def").scene_id
        for key in ("sentinel-2a_2026-09-23_R126", "sentinel-2b_2026-09-23_R083")
    }  # fmt: skip
    assert ids == {"mississippi-belle-chasse:sentinel-2a_2026-09-23_R126",
                   "mississippi-belle-chasse:sentinel-2b_2026-09-23_R083"}  # fmt: skip


def test_the_card_hash_names_the_whole_card() -> None:
    assert cards.card_hash(card()) != cards.card_hash(card("indicative"))


def test_a_series_row_keeps_an_ungauged_class_and_nothing_new_otherwise() -> None:
    from climate_pipeline.reach import run as reach_run

    days = tuple(date(2024, 1, 1) + timedelta(days=15 * k) for k in range(24))
    flat = [0.10 + 0.002 * (k % 3) for k in range(24)]
    baseline = records.Baseline(
        days, {"upstream": flat, "downstream": flat, "delta": [0.0] * 24},
        {"upstream": [0.5] * 24, "downstream": [0.5] * 24, "delta": [0.0] * 24},
    )  # fmt: skip
    rain = RainFlags(point=False, catchment=None, union="unknown")
    m = measure()
    for c, has in ((ungauged_card(), True), (card(), False)):
        rec = records.record("mississippi-st-joseph", m, baseline, [estimate(c, m)], rain, set(),
                             SCREENING, 3.0, "abc", "def")  # fmt: skip
        row = reach_run.summary_row(rec, "records/x.json")["estimates"][0]
        assert ("fnuClass" in row) is has
        if has:
            assert row["fnuClass"] == "100_and_over" and row["value"] is None
