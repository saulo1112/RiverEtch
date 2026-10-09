"""The offline analysis on synthetic snapshots: pairs, stages, records, MANIFEST and verify.

Station A sits on the reach and has samples whose TSS follows a power law of B04; station B has
IDEAM's daily concentration and discharge; station C has samples, discharge and monthly sediment
transport. The reach's real scenes and case file are copied in, so the observation records are
built from real D0 flags. Bootstrap and permutation counts are reduced to keep the test fast.
"""

import csv
import json
import math
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import numpy as np
import pytest
import yaml

from climate_pipeline.calibration.config import load_calibration_config
from climate_pipeline.calibration.fetching import STATION_COLUMNS, CalibrationPaths
from climate_pipeline.calibration.report import read_manifest, verify, write_outputs
from climate_pipeline.calibration.run import Results, analyse
from climate_pipeline.cli import main
from climate_pipeline.contract.observation import ObservationRecord, is_sealed

REPO = Path(__file__).parents[2]
PIPELINE = REPO / "pipeline"
BANDS = ("B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12")
WINDOW_COLUMNS = ("station", "collection", "key", "datetime_utc", "local_date", "family",
                  "window", "window_px", "data_px", "valid_px", "contamination", "glint_share",
                  "b11_median", "b11_ok", "ndti_px_median", *BANDS)  # fmt: skip


def write_csv(path: Path, rows: list[dict[str, Any]], columns: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(c, "") for c in columns])


