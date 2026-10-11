"""The network side of the water-quality validation v2: the Colombian station selection.

``fetch_stations`` reads metadata only (no sample value): the water-quality points of each listed
stream with a sample since the start date, their catalogue coordinates, the discharge and level
files that can judge flow stability, and the imagery that decides each point's main channel and
width (D15's rule, through D15's own functions and settings, which a test checks are unchanged).
Its ``stations.csv`` is committed before any value is fetched. Every fetch stops when free disk
space falls under the budget.
"""

from __future__ import annotations

import hashlib
import logging
import math
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx

from climate_pipeline.calibration import extract, sources
from climate_pipeline.calibration.config import load_calibration_config
from climate_pipeline.calibration.fetching import _csv, _reader, error_rows
from climate_pipeline.calibration.stations import (
    Candidate,
    bucket_listing,
    candidates,
    label_files,
    normalize,
    number,
    point_code,
    quality_points,
    read_catalog,
    station_id,
)
from climate_pipeline.quality.config import QualityConfig
from climate_pipeline.screening.config import load_screening_config

log = logging.getLogger(__name__)
STATION_COLUMNS = (
    "station_id", "stream", "name", "code", "quality_point", "lon", "lat", "coordinates_from",
    "swapped", "samples_turbidity", "samples_tss", "first_sample", "last_sample", "flow_code",
    "flow_label", "flow_km", "mask_source", "snap_m", "width_m", "selected", "reason",
    "scl_selected", "scl_reason", "scl_width_m",
)  # fmt: skip


class DiskBudgetError(RuntimeError):
    """Free disk space fell under the budget."""


def check_disk(path: Path, keep_free_gb: float) -> float:
    """Free space on the disk that holds ``path``, refusing to go on under the budget.

    Args:
        path: Any existing path on the disk.
        keep_free_gb: The free space every fetch keeps, in GB.

    Returns:
        The free space, in GB.

    Raises:
        DiskBudgetError: When less is free.
    """
    free = shutil.disk_usage(path).free / 1e9
    if free < keep_free_gb:
        raise DiskBudgetError(f"{free:.1f} GB free, {keep_free_gb:g} GB must stay free")
    return free


def distance_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance.

    Args:
        lon1: Longitude of the first point.
        lat1: Latitude of the first point.
        lon2: Longitude of the second point.
        lat2: Latitude of the second point.

    Returns:
        Kilometres.
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))


@dataclass(frozen=True)
class FlowLink:
    """The series that judges flow stability at a point."""

    code: str = ""  # bucket code (10 digits); empty: none
    label: str = ""  # Q_MEDIA_D or NV_MEDIA_D
    km: float = math.nan


def flow_link(
    cand: Candidate,
    catalog: Sequence[Mapping[str, str]],
    files: Mapping[str, Mapping[str, int]],
    labels: Sequence[str],
    max_km: float,
) -> FlowLink:
    """The point's own discharge (else level) series, else the nearest one on its stream.

    Args:
        cand: The candidate (a water-quality point).
        catalog: Catalogue rows of the point's stream.
        files: Bucket label -> (code -> bytes), labels in order of preference.
        labels: E.g. ``("Q_MEDIA_D", "NV_MEDIA_D")``.
        max_km: Largest distance to a station on the same stream.

    Returns:
        The link (empty when no station qualifies).
    """
    own = point_code(cand.quality_point)
    if own:
        for label in labels:
            for code in files.get(label, {}):
                if station_id(code) == station_id(own):
                    return FlowLink(code, label, 0.0)
    best: tuple[float, int, str, str] | None = None
    for row in catalog:
        code = str(row.get("Codigo", ""))
        lon, lat = number(row.get("Longitud")), number(row.get("Latitud"))
        if not (math.isfinite(lon) and math.isfinite(lat)) or not math.isfinite(cand.lon):
            continue
        km = distance_km(cand.lon, cand.lat, lon, lat)
        for rank, label in enumerate(labels):
            if code in files.get(label, {}) and km <= max_km:
                key = (km, rank, code, label)
                if best is None or key < best:
                    best = key
    return FlowLink(best[2], best[3], round(best[0], 3)) if best else FlowLink()


