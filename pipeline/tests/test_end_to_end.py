"""The whole screening on two synthetic sites: GeoTIFFs on disk, a fake STAC source, mocked rain."""

import csv
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
import pytest
import yaml
from synthetic import draw

from climate_pipeline.screening.events import EVENT_COLUMNS
from climate_pipeline.screening.rain import OpenMeteoClient
from climate_pipeline.screening.rio import Grid, rowcol_lonlat, site_grid, write_geotiff
from climate_pipeline.screening.run import RunPaths, run_screening
from climate_pipeline.screening.stac import AssetRef, Scene

ROOT = Path(__file__).parents[1]
PERIOD = (date(2022, 1, 1), date(2023, 12, 31))
TURBID_DAY = date(2023, 3, 2)
STORM_DAY = date(2023, 5, 1)
CONFLICT_DAY = date(2023, 7, 7)
SITES = {
    "synth-dam": ("A", (-76.70, 5.60, -76.57, 5.66)),
    "synth-control": ("D", (-72.70, 5.60, -72.57, 5.66)),
}
WATER = {"red": 0.040, "green": 0.055, "swir16": 0.010}
LAND = {"red": 0.050, "green": 0.080, "swir16": 0.200}


def acquisition_days() -> list[date]:
    days = [PERIOD[0] + timedelta(days=4 + 15 * k) for k in range(49)]
    return sorted({*days, TURBID_DAY, STORM_DAY + timedelta(days=1), CONFLICT_DAY})


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
    files: dict[str, Path] = {}
    folder = tmp / "tiles" / site_id
    folder.mkdir(parents=True)

    def write(name: str, data: np.ndarray, g: Grid) -> None:
        files[name] = folder / f"{name}.tif"
        write_geotiff(files[name], data, g)

    scl = np.where(river, 6, 4).astype(np.uint8)
    write("scl_clear", scl, grid)
    write("scl_cloud", np.full(grid.shape, 9, dtype=np.uint8), grid)
    partial = scl.copy()
    partial[:, : grid.width // 3] = 9
    write("scl_partial", partial, grid)
    turbid_cols = np.zeros(fine.shape, dtype=bool)
    turbid_cols[:, int(fine.shape[1] * 0.6) :] = True
    for variant, offset in (("o", -0.1), ("n", 0.0)):
        for band, res_grid, mask in (
            ("red", grid.with_resolution(10.0), fine),
            ("green", grid.with_resolution(10.0), fine),
            ("swir16", grid, river),
        ):
            for k, jitter in enumerate((-0.002, 0.0, 0.002)):
                refl = np.where(mask, WATER[band] + jitter, LAND[band])
                write(
                    f"{band}_{variant}_normal{k}",
                    ((refl - offset) / 1e-4).astype(np.uint16),
                    res_grid,
                )
            if band in ("red", "green"):
                turbid_value = {"red": 0.10, "green": 0.08}[band]
                down = np.where(
                    mask & turbid_cols, turbid_value, np.where(mask, WATER[band], LAND[band])
                )
                write(
                    f"{band}_{variant}_turbiddown",
                    ((down - offset) / 1e-4).astype(np.uint16),
                    res_grid,
                )
                both = np.where(mask, turbid_value, LAND[band])
                write(
                    f"{band}_{variant}_turbidall",
                    ((both - offset) / 1e-4).astype(np.uint16),
                    res_grid,
                )
    return SiteFiles(grid, river, files)


class FakeSource:
    name = "fake"

    def __init__(self, sites: dict[str, SiteFiles]) -> None:
        self.sites = sites

    def search(
        self, bbox: tuple[float, float, float, float], start: date, end: date
    ) -> list[Scene]:
        site_id = next(k for k, (_, b) in SITES.items() if b == bbox)
        files = self.sites[site_id].files
        epsg = self.sites[site_id].grid.epsg
        scenes = []
        for k, day in enumerate(acquisition_days()):
            if not start <= day <= end:
                continue
            old = day < date(2022, 1, 25)
            # Newer items alternate: pixels that already carry the BOA offset (flagged, as Earth
            # Search does; their listed -0.1 must not be applied again) and pixels that need it.
            in_pixels = not old and k % 2 == 0
            variant = "n" if old or in_pixels else "o"
            offset = 0.0 if old else -0.1
            baseline = 3.01 if old else 5.09
            pattern = f"normal{k % 3}"
            if site_id == "synth-dam" and day == TURBID_DAY:
                pattern = "turbiddown"
            if site_id == "synth-dam" and day == STORM_DAY + timedelta(days=1):
                pattern = "turbidall"
            scl = "scl_cloud" if k % 5 == 4 else "scl_partial" if k % 7 == 6 else "scl_clear"
            if day in (TURBID_DAY, STORM_DAY + timedelta(days=1), CONFLICT_DAY):
                scl = "scl_clear"
            listed_offset = 0.0 if (site_id == "synth-dam" and day == CONFLICT_DAY) else offset

            # B11 has no turbid variant: turbid scenes reuse a normal one.
            swir_pattern = pattern if pattern.startswith("normal") else "normal0"

            def band(
                name: str,
                pat: str = pattern,
                swir: str = swir_pattern,
                off: float = listed_offset,
                var: str = variant,
            ) -> AssetRef:
                key = f"{name}_{var}_{swir if name == 'swir16' else pat}"
                return AssetRef(str(files[key]), 1e-4, off, 0, epsg)

            scenes.append(
                Scene(
                    item_id=f"S2X_SYN_{site_id}_{day:%Y%m%d}_0_L2A",
                    datetime=datetime(day.year, day.month, day.day, 15, 30, tzinfo=UTC),
                    platform="sentinel-2a" if k % 2 else "sentinel-2b",
                    mgrs_tile="18NUL",
                    relative_orbit=25,
                    processing_baseline=baseline,
                    boa_offset_applied=in_pixels,
                    cloud_cover=10.0,
                    epsg=epsg,
                    bbox=SITES[site_id][1],
                    assets={
                        "scl": AssetRef(str(files[scl]), None, None, 0, epsg),
                        "red": band("red"),
                        "green": band("green"),
                        "swir16": band("swir16"),
                    },
                )
            )
        return scenes

    def sign(self, href: str) -> str:
        return href


def rain_client(tmp: Path) -> OpenMeteoClient:
    def handler(request: httpx.Request) -> httpx.Response:
        start = date.fromisoformat(request.url.params["start_date"])
        end = date.fromisoformat(request.url.params["end_date"])
        hours = ((end - start).days + 1) * 24
        times, values = [], []
        for h in range(hours):
            stamp = datetime(start.year, start.month, start.day) + timedelta(hours=h)
            times.append(stamp.strftime("%Y-%m-%dT%H:%M"))
            values.append(
                3.0 if stamp.date() == STORM_DAY else 0.1 if stamp.month in (4, 5, 10, 11) else 0.0
            )
        return httpx.Response(200, json={"hourly": {"time": times, "precipitation": values}})

    return OpenMeteoClient(
        "https://archive.test/v1/archive",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_dir=tmp / "rain",
    )


def write_site_yaml(directory: Path, site_id: str, category: str, files: SiteFiles) -> None:
    grid = files.grid
    rows = np.nonzero(files.river[:, 10])[0]
    up = rowcol_lonlat(grid, int(rows.mean()), 10)
    rows_end = np.nonzero(files.river[:, grid.width - 11])[0]
    down = rowcol_lonlat(grid, int(rows_end.mean()), grid.width - 11)
    center = rowcol_lonlat(grid, grid.height // 2, grid.width // 2)

    def point(lonlat: tuple[float, float], text: str) -> dict[str, object]:
        return {"lon": lonlat[0], "lat": lonlat[1], "description": text, "basis": "synthetic"}

    data = {
        "id": site_id,
        "name": f"Synthetic {site_id}",
        "river": "Synthetic",
        "category": category,
        "rationale": "test",
        "center": point(center, "center"),
        "aoi_bbox": list(SITES[site_id][1]),
        "upstream_anchor": point(up, "upstream end"),
        "downstream_anchor": point(down, "downstream end"),
        "rain_points": [point(center, "center")],
        "operator": "none",
        "regulator": "none",
        "citations": [
            {"url": "https://example.test", "title": "t", "supports": "s", "verification": "v"}
        ],
    }
    (directory / f"{site_id}.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def write_events(path: Path) -> None:
    common = ["Synthetic", "flow_increase", "Discharge increased"]
    rows = [
        ["e1", "synth-dam", (TURBID_DAY - timedelta(days=1)).isoformat(), "", "day", *common,
         "https://example.test/1", "news", "medium", "v", ""],
        ["e2", "synth-dam", "2022-06-18", "", "day", *common, "https://example.test/2", "news",
         "low", "v", ""],
        ["e3", "synth-dam", "2022-02", "", "month", "Synthetic", "flood", "High water",
         "https://example.test/3", "news", "low", "v", ""],
    ]  # fmt: skip
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(EVENT_COLUMNS)
        writer.writerows(rows)


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, object]:
    tmp = tmp_path_factory.mktemp("e2e")
    sites_dir = tmp / "sites"
    sites_dir.mkdir()
    files = {}
    for site_id, (category, bbox) in SITES.items():
        files[site_id] = make_site(tmp, site_id, bbox)
        write_site_yaml(sites_dir, site_id, category, files[site_id])
    events = tmp / "events.csv"
    write_events(events)
    method = tmp / "method.md"
    method.write_text("# method\n", encoding="utf-8")
    paths = RunPaths(
        config=ROOT / "screening.yaml",
        sites=sites_dir,
        events=events,
        method=method,
        out=tmp / "out",
        results=tmp / "results",
    )
    outputs = run_screening(
        paths, period=PERIOD, workers=4, source=FakeSource(files), rain=rain_client(tmp)
    )
    return tmp, outputs


def test_stage1_finds_the_rivers_and_the_selection_follows_the_rule(
    run: tuple[Path, object],
) -> None:
    _, outputs = run
    summaries = {r.site.id: r.summary for r in outputs.stage1}  # type: ignore[attr-defined]
    for summary in summaries.values():
        assert summary["geometry_failed"] == ""
        assert summary["width_px_10m"] > 10
        assert summary["clear"] >= 30
        assert summary["tile_integrity"] == pytest.approx(
            summary["clear"] / summary["acquisitions"], abs=0.25
        )
    # UTC rain spills into the local (UTC-5) last days of March and September.
    assert {"4", "5", "10", "11"} <= set(str(summaries["synth-dam"]["rainy_months"]).split())
    assert outputs.selected == ["synth-dam", "synth-control"]  # type: ignore[attr-defined]


def test_stage2_flags_the_turbid_scenes_and_the_rain(run: tuple[Path, object]) -> None:
    _, outputs = run
    dam = next(r for r in outputs.stage2 if r.site.id == "synth-dam")  # type: ignore[attr-defined]
    by_day = {s.datetime.date(): s for s in dam.scenes}
    turbid = by_day[TURBID_DAY]
    assert turbid.usable
    assert "delta" in turbid.anomalous(3.0) and "downstream" in turbid.anomalous(3.0)
    assert turbid.z["delta"] > 3 and not turbid.rain_coincident
    storm = by_day[STORM_DAY + timedelta(days=1)]
    assert storm.rain_coincident and storm.rain_mm[72] == pytest.approx(72 + 0.1 * 48)
    assert {"upstream", "downstream"} <= set(storm.anomalous(3.0))
    assert "scaling conflict" in by_day[CONFLICT_DAY].exclusion
    january = [s for d, s in by_day.items() if d < date(2022, 1, 25)]
    assert january and all(s.usable for s in january)
    assert abs(january[0].values["upstream"] - (-0.158)) < 0.03


def test_events_are_hits_and_misses_with_a_chance_rate(run: tuple[Path, object]) -> None:
    _, outputs = run
    status = {o.event.event_id: o.status for o in outputs.outcomes}  # type: ignore[attr-defined]
    assert status == {"e1": "hit", "e2": "miss"}
    rates = {c.site_id: c for c in outputs.chance}  # type: ignore[attr-defined]
    assert rates["synth-dam"].windows > 0
    rate, n = outputs.false_alarms["synth-control"]  # type: ignore[attr-defined]
    assert n > 20 and rate == 0


def test_outputs_are_written_small_and_reproducible(run: tuple[Path, object]) -> None:
    tmp, _ = run
    results = tmp / "results"
    for name in ("stage1_summary.csv", "stage1_monthly.csv", "scores.csv", "stage2_scenes.csv",
                 "event_validation.csv", "results.md", "run_manifest.json"):  # fmt: skip
        assert (results / name).exists(), name
    assert (tmp / "out" / "screening_stage1.csv").exists()
    figures = sorted((results / "figures").glob("*.png"))
    assert [f.name for f in figures] == [
        "synth-control_maps.png",
        "synth-control_mask.png",
        "synth-control_series.png",
        "synth-dam_maps.png",
        "synth-dam_mask.png",
        "synth-dam_series.png",
    ]
    assert all(f.stat().st_size < 300_000 for f in figures)
    manifest = json.loads((results / "run_manifest.json").read_text())
    assert manifest["stage2_sites"] == ["synth-dam", "synth-control"]
    assert len(manifest["config_sha256"]) == 64
    text = (results / "results.md").read_text()
    assert "relative index" in text and "e1" in text
