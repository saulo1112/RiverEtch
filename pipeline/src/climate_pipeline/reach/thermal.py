"""Water temperature records and the gauge's context at a reach (preregistration v6, C and D).

``thermal`` records each Landsat 8/9 pass of a reach that has a water-temperature card
(``docs/water-quality/results/models/<site>/water_temperature.json``): the gauge's core window on
Landsat's 30 m pixels, the median surface temperature of its clear-water pixels (at least the
card's minimum), the card's estimate with its level and 90 % interval, sealed and chained in the
reach's temperature ledger (``thermal/``). Beside the records, never in them, it notes the gauge's
own water temperature at each pass (approved, else provisional, and labelled).

``context`` notes, at each Sentinel-2 pass of the reach's records, the gauge's own readings
(discharge and gage height; at the Platte also water temperature, dissolved oxygen, specific
conductance and nitrate plus nitrite) in ``checks/context.csv``: measurements, never estimates.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from climate_pipeline.contract import thermal as contract
from climate_pipeline.provenance import head
from climate_pipeline.quality import imagery, landsat, variables
from climate_pipeline.quality.cards import card_hash
from climate_pipeline.quality.config import load_quality_config
from climate_pipeline.reach import run as reach_run
from climate_pipeline.reach.config import ReachConfig
from climate_pipeline.screening.rio import AcquisitionReader
from climate_pipeline.screening.stac import group_acquisitions, search_items
from climate_pipeline.sources import usgs

log = logging.getLogger(__name__)

FOLDER = "thermal"
ITEM_URL = f"{landsat.STAC_URL}/collections/{landsat.COLLECTION}/items/"
COVERAGE = 0.9
APPROVALS = ("Approved", "Provisional")
# The gauge's readings noted as context: parameter -> (name, unit, factor from the API's unit).
CONTEXT = {
    "00060": ("discharge", "m³/s", 0.0283168466),
    "00065": ("gage height", "m", 0.3048),
    "00010": ("water temperature", "°C", 1.0),
    "00300": ("dissolved oxygen", "mg/L", 1.0),
    "00095": ("specific conductance", "µS/cm", 1.0),
    "00630": ("nitrate plus nitrite (as N)", "mg/L", 1.0),
}
CONTEXT_COLUMNS = ("key", "date", "datetimeUtc", "parameter", "name", "value", "unit", "approval")
CHECK_COLUMNS = ("date", "sceneId", "datetimeUtc", "estimate", "gauge", "value", "approval")


def card_path(root: Path, site_id: str) -> Path:
    """Where a reach's water-temperature card lives.

    Args:
        root: Repository root.
        site_id: The reach.

    Returns:
        The path (it may not exist).
    """
    return reach_run.temperature_card(root, site_id)


def estimate(card: Mapping[str, Any], surface_k: float) -> contract.Estimate:
    """The card's water temperature for a pass's median surface temperature.

    Args:
        card: The water-temperature card.
        surface_k: The median surface temperature, kelvin.

    Returns:
        The estimate with its level and 90 % interval (no value under level ``indicative``, nor
        when the card names an input range and the pass lies outside it).
    """
    p = card["parameters"]
    level = next((r["level"] for r in card["levels"] if r["predicted_range"] == "all"), "none")
    st_c = surface_k - 273.15
    value = p["a"] + p["b"] * st_c
    bounds = card.get("inputRange")
    if bounds is not None and not float(bounds["min"]) <= st_c <= float(bounds["max"]):
        value = math.nan  # outside the fitted range: abstain (v7's common rule)
    model = {"level": level, "modelId": card["modelId"], "modelVersion": card["version"],
             "modelCardSha256": card_hash(card), "basis": card["basis"]}  # fmt: skip
    if level not in ("validated", "estimated") or not math.isfinite(value):
        return contract.Estimate.model_validate(model)
    half = float(card["halfWidth90"])
    return contract.Estimate.model_validate({
        **model, "value": round(value, 2),
        "interval": contract.Interval(low=round(value - half, 2), high=round(value + half, 2),
                                      coverage=COVERAGE, method="split_conformal_absolute"),
    })  # fmt: skip


def _append(path: Path, rec: contract.ThermalRecordV1, file: str, created: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    previous = hashlib.sha256(lines[-1].encode()).hexdigest() if lines else None
    line = {"sceneId": rec.scene_id, "date": rec.date, "recordSha256": rec.record_sha256,
            "file": file, "createdUtc": created, "previousLineSha256": previous}  # fmt: skip
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n")


def _gauge(client: httpx.Client, api: str, site: str, parameter: str, when: datetime,
           median: int, nearest: int, exclude: bool) -> tuple[float, str]:  # fmt: skip
    readings, _ = usgs.continuous_many(client, api, site, parameter,
                                       [(when - timedelta(minutes=nearest),
                                         when + timedelta(minutes=nearest))])  # fmt: skip
    for status in APPROVALS:
        value, _, _ = usgs.overpass_value(readings, when, median, nearest, status, exclude)
        if math.isfinite(value):
            return value, status
    return math.nan, ""


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> None:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    for r in rows:
        writer.writerow(["" if isinstance(r.get(c), float) and math.isnan(r[c]) else r.get(c, "")
                         for c in columns])  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(out.getvalue(), encoding="utf-8", newline="\n")


def thermal(cfg: ReachConfig, root: Path, site_id: str, cache: Path, since: date | None,
            until: date | None, workers: int = 8, http: httpx.Client | None = None
            ) -> dict[str, Any]:  # fmt: skip
    """Record the reach's Landsat passes with the water-temperature card (resumable).

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        cache: Cache folder.
        since: First day (default: 30 days before today).
        until: Last day (default: today).
        workers: Parallel reads for the geometry.
        http: HTTP client for the gauge (injectable).

    Returns:
        Counts.

    Raises:
        ReachError: Without a water-temperature card or an estimate station.
    """
    path = card_path(root, site_id)
    if not path.exists():
        raise reach_run.ReachError(f"{site_id}: no water-temperature card")
    card = json.loads(path.read_text(encoding="utf-8"))
    s = reach_run.setup(cfg, root, site_id, cache, workers, need_cards=False)
    if s.station is None:
        raise reach_run.ReachError(f"{site_id}: no estimate station")
    grid, window = variables.grid30(s.station.windows.masks["core"], s.station.windows.grid)
    last = until or datetime.now(UTC).date()
    first = since or last - timedelta(days=cfg.lookback_days)
    west, south, east, north = s.site.aoi_bbox
    scenes = [scene for item in search_items(landsat.STAC_URL, landsat.COLLECTION,
                                             (west, south, east, north), first, last, 100)
              if (scene := variables.thermal_parse(item)) is not None]  # fmt: skip
    acqs = sorted(group_acquisitions(scenes), key=lambda a: (a.datetime, a.key))
    reader = AcquisitionReader(landsat.source(), cache / "landsat-bands", ("qa_pixel",))
    folder = root / cfg.out / site_id / FOLDER
    (folder / "records").mkdir(parents=True, exist_ok=True)
    done = {p.stem.split("_", 1)[1] for p in (folder / "records").glob("*.json")}
    params = hashlib.sha256(json.dumps({"card": card_hash(card), "grid": grid.key()},
                                       sort_keys=True).encode()).hexdigest()  # fmt: skip
    commit, created = head(), datetime.now(UTC).isoformat(timespec="seconds")
    minimum = int(card["minWaterPixels"])
    recorded: list[str] = []
    for acq in acqs:
        if acq.key in done:
            continue
        row = variables.thermal_window(acq, reader, grid, window, s.reach.estimate_station)
        if row["water_px"] < minimum or not math.isfinite(row["st_k"]):
            continue
        rec = contract.seal(contract.ThermalRecordV1.model_validate({
            "reachId": site_id,
            "date": imagery_local_date(acq.datetime, s.quality.timezone),
            "datetimeUtc": acq.datetime.astimezone(UTC).isoformat(timespec="seconds"),
            "sceneId": f"{site_id}:{acq.key}", "platform": acq.platform,
            "window": {"pixels": row["window_px"], "waterPixels": row["water_px"],
                       "surfaceTemperatureK": row["st_k"]},
            "estimate": estimate(card, row["st_k"]),
            "provenance": {"stacItems": [{"id": sc.item_id, "url": f"{ITEM_URL}{sc.item_id}"}
                                         for sc in acq.scenes],
                           "codeCommit": commit, "processingParamsSha256": params},
        }))  # fmt: skip
        file = f"records/{rec.date}_{acq.key}.json"
        (folder / file).write_text(rec.model_dump_json(indent=2, by_alias=True) + "\n",
                                   encoding="utf-8", newline="\n")  # fmt: skip
        _append(folder / "ledger.jsonl", rec, file, created)
        recorded.append(file)
        log.info("%s: recorded %s", site_id, file)
    write_series(folder)
    check_rows = gauge_check(root, cfg, site_id, folder, http)
    return {"passes": len(acqs), "recorded": len(recorded), "checked": check_rows}


def imagery_local_date(when: datetime, timezone: str) -> str:
    """A pass's local date in the reach's time zone.

    Args:
        when: The pass (aware).
        timezone: IANA name.

    Returns:
        ``YYYY-MM-DD``.
    """
    from zoneinfo import ZoneInfo

    return when.astimezone(ZoneInfo(timezone)).date().isoformat()


def write_series(folder: Path) -> None:
    """``series.json``: every temperature record, by date, trimmed for a chart.

    Args:
        folder: The reach's ``thermal/`` folder.
    """
    rows = []
    for path in sorted((folder / "records").glob("*.json")):
        rec = contract.ThermalRecordV1.model_validate_json(path.read_text(encoding="utf-8"))
        data = rec.model_dump(mode="json", by_alias=True)
        rows.append({"date": rec.date, "sceneId": rec.scene_id,
                     "file": path.relative_to(folder).as_posix(),
                     "recordSha256": rec.record_sha256, "platform": rec.platform,
                     "waterPixels": rec.window.water_pixels,
                     "estimate": data["estimate"]})  # fmt: skip
    rows.sort(key=lambda r: (r["date"], r["sceneId"]))
    (folder / "series.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8",
                                        newline="\n")  # fmt: skip


def gauge_check(root: Path, cfg: ReachConfig, site_id: str, folder: Path,
                http: httpx.Client | None) -> int:  # fmt: skip
    """The gauge's water temperature at each recorded pass (report-only; ``thermal/checks.csv``).

    Args:
        root: Repository root.
        cfg: Reach settings.
        site_id: The reach.
        folder: The reach's ``thermal/`` folder.
        http: HTTP client (injectable).

    Returns:
        Rows written.
    """
    quality = load_quality_config(root / cfg.quality_config)
    u = quality.usgs
    card = json.loads(card_path(root, site_id).read_text(encoding="utf-8"))
    # A card validated at another gauge is checked there (v7.1, C: Belle Chasse at Baton Rouge).
    station = str(card.get("validationSite") or cfg.reach(site_id).estimate_station)
    client = http or httpx.Client(timeout=120, follow_redirects=True)
    rows = []
    for path in sorted((folder / "records").glob("*.json")):
        rec = contract.ThermalRecordV1.model_validate_json(path.read_text(encoding="utf-8"))
        when = datetime.fromisoformat(rec.datetime_utc)
        value, approval = _gauge(client, u.api, station, "00010", when,
                                 u.overpass_median_minutes, u.overpass_nearest_minutes,
                                 u.exclude_qualified)  # fmt: skip
        rows.append({"date": rec.date, "sceneId": rec.scene_id,
                     "datetimeUtc": when.isoformat(timespec="seconds"),
                     "estimate": rec.estimate.value if rec.estimate.value is not None else math.nan,
                     "gauge": station,
                     "value": round(value, 2) if math.isfinite(value) else value,
                     "approval": approval})  # fmt: skip
    _write_csv(folder / "checks.csv", rows, CHECK_COLUMNS)
    return len(rows)


def context(cfg: ReachConfig, root: Path, site_id: str, http: httpx.Client | None = None
            ) -> int:  # fmt: skip
    """The gauge's own readings at each Sentinel-2 pass of the reach's records.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        http: HTTP client (injectable).

    Returns:
        Rows written to ``checks/context.csv``.
    """
    quality = load_quality_config(root / cfg.quality_config)
    u = quality.usgs
    reach = cfg.reach(site_id)
    folder = root / cfg.out / site_id
    keys = {p.stem.split("_", 1)[1]: p.stem.split("_", 1)[0]
            for p in (folder / "records").glob("*.json")}  # fmt: skip
    if not keys:
        return 0
    days = sorted(date.fromisoformat(d) for d in keys.values())
    from climate_pipeline.screening.config import load_site

    site = load_site(reach.site_path(root))
    west, south, east, north = site.aoi_bbox
    acqs, _ = imagery.search(quality, "earth-search", (west, south, east, north),
                             days[0] - timedelta(days=1), days[-1] + timedelta(days=1))  # fmt: skip
    times = {a.key: a.datetime for a in acqs if a.key in keys}
    client = http or httpx.Client(timeout=120, follow_redirects=True)
    wanted = [p for p in CONTEXT if p in parameters_at(client, u.api, reach.estimate_station)]
    rows = []
    for parameter in wanted:
        name, unit, factor = CONTEXT[parameter]
        spans = [
            (
                t - timedelta(minutes=u.overpass_nearest_minutes),
                t + timedelta(minutes=u.overpass_nearest_minutes),
            )
            for t in times.values()
        ]
        readings: list[usgs.Reading] = []
        for k in range(0, len(spans), variables.BATCH):
            found, _ = usgs.continuous_many(client, u.api, reach.estimate_station, parameter,
                                            spans[k : k + variables.BATCH])  # fmt: skip
            readings += found
        for key, when in sorted(times.items(), key=lambda kv: kv[1]):
            for status in APPROVALS:
                value, _, _ = usgs.overpass_value(readings, when, u.overpass_median_minutes,
                                                  u.overpass_nearest_minutes, status,
                                                  u.exclude_qualified)  # fmt: skip
                if math.isfinite(value):
                    rows.append({"key": key, "date": keys[key],
                                 "datetimeUtc": when.astimezone(UTC).isoformat(timespec="seconds"),
                                 "parameter": parameter, "name": name,
                                 "value": round(value * factor, 3), "unit": unit,
                                 "approval": status})  # fmt: skip
                    break
    rows.sort(key=lambda r: (r["datetimeUtc"], r["parameter"]))
    _write_csv(folder / "checks" / "context.csv", rows, CONTEXT_COLUMNS)
    return len(rows)


def parameters_at(client: httpx.Client, api: str, station: str) -> set[str]:
    """The parameters a gauge measures continuously (its time-series metadata).

    Args:
        client: HTTP client.
        api: OGC API root.
        station: E.g. ``USGS-06805500``.

    Returns:
        Parameter codes.
    """
    rows, _ = usgs.features(client, f"{api}/collections/time-series-metadata/items",
                            {"monitoring_location_id": station, "limit": "200", "f": "json",
                             "skipGeometry": "true"})  # fmt: skip
    return {str(r.get("properties", {}).get("parameter_code", "")) for r in rows}
