"""Stage 2c: the Level-1C scenes ACOLITE needs, and the L2A pixels it is measured over.

ACOLITE runs outside this package, in its own environment (``pipeline/acolite/``), on Level-1C
files the project owner downloads. This module lists the matchup scenes of the primary pairs in
priority order (training before hold-out, sampled targets before the daily one), each with the
Level-1C product of the tile that covers the station window. It also writes the L2A water pixels
of each scene, so ACOLITE's reflectances are measured over exactly the pixels the L2A medians
used and the two corrections are compared on the same water.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from climate_pipeline.calibration import extract
from climate_pipeline.calibration.config import CalibrationConfig
from climate_pipeline.calibration.fetching import (
    CalibrationPaths,
    _csv,
    _reader,
    candidate_of,
    read_stations,
)
from climate_pipeline.calibration.matchups import fittable, split
from climate_pipeline.calibration.run import Inputs, load_inputs, target_pairs
from climate_pipeline.screening.config import load_screening_config
from climate_pipeline.screening.stac import search_items

log = logging.getLogger(__name__)
L1C_COLLECTION = "sentinel-2-l1c"
SCENE_COLUMNS = (
    "priority", "station", "key", "datetime_utc", "local_date", "split", "targets",
    "l2a_water_px", "tile", "l1c_item", "l1c_product", "datatake",
)  # fmt: skip
SearchFn = Callable[[tuple[float, float, float, float], date], list[dict[str, Any]]]


@dataclass(frozen=True)
class SceneUse:
    """One matchup scene of one station, and what it is used for."""

    station: str
    key: str
    group: int  # 0 sampled training, 1 sampled hold-out, 2 daily training, 3 daily hold-out
    day: date
    targets: tuple[str, ...] = field(default_factory=tuple)

    @property
    def split(self) -> str:
        """``train`` or ``holdout``.

        Returns:
            The split of the scene's most important use.
        """
        return "train" if self.group % 2 == 0 else "holdout"


def scene_uses(cfg: CalibrationConfig, inputs: Inputs) -> list[SceneUse]:
    """The scenes of the primary pairs (L2A, 300 m window), most important first.

    Args:
        cfg: Settings.
        inputs: Parsed snapshots.

    Returns:
        One entry per station and acquisition, sorted by group, scene day and station.
    """
    best: dict[tuple[str, str], tuple[int, date]] = {}
    targets: dict[tuple[str, str], set[str]] = {}
    for t in cfg.targets:
        pairs = fittable(target_pairs(cfg, inputs, t.id, "l2a-300m"))
        _, train, holdout = split(pairs, cfg.matchups.holdout_share)
        base = 2 if t.kind == "daily" else 0
        for offset, chosen in ((0, train), (1, holdout)):
            for p in chosen:
                k = (p.station, p.scene_key)
                group = base + offset
                if k not in best or group < best[k][0]:
                    best[k] = (group, p.scene_day)
                targets.setdefault(k, set()).add(t.id)
    uses = [
        SceneUse(station, key, group, day, tuple(sorted(targets[(station, key)])))
        for (station, key), (group, day) in best.items()
    ]
    return sorted(uses, key=lambda u: (u.group, u.day, u.station, u.key))


def _inside(lon: float, lat: float, ring: Sequence[Sequence[float]]) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, [*ring[1:], ring[0]], strict=True):
        if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def covers(geometry: Mapping[str, Any], box: tuple[float, float, float, float]) -> bool:
    """Whether a GeoJSON (multi)polygon contains the four corners of a box.

    Args:
        geometry: The item's footprint.
        box: West, south, east, north.

    Returns:
        True when every corner lies in one of its polygons' outer rings.
    """
    w, s, e, n = box
    polygons = (
        [geometry["coordinates"]]
        if geometry.get("type") == "Polygon"
        else list(geometry.get("coordinates", []))
    )
    corners = ((w, s), (w, n), (e, s), (e, n))
    return any(all(_inside(x, y, poly[0]) for x, y in corners) for poly in polygons)


def l1c_item(
    items: Sequence[Mapping[str, Any]], key: str, box: tuple[float, float, float, float]
) -> Mapping[str, Any] | None:
    """The Level-1C item of an acquisition whose footprint covers the station window.

    Args:
        items: Level-1C items of that day over the window.
        key: The acquisition key (``sentinel-2b_2023-01-28_R025``).
        box: The window's box.

    Returns:
        The first covering item by tile, or None.
    """
    platform, _, orbit = key.split("_")
    matching = []
    for item in items:
        props = item.get("properties", {})
        product = str(props.get("s2:product_uri", ""))
        if props.get("platform") != platform or f"_{orbit}_" not in product:
            continue
        if covers(item.get("geometry", {}), box):
            matching.append(item)
    return min(matching, key=lambda i: str(i["id"])) if matching else None


def datatake(product: str) -> str:
    """The name prefix shared by every processing of the same Level-1C datatake.

    Copernicus Data Space serves the current processing (often reprocessed, with a newer
    baseline and generation time), so its name differs from Earth Search's after the sensing
    time; this prefix and the tile identify it.

    Args:
        product: E.g. ``S2B_MSIL1C_20230128T152639_N0509_R025_T18NXP_20230128T184739.SAFE``.

    Returns:
        E.g. ``S2B_MSIL1C_20230128T152639`` (empty when the name does not parse).
    """
    m = re.match(r"^(S2[ABC]_MSIL1C_\d{8}T\d{6})_N\d{4}_R\d{3}_T\d{2}[A-Z]{3}_", product)
    return m.group(1) if m else ""


def _windows_by_key(text: str) -> dict[tuple[str, str], dict[str, str]]:
    return {
        (r["station"], r["key"]): r
        for r in csv.DictReader(io.StringIO(text))
        if r["window"] == "300m"
    }


def acolite_list(
    cfg: CalibrationConfig,
    paths: CalibrationPaths,
    work: Path,
    workers: int,
    search_l1c: SearchFn | None = None,
) -> list[dict[str, object]]:
    """Write the Stage 2c scene list and the pixels ACOLITE is measured over.

    Args:
        cfg: Settings.
        paths: Paths.
        work: Where the pixel file goes (gitignored; derived from the cache).
        workers: Parallel reads for the station geometry (from cache).
        search_l1c: Level-1C item search by box and day (injectable).

    Returns:
        The scene rows, also written to ``acolite/scenes.csv`` under the inputs.
    """
    inputs_dir = paths.at(cfg.outputs.inputs)
    inputs = load_inputs(cfg, paths)
    uses = scene_uses(cfg, inputs)
    windows_csv = (inputs_dir / "imagery" / f"windows-{cfg.imagery.primary}.csv").read_text(
        encoding="utf-8"
    )
    l2a = _windows_by_key(windows_csv)
    stations = {r["station_id"]: r for r in read_stations(inputs_dir / "stations" / "stations.csv")}
    screening = load_screening_config(paths.at(cfg.screening_config))
    reader = _reader(cfg, screening, paths.cache)

    def default_search(box: tuple[float, float, float, float], day: date) -> list[dict[str, Any]]:
        return search_items(cfg.imagery.url, L1C_COLLECTION, box, day, day, 100)

    search = search_l1c or default_search
    rows: list[dict[str, object]] = []
    pixel_out: dict[str, Any] = {"stations": {}, "scenes": []}
    by_station: dict[str, list[SceneUse]] = {}
    for use in uses:
        by_station.setdefault(use.station, []).append(use)
    priority = {(u.station, u.key): i + 1 for i, u in enumerate(uses)}
    for station, station_uses in by_station.items():
        cand = candidate_of(stations[station])
        bbox = extract.bbox_around(cand.lon, cand.lat, cfg.stations.grid_half_size_m)
        geo_acqs = extract.search(cfg, cfg.imagery.primary, bbox, cfg.geometry_period.start,
                                  cfg.geometry_period.end)  # fmt: skip
        geo = extract.station_geometry(cand, geo_acqs, reader, cfg, screening, workers)
        wins = extract.station_windows(geo, cfg)
        g = wins.grid
        pixel_out["stations"][station] = {
            "epsg": g.epsg, "x0": g.x0, "y0": g.y0, "resolution": g.resolution,
            "width": g.width, "height": g.height, "lon": cand.lon, "lat": cand.lat,
        }  # fmt: skip
        box = extract.bbox_around(cand.lon, cand.lat, cfg.window.radius_m + 100)
        days = sorted({u.day for u in station_uses})
        acqs = {
            a.key: a
            for a in extract.search(cfg, cfg.imagery.primary, bbox, days[0], days[-1])
        }  # fmt: skip
        for use in station_uses:
            meta = l2a[(station, use.key)]
            acq = acqs.get(use.key)
            water = (
                extract.water_pixels(acq, reader, wins, "300m", cfg, screening)
                if acq is not None
                else None
            )
            when = datetime.fromisoformat(meta["datetime_utc"]).astimezone(UTC)
            item = l1c_item(search(box, when.date()), use.key, box)
            product = str(item["properties"].get("s2:product_uri", "")) if item else ""
            rows.append({
                "priority": priority[(station, use.key)], "station": station, "key": use.key,
                "datetime_utc": meta["datetime_utc"], "local_date": meta["local_date"],
                "split": use.split, "targets": " ".join(use.targets),
                "l2a_water_px": int(water.sum()) if water is not None else 0,
                "tile": product.split("_")[5][1:] if product else "",
                "l1c_item": str(item["id"]) if item else "", "l1c_product": product,
                "datatake": datatake(product),
            })  # fmt: skip
            if water is not None:
                rr, cc = water.nonzero()
                pixel_out["scenes"].append({
                    "station": station, "key": use.key,
                    "pixels": [[int(r), int(c)] for r, c in zip(rr, cc, strict=True)],
                })  # fmt: skip
    rows.sort(key=lambda r: int(str(r["priority"])))
    (inputs_dir / "acolite").mkdir(parents=True, exist_ok=True)
    (inputs_dir / "acolite" / "scenes.csv").write_bytes(_csv(rows, SCENE_COLUMNS))
    work.mkdir(parents=True, exist_ok=True)
    pixel_out["rg_floor"] = screening.stage2.rg_floor
    pixel_out["timezone"] = cfg.timezone
    (work / "pixels.json").write_text(json.dumps(pixel_out), encoding="utf-8")
    return rows
