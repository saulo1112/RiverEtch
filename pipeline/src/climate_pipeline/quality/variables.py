"""Water-quality v6: more variables at the demo reaches (preregistration v6) — the fetch.

``fetch`` snapshots, under ``inputs/v6/``, everything v6's evaluation reads, raw:

* ``ssc.csv``: every discrete suspended-sediment sample (80154) of the two demo gauges since their
  continuous turbidity began;
* ``gauge-readings.csv``: the gauges' continuous readings within ±60 min of each sample
  (turbidity 63680, discharge 00060) and of each Landsat pass at the Platte (water temperature
  00010), every approval state kept and labelled;
* ``thermal-windows.csv``: each Landsat 8/9 Collection 2 Level-2 pass at the Platte gauge's core
  window, on Landsat's own 30 m grid: the median surface temperature of the pixels QA_PIXEL marks
  clear water, and their count.

Nothing here pairs or scores: the evaluation reads these snapshots, so it can be recomputed.
"""

from __future__ import annotations

import csv
import io
import logging
import math
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from climate_pipeline.calibration import sources
from climate_pipeline.calibration.fetching import _csv, error_rows
from climate_pipeline.quality import landsat
from climate_pipeline.quality.config import QualityConfig
from climate_pipeline.quality.fetching import check_disk
from climate_pipeline.reach import run as reach_run
from climate_pipeline.reach.config import load_reach_config
from climate_pipeline.screening.rio import AcquisitionReader, Grid
from climate_pipeline.screening.stac import (
    Acquisition,
    Scene,
    _asset_ref,
    _epsg,
    group_acquisitions,
    search_items,
)
from climate_pipeline.sources import usgs

log = logging.getLogger(__name__)

FOLDER = "v6"
# The demo reaches and their gauges (preregistration v6); water temperature only at the Platte.
GAUGES = {"mississippi-belle-chasse": "USGS-07374525", "platte-louisville": "USGS-06805500"}
TURBIDITY_FROM = {"USGS-07374525": "2012-09-30", "USGS-06805500": "2007-05-15"}
THERMAL_REACH = "platte-louisville"
SSC, TURBIDITY, DISCHARGE, TEMPERATURE = "80154", "63680", "00060", "00010"
START, END = date(2018, 12, 1), date(2026, 10, 12)  # Landsat passes (the lock box ends 2026-09-30)
MAX_CLOUD = 70.0
PAD = timedelta(minutes=60)
BATCH = 40  # time windows per continuous query
ST_SCALE, ST_OFFSET = 0.00341802, 149.0  # ST_B10 digital number to kelvin
QA_FILL, QA_UNUSABLE, QA_WATER = 1 << 0, 0b111110, 1 << 7
ZONES = {"UTC": 0, "GMT": 0, "EST": -5, "EDT": -4, "CST": -6, "CDT": -5, "MST": -7, "MDT": -6,
         "PST": -8, "PDT": -7}  # fmt: skip
READING_COLUMNS = ("site_id", "parameter", "time", "value", "approval", "qualified")
SAMPLE_COLUMNS = ("site_id", "date", "time", "zone", "value", "unit", "status")
THERMAL_COLUMNS = ("site_id", "key", "datetime_utc", "platform", "items", "cloud_cover",
                   "window_px", "water_px", "st_k")  # fmt: skip


def sample_time(row: Mapping[str, str]) -> datetime | None:
    """A discrete sample's time in UTC, from its local date, time and zone.

    Args:
        row: ``date``, ``time`` and ``zone`` of the sample.

    Returns:
        The time, or None when the time or the zone is missing or unknown.
    """
    offset = ZONES.get(row.get("zone", "").strip().upper())
    if offset is None or not row.get("time") or not row.get("date"):
        return None
    local = datetime.fromisoformat(f"{row['date']}T{row['time']}")
    return (local - timedelta(hours=offset)).replace(tzinfo=UTC)


def _windows(times: Sequence[datetime]) -> list[list[tuple[datetime, datetime]]]:
    spans = sorted((t - PAD, t + PAD) for t in times)
    return [spans[k : k + BATCH] for k in range(0, len(spans), BATCH)]


def _readings(client: httpx.Client, api: str, site: str, parameter: str,
              times: Sequence[datetime]) -> list[dict[str, Any]]:  # fmt: skip
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for batch in _windows(times):
        readings, _ = usgs.continuous_many(client, api, site, parameter, batch)
        for r in readings:
            stamp = r.time.astimezone(UTC).isoformat(timespec="seconds")
            rows[(stamp, r.approval)] = {"site_id": site, "parameter": parameter, "time": stamp,
                                         "value": r.value, "approval": r.approval,
                                         "qualified": int(r.qualified)}  # fmt: skip
    return [rows[k] for k in sorted(rows)]


