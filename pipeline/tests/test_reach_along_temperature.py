"""Water temperature along the river (preregistration-along-temperature.md): the file frozen before
any window is read, the guard that nothing reads before its anchor, the six classes, a pass's
classes on every window, and the seal and check of an along-river temperature record."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from climate_pipeline.quality import cards, variables
from climate_pipeline.reach import along, along_temperature
from climate_pipeline.reach.config import load_reach_config

ROOT = Path(__file__).resolve().parents[2]
CFG = load_reach_config(ROOT / "pipeline" / "reach.yaml")


def test_the_preregistration_is_frozen_before_any_window_is_read() -> None:
    frozen = [json.loads(t) for t in (ROOT / "docs/ledgers/frozen-artifacts.jsonl")
              .read_text(encoding="utf-8").splitlines() if t.strip()]  # fmt: skip
    listed = {x["path"]: x["sha256"] for x in frozen}
    path = ROOT / along_temperature.PREREGISTRATION
    assert (
        listed[along_temperature.PREREGISTRATION] == hashlib.sha256(path.read_bytes()).hexdigest()
    )


def test_nothing_reads_before_its_line_is_anchored(tmp_path: Path) -> None:
    (tmp_path / "docs/ledgers").mkdir(parents=True)
    lines = [{"path": along.PREREGISTRATION}, {"path": along_temperature.PREREGISTRATION}]
    (tmp_path / "docs/ledgers/frozen-artifacts.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")  # fmt: skip
    log = tmp_path / "docs/ledgers/anchors.jsonl"
    log.write_text(json.dumps({"label": along.FROZEN_LABEL, "lines": 1}) + "\n", encoding="utf-8")
    assert along.anchored(tmp_path)  # the turbidity's line is covered...
    assert not along.anchored(tmp_path, along_temperature.PREREGISTRATION)  # ...not this one
    log.write_text(json.dumps({"label": along.FROZEN_LABEL, "lines": 2}) + "\n", encoding="utf-8")
    assert along.anchored(tmp_path, along_temperature.PREREGISTRATION)


def test_a_value_on_an_edge_is_in_the_upper_class() -> None:
    cls = along_temperature.temperature_class
    assert [cls(v) for v in (-1.0, 9.99, 10.0, 14.9, 15.0, 25.0, 29.99, 30.0, 35.0)] == [
        "under_10", "under_10", "10_to_15", "10_to_15", "15_to_20", "25_to_30", "25_to_30",
        "30_and_over", "30_and_over",
    ]  # fmt: skip
    assert cls(math.nan) is None


class _Reader:
    """Serves one pass's QA_PIXEL and surface temperature on the test grid."""

    def __init__(self, qa: np.ndarray, dn: np.ndarray) -> None:
        self.bands = {"qa_pixel": qa, "lwir11": dn}
        self.reads: list[str] = []

    def read(self, acq: Any, asset: str, grid: Any) -> tuple[np.ndarray, dict[str, int]]:
        del acq, grid
        self.reads.append(asset)
        return self.bands[asset], {}


def _dn(celsius: float) -> int:
    return round((celsius + 273.15 - variables.ST_OFFSET) / variables.ST_SCALE)


def test_each_window_gets_its_class_or_a_reason() -> None:
    water = variables.QA_WATER  # clear water: no fill, no cloud bits
    qa = np.full((4, 4), water, dtype=np.int64)
    qa[2:, :2] = 1 << 3  # cloud over the third window
    dn = np.full((4, 4), _dn(21.0), dtype=np.int64)
    dn[:2, 2:] = _dn(45.0)  # the fourth window: hotter than the card's input range
    cores = {
        "w01": np.zeros((4, 4), bool), "w03": np.zeros((4, 4), bool),
        "w04": np.zeros((4, 4), bool),
    }  # fmt: skip
    cores["w01"][:2, :2] = True
    cores["w03"][2:, :2] = True
    cores["w04"][:2, 2:] = True
    windows = [
        along.Window("w01", 300.0, 0, 0, 400.0, 10.0, True, ""),
        along.Window("w02", 900.0, 0, 0, math.nan, math.nan, False, "too narrow"),
        along.Window("w03", 1500.0, 0, 0, 400.0, 10.0, True, ""),
        along.Window("w04", 2100.0, 0, 0, 400.0, 10.0, True, ""),
    ]
    card = {
        "parameters": {"a": 0.0, "b": 1.0}, "minWaterPixels": 2, "halfWidth90": 2.0,
        "inputRange": {"min": 0.0, "max": 40.0}, "modelId": "W", "version": "1",
        "basis": "preregistered_lockbox_site",
        "levels": [{"level": "estimated", "predicted_range": "all"}],
    }  # fmt: skip
    reader = _Reader(qa, dn)
    out = along_temperature.classes(None, reader, None, cores, windows, card)  # type: ignore[arg-type]
    assert out == [
        {"id": "w01", "temperatureClass": "20_to_25"},
        {"id": "w02", "abstainReason": along.NOT_PLACED},
        {"id": "w03", "abstainReason": along_temperature.TOO_FEW},
        {"id": "w04", "abstainReason": along_temperature.OUTSIDE},
    ]
    assert reader.reads == ["qa_pixel", "lwir11"]  # one read of each band for every window


def test_a_record_is_sealed_and_its_check_catches_an_edit(tmp_path: Path) -> None:
    site = "platte-louisville"
    plan = along.plan_path(tmp_path, site)
    plan.parent.mkdir(parents=True)
    shutil.copyfile(along.plan_path(ROOT, site), plan)
    card_rel = f"docs/water-quality/results/models/{site}/water_temperature.json"
    (tmp_path / card_rel).parent.mkdir(parents=True)
    shutil.copyfile(ROOT / card_rel, tmp_path / card_rel)
    card = json.loads((ROOT / card_rel).read_text(encoding="utf-8"))
    doc: dict[str, Any] = {
        "schema": along_temperature.SCHEMA, "reach": site, "sceneId": f"{site}:k",
        "date": "2026-10-11", "thermalRecordSha256": "0" * 64,
        "planSha256": hashlib.sha256(plan.read_bytes()).hexdigest(), "card": card_rel,
        "modelCardSha256": cards.card_hash(card), "modelId": card["modelId"], "items": [],
        "windows": [{"id": "w01", "temperatureClass": "15_to_20"},
                    {"id": "w02", "abstainReason": along_temperature.TOO_FEW}],
        "codeCommit": "c",
    }  # fmt: skip
    doc["recordSha256"] = along.seal(doc)
    out = along_temperature.folder(CFG, tmp_path, site)
    (out / "records").mkdir(parents=True)
    file = "records/2026-10-11_k.json"
    (out / file).write_text(json.dumps(doc), encoding="utf-8")
    along._append(out / "ledger.jsonl", doc, file, "2026-10-22T00:00:00+00:00")
    assert along_temperature.verify(CFG, tmp_path, site) == []
    row = along_temperature.series(CFG, tmp_path, site)[0]
    assert row["classes"] == ["15_to_20", None] and row["file"] == file
    doc["windows"][0]["temperatureClass"] = "30_and_over"  # change one class
    (out / file).write_text(json.dumps(doc), encoding="utf-8")
    assert any(
        "no longer matches its seal" in p for p in along_temperature.verify(CFG, tmp_path, site)
    )
