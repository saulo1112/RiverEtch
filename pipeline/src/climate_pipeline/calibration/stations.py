"""Station selection from metadata only: candidates, main channel, snap and width.

Candidates are water-quality points (datos.gov.co ``62gv-3857``) on the Magdalena with a sample
since the start date, plus IDEAM catalogue stations on the Magdalena that have a daily discharge,
level or sediment-concentration file in IDEAM's public bucket. No value is read here: only names,
codes, coordinates, sample counts, date ranges and file listings. A station is selected when it
snaps to a main channel at least the minimum width wide (pure functions below; the water
frequency comes from :mod:`climate_pipeline.calibration.extract`).
"""

from __future__ import annotations

import csv
import io
import math
import re
import unicodedata
import xml.etree.ElementTree as ElementTree
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
import numpy as np
from numpy.typing import NDArray

from climate_pipeline.screening.mask import component, erode

BoolArray = NDArray[np.bool_]
S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


def normalize(text: object) -> str:
    """Upper case without accents or surrounding spaces (``Río  Magdalena`` -> ``RIO  MAGDALENA``).

    Args:
        text: Any value.

    Returns:
        The normalized text.
    """
    decomposed = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip().upper()


def station_id(code: str) -> str:
    """A station id that matches across sources: the IDEAM code without leading zeros.

    Args:
        code: ``0023187010`` (bucket) or ``23187010`` (water-quality point).

    Returns:
        ``23187010``.
    """
    return code.lstrip("0") or "0"


def point_code(name: str) -> str | None:
    """The IDEAM code a water-quality point name carries in brackets, if any.

    Args:
        name: E.g. ``MAGDALENA_SAN_PUERTO WILCHES_PTO.WILCHES [23187010]``.

    Returns:
        ``23187010``, or None.
    """
    match = re.search(r"\[(\d{6,10})\]", name)
    return match.group(1) if match else None


def slug(name: str) -> str:
    """A file-safe id for a point without an IDEAM code.

    Args:
        name: The point name.

    Returns:
        Lower-case words joined by hyphens.
    """
    return re.sub(r"[^a-z0-9]+", "-", normalize(name).lower()).strip("-")


def number(text: object) -> float:
    """A float from text with either decimal separator (NaN when not a number).

    Args:
        text: E.g. ``7,3443888890``.

    Returns:
        The value.
    """
    try:
        return float(str(text).strip().replace(",", "."))
    except ValueError:
        return math.nan


def fix_lonlat(lon: float, lat: float) -> tuple[float, float, bool]:
    """Longitude and latitude for Colombia, swapping them when a source has them reversed.

    Args:
        lon: The value given as longitude.
        lat: The value given as latitude.

    Returns:
        ``(lon, lat, swapped)``.
    """

    def plausible(x: float, y: float) -> bool:
        return -82 <= x <= -66 and -5 <= y <= 14

    if plausible(lon, lat):
        return lon, lat, False
    if plausible(lat, lon):
        return lat, lon, True
    return lon, lat, False


@dataclass
class Candidate:
    """A station considered for selection (metadata only)."""

    station_id: str
    name: str
    lon: float
    lat: float
    coordinates_from: str  # "catalog" or "quality point"
    swapped: bool = False
    code: str = ""  # bucket code (10 digits), empty for points without one
    quality_point: str = ""
    sample_counts: dict[str, int] = field(default_factory=dict)
    first_sample: str = ""
    last_sample: str = ""
    files: dict[str, int] = field(default_factory=dict)  # bucket label -> bytes


