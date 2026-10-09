"""The network side of the calibration validation: station selection, then the value snapshots.

``fetch_stations`` reads metadata only (no sample value) and the imagery that decides each
station's main channel and width; its ``stations.csv`` is committed before any value is fetched.
``fetch_values`` reads the frozen list and snapshots every value the analysis needs. Both record
each input in a fetch manifest; imagery read errors are written out and must be zero.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from climate_pipeline.calibration import extract, sources
from climate_pipeline.calibration.config import CalibrationConfig
from climate_pipeline.calibration.matchups import samples_from_series, samples_from_soda
from climate_pipeline.calibration.stations import (
    Candidate,
    bucket_listing,
    candidates,
    label_files,
    normalize,
    quality_points,
    read_catalog,
)
from climate_pipeline.contract.observation import item_json_url, item_meta_from_json
from climate_pipeline.screening.config import ScreeningConfig, load_screening_config, load_site
from climate_pipeline.screening.rio import AcquisitionReader, sample_points
from climate_pipeline.screening.stac import Acquisition, make_source
from climate_pipeline.validation.grid import read_grid

log = logging.getLogger(__name__)
STATION_COLUMNS = (
    "station_id", "name", "code", "quality_point", "lon", "lat", "coordinates_from", "swapped",
    "samples_turbidity", "samples_tss", "first_sample", "last_sample", "files", "mask_source",
    "snap_m", "width_m", "selected", "reason", "roles", "scl_selected", "scl_reason",
    "scl_width_m",
)  # fmt: skip


@dataclass(frozen=True)
class CalibrationPaths:
    """Where the calibration reads and writes."""

    root: Path
    config: Path
    cache: Path

    def at(self, relative: str) -> Path:
        """A path from the repository root.

        Args:
            relative: As the settings write it.

        Returns:
            The absolute path.
        """
        return self.root / relative


def _csv(rows: Sequence[Mapping[str, object]], columns: Sequence[str]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row.get(c)) for c in columns])
    return out.getvalue().encode("utf-8")


def _cell(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return "" if math.isnan(value) else repr(round(value, 6))
    return "" if value is None else str(value)


def _reader(cfg: CalibrationConfig, screening: ScreeningConfig, cache: Path) -> AcquisitionReader:
    source = make_source(screening.stac.source, screening.stac.sources, screening.stac.page_size)
    return AcquisitionReader(source, cache / "calibration-bands", tuple(cfg.imagery.assets))


def roles(cand: Candidate, cfg: CalibrationConfig, reach_bbox: tuple[float, ...]) -> list[str]:
    """What a station is used for.

    Samples, ``cm_d``, flow (discharge or level), sediment transport, and whether it lies on
    the reach.

    Args:
        cand: The candidate.
        cfg: Settings.
        reach_bbox: The reach's site box.

    Returns:
        Role names.
    """
    out = []
    if cand.quality_point:
        out.append("samples")
    if "CM_D" in cand.files:
        out.append("cm_d")
    if {"Q_MEDIA_D", "NV_MEDIA_D"} & set(cand.files):
        out.append("flow")
    if set(cfg.stations.monthly_labels) & set(cand.files):
        out.append("transport")
    west, south, east, north = reach_bbox
    if west <= cand.lon <= east and south <= cand.lat <= north:
        out.append("reach")
    return out


def fetch_stations(
    cfg: CalibrationConfig, paths: CalibrationPaths, workers: int, http: httpx.Client | None = None
) -> list[dict[str, object]]:
    """Select the stations from metadata and imagery; snapshot the metadata and the list.

    Args:
        cfg: Settings.
        paths: Paths.
        workers: Parallel reads.
        http: HTTP client (injectable).

    Returns:
        The station rows (selected and not).
    """
    st = cfg.stations
    screening = load_screening_config(paths.at(cfg.screening_config))
    client = http or httpx.Client(timeout=400, follow_redirects=True)
    rec = sources.Recorder(paths.at(cfg.outputs.inputs))
    variables = list(st.quality_variables)
    rows, body = quality_points(client, st.quality_resource, variables,
                                st.samples_since.isoformat(), st.stream)  # fmt: skip
    rec.save("stations/quality-points.json", body, st.quality_resource, note="metadata only")
    catalog_url = f"{st.bucket}/{st.catalog}"
    catalog_body = sources.get(client, catalog_url)
    catalog = read_catalog(catalog_body)
    stream_rows = [r for r in catalog if normalize(r.get("Corriente", "")) == st.stream]
    rec.save(
        "stations/catalog-magdalena.csv",
        _csv([dict(r) for r in stream_rows], list(catalog[0]) if catalog else ["none"]),
        catalog_url,
        note=f"rows on {st.stream}; full file {len(catalog_body)} B, sha256 "
        f"{__import__('hashlib').sha256(catalog_body).hexdigest()}",
    )
    codes = {r.get("Codigo", "") for r in stream_rows}
    files: dict[str, dict[str, int]] = {}
    listing_rows = []
    for label in (*st.daily_labels, *st.monthly_labels):
        listing = bucket_listing(client, st.bucket, f"observaciones/historicos/csv/{label}/")
        files[label] = {c: s for c, s in label_files(listing, label).items() if c in codes}
        listing_rows += [{"label": label, "code": c, "bytes": s} for c, s in files[label].items()]
    rec.save("stations/bucket-listing.csv", _csv(listing_rows, ("label", "code", "bytes")),
             f"{st.bucket}?list-type=2", note="keys of the stream's stations only")  # fmt: skip
    site = load_site(paths.at(f"pipeline/sites/{cfg.climate.reach}.yaml"))
    reader = _reader(cfg, screening, paths.cache)
    out = []
    for cand in candidates(rows, stream_rows, files, st.stream, variables):
        row: dict[str, object] = {
            "station_id": cand.station_id, "name": cand.name, "code": cand.code,
            "quality_point": cand.quality_point, "lon": round(cand.lon, 6),
            "lat": round(cand.lat, 6), "coordinates_from": cand.coordinates_from,
            "swapped": cand.swapped, "samples_turbidity": cand.sample_counts.get(variables[0], 0),
            "samples_tss": cand.sample_counts.get(variables[1], 0) if len(variables) > 1 else 0,
            "first_sample": cand.first_sample, "last_sample": cand.last_sample,
            "files": " ".join(f"{k}:{v}" for k, v in sorted(cand.files.items())),
            "roles": " ".join(roles(cand, cfg, site.aoi_bbox)),
        }  # fmt: skip
        if not (math.isfinite(cand.lon) and math.isfinite(cand.lat)):
            out.append({**row, "selected": False, "reason": "no coordinates"})
            continue
        bbox = extract.bbox_around(cand.lon, cand.lat, st.grid_half_size_m)
        acqs = extract.search(cfg, cfg.imagery.primary, bbox, cfg.geometry_period.start,
                              cfg.geometry_period.end)  # fmt: skip
        geo = extract.station_geometry(cand, acqs, reader, cfg, screening, workers)
        log.info("%s: %s %s", cand.station_id, geo.selected, geo.reason or f"{geo.width_m:.0f} m")
        out.append({
            **row, "mask_source": geo.mask_source, "snap_m": round(geo.snap_m, 1),
            "width_m": round(geo.width_m, 1), "selected": geo.selected, "reason": geo.reason,
            "scl_selected": geo.scl_selected, "scl_reason": geo.scl_reason,
            "scl_width_m": round(geo.scl_width_m, 1),
        })  # fmt: skip
    rec.save("stations/stations.csv", _csv(out, STATION_COLUMNS), "derived",
             note="the frozen selection")  # fmt: skip
    rec.save("stations/read-errors.csv", _csv(error_rows(reader.errors), ("kind", "error")),
             "derived")  # fmt: skip
    (paths.at(cfg.outputs.inputs) / "fetch-manifest-stations.csv").write_text(
        rec.manifest(), encoding="utf-8", newline="\n"
    )
    return out


def error_kind(error: str) -> str:
    """``permanent`` for an asset in a non-public bucket (deviation 3), else ``transient``.

    Args:
        error: A reader error message.

    Returns:
        The kind.
    """
    return "permanent" if "/vsis3/" in error else "transient"


def error_rows(errors: Sequence[str]) -> list[dict[str, object]]:
    """Read errors with their kind, sorted.

    Args:
        errors: Reader error messages.

    Returns:
        Rows of ``kind`` and ``error``.
    """
    return [{"kind": error_kind(e), "error": e} for e in sorted(set(errors))]


def read_stations(path: Path) -> list[dict[str, str]]:
    """The frozen station list.

    Args:
        path: ``stations/stations.csv``.

    Returns:
        Rows as strings.
    """
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def candidate_of(row: dict[str, str]) -> Candidate:
    """Rebuild a candidate from its frozen row.

    Args:
        row: A ``stations.csv`` row.

    Returns:
        The candidate.
    """
    files = dict(item.split(":") for item in row["files"].split()) if row["files"] else {}
    return Candidate(
        row["station_id"], row["name"], float(row["lon"]), float(row["lat"]),
        row["coordinates_from"], row["swapped"] == "true", row["code"], row["quality_point"],
        files={k: int(v) for k, v in files.items()},
    )  # fmt: skip


def fetch_values(
    cfg: CalibrationConfig,
    paths: CalibrationPaths,
    workers: int,
    http: httpx.Client | None = None,
    chirps_reader: Callable[[str, list[tuple[float, float]]], list[float]] = sample_points,
) -> dict[str, int]:
    """Snapshot every value the analysis needs, for the frozen station list.

    Args:
        cfg: Settings.
        paths: Paths.
        workers: Parallel reads.
        http: HTTP client (injectable).
        chirps_reader: CHIRPS point reader (injectable).

    Returns:
        Counts: snapshots, failures, imagery read errors.
    """
    st = cfg.stations
    inputs = paths.at(cfg.outputs.inputs)
    stations = [r for r in read_stations(inputs / "stations" / "stations.csv")
                if r["selected"] == "true"]  # fmt: skip
    screening = load_screening_config(paths.at(cfg.screening_config))
    client = http or httpx.Client(timeout=400, follow_redirects=True)
    rec = sources.Recorder(inputs)
    period = (cfg.period.start - timedelta(days=31), cfg.period.end)

    # In-situ values.
    points = sorted({r["quality_point"] for r in stations if r["quality_point"]})
    samples_body = b"[]"
    if points:
        samples_body, url = sources.quality_samples(
            client, st.quality_resource, points, st.quality_variables, st.samples_since.isoformat()
        )
        rec.save("ideam/quality-samples.json", samples_body, url)
    series: dict[tuple[str, str], str] = {}
    for row in stations:
        for label in (*st.daily_labels, *st.monthly_labels):
            if f"{label}:" not in row["files"]:
                continue
            key = f"observaciones/historicos/csv/{label}/{row['code']}-{label}.csv"
            url = f"{st.bucket}/{key}"
            try:
                full = sources.get(client, url)
            except httpx.HTTPError as error:
                rec.fail(url, error)
                continue
            subset = sources.period_lines(full, *period)
            rec.save(f"ideam/{label}/{row['code']}-{label}.csv", subset, url,
                     note=f"lines in {period[0]}..{period[1]}; full file {len(full)} B, sha256 "
                     f"{__import__('hashlib').sha256(full).hexdigest()}")  # fmt: skip
            series[(row["station_id"], label)] = subset.decode("utf-8", errors="replace")

    # Rain, ENSO, coefficients.
    grid = read_grid(paths.at(cfg.climate.rain_grid))
    for point_id, lon, lat in grid:
        try:
            body, url = sources.open_meteo_daily(client, cfg.climate.open_meteo, lon, lat,
                                                 *period)  # fmt: skip
            rec.save(f"rain/open-meteo/{point_id}.json", body, url)
        except httpx.HTTPError as error:
            rec.fail(cfg.climate.open_meteo, f"{point_id}: {error}")
    chirps_rows, failed = sources.chirps_days(cfg.climate.chirps_template, grid, *period,
                                              chirps_reader, workers)  # fmt: skip
    rec.save("rain/chirps-daily.csv", _csv(chirps_rows, ["date", *[p[0] for p in grid]]),
             cfg.climate.chirps_template, note=f"{len(failed)} days unreadable")  # fmt: skip
    try:
        rec.save("climate/oni.ascii.txt", sources.get(client, cfg.climate.enso.oni_url),
                 cfg.climate.enso.oni_url)  # fmt: skip
    except httpx.HTTPError as error:
        rec.fail(cfg.climate.enso.oni_url, error)
    for path in sources.ACOLITE_FILES:
        url = sources.acolite_file_url(path)
        try:
            rec.save(f"coefficients/{Path(path).name}", sources.get(client, url), url,
                     note=f"ACOLITE commit {sources.ACOLITE_COMMIT}")  # fmt: skip
        except httpx.HTTPError as error:
            rec.fail(url, error)

    # Reach items for the observation records.
    case_path = paths.root / "docs/magdalena-validation/magdalena.sample.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    ids = sorted({i for s in case["ui"]["scenes"] if not s["excluded"] for i in s["stacItemIds"]})
    item_rows = []
    for item_id in ids:
        url = item_json_url(item_id)
        try:
            body = sources.get(client, url)
        except httpx.HTTPError as error:
            rec.fail(url, error)
            continue
        meta = item_meta_from_json(url, body, datetime.now(UTC).isoformat(timespec="seconds"))
        item_rows.append({"id": item_id, "url": url, "sha256": meta.sha256,
                          "retrieved_utc": meta.retrieved_utc,
                          "boa_offset_applied": meta.boa_offset_applied,
                          "processing_baseline": meta.processing_baseline})  # fmt: skip
    rec.save("reach/items.csv", _csv(item_rows, ("id", "url", "sha256", "retrieved_utc",
                                                 "boa_offset_applied", "processing_baseline")),
             "derived", note="SHA-256 of each STAC item JSON")  # fmt: skip

    # Imagery.
    soda = json.loads(samples_body)
    point_station = {r["quality_point"]: r["station_id"] for r in stations if r["quality_point"]}
    target_of = {t.variable: t.id for t in cfg.targets if t.variable}
    sample_days: dict[str, set[date]] = {}
    for s in samples_from_soda(soda, point_station, target_of):
        sample_days.setdefault(s.station, set()).add(s.day)
    cm_days: dict[str, set[date]] = {}
    for (sid, label), text in series.items():
        if label == "CM_D":
            cm_days[sid] = {s.day for s in samples_from_series(text, sid, "cm_d")}
    reader = _reader(cfg, screening, paths.cache)
    windows_rows: dict[str, list[dict[str, object]]] = {cfg.imagery.primary: [],
                                                         cfg.imagery.sensitivity: []}  # fmt: skip
    extent_rows: list[dict[str, object]] = []
    items: list[dict[str, object]] = []
    for row in stations:
        cand = candidate_of(row)
        sid = cand.station_id
        bbox = extract.bbox_around(cand.lon, cand.lat, st.grid_half_size_m)
        geo_acqs = extract.search(cfg, cfg.imagery.primary, bbox, cfg.geometry_period.start,
                                  cfg.geometry_period.end)  # fmt: skip
        geo = extract.station_geometry(cand, geo_acqs, reader, cfg, screening, workers)
        if not geo.selected:
            log.warning("%s no longer selected: %s", sid, geo.reason)
            continue
        wins = extract.station_windows(geo, cfg)
        acqs = extract.search(cfg, cfg.imagery.primary, bbox, cfg.period.start, cfg.period.end)
        days = sample_days.get(sid, set())
        everything = "cm_d" in row["roles"] or "reach" in row["roles"]
        near = cfg.matchups.sensitivity_days
        wanted = [a for a in acqs if everything or _near(a, cfg, days, near)]
        windows_rows[cfg.imagery.primary] += _measure(wanted, reader, wins, cfg, screening, sid,
                                                      cfg.imagery.primary, workers)  # fmt: skip
        items.append(_items(sid, cfg.imagery.primary, "windows", wanted))
        if "flow" in row["roles"]:
            extent_rows += _extents(acqs, reader, wins, cfg, screening, sid, workers)
            items.append(_items(sid, cfg.imagery.primary, "extent", acqs))
        c1 = extract.search(cfg, cfg.imagery.sensitivity, bbox, cfg.period.start, cfg.period.end)
        c1_wanted = [
            a for a in c1
            if _near(a, cfg, days, cfg.matchups.primary_days)
            or extract.local_date(a, cfg.timezone) in cm_days.get(sid, set())
        ]  # fmt: skip
        windows_rows[cfg.imagery.sensitivity] += _measure(
            c1_wanted, reader, wins, cfg, screening, sid, cfg.imagery.sensitivity, workers
        )
        items.append(_items(sid, cfg.imagery.sensitivity, "windows", c1_wanted))
    for collection, rows in windows_rows.items():
        rec.save(f"imagery/windows-{collection}.csv", _csv(rows, WINDOW_COLUMNS), cfg.imagery.url,
                 note="station-window statistics and band medians")  # fmt: skip
    rec.save("imagery/extents.csv", _csv(extent_rows, EXTENT_COLUMNS), cfg.imagery.url,
             note="water extent in the 2 km disk")  # fmt: skip
    rec.save(
        "imagery/items.csv",
        _csv(items, ("station", "collection", "purpose", "acquisitions", "item_ids_sha256")),
        "derived",
    )
    errors = error_rows(reader.errors)
    rec.save("imagery/read-errors.csv", _csv(errors, ("kind", "error")), "derived")
    (inputs / "fetch-manifest.csv").write_text(rec.manifest(), encoding="utf-8", newline="\n")
    return {
        "snapshots": len(rec.records),
        "failures": len(rec.failures),
        "read_errors": sum(1 for e in errors if e["kind"] == "transient"),
        "permanent_read_errors": sum(1 for e in errors if e["kind"] == "permanent"),
    }


WINDOW_COLUMNS = (
    "station", "collection", "key", "datetime_utc", "local_date", "family", "window",
    "window_px", "data_px", "valid_px", "contamination", "glint_share", "b11_median", "b11_ok",
    "ndti_px_median", *extract.BAND_ORDER, "bands_read",
)  # fmt: skip
EXTENT_COLUMNS = ("station", "key", "datetime_utc", "local_date", "family", "valid_fraction",
                  "water_px", "extent_km2", "b11_ok", "bands_read")  # fmt: skip


def _near(acq: Acquisition, cfg: CalibrationConfig, days: set[date], max_days: int) -> bool:
    day = extract.local_date(acq, cfg.timezone)
    return any(abs((day - d).days) <= max_days for d in days)


def _items(
    station: str, collection: str, purpose: str, acqs: Sequence[Acquisition]
) -> dict[str, object]:
    from climate_pipeline.screening.stac import evidence_hash

    return {"station": station, "collection": collection, "purpose": purpose,
            "acquisitions": len(acqs), "item_ids_sha256": evidence_hash(acqs)}  # fmt: skip


def _measure(
    acqs: Sequence[Acquisition],
    reader: AcquisitionReader,
    wins: extract.Windows,
    cfg: CalibrationConfig,
    screening: ScreeningConfig,
    station: str,
    collection: str,
    workers: int,
) -> list[dict[str, object]]:
    def one(acq: Acquisition) -> list[dict[str, object]]:
        stats = extract.measure_window(acq, reader, wins, ("300m", "1000m"), cfg, screening)
        base = {
            "station": station, "collection": collection, "key": acq.key,
            "datetime_utc": acq.datetime.astimezone(UTC).isoformat(timespec="seconds"),
            "local_date": extract.local_date(acq, cfg.timezone).isoformat(),
            "family": extract.family(acq),
        }  # fmt: skip
        return [{**base, "window": name, **values} for name, values in stats.items()]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return [r for rows in pool.map(one, acqs) for r in rows]


def _extents(
    acqs: Sequence[Acquisition],
    reader: AcquisitionReader,
    wins: extract.Windows,
    cfg: CalibrationConfig,
    screening: ScreeningConfig,
    station: str,
    workers: int,
) -> list[dict[str, object]]:
    def one(acq: Acquisition) -> dict[str, object]:
        return {
            "station": station, "key": acq.key,
            "datetime_utc": acq.datetime.astimezone(UTC).isoformat(timespec="seconds"),
            "local_date": extract.local_date(acq, cfg.timezone).isoformat(),
            "family": extract.family(acq),
            **extract.measure_extent(acq, reader, wins, screening,
                                     cfg.climate.width.valid_fraction_min),
        }  # fmt: skip

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, acqs))