def thermal_parse(item: Mapping[str, Any]) -> Scene | None:
    """One Landsat 8/9 Tier 1 item with its QA_PIXEL and surface-temperature assets.

    Args:
        item: The STAC item.

    Returns:
        The scene (None for another platform or tier, or without those assets).
    """
    props: Mapping[str, Any] = item["properties"]
    if (props.get("platform") not in landsat.PLATFORMS
            or props.get("landsat:collection_category") != "T1"):  # fmt: skip
        return None
    names = {"qa_pixel": "qa_pixel", "lwir11": "lwir11"}
    if any(k not in item["assets"] for k in names):
        return None
    epsg = _epsg(props)
    path = int(props.get("landsat:wrs_path", 0) or 0)
    row = int(props.get("landsat:wrs_row", 0) or 0)
    cloud = props.get("eo:cloud_cover")
    west, south, east, north = (float(v) for v in list(item.get("bbox") or [0, 0, 0, 0])[:4])
    return Scene(
        item_id=str(item["id"]),
        datetime=datetime.fromisoformat(str(props["datetime"]).replace("Z", "+00:00")),
        platform=str(props["platform"]), mgrs_tile=f"WRS{path:03d}{row:03d}",
        relative_orbit=path, processing_baseline=None, boa_offset_applied=None,
        cloud_cover=float(cloud) if cloud is not None else None, epsg=epsg,
        bbox=(west, south, east, north),
        assets={k: _asset_ref(item["assets"][v], epsg) for k, v in names.items()},
    )  # fmt: skip


def grid30(mask: np.ndarray, grid: Grid) -> tuple[Grid, np.ndarray]:
    """A window on Landsat's 30 m pixels: the cells whose centre falls in the 20 m mask.

    Args:
        mask: The window on its 20 m grid.
        grid: That grid.

    Returns:
        The 30 m grid over the same extent and the window on it.
    """
    width = math.ceil(grid.width * grid.resolution / 30.0)
    height = math.ceil(grid.height * grid.resolution / 30.0)
    coarse = Grid(grid.epsg, 30.0, grid.x0, grid.y0, width, height)
    rows = np.minimum(((np.arange(height) + 0.5) * 30.0 / grid.resolution).astype(int),
                      grid.height - 1)  # fmt: skip
    cols = np.minimum(((np.arange(width) + 0.5) * 30.0 / grid.resolution).astype(int),
                      grid.width - 1)  # fmt: skip
    return coarse, mask[np.ix_(rows, cols)]


def thermal_window(acquisition: Acquisition, reader: AcquisitionReader, grid: Grid,
                   window: np.ndarray, site: str) -> dict[str, Any]:  # fmt: skip
    """One Landsat pass at the gauge's core window: clear-water pixels and their median ST.

    Args:
        acquisition: The pass.
        reader: Reader signing Landsat assets.
        grid: The 30 m grid.
        window: The core window on it.
        site: The gauge.

    Returns:
        The row (``st_k`` NaN when no pixel is clear water).
    """
    qa = np.asarray(reader.read(acquisition, "qa_pixel", grid)[0]).astype(np.int64)
    water = (window & (qa != 0) & ((qa & QA_FILL) == 0) & ((qa & QA_UNUSABLE) == 0)
             & ((qa & QA_WATER) != 0))  # fmt: skip
    st = math.nan
    if water.any():
        dn = np.asarray(reader.read(acquisition, "lwir11", grid)[0]).astype(np.float64)
        values = dn[water & (dn > 0)] * ST_SCALE + ST_OFFSET
        st = float(np.median(values)) if values.size else math.nan
    clouds = [s.cloud_cover for s in acquisition.scenes if s.cloud_cover is not None]
    return {
        "site_id": site, "key": acquisition.key,
        "datetime_utc": acquisition.datetime.astimezone(UTC).isoformat(timespec="seconds"),
        "platform": acquisition.platform,
        "items": "|".join(s.item_id for s in acquisition.scenes),
        "cloud_cover": min(clouds) if clouds else math.nan,
        "window_px": int(window.sum()), "water_px": int(water.sum()), "st_k": round(st, 3),
    }  # fmt: skip