def quality_points(
    http: httpx.Client, url: str, variables: Sequence[str], since: str, stream: str
) -> tuple[list[dict[str, Any]], bytes]:
    """Water-quality points on the stream, with sample counts and date ranges (no values).

    Args:
        http: HTTP client.
        url: The SODA resource (``62gv-3857``).
        variables: The observed properties counted.
        since: First sample date (ISO).
        stream: The normalized stream name (exact match).

    Returns:
        One row per point and variable, and the raw response body.
    """
    names = ", ".join(f"'{v}'" for v in variables)
    params = {
        "$select": "nombre_del_punto_de_monitoreo, corriente, latitud, longitud, "
        "propiedad_observada, count(*) as n, min(fecha) as first, max(fecha) as last",
        "$where": f"upper(corriente) like '%{stream}%' AND fecha >= '{since}' "
        f"AND propiedad_observada in ({names})",
        "$group": "nombre_del_punto_de_monitoreo, corriente, latitud, longitud, "
        "propiedad_observada",
        "$limit": "50000",
    }
    response = http.get(url, params=params)
    response.raise_for_status()
    rows = [r for r in response.json() if normalize(r.get("corriente", "")) == stream]
    return rows, response.content


def bucket_listing(http: httpx.Client, bucket: str, prefix: str) -> list[tuple[str, int]]:
    """Every key under a prefix of an S3-compatible public bucket, with its size.

    Args:
        http: HTTP client.
        bucket: Bucket URL.
        prefix: Key prefix.

    Returns:
        ``(key, bytes)`` pairs.
    """
    out: list[tuple[str, int]] = []
    token: str | None = None
    while True:
        params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            params["continuation-token"] = token
        response = http.get(bucket, params=params)
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        for item in root.iter(f"{S3_NS}Contents"):
            key = item.findtext(f"{S3_NS}Key") or ""
            out.append((key, int(item.findtext(f"{S3_NS}Size") or 0)))
        if (root.findtext(f"{S3_NS}IsTruncated") or "false").lower() != "true":
            return out
        token = root.findtext(f"{S3_NS}NextContinuationToken")


def label_files(listing: Iterable[tuple[str, int]], label: str) -> dict[str, int]:
    """Station code -> file size for one bucket variable (``.../<label>/<code>-<label>.csv``).

    Args:
        listing: Keys and sizes.
        label: E.g. ``CM_D``.

    Returns:
        Code -> bytes.
    """
    pattern = re.compile(rf"/{re.escape(label)}/(\d+)-{re.escape(label)}\.csv$")
    return {m.group(1): size for key, size in listing if (m := pattern.search(key))}


def read_catalog(body: bytes) -> list[dict[str, str]]:
    """IDEAM's station catalogue CSV (UTF-8, or Latin-1 when that fails).

    Args:
        body: The raw file.

    Returns:
        One dict per station.
    """
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = body.decode("latin-1")
    return list(csv.DictReader(io.StringIO(text)))


def candidates(
    point_rows: Sequence[Mapping[str, Any]],
    catalog: Sequence[Mapping[str, str]],
    files: Mapping[str, Mapping[str, int]],
    stream: str,
    variables: Sequence[str],
) -> list[Candidate]:
    """The union of water-quality points and catalogue stations with bucket files.

    Args:
        point_rows: :func:`quality_points` rows.
        catalog: :func:`read_catalog` rows.
        files: Bucket label -> (code -> bytes).
        stream: The normalized stream name.
        variables: The observed properties counted.

    Returns:
        Candidates sorted by id; catalogue coordinates win when the code matches.
    """
    by_code = {
        station_id(str(row.get("Codigo", ""))): row
        for row in catalog
        if normalize(row.get("Corriente", "")) == stream
    }
    out: dict[str, Candidate] = {}
    for row in point_rows:
        name = str(row["nombre_del_punto_de_monitoreo"])
        code = point_code(name)
        sid = station_id(code) if code else slug(name)
        lon, lat, swapped = fix_lonlat(number(row.get("longitud")), number(row.get("latitud")))
        cand = out.setdefault(
            sid, Candidate(sid, name, lon, lat, "quality point", swapped, quality_point=name)
        )
        variable = str(row["propiedad_observada"])
        if variable in variables:
            cand.sample_counts[variable] = cand.sample_counts.get(variable, 0) + int(row["n"])
        first, last = str(row["first"])[:10], str(row["last"])[:10]
        cand.first_sample = min(filter(None, (cand.first_sample, first)))
        cand.last_sample = max(cand.last_sample, last)
    for label, by in files.items():
        for code, size in by.items():
            sid = station_id(code)
            if sid not in by_code:
                continue
            row = by_code[sid]
            if sid not in out:
                out[sid] = Candidate(
                    sid, str(row.get("Nombre", sid)), math.nan, math.nan, "catalog"
                )
            out[sid].files[label] = size
            out[sid].code = code
    for sid, cand in out.items():
        if sid in by_code:
            row = by_code[sid]
            lon, lat, swapped = fix_lonlat(number(row.get("Longitud")), number(row.get("Latitud")))
            if math.isfinite(lon) and math.isfinite(lat):
                cand.lon, cand.lat, cand.swapped = lon, lat, swapped
                cand.coordinates_from = "catalog"
            cand.code = cand.code or str(row.get("Codigo", ""))
    return [out[k] for k in sorted(out)]


