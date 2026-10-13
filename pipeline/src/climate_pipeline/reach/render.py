"""``climate-pipeline reach render``: a reach's shape and each scene's NDTI map, for the web.

Written beside the examples, never into a record. ``geometry.geojson`` holds the river corridor
between the anchors, its centreline (with chainage), the two sub-reaches a record measures, the
estimate station and its window. Each ``maps/<key>.png`` holds one recorded scene's NDTI at 10 m
over the corridor's eroded water, under the screening's pixel guards (SCL, the red + green floor,
B11 glint): inside the sub-reaches these are the pixels the record's medians read. A PNG packs four
bytes per pixel:

- R: NDTI, 1..255 over ``NDTI_RANGE`` (0: no value);
- G: the pixel's place along the reach, 0 at the upstream anchor to 255 at the downstream one;
- B: 1 in the upstream sub-reach, 2 in the downstream one, 3 elsewhere in the corridor, plus 4
  where the scene left the pixel unusable (cloud, glint, no data);
- A: 255 inside the corridor, 0 outside.

``maps.json`` gives that encoding, the image's corners in WGS84 and one entry per map. NDTI is a
relative index: the maps carry no unit.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from climate_pipeline.provenance import head
from climate_pipeline.quality import imagery
from climate_pipeline.quality.fetching import check_disk
from climate_pipeline.reach import run as reach_run
from climate_pipeline.reach.config import ReachConfig
from climate_pipeline.screening import rio
from climate_pipeline.screening.bands import read_reflectance
from climate_pipeline.screening.mask import erode, nearest_on_path, path_chainage, upsample2
from climate_pipeline.screening.stage2 import repeat2

log = logging.getLogger(__name__)

NDTI_RANGE = (-0.3, 0.3)
CODES = {"upstream": 1, "downstream": 2, "between": 3}
UNUSABLE = 4
MARGIN_PX = 8  # 20 m pixels kept around the corridor
CENTRELINE_STEP = 5  # every fifth centreline pixel (100 m)
DIGITS = 6  # about 0.1 m in WGS84 degrees

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]


def ndti_bytes(ndti: NDArray[np.floating[Any]]) -> NDArray[np.uint8]:
    """NDTI as bytes, 1..255 over ``NDTI_RANGE`` (clipped), 0 where it is NaN.

    Args:
        ndti: NDTI values.

    Returns:
        The bytes.
    """
    low, high = NDTI_RANGE
    scaled = np.rint((np.clip(ndti, low, high) - low) / (high - low) * 254) + 1
    return np.where(np.isfinite(ndti), scaled, 0).astype(np.uint8)


def encode(ndti: NDArray[np.floating[Any]], area: dict[str, BoolArray], use: dict[str, BoolArray],
           progress: FloatArray) -> NDArray[np.uint8]:  # fmt: skip
    """One scene's map as RGBA bytes (see the module docstring).

    Args:
        ndti: NDTI on the 10 m grid (read where ``use`` is True).
        area: The eroded water of each part (``upstream``, ``downstream``, ``between``).
        use: Each part's pixels the scene left usable.
        progress: Place along the reach, 0..1, on the 10 m grid.

    Returns:
        ``(rows, cols, 4)`` bytes.
    """
    rgba = np.zeros((*progress.shape, 4), dtype=np.uint8)
    values = ndti_bytes(ndti)
    place = np.rint(np.clip(np.nan_to_num(progress), 0.0, 1.0) * 255).astype(np.uint8)
    for name, inside in area.items():
        usable = use[name] & inside
        code = np.where(usable, CODES[name], CODES[name] + UNUSABLE)
        rgba[inside, 1] = place[inside]
        rgba[inside, 2] = code[inside].astype(np.uint8)
        rgba[inside, 3] = 255
        rgba[usable, 0] = values[usable]
    return rgba


class Frame:
    """The reach's corridor, cropped from the site grid, with each part and its chainage."""

    def __init__(self, s: reach_run.Setup) -> None:
        """Crop the site grid to the corridor between the anchors, plus a margin.

        Args:
            s: The reach's setup.

        Raises:
            ReachError: When the frozen geometry has no corridor.
        """
        geometry = s.full.geometry
        if geometry.corridor is None:
            raise reach_run.ReachError(f"{s.reach.site}: the geometry has no corridor")
        full = s.full.grid
        corridor = geometry.corridor & geometry.river_mask
        rows, cols = np.nonzero(corridor)
        r0, c0 = max(0, int(rows.min()) - MARGIN_PX), max(0, int(cols.min()) - MARGIN_PX)
        r1 = min(full.height, int(rows.max()) + MARGIN_PX + 1)
        c1 = min(full.width, int(cols.max()) + MARGIN_PX + 1)
        self.grid = rio.Grid(full.epsg, full.resolution, full.x0 + c0 * full.resolution,
                             full.y0 - r0 * full.resolution, c1 - c0, r1 - r0)  # fmt: skip
        self.corridor = corridor[r0:r1, c0:c1]
        self.subreaches = {sub.name: sub.mask[r0:r1, c0:c1] & self.corridor
                           for sub in geometry.subreaches}  # fmt: skip
        chainage = path_chainage(geometry.centerline, full.resolution)
        pixels = np.argwhere(self.corridor).astype(np.int64)
        path = np.array(geometry.centerline, dtype=np.int64) - np.array([r0, c0])
        nearest, _ = nearest_on_path(pixels, path)
        chain = np.full(self.corridor.shape, np.nan)
        chain[pixels[:, 0], pixels[:, 1]] = chainage[nearest]
        self.progress = repeat2(chain / max(geometry.reach_length_m, 1.0))

    def parts(self) -> dict[str, BoolArray]:
        """Each part of the corridor on the 20 m grid: the sub-reaches and the water between."""
        between = self.corridor.copy()
        for mask in self.subreaches.values():
            between &= ~mask
        return {**self.subreaches, "between": between}


