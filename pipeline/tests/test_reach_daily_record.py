"""The daily flow record (preregistration-daily-record.md).

The file frozen before anything runs, the guard that nothing runs before its anchor, a year sealed
once and again only when its source changes it, the snapshot rebuilt from the seals when the
source is down, and the river's usual flow for each calendar day."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from climate_pipeline.contract import daily_record as contract
from climate_pipeline.reach import along, climate, daily_record
from climate_pipeline.reach import run as reach_run
from climate_pipeline.reach.config import load_reach_config

ROOT = Path(__file__).resolve().parents[2]
CFG = load_reach_config(ROOT / "pipeline" / "reach.yaml")
SITE = "platte-louisville"


def test_the_preregistration_is_frozen_before_anything_runs() -> None:
    frozen = [json.loads(t) for t in (ROOT / "docs/ledgers/frozen-artifacts.jsonl")
              .read_text(encoding="utf-8").splitlines() if t.strip()]  # fmt: skip
    listed = {x["path"]: x["sha256"] for x in frozen}
    path = ROOT / daily_record.PREREGISTRATION
    assert listed[daily_record.PREREGISTRATION] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_nothing_runs_before_its_line_is_anchored(tmp_path: Path) -> None:
    (tmp_path / "docs/ledgers").mkdir(parents=True)
    (tmp_path / "docs/ledgers/frozen-artifacts.jsonl").write_text(
        json.dumps({"path": daily_record.PREREGISTRATION}) + "\n", encoding="utf-8")  # fmt: skip
    (tmp_path / "docs/ledgers/anchors.jsonl").write_text("", encoding="utf-8")
    assert not along.anchored(tmp_path, daily_record.PREREGISTRATION)
    with pytest.raises(reach_run.ReachError, match="not anchored yet"):
        daily_record.run(CFG, tmp_path, SITE)


def _rows(values: dict[str, float], status: str = "Approved") -> list[dict[str, Any]]:
    return [{"day": d, "parameter": climate.DISCHARGE, "value": v, "approval": status}
            for d, v in values.items()]  # fmt: skip


def _fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, rows: list[dict[str, Any]] | None
          ) -> None:  # fmt: skip
    monkeypatch.setattr(along, "anchored", lambda root, prereg: True)
    monkeypatch.setattr(daily_record, "head", lambda: "abc123")
    monkeypatch.setattr(daily_record, "_source", lambda cfg, root, site: {
        "kind": "usgs", "stationId": "USGS-1", "name": "A station", "measured": True,
        "url": "https://example.org/station"})  # fmt: skip
    monkeypatch.setattr(climate, "snapshot_path", lambda root, site: tmp_path / "daily.csv")

    def fetch(*args: Any) -> tuple[list[dict[str, Any]], str, dict[str, str]]:
        if rows is None:
            raise reach_run.ReachError("down")
        return rows, "https://example.org/api", {"monitoring_location_id": "USGS-1"}

    monkeypatch.setattr(daily_record, "_fetch", fetch)


def test_a_year_is_sealed_once_and_again_only_when_its_source_changes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = {"2024-12-30": 100.0, "2024-12-31": 110.0, "2025-01-01": 120.0}
    _fake(monkeypatch, tmp_path, _rows(first))
    at = datetime(2026, 10, 23, 1, 0, tzinfo=UTC)
    done = daily_record.run(CFG, tmp_path, SITE, now=at)
    assert done["sealed"] == [2024, 2025]
    out = daily_record.folder(tmp_path, SITE)
    records = sorted((out / "records").glob("*.json"))
    assert [p.name for p in records] == ["2024_20261023T010000Z.json", "2025_20261023T010000Z.json"]
    sealed = contract.DailyRecordV1.model_validate(json.loads(records[0].read_text("utf-8")))
    assert contract.is_sealed(sealed) and sealed.replaces is None
    assert sealed.series[0].days == [("2024-12-30", 100.0, "Approved"),
                                     ("2024-12-31", 110.0, "Approved")]  # fmt: skip
    assert sealed.source.measured and sealed.date == "2024-12-31"
    # The fresh snapshot, for climate.json.
    assert len(climate.read_snapshot(tmp_path / "daily.csv")[climate.DISCHARGE]) == 3

    # The same values again: nothing new.
    again = daily_record.run(CFG, tmp_path, SITE, now=at + timedelta(hours=12))
    assert again["sealed"] == [] and again["unchanged"] == 2

    # The source revises one day of 2025 (a new value, now approved): that year only.
    revised = _rows({"2024-12-30": 100.0, "2024-12-31": 110.0}) + _rows(
        {"2025-01-01": 121.5}, "Approved")  # fmt: skip
    _fake(monkeypatch, tmp_path, revised)
    later = daily_record.run(CFG, tmp_path, SITE, now=at + timedelta(days=1))
    assert later["sealed"] == [2025]
    newest = daily_record.latest(out)[2025]
    old = json.loads(records[1].read_text("utf-8"))
    assert newest["record"]["replaces"] == old["recordSha256"]
    assert daily_record.verify(tmp_path, SITE) == []
    index = json.loads((out / "series.json").read_text("utf-8"))
    assert [(r["year"], r["records"]) for r in index] == [(2024, 1), (2025, 2)]

    # Any change to a sealed file shows.
    text = records[0].read_text("utf-8").replace("110.0", "111.0")
    records[0].write_text(text, encoding="utf-8")
    assert any("does not match its seal" in p for p in daily_record.verify(tmp_path, SITE))


def test_without_its_source_the_snapshot_comes_from_the_sealed_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake(monkeypatch, tmp_path, _rows({"2025-06-01": 50.0, "2025-06-02": 51.0}))
    daily_record.run(CFG, tmp_path, SITE)
    (tmp_path / "daily.csv").write_text("day,parameter,value,approval\n", encoding="utf-8")
    _fake(monkeypatch, tmp_path, None)
    with pytest.raises(reach_run.ReachError, match="rebuilt from the sealed records"):
        daily_record.run(CFG, tmp_path, SITE)
    values = climate.read_snapshot(tmp_path / "daily.csv")[climate.DISCHARGE]
    assert [d.value for d in values] == [50.0, 51.0]


def _year(year: int, value: float) -> list[climate.Daily]:
    first = date(year, 1, 1)
    days = (date(year + 1, 1, 1) - first).days
    return [climate.Daily(first + timedelta(days=k), value, False) for k in range(days)]


def test_the_usual_flow_is_the_reference_years_values_around_each_calendar_day() -> None:
    assert climate.calendar_index(date(2023, 1, 1)) == 0
    assert climate.calendar_index(date(2024, 2, 29)) == climate.calendar_index(date(2023, 2, 28))
    assert climate.calendar_index(date(2023, 12, 31)) == 365
    # Three complete years of 10, 20 and 30, and 2026 (after 2025: never a reference) of 1000.
    values = [*_year(2020, 10.0), *_year(2021, 20.0), *_year(2022, 30.0), *_year(2026, 1000.0)]
    band = climate.typical_flow(values, {2020, 2021, 2022, 2026}, factor=1.0)
    assert band is not None
    assert (band["first"], band["last"], band["years"], band["windowDays"]) == (2020, 2022, 3, 7)
    assert len(band["p50"]) == 366
    # Mid-year, each window holds 7 days of each year (21 values): the median is 20, and the 10th
    # and 90th percentiles (linear, at places 2 and 18 of 0 to 20) are 10 and 30.
    k = climate.calendar_index(date(2021, 7, 1))
    assert (band["p10"][k], band["p50"][k], band["p90"][k]) == (10.0, 20.0, 30.0)
    # 29 February is 28 February.
    assert band["p50"][59] == band["p50"][58]
    # The latest day (2026's last, 1000) is higher than every reference value around it.
    latest = climate.latest_flow(values, {2020, 2021, 2022}, factor=1.0)
    assert latest is not None
    assert latest["day"] == "2026-12-31" and latest["higherShare"] == 0.0
    low = climate.latest_flow([*values[:-1], climate.Daily(date(2026, 12, 31), 15.0, True)],
                              {2020, 2021, 2022}, factor=1.0)  # fmt: skip
    assert low is not None and low["provisional"]
    # Of the 21 values around 31 December (7 days of 3 years), the 14 of 2021 and 2022 are higher.
    assert low["higherShare"] == pytest.approx(round(14 / low["values"], 2))