def fetch_stations(
    cfg: QualityConfig, root: Path, cache: Path, workers: int, http: httpx.Client | None = None
) -> list[dict[str, object]]:
    """Select the Colombian stations from metadata and imagery; snapshot the metadata and the list.

    Args:
        cfg: The v2 settings.
        root: Repository root.
        cache: Cache folder (the station grids are D15's, so its reads are reused).
        workers: Parallel reads.
        http: HTTP client (injectable).

    Returns:
        The station rows (selected and not).
    """
    st = cfg.stations
    d15 = load_calibration_config(root / cfg.calibration_config)
    screening = load_screening_config(root / cfg.screening_config)
    client = http or httpx.Client(timeout=400, follow_redirects=True)
    inputs = root / cfg.outputs.inputs
    rec = sources.Recorder(inputs)
    check_disk(root, cfg.budgets.keep_free_gb)
    variables = list(st.quality_variables)
    catalog_url = f"{st.bucket}/{st.catalog}"
    catalog_body = sources.get(client, catalog_url)
    catalog = read_catalog(catalog_body)
    on_streams = [r for r in catalog if normalize(r.get("Corriente", "")) in st.streams]
    rec.save("stations/catalog-streams.csv",
             _csv([dict(r) for r in on_streams], list(catalog[0]) if catalog else ["none"]),
             catalog_url, note=f"rows on the listed streams; full file {len(catalog_body)} B, "
             f"sha256 {hashlib.sha256(catalog_body).hexdigest()}")  # fmt: skip
    codes = {r.get("Codigo", "") for r in on_streams}
    files: dict[str, dict[str, int]] = {}
    listing_rows = []
    for label in st.flow_labels:
        listing = bucket_listing(client, st.bucket, f"observaciones/historicos/csv/{label}/")
        files[label] = {c: s for c, s in label_files(listing, label).items() if c in codes}
        listing_rows += [{"label": label, "code": c, "bytes": s} for c, s in files[label].items()]
    rec.save("stations/bucket-listing.csv", _csv(listing_rows, ("label", "code", "bytes")),
             f"{st.bucket}?list-type=2", note="flow files of the listed streams only")  # fmt: skip
    reader = _reader(d15, screening, cache)
    out: list[dict[str, object]] = []
    for stream in st.streams:
        rows, body = quality_points(client, st.quality_resource, variables,
                                    st.samples_since.isoformat(), stream)  # fmt: skip
        slug = stream.lower().replace(" ", "-")
        rec.save(f"stations/quality-points/{slug}.json", body, st.quality_resource,
                 note="metadata only")  # fmt: skip
        stream_catalog = [r for r in on_streams if normalize(r.get("Corriente", "")) == stream]
        for cand in candidates(rows, stream_catalog, {}, stream, variables):
            link = flow_link(cand, stream_catalog, files, st.flow_labels, st.flow_search_km)
            row: dict[str, object] = {
                "station_id": cand.station_id, "stream": stream, "name": cand.name,
                "code": cand.code, "quality_point": cand.quality_point,
                "lon": round(cand.lon, 6), "lat": round(cand.lat, 6),
                "coordinates_from": cand.coordinates_from, "swapped": cand.swapped,
                "samples_turbidity": cand.sample_counts.get(variables[0], 0),
                "samples_tss": cand.sample_counts.get(variables[1], 0),
                "first_sample": cand.first_sample, "last_sample": cand.last_sample,
                "flow_code": link.code, "flow_label": link.label, "flow_km": link.km,
            }  # fmt: skip
            if not (math.isfinite(cand.lon) and math.isfinite(cand.lat)):
                out.append({**row, "selected": False, "reason": "no coordinates"})
                continue
            check_disk(root, cfg.budgets.keep_free_gb)
            bbox = extract.bbox_around(cand.lon, cand.lat, st.grid_half_size_m)
            acqs = extract.search(d15, d15.imagery.primary, bbox, cfg.geometry_period.start,
                                  cfg.geometry_period.end)  # fmt: skip
            geo = extract.station_geometry(cand, acqs, reader, d15, screening, workers)
            log.info("%s %s: %s %s", stream, cand.station_id, geo.selected,
                     geo.reason or f"{geo.width_m:.0f} m")  # fmt: skip
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
    (inputs / "fetch-manifest-stations.csv").write_text(rec.manifest(), encoding="utf-8",
                                                         newline="\n")  # fmt: skip
    return out