def scene_map(s: reach_run.Setup, frame: Frame, acquisition: Any) -> NDArray[np.uint8]:
    """One scene's encoded map over the corridor (the screening's pixel guards).

    Args:
        s: The reach's setup.
        frame: The cropped corridor.
        acquisition: The pass.

    Returns:
        RGBA bytes on the corridor's 10 m grid.
    """
    cfg = s.screening
    grid10 = frame.grid.with_resolution(10.0)
    erosion = (s.site.erosion_px_10m if s.site.erosion_px_10m is not None
               else cfg.mask.erosion_px_10m)  # fmt: skip
    scl20, _ = s.reader.read(acquisition, "scl", frame.grid)
    red, _ = read_reflectance(s.reader, acquisition, "red", grid10)
    green, _ = read_reflectance(s.reader, acquisition, "green", grid10)
    swir20, _ = read_reflectance(s.reader, acquisition, "swir16", frame.grid)
    scl = repeat2(scl20)
    swir = repeat2(swir20).astype(np.float32, copy=False)
    excluded = np.array(sorted(set(cfg.scl.invalid) | set(cfg.scl.nodata)))
    finite = np.isfinite(red) & np.isfinite(green) & np.isfinite(swir)
    passes = (~np.isin(scl, excluded) & finite & ((red + green) > cfg.stage2.rg_floor)
              & (swir <= cfg.stage2.swir16_max))  # fmt: skip
    area = {name: erode(upsample2(mask), erosion) for name, mask in frame.parts().items()}
    use = {name: inside & passes for name, inside in area.items()}
    with np.errstate(invalid="ignore", divide="ignore"):
        ndti = (red - green) / (red + green)
    return encode(ndti, area, use, np.asarray(frame.progress, dtype=np.float64))


def _ring(points: list[tuple[float, float]]) -> list[list[float]]:
    return [[round(lon, DIGITS), round(lat, DIGITS)] for lon, lat in points]


def _area(kind: str, grid: rio.Grid, mask: BoolArray, **properties: Any) -> dict[str, Any]:
    polygons = [[_ring(r) for r in rings] for rings in rio.mask_polygons(grid, mask)]
    return {"type": "Feature", "properties": {"kind": kind, **properties},
            "geometry": {"type": "MultiPolygon", "coordinates": polygons}}  # fmt: skip


