"""Water-quality v7 and v7.1 (preregistration): the fetch.

``fetch`` snapshots, under ``inputs/v7/``, everything v7's evaluation reads:

* ``surface.csv``: each Sentinel-2 L2A pass at the Platte (item cloud ≤ 70 %), its active channel's
  clear pixels and, for a clear pass, its water pixels by SCL class 6 and by MNDWI > 0;
* ``aoi.json``: the active channel's grid, pixel count and SHA-256 (it is fixed once);
* ``gauge-readings.csv``: the gauges' continuous readings within ±60 min of each pass they pair
  with: the Platte's discharge (00060) at each measured Sentinel-2 pass and its specific
  conductance (00095) at each clear one, its dissolved oxygen (00300) at each Landsat pass of v6
  with clear water, and Baton Rouge's water temperature (00010) at its own and at Belle Chasse's
  Landsat passes, every approval state kept and labelled;
* ``daily.csv``: the Platte's daily means (discharge, conductance, oxygen) in the training years,
  for the nulls;
* ``thermal-windows.csv``: each Landsat 8/9 pass at Baton Rouge's and Belle Chasse's core windows
  (v6's method);
* ``sites.csv``: the gauges' names and datum altitudes (the oxygen saturation's pressure).

Nothing here pairs or scores: the evaluation (``v7``) reads these snapshots.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from climate_pipeline.calibration import extract, sources
from climate_pipeline.calibration.config import load_calibration_config
from climate_pipeline.calibration.fetching import _csv, _reader, error_rows
from climate_pipeline.calibration.stations import Candidate
from climate_pipeline.quality import imagery, landsat, surface, variables
from climate_pipeline.quality.config import QualityConfig
from climate_pipeline.quality.fetching import check_disk
from climate_pipeline.reach import run as reach_run
from climate_pipeline.reach.config import load_reach_config
from climate_pipeline.screening.bands import read_average, read_reflectance
from climate_pipeline.screening.config import load_screening_config
from climate_pipeline.screening.rio import AcquisitionReader, Grid
from climate_pipeline.screening.stac import (
    Acquisition,
    group_acquisitions,
    make_source,
    search_items,
)
from climate_pipeline.sources import usgs

log = logging.getLogger(__name__)

FOLDER = "v7"
PLATTE, PLATTE_GAUGE = "platte-louisville", "USGS-06805500"
BELLE, BELLE_GAUGE = "mississippi-belle-chasse", "USGS-07374525"
BATON_ROUGE = "USGS-07374000"
DISCHARGE, CONDUCTANCE, OXYGEN, TEMPERATURE = "00060", "00095", "00300", "00010"
S2_START, S2_END = date(2018, 12, 1), date(2026, 10, 10)
LANDSAT_START, LANDSAT_END = date(2018, 12, 1), date(2026, 10, 12)
DAILY_START, DAILY_END = "2018-12-01", "2023-11-30"
MAX_CLOUD = 70.0
S2_CAP_GB, LANDSAT_CAP_GB = 6.0, 2.0
LANDSAT_MB = 0.6  # one Landsat asset's blocks over a core window (estimate)
# Block costs as in ``reach.run.corridor_mb``: a 10 m band in 1024-pixel blocks, a 20 m band in
# 512-pixel blocks (deviation 13: the meter counts the bands read and no cached read).
MB_10M_BLOCK, MB_20M_BLOCK = 1.5, 0.4
MARGIN_PX = 4
SURFACE_COLUMNS = ("key", "datetime_utc", "platform", "items", "cloud_cover", "aoi_px", "clear_px",
                   "clear", "scl_water_px", "mndwi_water_px", "problems")  # fmt: skip
DAILY_COLUMNS = ("site_id", "parameter", "day", "value", "approval", "qualified")
SITE_COLUMNS = ("site_id", "name", "altitude_ft", "vertical_datum")
Rows = list[dict[str, Any]]
Errors = list[dict[str, object]]


class Network:
    """Estimated network use against a cap."""

    def __init__(self, cap_gb: float) -> None:
        """Start at zero.

        Args:
            cap_gb: The cap.
        """
        self.cap_gb = cap_gb
        self.mb = 0.0

    def spend(self, mb: float) -> bool:
        """Add an estimate; False once the cap is reached (nothing more should be read).

        Args:
            mb: Megabytes about to be read.

        Returns:
            Whether the read stays under the cap.
        """
        if (self.mb + mb) / 1000 > self.cap_gb:
            return False
        self.mb += mb
        return True


def _blocks(n: int, size: int) -> int:
    return math.ceil(n / size) + 1  # a box rarely starts on a block edge


def scl_mb(grid: Grid) -> float:
    """Estimated download of one scene's SCL over a 20 m grid.

    Args:
        grid: The grid.

    Returns:
        Megabytes.
    """
    return _blocks(grid.width, 512) * _blocks(grid.height, 512) * MB_20M_BLOCK


def bands_mb(grid: Grid) -> float:
    """Estimated download of one scene's B03 (10 m) and B11 (20 m) over a 20 m grid.

    Args:
        grid: The grid.

    Returns:
        Megabytes.
    """
    b10 = _blocks(grid.width * 2, 1024) * _blocks(grid.height * 2, 1024)
    return b10 * MB_10M_BLOCK + scl_mb(grid)


def crop(grid: Grid, mask: np.ndarray, margin: int = MARGIN_PX) -> tuple[Grid, tuple[slice, slice]]:
    """The smallest aligned sub-grid holding ``mask``, plus a margin.

    Args:
        grid: The site grid.
        mask: Pixels to keep (not empty).
        margin: Pixels added on each side.

    Returns:
        The sub-grid and the slices that cut it from ``grid``.
    """
    rows, cols = np.nonzero(mask)
    r0, c0 = max(0, int(rows.min()) - margin), max(0, int(cols.min()) - margin)
    r1 = min(grid.height, int(rows.max()) + margin + 1)
    c1 = min(grid.width, int(cols.max()) + margin + 1)
    sub = Grid(grid.epsg, grid.resolution, grid.x0 + c0 * grid.resolution,
               grid.y0 - r0 * grid.resolution, c1 - c0, r1 - r0)  # fmt: skip
    return sub, (slice(r0, r1), slice(c0, c1))


def filter_cloud(acqs: Sequence[Acquisition], max_cloud: float = MAX_CLOUD) -> list[Acquisition]:
    """The acquisitions regrouped from their items with cloud cover ≤ ``max_cloud`` (or unknown).

    Args:
        acqs: Acquisitions.
        max_cloud: Item cloud cap, percent.

    Returns:
        Acquisitions of the kept items.
    """
    scenes = [s for a in acqs for s in a.scenes
              if s.cloud_cover is None or s.cloud_cover <= max_cloud]  # fmt: skip
    return group_acquisitions(scenes)


def surface_row(acq: Acquisition, reader: AcquisitionReader, grid: Grid, aoi: np.ndarray,
                sub: Grid, cut: tuple[slice, slice], net: Network,
                band_mb: float) -> dict[str, Any]:  # fmt: skip
    """One pass's clear pixels and water counts over the active channel.

    Args:
        acq: The pass.
        reader: Reader (SCL cached).
        grid: The site grid (SCL).
        aoi: The active channel on it.
        sub: The cropped grid for B03 and B11.
        cut: Slices of ``sub`` in ``grid``.
        net: Network budget.
        band_mb: Estimated megabytes of B03 and B11 over ``sub``.

    Returns:
        The row.
    """
    scl = np.asarray(reader.read(acq, "scl", grid)[0])
    clear = surface.clear_pixels(scl, aoi)
    ok = surface.is_clear(clear, aoi)
    problems: list[str] = []
    index = None
    if ok and net.spend(band_mb):
        green, p1 = read_reflectance(reader, acq, "green", sub, read_average)
        swir, p2 = read_reflectance(reader, acq, "swir16", sub)
        problems = p1 + p2
        index = np.full(grid.shape, np.nan)
        index[cut] = surface.mndwi(green, swir)
    elif ok:
        problems = ["network cap reached"]
    scl_water, mndwi_water = surface.water_counts(scl, clear, index)
    clouds = [s.cloud_cover for s in acq.scenes if s.cloud_cover is not None]
    return {
        "key": acq.key, "datetime_utc": acq.datetime.astimezone(UTC).isoformat(timespec="seconds"),
        "platform": acq.platform, "items": "|".join(s.item_id for s in acq.scenes),
        "cloud_cover": min(clouds) if clouds else math.nan, "aoi_px": int(aoi.sum()),
        "clear_px": int(clear.sum()), "clear": int(ok),
        "scl_water_px": scl_water if ok else "", "mndwi_water_px": mndwi_water if index is not None
        else "", "problems": "; ".join(problems),
    }  # fmt: skip


def platte_surface(root: Path, cache: Path, workers: int, keep_free_gb: float
                   ) -> tuple[Rows, dict[str, Any], Errors]:  # fmt: skip
    """The Platte's active channel and every pass's water counts (v7, A).

    Args:
        root: Repository root.
        cache: Cache folder.
        workers: Parallel reads.
        keep_free_gb: The free-disk floor.

    Returns:
        The rows, the area of interest's summary and the read errors.

    Raises:
        RuntimeError: When the frozen geometry has no corridor or frequency.
    """
    reach_cfg = load_reach_config(root / "pipeline/reach.yaml")
    s = reach_run.setup(reach_cfg, root, PLATTE, cache, workers, need_cards=False)
    geometry = s.full.geometry
    if geometry.corridor is None or s.full.frequency is None:
        raise RuntimeError(f"{PLATTE}: the frozen geometry has no corridor or frequency")
    grid = s.full.grid
    aoi = surface.active_channel(geometry.corridor, s.full.frequency, geometry.river_mask)
    sub, cut = crop(grid, aoi)
    summary = {
        "site": PLATTE, "epsg": grid.epsg, "resolution": grid.resolution, "x0": grid.x0,
        "y0": grid.y0, "width": grid.width, "height": grid.height, "pixels": int(aoi.sum()),
        "area_km2": round(float(aoi.sum()) * grid.resolution**2 / 1e6, 4),
        "maskSha256": hashlib.sha256(np.packbits(aoi).tobytes()).hexdigest(),
        "minFrequency": surface.MIN_FREQUENCY, "minClearShare": surface.MIN_CLEAR_SHARE,
        "geometryPeriod": [str(s.reach.geometry_start), str(s.reach.geometry_end)],
    }  # fmt: skip
    acqs, _ = imagery.search(s.quality, "earth-search", reach_run._bbox(s.site), S2_START, S2_END)
    acqs = sorted(filter_cloud(acqs), key=lambda a: (a.datetime, a.key))
    source = make_source("earth-search", s.screening.stac.sources, s.screening.stac.page_size)
    reader = AcquisitionReader(source, cache / "bands")
    net = Network(S2_CAP_GB)
    band_mb = bands_mb(sub)
    rows: list[dict[str, Any]] = []

    def one(acq: Acquisition) -> dict[str, Any] | None:
        check_disk(root, keep_free_gb)
        cost = 0.0 if reader.is_cached(acq, "scl", grid) else scl_mb(grid) * len(acq.scenes)
        if not net.spend(cost):
            return None
        return surface_row(acq, reader, grid, aoi, sub, cut, net, band_mb * len(acq.scenes))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = [r for r in pool.map(one, acqs) if r is not None]
    summary["passes"] = len(acqs)
    summary["measured"] = len(rows)
    summary["networkGbEstimated"] = round(net.mb / 1000, 3)
    log.info("%s: %d passes, %d measured, %d clear, ~%.2f GB", PLATTE, len(acqs), len(rows),
             sum(int(r["clear"]) for r in rows), net.mb / 1000)  # fmt: skip
    return rows, summary, error_rows(reader.errors)


def station_windows(root: Path, quality: QualityConfig, candidate: Candidate, cache: Path,
                    workers: int) -> tuple[Grid, np.ndarray]:  # fmt: skip
    """A gauge's core window on Landsat's 30 m grid, built as the pilot built it.

    Args:
        root: Repository root.
        quality: The v2 settings.
        candidate: The gauge.
        cache: Cache folder.
        workers: Parallel reads.

    Returns:
        The 30 m grid and the core window on it.

    Raises:
        RuntimeError: When the gauge does not snap to a main channel.
    """
    reach_cfg = load_reach_config(root / "pipeline/reach.yaml")
    d15 = load_calibration_config(root / reach_cfg.calibration_config)
    screening = load_screening_config(root / reach_cfg.screening_config)
    bbox = extract.bbox_around(candidate.lon, candidate.lat, quality.stations.grid_half_size_m)
    acqs = extract.search(d15, d15.imagery.primary, bbox, quality.geometry_period.start,
                          quality.geometry_period.end)  # fmt: skip
    geo = extract.station_geometry(candidate, acqs, _reader(d15, screening, cache), d15,
                                   screening, workers)  # fmt: skip
    if not geo.selected:
        raise RuntimeError(f"{candidate.station_id}: no main channel at the gauge")
    windows = imagery.small_windows(geo, quality)
    return variables.grid30(windows.masks["core"], windows.grid)


def landsat_windows(candidate: Candidate, grid: Grid, window: np.ndarray, cache: Path,
                    workers: int, net: Network) -> tuple[Rows, Errors]:  # fmt: skip
    """Every Landsat 8/9 pass at a gauge's core window (v6's method).

    Args:
        candidate: The gauge.
        grid: The 30 m grid.
        window: The core window on it.
        cache: Cache folder.
        workers: Parallel reads.
        net: Network budget.

    Returns:
        The rows and the read errors.
    """
    bbox = extract.bbox_around(candidate.lon, candidate.lat, 2000.0)
    found = [
        scene for item in search_items(landsat.STAC_URL, landsat.COLLECTION, bbox, LANDSAT_START,
                                       LANDSAT_END, 100)
        if (scene := variables.thermal_parse(item)) is not None
        and (scene.cloud_cover is None or scene.cloud_cover <= MAX_CLOUD)
    ]  # fmt: skip
    acqs = sorted(group_acquisitions(found), key=lambda a: (a.datetime, a.key))
    reader = AcquisitionReader(landsat.source(), cache / "landsat-bands", ("qa_pixel",))
    one: Callable[[Acquisition], dict[str, Any]] = partial(
        variables.thermal_window, reader=reader, grid=grid, window=window,
        site=candidate.station_id)  # fmt: skip
    kept = [a for a in acqs if net.spend(2 * LANDSAT_MB * len(a.scenes))]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(one, kept))
    log.info("%s: %d Landsat passes, %d read", candidate.station_id, len(acqs), len(kept))
    return rows, error_rows(reader.errors)


def _times(rows: Sequence[Mapping[str, Any]], test: Callable[[Mapping[str, Any]], bool]
           ) -> list[datetime]:  # fmt: skip
    return [datetime.fromisoformat(str(r["datetime_utc"])) for r in rows if test(r)]


def _site_row(client: httpx.Client, api: str, site: str) -> dict[str, Any]:
    body = usgs.get(client, f"{api}/collections/monitoring-locations/items/{site}",
                    {"f": "json"}).json()  # fmt: skip
    p = body.get("properties", {})
    return {"site_id": site, "name": p.get("monitoring_location_name", ""),
            "altitude_ft": p.get("altitude", ""),
            "vertical_datum": p.get("vertical_datum", "")}  # fmt: skip


def _pilot_candidate(root: Path, cfg: QualityConfig, site: str) -> Candidate:
    path = root / cfg.outputs.inputs / "usgs" / "sites.csv"
    for r in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))):
        if r["site_id"] == site:
            return Candidate(r["site_id"], r["name"], float(r["lon"]), float(r["lat"]), "usgs")
    raise RuntimeError(f"{site}: not in the pilot's site list")


def fetch(cfg: QualityConfig, root: Path, cache: Path, workers: int = 8,
          http: httpx.Client | None = None) -> dict[str, Any]:  # fmt: skip
    """Snapshot v7's inputs (see the module docstring).

    Args:
        cfg: The v2 settings.
        root: Repository root.
        cache: Cache folder.
        workers: Parallel reads.
        http: HTTP client (injectable).

    Returns:
        Counts.
    """
    keep = cfg.budgets.keep_free_gb
    check_disk(root, keep)
    inputs = root / cfg.outputs.inputs
    rec = sources.Recorder(inputs)
    client = http or httpx.Client(timeout=180, follow_redirects=True)
    api = cfg.usgs.api

    surface_rows, aoi, s2_errors = platte_surface(root, cache, workers, keep)
    clear = _times(surface_rows, lambda r: r["clear"] == 1)
    measured = _times(surface_rows, lambda r: True)
    # Discharge at every measured pass: the report-only share of passes the clear rule skipped,
    # by tercile of discharge (v7, A). Conductance only where a water fraction exists.
    readings = variables._readings(client, api, PLATTE_GAUGE, DISCHARGE, measured)
    readings += variables._readings(client, api, PLATTE_GAUGE, CONDUCTANCE, clear)
    v6 = variables.load(root, cfg)
    landsat_platte = _times(v6["thermal"] if v6 else [],
                            lambda r: int(r["water_px"]) >= 10)  # fmt: skip
    readings += variables._readings(client, api, PLATTE_GAUGE, OXYGEN, landsat_platte)
    daily_rows: list[dict[str, Any]] = []
    for parameter in (DISCHARGE, CONDUCTANCE, OXYGEN):
        values, _ = usgs.daily(client, api, PLATTE_GAUGE, parameter, DAILY_START, DAILY_END)
        daily_rows += [{"site_id": PLATTE_GAUGE, "parameter": parameter,
                        "day": r.time.date().isoformat(), "value": r.value,
                        "approval": r.approval, "qualified": int(r.qualified)}
                       for r in values]  # fmt: skip

    net = Network(LANDSAT_CAP_GB)
    thermal: list[dict[str, Any]] = []
    landsat_errors: Errors = []
    baton = _pilot_candidate(root, cfg, BATON_ROUGE)
    reach_cfg = load_reach_config(root / "pipeline/reach.yaml")
    belle = reach_run.setup(reach_cfg, root, BELLE, cache, workers, need_cards=False)
    if belle.station is None:
        raise RuntimeError(f"{BELLE}: no estimate station")
    belle_candidate = reach_run.station_candidate(belle.reach, belle.quality, root)
    if belle_candidate is None:
        raise RuntimeError(f"{BELLE}: its gauge is not listed")
    belle_grid, belle_window = variables.grid30(belle.station.windows.masks["core"],
                                                belle.station.windows.grid)  # fmt: skip
    targets = [(baton, *station_windows(root, cfg, baton, cache, workers)),
               (belle_candidate, belle_grid, belle_window)]  # fmt: skip
    for candidate, grid30, window30 in targets:
        rows, errors = landsat_windows(candidate, grid30, window30, cache, workers, net)
        thermal += rows
        landsat_errors += errors
    landsat_times = _times(thermal, lambda r: int(r["water_px"]) >= 10)
    readings += variables._readings(client, api, BATON_ROUGE, TEMPERATURE, landsat_times)
    sites = [_site_row(client, api, s) for s in (PLATTE_GAUGE, BATON_ROUGE, BELLE_GAUGE)]

    rec.save(f"{FOLDER}/surface.csv", _csv(surface_rows, SURFACE_COLUMNS), "derived",
             note="Sentinel-2 L2A water counts over the Platte's active channel")  # fmt: skip
    rec.save(f"{FOLDER}/aoi.json", (json.dumps(aoi, indent=2, sort_keys=True) + "\n").encode(),
             "derived", note="The Platte's active channel (v7, A)")  # fmt: skip
    rec.save(f"{FOLDER}/gauge-readings.csv", _csv(readings, variables.READING_COLUMNS), "raw",
             note="USGS continuous readings within 60 min of each pass")  # fmt: skip
    rec.save(f"{FOLDER}/daily.csv", _csv(daily_rows, DAILY_COLUMNS), "raw",
             note="USGS daily means of the Platte gauge, training years")  # fmt: skip
    rec.save(f"{FOLDER}/thermal-windows.csv", _csv(thermal, variables.THERMAL_COLUMNS),
             "derived", note="Landsat 8/9 C2-L2 T1 at Baton Rouge's and Belle Chasse's core "
             "windows")  # fmt: skip
    rec.save(f"{FOLDER}/sites.csv", _csv(sites, SITE_COLUMNS), "raw",
             note="USGS monitoring-location names and datum altitudes")  # fmt: skip
    errors = s2_errors + landsat_errors
    rec.save(f"{FOLDER}/read-errors.csv", _csv(errors, ("kind", "error")), "derived")
    (inputs / "fetch-manifest-v7.csv").write_text(rec.manifest(), encoding="utf-8", newline="\n")
    return {
        "s2_passes": aoi["passes"], "s2_measured": aoi["measured"], "s2_clear": len(clear),
        "s2_gb": aoi["networkGbEstimated"], "landsat_passes": len(thermal),
        "landsat_gb": round(net.mb / 1000, 3), "readings": len(readings),
        "daily": len(daily_rows), "read_errors": len(errors), "failures": len(rec.failures),
    }  # fmt: skip


def load(root: Path, cfg: QualityConfig) -> dict[str, Any] | None:
    """v7's snapshots (None before the fetch).

    Args:
        root: Repository root.
        cfg: The v2 settings.

    Returns:
        ``surface``, ``readings``, ``daily``, ``thermal`` and ``sites`` rows, and ``aoi``.
    """
    folder = root / cfg.outputs.inputs / FOLDER
    names = {"surface": "surface.csv", "readings": "gauge-readings.csv", "daily": "daily.csv",
             "thermal": "thermal-windows.csv", "sites": "sites.csv"}  # fmt: skip
    if not all((folder / f).exists() for f in names.values()) or not (folder / "aoi.json").exists():
        return None
    out: dict[str, Any] = {
        k: list(csv.DictReader(io.StringIO((folder / f).read_text(encoding="utf-8"))))
        for k, f in names.items()
    }
    out["aoi"] = json.loads((folder / "aoi.json").read_text(encoding="utf-8"))
    return out