def window_row(station: str, collection: str, day: date, b04: float, window: str) -> dict[str, Any]:
    bands = {"B02": 0.03, "B03": b04 * 0.8, "B04": b04, "B05": b04 * 1.1, "B06": 0.05,
             "B07": 0.05, "B08": 0.04, "B8A": b04 * 0.4, "B11": 0.01, "B12": 0.005}  # fmt: skip
    return {"station": station, "collection": collection, "key": f"sentinel-2a_{day}_R025",
            "datetime_utc": f"{day}T15:30:00+00:00", "local_date": day.isoformat(),
            "family": "05.xx" if day.year >= 2022 else "02.xx", "window": window,
            "window_px": 400, "data_px": 400, "valid_px": 300, "contamination": 0.0,
            "glint_share": 0.05, "b11_median": 0.01, "b11_ok": 1.0,
            "ndti_px_median": (b04 - bands["B03"]) / (b04 + bands["B03"]), **bands}  # fmt: skip


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> tuple[CalibrationPaths, Results]:
    root = tmp_path_factory.mktemp("calibration")
    rng = np.random.default_rng(20261009)
    config = yaml.safe_load((PIPELINE / "calibration.yaml").read_text(encoding="utf-8"))
    config["stage1"]["resamples"] = 300
    config["climate"]["width"]["resamples"] = 300
    config["climate"]["enso"]["permutations"] = 300
    (root / "pipeline").mkdir()
    (root / "pipeline" / "calibration.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    (root / "pipeline" / "sites").mkdir()
    shutil.copy(PIPELINE / "sites" / "magdalena-puerto-wilches.yaml", root / "pipeline" / "sites")
    docs = root / "docs" / "magdalena-validation"
    (docs / "results").mkdir(parents=True)
    shutil.copy(REPO / "docs/magdalena-validation/results/scenes.csv", docs / "results")
    shutil.copy(REPO / "docs/magdalena-validation/magdalena.sample.json", docs)
    (docs / "calibration-preregistration.md").write_text("# prereg\n", encoding="utf-8")
    inputs = docs / "calibration" / "inputs"

    with (docs / "results" / "scenes.csv").open(encoding="utf-8") as handle:
        reach_days = sorted({date.fromisoformat(r["date"]) for r in csv.DictReader(handle)
                             if r["site_id"] == "magdalena-puerto-wilches"})  # fmt: skip
    stations = [
        {"station_id": "23187010", "name": "A", "code": "0023187010",
         "quality_point": "A [23187010]",
         "lon": -73.905, "lat": 7.344, "coordinates_from": "catalog", "swapped": "false",
         "files": "", "selected": "true", "reason": "", "roles": "samples reach", "width_m": 600},
        {"station_id": "21237010", "name": "B", "code": "0021237010", "quality_point": "",
         "lon": -74.84, "lat": 4.39, "coordinates_from": "catalog", "swapped": "false",
         "files": "CM_D:1 Q_MEDIA_D:1", "selected": "true", "reason": "", "roles": "cm_d flow",
         "width_m": 300},
        {"station_id": "23157030", "name": "C", "code": "0023157030",
         "quality_point": "C [23157030]", "lon": -73.876, "lat": 7.06,
         "coordinates_from": "catalog", "swapped": "false", "files": "Q_MEDIA_D:1 TR_QS_M:1",
         "selected": "true", "reason": "", "roles": "samples flow transport", "width_m": 500},
        {"station_id": "99", "name": "narrow", "code": "", "quality_point": "N", "lon": -75.0,
         "lat": 2.0, "coordinates_from": "quality point", "swapped": "false", "files": "",
         "selected": "false", "reason": "main channel 60 m wide", "roles": "samples"},
    ]  # fmt: skip
    write_csv(inputs / "stations" / "stations.csv", stations, STATION_COLUMNS)

    windows: dict[str, list[dict[str, Any]]] = {"sentinel-2-l2a": [], "sentinel-2-c1-l2a": []}
    soda: list[dict[str, Any]] = []
    cm: list[dict[str, Any]] = []
    q_b: list[dict[str, Any]] = []
    q_c: list[dict[str, Any]] = []
    extents: list[dict[str, Any]] = []
    b04_of: dict[tuple[str, date], float] = {}
    for sid, days in (("23187010", reach_days), ("23157030", reach_days[::2]),
                      ("21237010", reach_days[::3])):  # fmt: skip
        for d in days:
            b04 = float(np.exp(rng.uniform(np.log(0.03), np.log(0.15))))
            b04_of[(sid, d)] = b04
            for w in ("300m", "1000m"):
                windows["sentinel-2-l2a"].append(window_row(sid, "sentinel-2-l2a", d, b04, w))
            windows["sentinel-2-c1-l2a"].append(
                window_row(sid, "sentinel-2-c1-l2a", d, b04 * 1.01, "300m")
            )
    for sid, point in (("23187010", "A [23187010]"), ("23157030", "C [23157030]")):
        days = [d for (s, d) in b04_of if s == sid][::2]
        for k, d in enumerate(days):
            b04 = b04_of[(sid, d)]
            tss = 5000 * b04**1.5 * float(np.exp(rng.normal(scale=0.15)))
            sample_day = d + timedelta(days=int(k % 2))  # 0 or 1 day after the scene
            for variable, value in (
                ("SOLIDOS SUSPENDIDOS TOTALES", f"{tss:.1f}"),
                ("TURBIDEZ", "<5" if k % 9 == 0 else f"{tss * 0.8:.1f}"),
            ):
                soda.append({"nombre_del_punto_de_monitoreo": point,
                             "fecha": f"{sample_day}T00:00:00.000",
                             "propiedad_observada": variable,
                             "resultado": value.replace(".", ","),
                             "unidad_del_resultado": "mg/L"})  # fmt: skip
    for (sid, d), b04 in b04_of.items():
        if sid == "21237010":
            cm.append(
                {
                    "fechaObservacion": f"{d} 07:00:00",
                    "valorObservado": f"{3000 * b04**1.2:.2f}",
                    "nivelAprobacion": "900",
                }
            )
        if sid in ("21237010", "23157030"):
            flow = 1000 + 20000 * b04
            (q_b if sid == "21237010" else q_c).append(
                {"fechaObservacion": f"{d} 00:00:00", "valorObservado": f"{flow:.1f}",
                 "nivelAprobacion": "900"})  # fmt: skip
            extents.append({"station": sid, "key": f"sentinel-2a_{d}_R025",
                            "datetime_utc": f"{d}T15:30:00+00:00", "local_date": d.isoformat(),
                            "family": "05.xx", "valid_fraction": 0.95,
                            "water_px": 1000 + flow / 10, "extent_km2": (1000 + flow / 10) * 4e-4,
                            "b11_ok": 1.0})  # fmt: skip
    (inputs / "ideam").mkdir(parents=True)
    (inputs / "ideam" / "quality-samples.json").write_text(json.dumps(soda), encoding="utf-8")
    series_cols = ("fechaObservacion", "valorObservado", "nivelAprobacion")
    write_csv(inputs / "ideam" / "CM_D" / "0021237010-CM_D.csv", cm, series_cols)
    write_csv(inputs / "ideam" / "Q_MEDIA_D" / "0021237010-Q_MEDIA_D.csv", q_b, series_cols)
    write_csv(inputs / "ideam" / "Q_MEDIA_D" / "0023157030-Q_MEDIA_D.csv", q_c, series_cols)
    months = [{"fechaObservacion": f"{y}-{m:02d}-01 00:00:00",
               "valorObservado": f"{50 + 10 * math.sin(m):.2f}", "nivelAprobacion": "900"}
              for y in range(2019, 2026) for m in range(1, 13)]  # fmt: skip
    write_csv(inputs / "ideam" / "TR_QS_M" / "0023157030-TR_QS_M.csv", months, series_cols)
    write_csv(inputs / "imagery" / "windows-sentinel-2-l2a.csv", windows["sentinel-2-l2a"],
              WINDOW_COLUMNS)  # fmt: skip
    write_csv(inputs / "imagery" / "windows-sentinel-2-c1-l2a.csv",
              windows["sentinel-2-c1-l2a"], WINDOW_COLUMNS)  # fmt: skip
    write_csv(inputs / "imagery" / "extents.csv", extents,
              ("station", "key", "datetime_utc", "local_date", "family", "valid_fraction",
               "water_px", "extent_km2", "b11_ok"))  # fmt: skip
    write_csv(inputs / "imagery" / "read-errors.csv", [], ("error",))
    start = date(2018, 11, 1)
    days = [start + timedelta(days=k) for k in range(2700)]
    for point in ("g01", "g02"):
        (inputs / "rain" / "open-meteo").mkdir(parents=True, exist_ok=True)
        (inputs / "rain" / "open-meteo" / f"{point}.json").write_text(json.dumps({"daily": {
            "time": [d.isoformat() for d in days],
            "precipitation_sum": [round(float(rng.gamma(0.6, 8.0)), 1) for _ in days],
        }}), encoding="utf-8")  # fmt: skip
    write_csv(inputs / "rain" / "chirps-daily.csv",
              [{"date": d.isoformat(), "g01": 3.0, "g02": 4.0} for d in days],
              ("date", "g01", "g02"))  # fmt: skip
    seasons = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]
    oni = ["SEAS  YR   TOTAL   ANOM"] + [
        f"{s}  {y}  27.0  {(-1.0 if y in (2021, 2022) else 1.0 if y == 2023 else 0.0):.1f}"
        for y in range(2018, 2027) for s in seasons
    ]  # fmt: skip
    (inputs / "climate").mkdir()
    (inputs / "climate" / "oni.ascii.txt").write_text("\n".join(oni) + "\n", encoding="utf-8")
    (inputs / "coefficients").mkdir()
    (inputs / "coefficients" / "Nechad_calibration_201609.txt").write_text(
        "TUR\tMSI\tB4\t665\t366.14\t0.19563\nTUR\tMSI\tB8A\t865\t3250.32\t0.21151\n"
        "SPM\tMSI\tB4\t665\t342.10\t0.19563\n", encoding="utf-8")  # fmt: skip
    (inputs / "coefficients" / "defaults.txt").write_text("lower_lim=0.05\nupper_lim=0.07\n",
                                                          encoding="utf-8")  # fmt: skip
    case = json.loads((docs / "magdalena.sample.json").read_text(encoding="utf-8"))
    ids = sorted({i for s in case["ui"]["scenes"] for i in s["stacItemIds"]})
    write_csv(inputs / "reach" / "items.csv",
              [{"id": i, "url": f"https://s3.test/{i}.json", "sha256": "a" * 64,
                "retrieved_utc": "2026-10-09T00:00:00+00:00", "boa_offset_applied": "true",
                "processing_baseline": "05.00"} for i in ids],
              ("id", "url", "sha256", "retrieved_utc", "boa_offset_applied",
               "processing_baseline"))  # fmt: skip
    write_csv(inputs / "fetch-manifest.csv", [], ("path", "url", "status", "bytes", "sha256",
                                                  "fetched_utc", "note"))  # fmt: skip
    paths = CalibrationPaths(root, root / "pipeline" / "calibration.yaml", root / "cache")
    cfg = load_calibration_config(paths.config)
    results = analyse(cfg, paths)
    write_outputs(results, cfg, paths, paths.at(cfg.outputs.results))
    return paths, results


