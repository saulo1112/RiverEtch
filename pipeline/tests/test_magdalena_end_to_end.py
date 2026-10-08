"""The baseline validation (Magdalena settings) on the synthetic reaches of the Urrá test.

The target carries five injected turbid passes, so it must not read as quiet; the in-situ data
come from a mocked open-data endpoint whose turbidity follows the synthetic NDTI.
"""

import csv
import json
import shutil
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import yaml
from test_sites import FORBIDDEN
from test_validation_end_to_end import (
    ANOMALIES,
    DAYS,
    END,
    SITES,
    START,
    FakeSource,
    SiteFiles,
    make_site,
    open_meteo,
    site_yaml,
)

from climate_pipeline.screening.config import config_hash
from climate_pipeline.screening.events import EVENT_COLUMNS
from climate_pipeline.screening.rain import OpenMeteoClient
from climate_pipeline.screening.stac import evidence_hash, group_acquisitions
from climate_pipeline.validation.case import names_outside_context
from climate_pipeline.validation.report import write_outputs
from climate_pipeline.validation.run import ValidationOutputs, ValidationPaths, run_validation

PIPELINE = Path(__file__).parents[1]
LOCAL = ZoneInfo("America/Bogota")
TWO = {k: v for k, v in SITES.items() if k != "synth-reference"}
EVENT_DAY = sorted(ANOMALIES)[2] - timedelta(days=1)
POST_HOC = date(2022, 8, 15)


def insitu_client() -> httpx.Client:
    """Turbidity rising with the synthetic NDTI pattern on clear days; hourly levels."""
    quality = []
    levels = []
    for k, day in enumerate(DAYS):
        if k % 6 == 5:
            continue
        value = 10.0 * (k % 3 + 1) + (100.0 if day in ANOMALIES else 0.0)
        quality.append(
            {
                "nombre_del_punto_de_monitoreo": "SYN [23187010]",
                "fecha": f"{day.isoformat()}T00:00:00.000",
                "propiedad_observada": "TURBIDEZ",
                "resultado": f"{value:.1f}".replace(".", ","),
                "unidad_del_resultado": "NTU",
            }
        )
        for hour in range(6, 15):
            levels.append(
                {
                    "fechaobservacion": f"{day.isoformat()}T{hour:02d}:00:00.000",
                    "valorobservado": f"{3 + k % 5}",
                    "unidadmedida": "mt",
                }
            )

    def handler(request: httpx.Request) -> httpx.Response:
        if "62gv-3857" in request.url.path:
            return httpx.Response(200, json=quality)
        return httpx.Response(200, json=levels)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(scope="module")