def geometry_features(s: reach_run.Setup, frame: Frame, root: Path) -> dict[str, Any]:
    """The corridor, centreline, sub-reaches, estimate station and its window, as GeoJSON.

    Args:
        s: The reach's setup.
        frame: The cropped corridor.
        root: Repository root.

    Returns:
        A FeatureCollection in WGS84.
    """
    geometry = s.full.geometry
    chainage = path_chainage(geometry.centerline, s.full.grid.resolution)
    keep = [*range(0, len(geometry.centerline), CENTRELINE_STEP), len(geometry.centerline) - 1]
    line = rio.rowcols_lonlat(s.full.grid, [geometry.centerline[k][0] for k in keep],
                              [geometry.centerline[k][1] for k in keep])  # fmt: skip
    features = [
        _area("river", frame.grid, frame.corridor,
              lengthM=round(geometry.reach_length_m, 1)),
        {"type": "Feature",
         "properties": {"kind": "centreline",
                        "chainageM": [round(float(chainage[k]), 1) for k in keep]},
         "geometry": {"type": "LineString", "coordinates": _ring(line)}},
    ]  # fmt: skip
    for sub in geometry.subreaches:
        features.append(_area("subreach", frame.grid, frame.subreaches[sub.name], name=sub.name,
                              chainageM=[round(c, 1) for c in sub.chainage_m]))  # fmt: skip
    cand = reach_run.station_candidate(s.reach, s.quality, root)
    if cand is not None:
        features.append({
            "type": "Feature",
            "properties": {"kind": "station", "id": cand.station_id, "name": cand.name},
            "geometry": {"type": "Point", "coordinates": [round(cand.lon, DIGITS),
                                                          round(cand.lat, DIGITS)]},
        })  # fmt: skip
    if s.station is not None and s.window in s.station.windows.masks:
        features.append(_area("window", s.station.windows.grid,
                              s.station.windows.masks[s.window], name=s.window))  # fmt: skip
    return {"type": "FeatureCollection", "features": features}


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, separators=(",", ":")) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def render(cfg: ReachConfig, root: Path, site_id: str, cache: Path, workers: int = 8
           ) -> dict[str, Any]:  # fmt: skip
    """Write the reach's geometry and the NDTI map of every recorded scene (resumable).

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        cache: Cache folder.
        workers: Parallel reads for the geometry.

    Returns:
        Counts.

    Raises:
        ReachError: Before the reach has a record.
    """
    folder = root / cfg.out / site_id
    files = sorted((folder / "records").glob("*.json"))
    if not files:
        raise reach_run.ReachError(f"{site_id}: no records yet; run `reach run` first")
    s = reach_run.setup(cfg, root, site_id, cache, workers, need_cards=False)
    frame = Frame(s)
    out = root / "docs" / "water-quality" / "reach" / site_id / "examples"
    _write_json(out / "geometry.geojson", geometry_features(s, frame, root))
    records = [json.loads(p.read_text(encoding="utf-8")) for p in files]
    keys = [p.stem.split("_", 1)[1] for p in files]
    days = sorted(date.fromisoformat(r["date"]) for r in records)
    west, south, east, north = s.site.aoi_bbox
    pad = timedelta(days=1)
    bbox = (west, south, east, north)
    acqs, _ = imagery.search(s.quality, "earth-search", bbox, days[0] - pad, days[-1] + pad)
    by_key = {a.key: a for a in acqs}
    entries, drawn, missing = [], 0, []
    for key, rec in zip(keys, records, strict=True):
        name = f"maps/{key}.png"
        if not (out / name).exists():
            acq = by_key.get(key)
            if acq is None:
                missing.append(key)
                continue
            check_disk(root, cfg.budgets.keep_free_gb)
            rgba = scene_map(s, frame, acq)
            (out / "maps").mkdir(parents=True, exist_ok=True)
            Image.fromarray(rgba, "RGBA").save(out / name, format="PNG", optimize=True)
            s.reader.forget(acq)
            drawn += 1
            log.info("%s: drew %s", site_id, name)
        entries.append({"key": key, "sceneId": rec["sceneId"], "date": rec["date"],
                        "recordSha256": rec["recordSha256"], "file": name})  # fmt: skip
    grid10 = frame.grid.with_resolution(10.0)
    _write_json(out / "maps.json", {
        "site": site_id, "codeCommit": head(), "width": grid10.width, "height": grid10.height,
        "corners": [[round(lon, DIGITS), round(lat, DIGITS)]
                    for lon, lat in rio.corners_lonlat(grid10)],
        "encoding": {"r": {"ndti": list(NDTI_RANGE), "bytes": [1, 255], "none": 0},
                     "g": "place along the reach, 0 at the upstream anchor to 255 downstream",
                     "b": {**CODES, "unusable": UNUSABLE}, "a": "255 inside the corridor"},
        "maps": entries,
    })  # fmt: skip
    return {"maps": len(entries), "drawn": drawn, "missing": missing}