def table(results: Results, name: str) -> list[dict[str, Any]]:
    return results.tables[name]


def test_pairs_follow_the_rules(world: tuple[CalibrationPaths, Results]) -> None:
    _, results = world
    counts = {r["target"]: r for r in table(results, "pair_counts")}
    assert counts["tss"]["pairs_primary"] > 30 and counts["cm_d"]["pairs_primary"] > 20
    assert "99" not in counts["tss"]["stations"]  # the unselected station never pairs
    pairs = table(results, "pairs")
    assert all(r["gap_days"] <= 1 for r in pairs if r["target"] != "cm_d")
    assert all(r["gap_days"] == 0 for r in pairs if r["target"] == "cm_d")
    censored = [r for r in pairs if r["censored"]]
    assert censored and all(r["split"] == "censored" for r in censored)
    holdout = [r["sample_day"] for r in pairs if r["target"] == "tss" and r["split"] == "holdout"]
    training = [r["sample_day"] for r in pairs if r["target"] == "tss" and r["split"] == "training"]
    assert min(holdout) > max(training)


def test_stage1_reports_every_candidate_and_passes_the_true_driver(
    world: tuple[CalibrationPaths, Results],
) -> None:
    _, results = world
    rows = table(results, "stage1")
    assert len(rows) == 27
    by = {(r["target"], r["candidate"]): r for r in rows}
    assert by[("tss", "B04")]["status"] == "passed"
    assert by[("cm_d", "B04")]["status"] == "passed"
    sens = {r["variant"] for r in table(results, "stage1_sensitivity")}
    assert {"window 1 km", "C1 (2b)", "+-3 days", "validated states only",
            "partial given log discharge"} <= sens  # fmt: skip