def setup(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, SiteFiles]]:
    root = tmp_path_factory.mktemp("magdalena")
    (root / "pipeline" / "sites").mkdir(parents=True)
    shutil.copy(PIPELINE / "screening.yaml", root / "pipeline" / "screening.yaml")
    files = {site_id: make_site(root, site_id, bbox) for site_id, bbox in TWO.items()}
    for site_id, f in files.items():
        (root / "pipeline" / "sites" / f"{site_id}.yaml").write_text(
            yaml.safe_dump(site_yaml(site_id, f)), encoding="utf-8"
        )
    docs = root / "docs"
    (docs / "site-screening" / "results-posthoc").mkdir(parents=True)
    (docs / "magdalena-validation" / "sources").mkdir(parents=True)
    events = docs / "site-screening" / "events.csv"
    with events.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(EVENT_COLUMNS)
        writer.writerow(
            ["e1", "synth-target", EVENT_DAY.isoformat(), "", "day", "Río Sintético",
             "dredging_activity", "A dredge was reported at the reach", "https://news.test/1",
             "news", "medium", "v", ""]
        )  # fmt: skip
        writer.writerow(
            ["e2", "synth-target", "2023-06-01", "2030-12-31", "range", "Río Sintético",
             "dredging_activity", "Contracted maintenance dredging period of the sector",
             "https://news.test/2", "news", "medium", "v", ""]
        )  # fmt: skip
    reference = docs / "site-screening" / "results-posthoc"
    (reference / "stage1_summary.csv").write_text(
        "site_id,mask_source\nsynth-target,scl\n", encoding="utf-8"
    )
    (reference / "stage2_scenes.csv").write_text(
        "site_id,acquisition,excluded,upstream_ndti,downstream_ndti,delta_ndti\n", encoding="utf-8"
    )
    folder = docs / "magdalena-validation"
    (folder / "method.md").write_text("# method\n", encoding="utf-8")
    (folder / "rain-grid.csv").write_text(
        "point_id,lon,lat\ng01,-76.70,5.50\ng02,-76.65,5.55\ng03,-76.25,5.75\n", encoding="utf-8"
    )
    (folder / "post-hoc-events.csv").write_text(
        "id,date_start,date_end,date_precision,description,source_url\n"
        f"p1,{POST_HOC:%Y-%m},{POST_HOC:%Y-%m},month,A dike works report,https://news.test/3\n",
        encoding="utf-8",
    )
    (folder / "sources" / "regulatory-sources.csv").write_text(
        "id,url,purpose\nctx-1,https://example.test/contract,Cormagdalena dredging contract\n",
        encoding="utf-8",
    )
    source = FakeSource(files)
    recent = {
        site_id: evidence_hash(
            group_acquisitions(
                s for s in source.scenes(site_id) if date(2022, 1, 1) <= s.datetime.date()
            )
        )
        for site_id in TWO
    }
    config = yaml.safe_load((PIPELINE / "magdalena-validation.yaml").read_text(encoding="utf-8"))
    config.update(
        {
            "sites": {"target": "synth-target", "control": "synth-control"},
            "period": {"start": START.isoformat(), "end": END.isoformat()},
            "geometry_period": {"start": "2022-01-01", "end": END.isoformat()},
            "holdout": {"start": START.isoformat(), "end": "2021-12-31"},
            "rainy_months": {s: [4, 5, 10, 11] for s in TWO},
        }
    )
    config["screening_reference"].update(
        {"evidence_sha256": recent, "events_sha256": config_hash([events])}
    )
    config["chirps"]["probe_date"] = "2022-03-01"
    config["context"]["source_ids"] = ["ctx-1"]
    config["insitu"]["min_pairs"] = 8
    config["insitu"]["bootstrap"] = 200
    (root / "pipeline" / "magdalena-validation.yaml").write_text(
        yaml.safe_dump(config, allow_unicode=True), encoding="utf-8"
    )
    return root, files


@pytest.fixture(scope="module")
def full(setup: tuple[Path, dict[str, SiteFiles]]) -> ValidationOutputs:
    root, files = setup
    paths = ValidationPaths(
        root, root / "pipeline" / "magdalena-validation.yaml", root / "pipeline" / "out"
    )
    storm = sorted(ANOMALIES)[4] - timedelta(days=1)
    rain = OpenMeteoClient("https://archive.test", http=open_meteo(storm), cache_dir=root / "rain")
    outputs = run_validation(
        paths,
        stage1_only=False,
        workers=4,
        source=FakeSource(files),
        rain=rain,
        grid_http=open_meteo(storm),
        chirps_reader=lambda url, points: [1.0] * len(points),
        placebo_shuffles=10,
        insitu_http=insitu_client(),
    )
    write_outputs(outputs, root / "docs" / "magdalena-validation" / "results", root)
    return outputs


def test_a_reach_with_injected_turbid_passes_is_not_quiet(full: ValidationOutputs) -> None:
    q = full.quietness
    assert full.verdict is None and q is not None
    assert q.k >= 4 and q.n > 50 and not q.quiet
    assert q.control_k == 0 and q.comparison in {
        "higher than the control",
        "not distinguishable from the control",
    }
    rows = full.tables["quietness"]
    assert {r["site_id"] for r in rows} == {"synth-target", "synth-control"}
    assert len(rows) == 2 * len(full.cfg.variants)


def test_every_corridor_is_reported(full: ValidationOutputs) -> None:
    corridors = {r["corridor"] for r in full.tables["corridors"]}
    assert corridors == {"600 m (frozen)", "300 m", "150 m (main-channel approximation)"}