# ----------------------------------------------------------------------------------------------
# Main channel, snap and width (pure)
# ----------------------------------------------------------------------------------------------


def largest_component(mask: BoolArray) -> BoolArray:
    """The largest 4-connected region of a mask (empty when the mask is empty).

    Args:
        mask: Water pixels.

    Returns:
        The main channel.
    """
    remaining = mask.copy()
    best = np.zeros_like(mask)
    best_size = 0
    while remaining.any():
        seed = tuple(int(v) for v in np.argwhere(remaining)[0])
        region = component(remaining, (seed[0], seed[1]))
        size = int(region.sum())
        if size > best_size:
            best, best_size = region, size
        remaining &= ~region
    return best


def width_m(
    main: BoolArray, snapped: tuple[int, int], search_px: float, resolution: float
) -> float:
    """Twice the largest distance to land among main-channel pixels near the snapped point.

    Distances run between pixel centres. Land outside the grid is not seen, so a channel wider
    than the grid reads as the grid's limit.

    Args:
        main: The main channel.
        snapped: The snapped pixel.
        search_px: Radius around the snapped pixel, in pixels.
        resolution: Pixel size in meters.

    Returns:
        The width in meters.
    """
    r0, c0 = snapped
    rows, cols = np.nonzero(main)
    near = (rows - r0) ** 2 + (cols - c0) ** 2 <= search_px**2
    water = np.column_stack([rows[near], cols[near]]).astype(np.float64)
    land = np.argwhere(~main).astype(np.float64)
    if water.size == 0:
        return 0.0
    if land.size == 0:
        return float(2 * max(main.shape) * resolution)
    best = 0.0
    for start in range(0, len(water), 256):
        chunk = water[start : start + 256]
        d2 = ((chunk[:, None, :] - land[None, :, :]) ** 2).sum(axis=2).min(axis=1)
        best = max(best, float(np.sqrt(d2.max())))
    return 2 * best * resolution


def window_mask(
    main: BoolArray, snapped: tuple[int, int], radius_px: float, erosion_px: int
) -> BoolArray:
    """Main-channel pixels within a radius of the snapped point, after eroding the water mask.

    Args:
        main: The main channel.
        snapped: The snapped pixel.
        radius_px: Window radius in pixels.
        erosion_px: Erosion steps against land adjacency.

    Returns:
        The window.
    """
    rows, cols = np.indices(main.shape)
    disk = (rows - snapped[0]) ** 2 + (cols - snapped[1]) ** 2 <= radius_px**2
    return erode(main, erosion_px) & disk


def disk(shape: tuple[int, int], center: tuple[int, int], radius_px: float) -> BoolArray:
    """All pixels within a radius of a centre.

    Args:
        shape: Grid shape.
        center: Centre pixel.
        radius_px: Radius in pixels.

    Returns:
        The disk.
    """
    rows, cols = np.indices(shape)
    return np.asarray((rows - center[0]) ** 2 + (cols - center[1]) ** 2 <= radius_px**2)