def test_stage3_calibrates_and_writes_a_model_card(
    world: tuple[CalibrationPaths, Results],
) -> None:
    paths, results = world
    rows = {r["target"]: r for r in table(results, "stage3_calibration")}
    assert rows["tss"]["status"] == "passed"
    card = json.loads((paths.root / "docs/magdalena-validation/calibration/results/models/tss.json")
                      .read_text(encoding="utf-8"))  # fmt: skip
    assert card["target"] == "tss" and len(card["parametersHash"]) == 64
    assert "23187010" in card["trainingStations"]
    assert table(results, "stage4_transfer") and table(results, "stage3_leave_one_station_out")


def test_climate_stages_and_maturity(world: tuple[CalibrationPaths, Results]) -> None:
    _, results = world
    assert {r["signal"] for r in table(results, "stage5a_climate")} == {
        "upstream",
        "downstream",
        "delta",
    }
    flows = {r["station"]: r for r in table(results, "stage5b_extent_flow")}
    assert flows["21237010"]["status"] == "passed"  # extent follows discharge exactly
    assert any(r["entity"].startswith("TR_QS_M") for r in table(results, "stage5c_enso"))
    assert results.summary["maturity"] == "validated in situ"


def test_records_are_sealed_valid_and_honest(world: tuple[CalibrationPaths, Results]) -> None:
    _, results = world
    schema = json.loads((REPO / "docs/schema/observation-record.v1.schema.json")
                        .read_text(encoding="utf-8"))  # fmt: skip
    validator = jsonschema.Draft202012Validator(schema)
    assert len(results.records) == 112
    for data in results.records:
        assert list(validator.iter_errors(data)) == []
        record = ObservationRecord.model_validate(data)
        assert is_sealed(record)
        c = record.calibration
        # A record carries the first target, in the settings' order, whose calibration passed.
        assert c.status == "passed" and c.target == "turbidity"
        assert (c.value is None) == (c.abstain_reason is not None)
        if record.climate_context.status != "passed":
            assert record.climate_context.label == "not_evaluated"
    flagged = [r for r in results.records if r["verdict"]["anomalous"]]
    assert flagged and all(r["climateContext"]["signal"] in (None, "delta") for r in flagged)


def test_outputs_verify_byte_for_byte(world: tuple[CalibrationPaths, Results]) -> None:
    paths, _ = world
    cfg = load_calibration_config(paths.config)
    folder = paths.at(cfg.outputs.results)
    manifest = read_manifest(folder / "MANIFEST")
    assert "results.md" in manifest and "provenance.json" in manifest
    assert any(name.endswith(".png") for name in manifest)
    assert verify(cfg, paths) == []
    (folder / "stage1.csv").write_text("tampered\n", encoding="utf-8")
    lines = (folder / "MANIFEST").read_text(encoding="utf-8").splitlines()
    tampered = [line if not line.endswith("  stage1.csv") else "0" * 64 + "  stage1.csv"
                for line in lines]  # fmt: skip
    (folder / "MANIFEST").write_text("\n".join(tampered) + "\n", encoding="utf-8")
    assert verify(cfg, paths) == [
        f"stage1.csv: committed {'0' * 64} recomputed {manifest['stage1.csv']}"
    ]
    assert main(["calibration", "run", "--root", str(paths.root)]) == 0
    assert main(["calibration", "verify", "--root", str(paths.root)]) == 0
    assert (folder / "run.json").exists() and "run.json" not in read_manifest(folder / "MANIFEST")