def fetch(cfg: QualityConfig, root: Path, cache: Path, workers: int = 8,
          http: httpx.Client | None = None) -> dict[str, Any]:  # fmt: skip
    """Snapshot v6's inputs (see the module docstring).

    Args:
        cfg: The v2 settings.
        root: Repository root.
        cache: Cache folder.
        workers: Parallel reads.
        http: HTTP client (injectable).

    Returns:
        Counts.
    """
    check_disk(root, cfg.budgets.keep_free_gb)
    inputs = root / cfg.outputs.inputs
    rec = sources.Recorder(inputs)
    client = http or httpx.Client(timeout=180, follow_redirects=True)
    api = cfg.usgs.api
    samples: list[dict[str, Any]] = []
    readings: list[dict[str, Any]] = []
    for site in GAUGES.values():
        body = usgs.samples(client, site, SSC, TURBIDITY_FROM[site], "2026-09-30")
        rows = [{"site_id": site, **r} for r in usgs.parse_samples(body)]
        samples += rows
        times = [t for t in (sample_time(r) for r in rows) if t is not None]
        for parameter in (TURBIDITY, DISCHARGE):
            readings += _readings(client, api, site, parameter, times)
        log.info("%s: %d SSC samples, %d with a time", site, len(rows), len(times))

    reach_cfg = load_reach_config(root / "pipeline/reach.yaml")
    s = reach_run.setup(reach_cfg, root, THERMAL_REACH, cache, workers, need_cards=False)
    if s.station is None:
        raise RuntimeError(f"{THERMAL_REACH}: no estimate station")
    grid, window = grid30(s.station.windows.masks["core"], s.station.windows.grid)
    west, south, east, north = s.site.aoi_bbox
    found = [
        scene for item in search_items(landsat.STAC_URL, landsat.COLLECTION,
                                       (west, south, east, north), START, END, 100)
        if (scene := thermal_parse(item)) is not None
        and (scene.cloud_cover is None or scene.cloud_cover <= MAX_CLOUD)
    ]  # fmt: skip
    acqs = group_acquisitions(found)
    reader = AcquisitionReader(landsat.source(), cache / "landsat-bands", ("qa_pixel",))
    site = GAUGES[THERMAL_REACH]
    one = partial(thermal_window, reader=reader, grid=grid, window=window, site=site)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        thermal = list(pool.map(one, acqs))
    times = [datetime.fromisoformat(r["datetime_utc"]) for r in thermal if r["water_px"] > 0]
    readings += _readings(client, api, site, TEMPERATURE, times)
    log.info("%s: %d Landsat passes, %d with clear water", site, len(thermal), len(times))

    rec.save(
        f"{FOLDER}/ssc.csv",
        _csv(samples, SAMPLE_COLUMNS),
        "raw",
        note="USGS discrete samples, 80154, since each gauge's continuous turbidity began",
    )
    rec.save(
        f"{FOLDER}/gauge-readings.csv",
        _csv(readings, READING_COLUMNS),
        "raw",
        note="USGS continuous readings within 60 min of each sample or Landsat pass",
    )
    rec.save(
        f"{FOLDER}/thermal-windows.csv",
        _csv(thermal, THERMAL_COLUMNS),
        "derived",
        note="Landsat 8/9 C2-L2 T1 surface temperature at the Platte gauge's core window",
    )
    errors = error_rows(reader.errors)
    rec.save(f"{FOLDER}/read-errors.csv", _csv(errors, ("kind", "error")), "derived")
    (inputs / "fetch-manifest-v6.csv").write_text(rec.manifest(), encoding="utf-8", newline="\n")
    return {"samples": len(samples), "readings": len(readings), "landsat_passes": len(thermal),
            "clear_water": len(times), "read_errors": len(errors),
            "failures": len(rec.failures)}  # fmt: skip


def load(root: Path, cfg: QualityConfig) -> dict[str, list[dict[str, str]]] | None:
    """v6's snapshots as rows (None before the fetch).

    Args:
        root: Repository root.
        cfg: The v2 settings.

    Returns:
        ``ssc``, ``readings`` and ``thermal`` rows.
    """
    folder = root / cfg.outputs.inputs / FOLDER
    names = {"ssc": "ssc.csv", "readings": "gauge-readings.csv", "thermal": "thermal-windows.csv"}
    if not all((folder / f).exists() for f in names.values()):
        return None
    return {k: list(csv.DictReader(io.StringIO((folder / f).read_text(encoding="utf-8"))))
            for k, f in names.items()}  # fmt: skip