def test_injection_recovery_and_the_demo_event(full: ValidationOutputs) -> None:
    thresholds = {r["scale"]: r for r in full.tables["injection_thresholds"]}
    assert thresholds["ndti"]["interpolated_step"] != ""
    zero = [
        r
        for r in full.tables["injection"]
        if r["scale"] == "ndti" and r["size"] == 0.0 and r["stratum"] == "all"
    ]
    assert len(zero) == 1 and float(str(zero[0]["detected"])) < 0.2
    demo = full.demo
    assert demo is not None and demo.detected and demo.label.startswith("SYNTHETIC")
    # Every catalogued event is avoided, the contract range included.
    assert demo.day <= date(2023, 5, 2)
    assert abs((demo.day - EVENT_DAY).days) >= 30
    assert not (date(2022, 7, 2) <= demo.day <= date(2022, 9, 29))
    assert demo.day >= START


def test_the_case_keeps_the_synthetic_layer_apart(full: ValidationOutputs) -> None:
    case = full.case
    assert case is not None and case.synthetic_overlay is not None and full.demo is not None
    event = case.synthetic_overlay.events[0]
    assert event.synthetic and event.scene_key == full.demo.key and event.detected
    real = next(s for s in case.ui.scenes if s.stac_item_ids == event.stac_item_ids)
    assert real.date == event.date == full.demo.day.isoformat()
    assert real.ndti["downstream"] == pytest.approx(event.real_ndti, abs=1e-4)
    assert event.overlay_ndti == pytest.approx(event.real_ndti + event.magnitude_ndti, abs=1e-4)
    assert case.ui.validation.kind == "baseline"
    assert case.ui.reach_label == "Río Magdalena between Puerto Wilches and San Pablo"
    assert names_outside_context(case, full.cfg.context.forbidden_names) == []
    assert full.manifest["case_names_outside_context"] == []
    data = json.loads(case.to_json())
    assert data["synthetic_overlay"]["synthetic"] is True
    assert "Cormagdalena" in json.dumps(data["context"], ensure_ascii=False)
    without = {k: v for k, v in data.items() if k != "synthetic_overlay"}
    assert "SYNTHETIC" not in json.dumps(without)


def test_insitu_comparisons_follow_the_rule(full: ValidationOutputs) -> None:
    rows = {r["comparison"]: r for r in full.tables["insitu_comparison"]}
    primary = rows["TURBIDEZ, primary stations, +-1 d"]
    assert int(str(primary["pairs"])) >= 8 and primary["reading"] == "tracks"
    assert rows["SOLIDOS SUSPENDIDOS TOTALES, primary stations, +-1 d"]["reading"] == (
        "not enough data"
    )
    assert "river level percentile, stations pooled" in rows
    stations = {r["code"]: r for r in full.tables["insitu_stations"] if r["kind"] == "quality"}
    assert stations["23187010"]["distance_km"] != ""
    assert full.level_percentiles and all(0 < v <= 1 for v in full.level_percentiles.values())
    assert full.tables["saturation"]
    assert {"insitu_sha256"} <= set(full.manifest)


def test_outputs_are_written_and_observational(
    full: ValidationOutputs, setup: tuple[Path, dict[str, SiteFiles]]
) -> None:
    root = setup[0]
    results = root / "docs" / "magdalena-validation" / "results"
    text = (results / "results.md").read_text(encoding="utf-8")
    assert text.startswith("# Magdalena validation: generated results")
    assert "Mechanical reading: not quiet" in text and "SYNTHETIC" in text
    figures = {p.name for p in (results / "figures").glob("*.png")}
    assert {"detection_curve.png", "ndti_vs_red.png", "ndti_vs_insitu.png"} <= figures
    assert "demo_event_synthetic.png" in figures
    assert all(p.stat().st_size < 300_000 for p in (results / "figures").glob("*.png"))
    sample = root / "docs" / "magdalena-validation" / "magdalena.sample.json"
    assert (
        sample.read_bytes() == (root / "pipeline" / "out" / "case" / "magdalena.json").read_bytes()
    )
    disclaimer = "never evidence that any actor caused anything"
    assert full.case is not None
    for body in (text, full.case.ui.model_dump_json()):
        cleaned = " ".join(body.split()).lower().replace(disclaimer, "")
        assert not [word for word in FORBIDDEN if word in cleaned]
