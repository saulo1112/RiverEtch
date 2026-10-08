"""The whole validation on three synthetic reaches: GeoTIFFs, a fake STAC source, mocked rain.

Items before 2022-01-25 mix the two pre-2022 processing families met in the archive: baseline
02.09 with offset 0, and reprocessed baseline 05.00 items flagged ``boa_offset_applied``.
"""

import csv
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
import pytest
import yaml
from synthetic import draw
from test_sites import FORBIDDEN

from climate_pipeline.screening.config import config_hash
from climate_pipeline.screening.events import EVENT_COLUMNS
from climate_pipeline.screening.rain import OpenMeteoClient
from climate_pipeline.screening.rio import Grid, rowcol_lonlat, site_grid, write_geotiff
from climate_pipeline.screening.stac import AssetRef, Scene, evidence_hash, group_acquisitions
from climate_pipeline.validation.case import names_outside_context
from climate_pipeline.validation.report import write_outputs
from climate_pipeline.validation.run import ValidationOutputs, ValidationPaths, run_validation

PIPELINE = Path(__file__).parents[1]
START, END = date(2020, 12, 1), date(2023, 12, 31)
SITES = {
    "synth-target": (-76.70, 5.60, -76.57, 5.66),
    "synth-control": (-72.70, 5.60, -72.57, 5.66),
    "synth-reference": (-74.70, 5.60, -74.57, 5.66),
}
WATER = {"red": 0.040, "green": 0.055, "swir16": 0.010}
LAND = {"red": 0.050, "green": 0.080, "swir16": 0.200}
TURBID = {"red": 0.10, "green": 0.08}


def acquisition_days() -> list[date]:
    days = []
    day = START + timedelta(days=4)
    while day <= END:
        days.append(day)
        day += timedelta(days=12)
    return days


DAYS = acquisition_days()
# Five anomalous passes, far apart: one in the hold-out period, four in 2022-2023.
ANOMALIES = {DAYS[k] for k in (12, 40, 58, 72, 88)}


@dataclass
class SiteFiles:
    grid: Grid
    river: np.ndarray
    files: dict[str, Path]


