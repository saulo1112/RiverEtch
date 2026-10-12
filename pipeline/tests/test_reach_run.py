import json
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from test_reach_records import ITEM, STATS, card

from climate_pipeline.calibration.config import load_calibration_config
from climate_pipeline.contract.observation import RainFlags
from climate_pipeline.quality import imagery
from climate_pipeline.quality.config import load_quality_config
from climate_pipeline.reach import measure as m
from climate_pipeline.reach import records
from climate_pipeline.reach import run as reach_run
from climate_pipeline.reach.config import load_reach_config
from climate_pipeline.screening.config import load_screening_config, load_site
from climate_pipeline.screening.rio import Grid
from climate_pipeline.screening.stac import Acquisition

PIPELINE = Path(__file__).parents[1]
SITE = "magdalena-puerto-wilches"
FILES = ("pipeline/reach.yaml", "pipeline/screening.yaml", "pipeline/water-quality.yaml")


def acquisition(day: date, name: str) -> Acquisition:
    return Acquisition(name, datetime(day.year, day.month, day.day, 15, 30, tzinfo=UTC),
                       "sentinel-2a", 25)  # fmt: skip


@pytest.fixture
def root(tmp_path: Path) -> Path:
    for f in FILES:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(PIPELINE.parent / f, tmp_path / f)
    scenes = tmp_path / "docs/magdalena-validation/results/scenes.csv"
    scenes.parent.mkdir(parents=True)
    lines = ["site_id,acquisition,date,excluded,upstream_ndti,downstream_ndti"]
    ratio = ["key,date,nir_red_upstream,nir_red_downstream"]
    for k in range(30):
        day = date(2023, 1, 5) + timedelta(days=24 * k)
        v = 0.10 + 0.004 * (k % 4)
        lines.append(f"{SITE},old{k},{day},,{v},{v + 0.002}")
        ratio.append(f"old{k},{day},{0.5 + 0.01 * (k % 3)},{0.52 + 0.01 * (k % 3)}")
    lines.append(f"{SITE},cloudy-old,2023-02-01,cloud,,")
    scenes.write_text("\n".join(lines) + "\n", encoding="utf-8")
    nir = tmp_path / f"docs/water-quality/reach/{SITE}/nir-red-baseline.csv"
    nir.parent.mkdir(parents=True)
    nir.write_text("\n".join(ratio) + "\n", encoding="utf-8")
    return tmp_path


def prepared(root: Path) -> reach_run.Setup:
    cfg = load_reach_config(root / "pipeline/reach.yaml")
    grid = Grid(32618, 20.0, 500_000.0, 800_000.0, 150, 400)
    corridor = cast(Any, SimpleNamespace(grid=grid))
    return reach_run.Setup(
        cfg, cfg.reach(SITE), root, load_screening_config(PIPELINE / "screening.yaml"),
        load_quality_config(PIPELINE / "water-quality.yaml"),
        load_calibration_config(PIPELINE / "calibration.yaml"),
        load_site(PIPELINE / "sites" / f"{SITE}.yaml"), corridor, corridor, None,
        cast(Any, None), {"turbidity": card()}, "core",
    )  # fmt: skip


def fake_measure(acq: Acquisition, *args: Any) -> records.Measure:
    day = acq.datetime.date()
    down = 0.40 if acq.key == "turbid" else 0.11
    return records.Measure(
        acq.key, day, (ITEM,), "B11 out of range" if acq.key == "glinted" else "",
        {"upstream": 0.11, "downstream": down}, {"upstream": 0.5, "downstream": 0.52},
        {"B8A/B04": 1.0}, STATS,
    )  # fmt: skip


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Acquisition]]:
    scenes = {"found": [acquisition(date(2026, 9, 2), "cloudy"),
                        acquisition(date(2026, 9, 7), "glinted"),
                        acquisition(date(2026, 9, 12), "normal"),
                        acquisition(date(2026, 9, 17), "turbid")]}  # fmt: skip
    monkeypatch.setattr(imagery, "search", lambda *a: (scenes["found"], {}))
    monkeypatch.setattr(m, "observable", lambda acq, *a: acq.key != "cloudy")
    monkeypatch.setattr(m, "measure", fake_measure)
    monkeypatch.setattr(reach_run, "check_disk", lambda *a: 100.0)
    unknown = RainFlags(point=None, catchment=None, union="unknown")
    monkeypatch.setattr(reach_run, "rain_flags", lambda *a: unknown)
    return scenes


def go(root: Path, s: reach_run.Setup | None = None) -> reach_run.RunSummary:
    s = s or prepared(root)
    return reach_run.run(s.cfg, root, SITE, date(2026, 9, 1), date(2026, 9, 30), root / "cache",
                         prepared=s)  # fmt: skip


