"""Phase 3: Landsat 8/9 Collection 2 Level-2 at the wide Colombian stations (preregistration).

``select_stations`` writes the stations whose main channel is at least 240 m wide (their D15
width), before any Landsat value. ``fetch_values`` reads, at each of them, the Tier 1 Landsat 8/9
acquisitions within the sensitivity days of a sample. The bands are resampled (nearest) onto the
station's 20 m grid and measured in the Sentinel-2 station windows (300 m and core), with D15's
window rules and QA_PIXEL in place of SCL:

* a pixel has data unless QA_PIXEL is 0 (outside the scene) or flags fill (bit 0);
* it is valid unless it flags dilated cloud, cirrus, cloud, cloud shadow or snow (bits 1-5);
* SWIR-1 plays B11's part: above the screening's pixel guard a valid pixel is glint, and the
  median SWIR-1 of the valid pixels must lie in the water range;
* QA_PIXEL is read first: a window that cannot pass skips the bands (D15's deviation 4).

The rows have the Sentinel-2 window columns, with Landsat's bands in the Sentinel-2 slots that
match them (blue B02, green B03, red B04, NIR B8A, SWIR-1 B11, SWIR-2 B12; B05-B08 stay empty).
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np

from climate_pipeline.calibration import extract, sources
from climate_pipeline.calibration.config import load_calibration_config
from climate_pipeline.calibration.fetching import (
    _csv,
    _reader,
    candidate_of,
    error_rows,
    read_stations,
)
from climate_pipeline.quality import imagery, route_a
from climate_pipeline.quality.config import QualityConfig
from climate_pipeline.quality.fetching import check_disk
from climate_pipeline.quality.values import WINDOW_COLUMNS, near
from climate_pipeline.screening.bands import read_reflectance
from climate_pipeline.screening.config import (
    AssetKeys,
    ScreeningConfig,
    StacSourceConfig,
    load_screening_config,
)
from climate_pipeline.screening.rio import AcquisitionReader
from climate_pipeline.screening.stac import (
    Acquisition,
    PlanetaryComputerSource,
    Scene,
    _asset_ref,
    _epsg,
    evidence_hash,
    group_acquisitions,
    search_items,
)

log = logging.getLogger(__name__)

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "landsat-c2-l2"
TOKEN_URL = f"https://planetarycomputer.microsoft.com/api/sas/v1/token/{COLLECTION}"
PLATFORMS = ("landsat-8", "landsat-9")
START = date(2015, 7, 1)
END = date(2026, 9, 30)
MIN_WIDTH_M = 240.0
BANDS = {"B02": "blue", "B03": "green", "B04": "red", "B8A": "nir08", "B11": "swir16",
         "B12": "swir22"}  # fmt: skip
QA_FILL = 1 << 0
QA_UNUSABLE = 0b111110  # dilated cloud, cirrus, cloud, cloud shadow, snow
QA_MB, BANDS_MB = 0.1, 2.0  # estimated download per acquisition (QA block; six band blocks)
STATION_COLUMNS = ("station_id", "stream", "name", "width_m", "lon", "lat")
ITEM_COLUMNS = ("station", "acquisitions", "item_ids_sha256")


def source() -> PlanetaryComputerSource:
    """The signing source for Landsat assets (a SAS token of the Landsat collection).

    Returns:
        The source (its ``search`` is not used: :func:`search` parses Landsat items).
    """
    keys = AssetKeys(scl="qa_pixel", red="red", green="green", swir16="swir16")
    config = StacSourceConfig(
        url=STAC_URL, collection=COLLECTION, assets=keys, sas_token_url=TOKEN_URL
    )
    return PlanetaryComputerSource(config, 100)


def _bbox(item: Mapping[str, Any]) -> tuple[float, float, float, float]:
    west, south, east, north = (float(v) for v in list(item.get("bbox") or [0, 0, 0, 0])[:4])
    return west, south, east, north


def parse(item: Mapping[str, Any]) -> Scene | None:
    """One Landsat 8/9 Tier 1 item as a scene (None for another platform or tier).

    Args:
        item: The STAC item.

    Returns:
        The scene, its assets under the logical names.
    """
    props: Mapping[str, Any] = item["properties"]
    if props.get("platform") not in PLATFORMS or props.get("landsat:collection_category") != "T1":
        return None
    epsg = _epsg(props)
    names = {"qa_pixel": "qa_pixel", **{v: v for v in BANDS.values()}}
    if any(k not in item["assets"] for k in names):
        return None
    path = int(props.get("landsat:wrs_path", 0) or 0)
    row = int(props.get("landsat:wrs_row", 0) or 0)
    when = datetime.fromisoformat(str(props["datetime"]).replace("Z", "+00:00"))
    cloud = props.get("eo:cloud_cover")
    return Scene(
        item_id=str(item["id"]), datetime=when, platform=str(props["platform"]),
        mgrs_tile=f"WRS{path:03d}{row:03d}", relative_orbit=path, processing_baseline=None,
        boa_offset_applied=None, cloud_cover=float(cloud) if cloud is not None else None,
        epsg=epsg, bbox=_bbox(item),
        assets={k: _asset_ref(item["assets"][v], epsg) for k, v in names.items()},
    )  # fmt: skip


def search(bbox: tuple[float, float, float, float], start: date, end: date
           ) -> tuple[list[Acquisition], dict[str, float]]:  # fmt: skip
    """Landsat 8/9 Tier 1 acquisitions over a box, and the sun zenith of each item.

    Args:
        bbox: West, south, east, north.
        start: First day.
        end: Last day.

    Returns:
        Acquisitions and item id -> sun zenith (90 minus the sun elevation).
    """
    scenes, sun = [], {}
    for item in search_items(STAC_URL, COLLECTION, bbox, start, end, 100):
        try:
            scene = parse(item)
        except (KeyError, TypeError, ValueError) as error:
            log.warning("skipping item %s: %s", item.get("id", "?"), error)
            continue
        if scene is None:
            continue
        scenes.append(scene)
        elevation = item["properties"].get("view:sun_elevation")
        sun[scene.item_id] = 90.0 - float(elevation) if elevation is not None else math.nan
    return group_acquisitions(scenes), sun


def _median(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    return float(np.median(finite)) if finite.size else math.nan


def measure(acquisition: Acquisition, reader: AcquisitionReader, windows: extract.Windows,
            station: str, sun: Mapping[str, float], cfg: QualityConfig,
            screening: ScreeningConfig) -> list[dict[str, Any]]:  # fmt: skip
    """The window rows of one Landsat acquisition (see the module docstring).

    Args:
        acquisition: The pass.
        reader: Reader signing Landsat assets.
        windows: The station's Sentinel-2 windows (20 m grid).
        station: Station id.
        sun: Item id -> sun zenith.
        cfg: The v2 settings.
        screening: Screening settings (pixel guard, water range).

    Returns:
        One row per window, in the Sentinel-2 window columns.
    """
    w = cfg.window
    qa = np.asarray(reader.read(acquisition, "qa_pixel", windows.grid)[0]).astype(np.int64)
    data = (qa != 0) & ((qa & QA_FILL) == 0)
    unusable = (qa & QA_UNUSABLE) != 0
    base = {
        "station": station, "source": "landsat", "key": acquisition.key,
        "datetime_utc": acquisition.datetime.astimezone(UTC).isoformat(timespec="seconds"),
        "local_date": extract.local_date(acquisition, cfg.timezone).isoformat(),
        "family": acquisition.platform,
        "sun_zenith": float(np.nanmean([sun.get(s.item_id, math.nan) for s in acquisition.scenes])),
    }  # fmt: skip
    stats = {}
    for name, window in windows.masks.items():
        pixels = window & data
        n = int(pixels.sum())
        stats[name] = (pixels, n, float((pixels & unusable).sum() / n) if n else math.nan)
    if not any(n and int((p & ~unusable).sum()) >= w.min_valid_px and c <= w.max_contamination
               for p, n, c in stats.values()):  # fmt: skip
        return [{**base, "window": name, "window_px": float(windows.masks[name].sum()),
                 "data_px": float(n), "valid_px": math.nan, "contamination": c,
                 "glint_share": math.nan, "b11_median": math.nan, "b11_ok": math.nan,
                 "ndti_px_median": math.nan, **dict.fromkeys(extract.BAND_ORDER, math.nan),
                 "bands_read": 0.0} for name, (_, n, c) in stats.items()]  # fmt: skip
    bands = {b: read_reflectance(reader, acquisition, asset, windows.grid)[0]
             for b, asset in BANDS.items()}  # fmt: skip
    low, high = screening.stage2.water_swir16_range
    rows = []
    for name, (pixels, n, contamination) in stats.items():
        valid = pixels & ~unusable
        glint = valid & (bands["B11"] > screening.stage2.swir16_max)
        water = valid & ~glint
        for b in BANDS:
            water &= np.isfinite(bands[b])
        n_valid = int(valid.sum())
        b11 = _median(bands["B11"][valid])
        red, green = bands["B04"][water], bands["B03"][water]
        rg = red + green
        keep = rg >= screening.stage2.rg_floor
        row = {**base, "window": name, "window_px": float(windows.masks[name].sum()),
               "data_px": float(n), "valid_px": float(int(water.sum())),
               "contamination": contamination,
               "glint_share": float(glint.sum() / n_valid) if n_valid else math.nan,
               "b11_median": b11,
               "b11_ok": float(low <= b11 <= high) if math.isfinite(b11) else 0.0,
               "ndti_px_median": _median((red[keep] - green[keep]) / rg[keep]),
               **dict.fromkeys(extract.BAND_ORDER, math.nan), "bands_read": 1.0}  # fmt: skip
        for b in BANDS:
            row[b] = _median(bands[b][water])
        rows.append(row)
    return rows


def select_stations(cfg: QualityConfig, root: Path) -> list[dict[str, Any]]:
    """Write the Landsat stations: the selected ones with a main channel of at least 240 m.

    Args:
        cfg: The v2 settings.
        root: Repository root.

    Returns:
        The stations (also in ``landsat/stations.csv``).
    """
    inputs = root / cfg.outputs.inputs
    rows = [
        r for r in read_stations(inputs / "stations" / "stations.csv")
        if r["selected"] == "true" and r["width_m"] and float(r["width_m"]) >= MIN_WIDTH_M
    ]  # fmt: skip
    out = [{k: r[k] for k in STATION_COLUMNS} for r in rows]
    path = inputs / "landsat" / "stations.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_csv(out, STATION_COLUMNS))
    return out


def fetch_values(cfg: QualityConfig, root: Path, cache: Path, workers: int) -> dict[str, Any]:
    """Snapshot the Landsat windows near the samples of the frozen Landsat stations.

    Args:
        cfg: The v2 settings.
        root: Repository root.
        cache: Cache folder (the station geometry reads are D15's, cached).
        workers: Parallel reads.

    Returns:
        Counts, the estimated volume and the incomplete parts.
    """
    inputs = root / cfg.outputs.inputs
    path = inputs / "landsat" / "stations.csv"
    wanted = {r["station_id"] for r in csv.DictReader(io.StringIO(path.read_text("utf-8")))}
    stations = [r for r in read_stations(inputs / "stations" / "stations.csv")
                if r["station_id"] in wanted]  # fmt: skip
    ci = route_a.load(cfg, root)
    if ci is None:
        raise RuntimeError("no Colombian snapshots: run quality fetch first")
    d15 = load_calibration_config(root / cfg.calibration_config)
    screening = load_screening_config(root / cfg.screening_config)
    geo_reader = _reader(d15, screening, cache)
    reader = AcquisitionReader(source(), cache / "landsat-bands", ("qa_pixel",))
    rec = sources.Recorder(inputs)
    budget_mb, cap_mb = 0.0, cfg.budgets.network_gb.landsat * 1000
    days: dict[str, set[date]] = {}
    for s in ci.samples:
        days.setdefault(s.station, set()).add(s.day)
    rows: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    incomplete: list[str] = []
    span = cfg.matchups.sensitivity_days
    for row in stations:
        sid = row["station_id"]
        if not days.get(sid):
            continue
        if budget_mb >= cap_mb:
            incomplete.append(f"landsat: network cap reached before {sid}")
            break
        check_disk(root, cfg.budgets.keep_free_gb)
        cand = candidate_of({**row, "files": ""})
        bbox = extract.bbox_around(cand.lon, cand.lat, cfg.stations.grid_half_size_m)
        geo_acqs = extract.search(d15, d15.imagery.primary, bbox, cfg.geometry_period.start,
                                  cfg.geometry_period.end)  # fmt: skip
        geo = extract.station_geometry(cand, geo_acqs, geo_reader, d15, screening, workers)
        if not geo.selected:
            log.warning("%s no longer selected: %s", sid, geo.reason)
            continue
        wins = imagery.small_windows(geo, cfg)
        small = extract.bbox_around(cand.lon, cand.lat, cfg.imagery.read_half_size_m)
        first = max(min(days[sid]) - timedelta(days=span + 1), START)
        last = min(max(days[sid]) + timedelta(days=span + 1), END)
        if first > last:
            continue
        acqs, sun = search(small, first, last)
        acqs = [a for a in acqs if near(extract.local_date(a, cfg.timezone), days[sid], span)]
        items.append({"station": sid, "acquisitions": len(acqs),
                      "item_ids_sha256": evidence_hash(acqs)})  # fmt: skip
        one = partial(measure, reader=reader, windows=wins, station=sid, sun=sun, cfg=cfg,
                      screening=screening)  # fmt: skip
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for found in pool.map(one, acqs):
                rows += found
                budget_mb += QA_MB + (BANDS_MB if any(r["bands_read"] == 1.0 for r in found)
                                      else 0.0)  # fmt: skip
        log.info("%s: %d Landsat acquisitions near samples, about %.2f GB read", sid, len(acqs),
                 budget_mb / 1000)  # fmt: skip
    rec.save("landsat/windows.csv", _csv(rows, WINDOW_COLUMNS), "derived",
             note="Landsat 8/9 C2-L2 Tier 1 in the Sentinel-2 windows (QA_PIXEL)")  # fmt: skip
    rec.save("landsat/items.csv", _csv(items, ITEM_COLUMNS), "derived")
    errors = error_rows([*reader.errors, *geo_reader.errors])
    rec.save("landsat/read-errors.csv", _csv(errors, ("kind", "error")), "derived")
    rec.save("landsat/incomplete.json", (json.dumps(incomplete, indent=1) + "\n").encode(),
             "derived")  # fmt: skip
    (inputs / "fetch-manifest-landsat.csv").write_text(rec.manifest(), encoding="utf-8",
                                                       newline="\n")  # fmt: skip
    return {"stations": len(items), "acquisitions": sum(i["acquisitions"] for i in items),
            "windows_with_bands": sum(1 for r in rows if r["bands_read"] == 1.0),
            "read_errors": sum(1 for e in errors if e["kind"] == "transient"),
            "failures": len(rec.failures), "estimated_gb": round(budget_mb / 1000, 2),
            "incomplete": incomplete}  # fmt: skip