def make_site(tmp: Path, site_id: str, bbox: tuple[float, float, float, float]) -> SiteFiles:
    grid = site_grid(bbox)
    river = np.zeros(grid.shape, dtype=bool)
    mid = grid.height // 2
    draw(river, [(mid, 8), (mid - 20, grid.width // 2), (mid, grid.width - 8)], half=4)
    fine = np.repeat(np.repeat(river, 2, axis=0), 2, axis=1)
    downstream = np.zeros(fine.shape, dtype=bool)
    downstream[:, int(fine.shape[1] * 0.6) :] = True
    folder = tmp / "tiles" / site_id
    folder.mkdir(parents=True)
    files: dict[str, Path] = {}

    def write(name: str, data: np.ndarray, g: Grid) -> None:
        files[name] = folder / f"{name}.tif"
        write_geotiff(files[name], data, g)

    write("scl_clear", np.where(river, 6, 4).astype(np.uint8), grid)
    write("scl_cloud", np.full(grid.shape, 9, dtype=np.uint8), grid)
    for variant, offset in (("o", -0.1), ("n", 0.0)):
        for band, g, mask in (
            ("red", grid.with_resolution(10.0), fine),
            ("green", grid.with_resolution(10.0), fine),
            ("swir16", grid, river),
        ):
            for k, jitter in enumerate((-0.002, 0.0, 0.002)):
                refl = np.where(mask, WATER[band] + jitter, LAND[band])
                write(f"{band}_{variant}_normal{k}", ((refl - offset) / 1e-4).astype(np.uint16), g)
            if band in TURBID:
                refl = np.where(
                    mask & downstream, TURBID[band], np.where(mask, WATER[band], LAND[band])
                )
                write(f"{band}_{variant}_turbid", ((refl - offset) / 1e-4).astype(np.uint16), g)
    return SiteFiles(grid, river, files)


class FakeSource:
    name = "fake"

    def __init__(self, sites: dict[str, SiteFiles]) -> None:
        self.sites = sites

    def scenes(self, site_id: str) -> list[Scene]:
        files = self.sites[site_id].files
        epsg = self.sites[site_id].grid.epsg
        out = []
        for k, day in enumerate(DAYS):
            old = day < date(2022, 1, 25)
            reprocessed = old and k % 2 == 1  # baseline 05.00, offset already in the pixels
            in_pixels = reprocessed or (not old and k % 2 == 0)
            baseline = 5.0 if reprocessed else 2.09 if old else 5.09
            offset = 0.0 if old and not reprocessed else -0.1
            variant = "n" if old or in_pixels else "o"
            turbid = site_id == "synth-target" and day in ANOMALIES
            pattern = "turbid" if turbid else f"normal{k % 3}"
            scl = "scl_cloud" if k % 6 == 5 and not turbid else "scl_clear"

            def band(
                name: str, pat: str = pattern, var: str = variant, off: float = offset
            ) -> AssetRef:
                key = f"{name}_{var}_{'normal0' if name == 'swir16' and pat == 'turbid' else pat}"
                return AssetRef(str(files[key]), 1e-4, off, 0, epsg)

            out.append(
                Scene(
                    item_id=f"S2X_SYN_{site_id}_{day:%Y%m%d}_0_L2A",
                    datetime=datetime(day.year, day.month, day.day, 15, 30, tzinfo=UTC),
                    platform="sentinel-2a" if k % 2 else "sentinel-2b",
                    mgrs_tile="18NUL",
                    relative_orbit=25,
                    processing_baseline=baseline,
                    boa_offset_applied=in_pixels if not (old and not reprocessed) else None,
                    cloud_cover=10.0,
                    epsg=epsg,
                    bbox=SITES[site_id],
                    assets={
                        "scl": AssetRef(str(files[scl]), None, None, 0, epsg),
                        "red": band("red"),
                        "green": band("green"),
                        "swir16": band("swir16"),
                    },
                )
            )
        return out

    def search(
        self, bbox: tuple[float, float, float, float], start: date, end: date
    ) -> list[Scene]:
        site_id = next(k for k, b in SITES.items() if b == bbox)
        return [s for s in self.scenes(site_id) if start <= s.datetime.date() <= end]

    def sign(self, href: str) -> str:
        return href


def hourly_rain(day: date, storm: date) -> float:
    """Light rain that varies from day to day, none in the week before an anomaly, one storm."""
    if day == storm:
        return 3.0
    if any(0 <= (a - day).days <= 8 for a in ANOMALIES):
        return 0.0
    return 0.01 * ((day.toordinal() * 7919) % 11)


def open_meteo(storm: date) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        first = date.fromisoformat(request.url.params["start_date"])
        last = date.fromisoformat(request.url.params["end_date"])
        hours = ((last - first).days + 1) * 24
        base = datetime(first.year, first.month, first.day)
        times = [(base + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)]
        values = [hourly_rain((base + timedelta(hours=h)).date(), storm) for h in range(hours)]
        lat, lon = float(request.url.params["latitude"]), float(request.url.params["longitude"])
        return httpx.Response(
            200,
            json={
                "latitude": round(lat * 4) / 4,
                "longitude": round(lon * 4) / 4,
                "hourly": {"time": times, "precipitation": values},
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def site_yaml(site_id: str, files: SiteFiles) -> dict[str, object]:
    grid = files.grid
    up_rows = np.nonzero(files.river[:, 10])[0]
    down_rows = np.nonzero(files.river[:, grid.width - 11])[0]

    def point(rc: tuple[int, int], text: str) -> dict[str, object]:
        lon, lat = rowcol_lonlat(grid, *rc)
        return {"lon": lon, "lat": lat, "description": text, "basis": "synthetic"}

    center = point((grid.height // 2, grid.width // 2), "reach center")
    return {
        "id": site_id,
        "name": f"Synthetic {site_id} (Tierralta, Córdoba)",
        "river": "Río Sintético",
        "category": "A" if site_id == "synth-target" else "D",
        "rationale": "test",
        "center": center,
        "aoi_bbox": list(SITES[site_id]),
        "upstream_anchor": point((int(up_rows.mean()), 10), "upstream end"),
        "downstream_anchor": point((int(down_rows.mean()), grid.width - 11), "downstream end"),
        "rain_points": [center],
        "operator": "none",
        "regulator": "none",
        "citations": [
            {"url": "https://example.test", "title": "t", "supports": "s", "verification": "v"}
        ],
    }


@pytest.fixture(scope="module")
def setup(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, SiteFiles]]:
    root = tmp_path_factory.mktemp("validation")
    (root / "pipeline" / "sites").mkdir(parents=True)
    shutil.copy(PIPELINE / "screening.yaml", root / "pipeline" / "screening.yaml")
    files = {site_id: make_site(root, site_id, bbox) for site_id, bbox in SITES.items()}
    for site_id, f in files.items():
        (root / "pipeline" / "sites" / f"{site_id}.yaml").write_text(
            yaml.safe_dump(site_yaml(site_id, f)), encoding="utf-8"
        )
    docs = root / "docs"
    (docs / "site-screening" / "results-posthoc").mkdir(parents=True)
    (docs / "urra-validation").mkdir(parents=True)
    events = docs / "site-screening" / "events.csv"
    with events.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(EVENT_COLUMNS)
        anomaly = sorted(ANOMALIES)[2]
        writer.writerow(
            [
                "e1",
                "synth-target",
                (anomaly - timedelta(days=1)).isoformat(),
                "",
                "day",
                "Río Sintético",
                "flow_increase",
                "Discharges from the Urrá I reservoir rose",
                "https://news.test/1",
                "news",
                "medium",
                "v",
                "",
            ]
        )
    reference = docs / "site-screening" / "results-posthoc"
    (reference / "stage1_summary.csv").write_text(
        "site_id,mask_source\nsynth-target,scl\n", encoding="utf-8"
    )
    (reference / "stage2_scenes.csv").write_text(
        "site_id,acquisition,excluded,upstream_ndti,downstream_ndti,delta_ndti\n", encoding="utf-8"
    )
    (docs / "urra-validation" / "method.md").write_text("# method\n", encoding="utf-8")
    (docs / "urra-validation" / "rain-grid.csv").write_text(
        "point_id,lon,lat\ng01,-76.70,5.50\ng02,-76.65,5.55\ng03,-76.25,5.75\n", encoding="utf-8"
    )
    source = FakeSource(files)
    recent = {
        site_id: evidence_hash(
            group_acquisitions(
                s for s in source.scenes(site_id) if date(2022, 1, 1) <= s.datetime.date()
            )
        )
        for site_id in SITES
    }
    config = yaml.safe_load((PIPELINE / "urra-validation.yaml").read_text(encoding="utf-8"))
    config.update(
        {
            "sites": {
                "target": "synth-target",
                "control": "synth-control",
                "reference": "synth-reference",
            },
            "period": {"start": START.isoformat(), "end": END.isoformat()},
            "geometry_period": {"start": "2022-01-01", "end": END.isoformat()},
            "holdout": {"start": START.isoformat(), "end": "2021-12-31"},
            "rainy_months": {s: [4, 5, 10, 11] for s in SITES},
        }
    )
    config["screening_reference"].update(
        {"evidence_sha256": recent, "events_sha256": config_hash([events])}
    )
    config["chirps"]["probe_date"] = "2022-03-01"
    (root / "pipeline" / "urra-validation.yaml").write_text(
        yaml.safe_dump(config), encoding="utf-8"
    )
    return root, files


def run(setup: tuple[Path, dict[str, SiteFiles]], stage1_only: bool) -> ValidationOutputs:
    root, files = setup
    paths = ValidationPaths(
        root, root / "pipeline" / "urra-validation.yaml", root / "pipeline" / "out"
    )
    storm = sorted(ANOMALIES)[4] - timedelta(days=1)  # rain on the eve of the last anomaly
    rain = OpenMeteoClient("https://archive.test", http=open_meteo(storm), cache_dir=root / "rain")
    return run_validation(
        paths,
        stage1_only=stage1_only,
        workers=4,
        source=FakeSource(files),
        rain=rain,
        grid_http=open_meteo(storm),
        chirps_reader=lambda url, points: [1.0] * len(points),
        placebo_shuffles=10,
    )


@pytest.fixture(scope="module")
def full(setup: tuple[Path, dict[str, SiteFiles]]) -> ValidationOutputs:
    outputs = run(setup, stage1_only=False)
    write_outputs(outputs, setup[0] / "docs" / "urra-validation" / "results", setup[0])
    return outputs


def test_the_smoke_run_stops_before_any_ndti(setup: tuple[Path, dict[str, SiteFiles]]) -> None:
    outputs = run(setup, stage1_only=True)
    assert outputs.verdict is None and "scenes" not in outputs.tables
    assert all(r.stage2 == {} for r in outputs.runs.values())
    families = {row["baseline_family"] for row in outputs.tables["stage1_counts"]}
    assert {"02.xx", "05.xx"} <= families
    assert outputs.tables["chirps_probe"][0]["status"] == "ok"
    assert [c["points"] for c in outputs.tables["catchment_cells"]] == ["g01 g02", "g03"]
    hashes = [
        r for r in outputs.tables["reproduction_stage1"] if r["check"] == "item-id sha256 2022-2025"
    ]
    assert len(hashes) == 3 and all(r["pass"] for r in hashes)


def test_the_geometry_comes_from_the_screening_period_only(full: ValidationOutputs) -> None:
    for run_ in full.runs.values():
        assert run_.stage1 is not None
        assert run_.stage1.geometry_acquisitions < len(run_.stage1.acquisitions)
        assert run_.stage1.check_geometry is not None
    overlaps = [r["overlap"] for r in full.tables["geometry_check"]]
    assert overlaps and all(o == 1.0 for o in overlaps)


def test_pre_2022_items_of_both_families_are_usable(full: ValidationOutputs) -> None:
    target = full.runs["target"]
    limit = 0.05
    old = [s for s in target.stage2[limit].scenes if s.datetime.date() < date(2022, 1, 25)]
    assert old and all(s.usable for s in old)
    assert {"offset-in-pixels", "ok"} <= {status for s in old for status in s.scaling}
    normal = next(s for s in old if s.datetime.date() not in ANOMALIES)
    assert abs(normal.values["upstream"] - (-0.158)) < 0.03


def test_the_injected_episodes_give_a_candidate_signal(full: ValidationOutputs) -> None:
    target = full.runs["target"]
    assert target.persistence is not None
    anomalous = {
        r.day for r, n in zip(target.records, target.persistence.counts, strict=True) if n >= 8
    }
    assert anomalous == ANOMALIES
    # The last anomaly has rain the day before: it is persistent but rain-coincident.
    assert len(target.persistence.candidates) == 4 and len(target.persistence.episodes) == 4
    verdict = full.verdict
    assert verdict is not None and verdict.label == "candidate signal"
    assert verdict.control_anomalous == 0 and verdict.control_share == pytest.approx(
        0.5 / verdict.control_scored
    )
    assert full.placebo is not None and full.placebo.observed_s2 == 4
    holdout = next(
        r
        for r in full.tables["holdout"]
        if r["site_id"] == "synth-target" and str(r["part"]).startswith("hold-out")
    )
    assert holdout["persistent"] == 1
    event = full.tables["events"][0]
    assert event["status_d0"] == "hit" and event["persistent_scene_in_window"]


def test_outputs_are_written_small_and_anonymous(
    full: ValidationOutputs, setup: tuple[Path, dict[str, SiteFiles]]
) -> None:
    root = setup[0]
    results = root / "docs" / "urra-validation" / "results"
    text = (results / "results.md").read_text(encoding="utf-8")
    assert "Mechanical verdict: candidate signal" in text and "relative index" in text
    manifest = json.loads((results / "run_manifest.json").read_text())
    assert manifest["run"] == "full" and len(manifest["item_ids_sha256"]) == 3
    assert all(p.stat().st_size < 300_000 for p in (results / "figures").glob("*.png"))
    assert len(list((results / "figures").glob("*.png"))) == 3
    for name in ("scenes", "variants", "episodes", "holdout", "stage1_counts", "reproduction_ndti"):
        assert (results / f"{name}.csv").exists(), name
    assert full.case is not None and names_outside_context(full.case) == []
    sample = root / "docs" / "urra-validation" / "urra.sample.json"
    data = json.loads(sample.read_text(encoding="utf-8"))
    assert data["ui"]["permit"]["holder"] == "simulated permit holder"
    assert data["ui"]["reachLabel"] == "Río Sintético near Tierralta, Córdoba"
    assert "Urrá" in json.dumps(data["context"], ensure_ascii=False)
    assert sample.read_bytes() == (root / "pipeline" / "out" / "case" / "urra.json").read_bytes()


def test_generated_text_is_observational(
    full: ValidationOutputs, setup: tuple[Path, dict[str, SiteFiles]]
) -> None:
    disclaimer = "never evidence that any actor caused anything"
    results = setup[0] / "docs" / "urra-validation" / "results" / "results.md"
    assert full.case is not None
    for text in (results.read_text(encoding="utf-8"), full.case.ui.model_dump_json()):
        cleaned = " ".join(text.split()).lower().replace(disclaimer, "")
        assert not [word for word in FORBIDDEN if word in cleaned]
        assert "candidate_human_pressure" not in cleaned