def test_a_run_records_usable_scenes_and_chains_the_ledger(
    root: Path, offline: dict[str, list[Acquisition]]
) -> None:
    summary = go(root)
    folder = root / "pipeline/out/reach" / SITE
    assert summary.exit_code == reach_run.EXIT_OK and len(summary.recorded) == 2
    assert summary.skipped == {"cloudy": "not observable", "glinted": "excluded: B11 out of range"}
    latest = json.loads((folder / "latest.json").read_text(encoding="utf-8"))
    assert latest["date"] == "2026-09-17" and latest["verdict"]["anomalous"]
    assert latest["estimates"][0]["level"] == "estimated" and latest["estimates"][1]["level"] == (
        "none")  # fmt: skip
    series = json.loads((folder / "series.json").read_text(encoding="utf-8"))
    assert [r["date"] for r in series] == ["2026-09-12", "2026-09-17"]
    assert not series[0]["verdict"]["anomalous"]
    assert reach_run.ledger_ok(folder / "ledger.jsonl")
    assert go(root).recorded == []  # nothing new: the state remembers every decision
    assert len((folder / "ledger.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_a_failed_scene_is_retried_by_the_next_run(
    root: Path, offline: dict[str, list[Acquisition]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(acq: Acquisition, *args: Any) -> records.Measure:
        if acq.key == "turbid":
            raise OSError("connection reset")
        return fake_measure(acq, *args)

    monkeypatch.setattr(m, "measure", broken)
    first = go(root)
    assert first.exit_code == reach_run.EXIT_PARTIAL and list(first.failed) == ["turbid"]
    monkeypatch.setattr(m, "measure", fake_measure)
    second = go(root)
    assert second.exit_code == reach_run.EXIT_OK and len(second.recorded) == 1
    assert reach_run.ledger_ok(root / "pipeline/out/reach" / SITE / "ledger.jsonl")


def test_the_network_cap_stops_a_run(root: Path, offline: dict[str, list[Acquisition]]) -> None:
    s = prepared(root)
    tight = s.cfg.model_copy(update={"budgets": s.cfg.budgets.model_copy(update={"max_gb": 0.01})})
    summary = go(root, reach_run.Setup(**{**s.__dict__, "cfg": tight}))
    assert summary.exit_code == reach_run.EXIT_CAP and "network cap" in summary.stopped
    assert len(summary.recorded) < 2


def test_a_tampered_ledger_breaks_the_chain(
    root: Path, offline: dict[str, list[Acquisition]]
) -> None:
    go(root)
    ledger = root / "pipeline/out/reach" / SITE / "ledger.jsonl"
    lines = ledger.read_text(encoding="utf-8").splitlines()
    ledger.write_text(lines[0].replace("2026-09-12", "2026-09-13") + "\n" + lines[1] + "\n",
                      encoding="utf-8")  # fmt: skip
    assert not reach_run.ledger_ok(ledger)


def test_the_corridor_estimate_counts_blocks() -> None:
    small = reach_run.corridor_mb(Grid(32618, 20.0, 0.0, 0.0, 100, 100))
    large = reach_run.corridor_mb(Grid(32618, 20.0, 0.0, 0.0, 445, 890))
    assert 0 < small < large


def test_the_baseline_resumes_without_measuring_a_scene_twice(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = [acquisition(date(2023, 1, 5) + timedelta(days=24 * k), f"old{k}") for k in range(30)]
    measured: list[str] = []

    def scene(corridor: Any, acq: Acquisition, *a: Any) -> Any:
        measured.append(acq.key)
        sub = SimpleNamespace(ndti=0.1)
        return SimpleNamespace(exclusion="", sub={"upstream": sub, "downstream": sub})

    monkeypatch.setattr(imagery, "search", lambda *a: (found, {}))
    monkeypatch.setattr(reach_run, "measure_acquisition", scene)
    monkeypatch.setattr(m, "nir_red", lambda *a: {"upstream": 0.5, "downstream": 0.6})
    monkeypatch.setattr(reach_run, "check_disk", lambda *a: 100.0)
    s = prepared(root)
    (root / s.reach.nir_red_baseline).unlink()  # the fixture's file is for the run tests
    s = reach_run.Setup(**{**s.__dict__, "reader": SimpleNamespace(forget=lambda acq: None)})
    per_scene = reach_run.corridor_mb(s.corridor.grid) / 1000
    small = s.cfg.model_copy(update={"budgets": s.cfg.budgets.model_copy(
        update={"baseline_max_gb": per_scene * 10})})  # fmt: skip
    first = reach_run.build_baseline(
        small, root, SITE, root / "cache", prepared=reach_run.Setup(**{**s.__dict__, "cfg": small})
    )
    assert first["measured"] == 10 and first["stopped"] and len(measured) == 10
    path = root / s.reach.nir_red_baseline
    head_rows = path.read_text(encoding="utf-8").splitlines()[:11]
    second = reach_run.build_baseline(s.cfg, root, SITE, root / "cache", prepared=s)
    assert second["measured"] == 30 and not second["stopped"] and len(measured) == 30
    assert path.read_text(encoding="utf-8").splitlines()[:11] == head_rows
    assert second["network_gb_estimated"] == pytest.approx(per_scene * 30, rel=1e-3)


def test_a_reach_without_validation_scenes_measures_its_own_baseline(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    days = [date(2023, 1, 5) + timedelta(days=30 * k) for k in range(6)]
    found = [acquisition(d, f"own{k}") for k, d in enumerate(days)]
    found.append(acquisition(date(2024, 2, 1), "after"))  # beyond baseline_end: never measured

    def scene(corridor: Any, acq: Acquisition, *a: Any) -> Any:
        sub = SimpleNamespace(ndti=0.1 + 0.01 * int(acq.key[-1]))
        exclusion = "glint" if acq.key == "own3" else ""
        return SimpleNamespace(exclusion=exclusion, sub={"upstream": sub, "downstream": sub})

    monkeypatch.setattr(imagery, "search", lambda *a: ([a for a in found if a.key != "after"], {}))
    monkeypatch.setattr(m, "observable", lambda acq, *a: acq.key != "own1")
    monkeypatch.setattr(reach_run, "measure_acquisition", scene)
    monkeypatch.setattr(m, "nir_red", lambda *a: {"upstream": 0.5, "downstream": 0.6})
    monkeypatch.setattr(reach_run, "check_disk", lambda *a: 100.0)
    s = prepared(root)
    own = s.reach.model_copy(update={
        "ndti_scenes": None, "baseline_start": date(2023, 1, 1),
        "baseline_end": date(2023, 12, 31), "nir_red_baseline": "docs/own/nir-red-baseline.csv",
    })  # fmt: skip
    s = reach_run.Setup(**{**s.__dict__, "reach": own,
                           "reader": SimpleNamespace(forget=lambda acq: None)})  # fmt: skip
    info = reach_run.build_baseline(s.cfg, root, SITE, root / "cache", prepared=s)
    assert info["measured"] == 6 and info["usable"] == 4 and info["frozen_scenes"] is None
    rows = (root / own.nir_red_baseline).read_text(encoding="utf-8").splitlines()
    assert any(r.startswith("own1,") and "not observable" in r for r in rows)
    baseline = reach_run.load_baseline(s)
    assert len(baseline.days) == 4 and days[1] not in baseline.days and days[3] not in baseline.days
    assert baseline.ndti["upstream"][0] == pytest.approx(0.10)


def test_reach_settings_need_a_baseline_source_and_declared_cards_must_exist(root: Path) -> None:
    from climate_pipeline.reach.config import Reach

    cfg = load_reach_config(root / "pipeline/reach.yaml")
    base = cfg.reach(SITE).model_dump()
    with pytest.raises(ValueError, match="baseline_start"):
        Reach.model_validate({**base, "ndti_scenes": None})
    hermann = cfg.reach("missouri-hermann")
    assert hermann.station_source == "usgs" and hermann.targets == ("turbidity",)
    assert reach_run.reach_cards(cfg, hermann, root, strict=False) == {}
    with pytest.raises(reach_run.ReachError, match="no model card"):
        reach_run.reach_cards(cfg, hermann, root)
    path = root / hermann.cards["turbidity"]
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({**card(), "target": "tss"}), encoding="utf-8")
    with pytest.raises(reach_run.ReachError, match="tss card"):
        reach_run.reach_cards(cfg, hermann, root)


def test_verify_catches_an_edited_record_and_a_broken_ledger(
    root: Path, offline: dict[str, list[Acquisition]]
) -> None:
    go(root)
    cfg = load_reach_config(root / "pipeline/reach.yaml")
    folder = root / "pipeline/out/reach" / SITE
    assert reach_run.verify_outputs(cfg, root, SITE) == []
    record = sorted((folder / "records").glob("*.json"))[0]
    data = json.loads(record.read_text(encoding="utf-8"))
    data["indices"]["ndti"]["downstream"] = 0.9  # an edited value
    record.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    problems = reach_run.verify_outputs(cfg, root, SITE)
    assert any("no longer matches its recordSha256" in p for p in problems)
    ledger = folder / "ledger.jsonl"
    lines = ledger.read_text(encoding="utf-8").splitlines()
    ledger.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")  # reordered
    assert any("does not name the hash" in p for p in reach_run.verify_outputs(cfg, root, SITE))


def test_the_station_keeps_the_width_its_card_was_trained_with() -> None:
    cfg = load_reach_config(PIPELINE / "reach.yaml")
    quality = load_quality_config(PIPELINE / "water-quality.yaml")
    assert reach_run.frozen_width(cfg.reach("missouri-hermann"), quality, PIPELINE.parent) == 394.0
    assert reach_run.frozen_width(cfg.reach(SITE), quality, PIPELINE.parent) == 572.7
