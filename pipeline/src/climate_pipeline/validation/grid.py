"""The catchment rain grid: HydroBASINS outlet, the basins upstream of it and a lattice of points.

HydroBASINS (Lehner and Grill 2013) ships as shapefiles; this module reads the three files it
needs (``.shp`` polygons, ``.shx`` offsets, ``.dbf`` attributes) with the standard library only,
so the pipeline gains no vector dependency. Only polygons of type 5 (polygon) are read; a point
is inside a basin by the even-odd rule over all of its rings, so holes are respected.
"""

from __future__ import annotations

import csv
import hashlib
import math
import struct
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import httpx

GRID_COLUMNS = (
    "point_id", "lon", "lat", "spacing_deg", "hybas_id", "outlet_hybas_id", "catchment_basins",
    "catchment_area_km2", "hydrobasins_sha256",
)  # fmt: skip

Ring = tuple[tuple[float, float], ...]
BBox = tuple[float, float, float, float]


# ----------------------------------------------------------------------------------------------
# Shapefile reading
# ----------------------------------------------------------------------------------------------


def read_dbf(path: Path, fields: Sequence[str]) -> list[dict[str, float]]:
    """Read numeric fields of a dBASE table, one row per record in file order.

    Args:
        path: The ``.dbf`` file.
        fields: Field names to read (numeric: types N or F).

    Returns:
        One row per record, in file order, with the requested fields as floats.

    Raises:
        KeyError: If a field is missing.
    """
    with path.open("rb") as handle:
        header = handle.read(32)
        count = struct.unpack("<I", header[4:8])[0]
        header_size, record_size = struct.unpack("<HH", header[8:12])
        layout: dict[str, tuple[int, int]] = {}
        position = 1  # byte 0 of each record is the deletion flag
        while True:
            descriptor = handle.read(32)
            if not descriptor or descriptor[0] == 0x0D:
                break
            name = descriptor[:11].split(b"\x00", 1)[0].decode("ascii").strip()
            length = descriptor[16]
            layout[name] = (position, length)
            position += length
        missing = [f for f in fields if f not in layout]
        if missing:
            raise KeyError(f"{path.name}: no fields {missing}")
        handle.seek(header_size)
        rows = []
        for _ in range(count):
            record = handle.read(record_size)
            row = {}
            for name in fields:
                start, length = layout[name]
                text = record[start : start + length].strip()
                row[name] = float(text) if text else math.nan
            rows.append(row)
    return rows


def read_shx(path: Path) -> list[int]:
    """Byte offsets of every record in the matching ``.shp`` file.

    Args:
        path: The ``.shx`` file.

    Returns:
        Offsets in bytes, in record order.
    """
    data = path.read_bytes()[100:]
    return [struct.unpack(">i", data[k : k + 4])[0] * 2 for k in range(0, len(data), 8)]


def read_bbox(handle: BinaryIO, offset: int) -> BBox | None:
    """The bounding box of one record (None for a null shape).

    Args:
        handle: The open ``.shp`` file.
        offset: The record's byte offset.

    Returns:
        ``(west, south, east, north)``.
    """
    handle.seek(offset + 8)
    content = handle.read(36)
    if struct.unpack("<i", content[:4])[0] == 0:
        return None
    west, south, east, north = struct.unpack("<4d", content[4:36])
    return west, south, east, north


def read_polygon(handle: BinaryIO, offset: int) -> tuple[Ring, ...]:
    """The rings of one polygon record.

    Args:
        handle: The open ``.shp`` file.
        offset: The record's byte offset.

    Returns:
        The rings as ``(lon, lat)`` tuples.

    Raises:
        ValueError: If the record is not a polygon.
    """
    handle.seek(offset + 8)
    shape_type = struct.unpack("<i", handle.read(4))[0]
    if shape_type == 0:
        return ()
    if shape_type != 5:
        raise ValueError(f"shape type {shape_type} is not a polygon")
    handle.read(32)  # bounding box
    parts_n, points_n = struct.unpack("<ii", handle.read(8))
    parts = list(struct.unpack(f"<{parts_n}i", handle.read(4 * parts_n)))
    flat = struct.unpack(f"<{2 * points_n}d", handle.read(16 * points_n))
    points = [(flat[2 * k], flat[2 * k + 1]) for k in range(points_n)]
    bounds = [*parts, points_n]
    return tuple(tuple(points[bounds[k] : bounds[k + 1]]) for k in range(parts_n))


def point_in_rings(lon: float, lat: float, rings: Iterable[Ring]) -> bool:
    """Whether a point lies inside a polygon (even-odd rule over all rings, holes included).

    Args:
        lon: Longitude.
        lat: Latitude.
        rings: The polygon's rings.

    Returns:
        True inside.
    """
    inside = False
    for ring in rings:
        n = len(ring)
        for k in range(n):
            x1, y1 = ring[k]
            x2, y2 = ring[(k + 1) % n]
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def _within(bbox: BBox | None, lon: float, lat: float) -> bool:
    return bbox is not None and bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


@dataclass
class HydroBasins:
    """A HydroBASINS layer: attributes in memory, polygons read on demand."""

    shp: Path
    ids: list[int]
    next_down: list[int]
    up_area: list[float]
    sub_area: list[float]
    offsets: list[int]
    bboxes: list[BBox | None]

    @classmethod
    def open(cls, shp: Path) -> HydroBasins:
        """Read a layer's attributes, record offsets and bounding boxes.

        Args:
            shp: The ``.shp`` file (its ``.shx`` and ``.dbf`` sit next to it).

        Returns:
            The layer.
        """
        rows = read_dbf(shp.with_suffix(".dbf"), ("HYBAS_ID", "NEXT_DOWN", "UP_AREA", "SUB_AREA"))
        offsets = read_shx(shp.with_suffix(".shx"))
        with shp.open("rb") as handle:
            bboxes = [read_bbox(handle, offset) for offset in offsets]
        return cls(
            shp,
            [int(r["HYBAS_ID"]) for r in rows],
            [int(r["NEXT_DOWN"]) for r in rows],
            [r["UP_AREA"] for r in rows],
            [r["SUB_AREA"] for r in rows],
            offsets,
            bboxes,
        )

    def polygons(self, indices: Iterable[int]) -> dict[int, tuple[Ring, ...]]:
        """The rings of some records.

        Args:
            indices: Record indices.

        Returns:
            Rings by record index.
        """
        with self.shp.open("rb") as handle:
            return {i: read_polygon(handle, self.offsets[i]) for i in indices}

    def containing(self, lon: float, lat: float) -> list[int]:
        """Records whose polygon contains a point.

        Args:
            lon: Longitude.
            lat: Latitude.

        Returns:
            Record indices.
        """
        candidates = [i for i, b in enumerate(self.bboxes) if _within(b, lon, lat)]
        rings = self.polygons(candidates)
        return [i for i in candidates if point_in_rings(lon, lat, rings[i])]


# ----------------------------------------------------------------------------------------------
# Catchment and lattice
# ----------------------------------------------------------------------------------------------


def basin_containing(layer: HydroBasins, lon: float, lat: float, tolerance: float) -> int | None:
    """The outlet basin: largest upstream area among basins holding the point or 8 neighbours.

    Args:
        layer: The HydroBASINS layer.
        lon: Longitude of the downstream anchor.
        lat: Latitude of the downstream anchor.
        tolerance: Offset of the 8 neighbouring points, in degrees.

    Returns:
        The record index, or None if no basin holds any of the nine points.
    """
    found: set[int] = set()
    for dx in (-tolerance, 0.0, tolerance):
        for dy in (-tolerance, 0.0, tolerance):
            found.update(layer.containing(lon + dx, lat + dy))
    if not found:
        return None
    return max(found, key=lambda i: (layer.up_area[i], -layer.ids[i]))


def upstream_basins(ids: Sequence[int], next_down: Sequence[int], outlet: int) -> list[int]:
    """The outlet and every basin draining into it, following the downstream links.

    Args:
        ids: Basin ids, one per record.
        next_down: Id of each record's downstream basin (0 at a sink).
        outlet: Record index of the outlet.

    Returns:
        Record indices, sorted.
    """
    children: dict[int, list[int]] = defaultdict(list)
    for index, down in enumerate(next_down):
        children[down].append(index)
    found = {outlet}
    stack = [outlet]
    while stack:
        current = stack.pop()
        for child in children[ids[current]]:
            if child not in found:
                found.add(child)
                stack.append(child)
    return sorted(found)


@dataclass(frozen=True)
class GridPoint:
    """One lattice point inside the catchment."""

    lon: float
    lat: float
    hybas_id: int


def lattice(
    polygons: dict[int, tuple[Ring, ...]],
    ids: Sequence[int],
    spacing: float,
) -> list[GridPoint]:
    """Points at whole multiples of a spacing that fall inside the catchment.

    Args:
        polygons: Rings of each catchment basin, by record index.
        ids: Basin ids, one per record.
        spacing: Lattice spacing in degrees.

    Returns:
        The points, west to east within south to north.
    """
    xs = [x for rings in polygons.values() for ring in rings for x, _ in ring]
    ys = [y for rings in polygons.values() for ring in rings for _, y in ring]
    if not xs:
        return []
    boxes = {
        index: (
            min(x for ring in rings for x, _ in ring),
            min(y for ring in rings for _, y in ring),
            max(x for ring in rings for x, _ in ring),
            max(y for ring in rings for _, y in ring),
        )
        for index, rings in polygons.items()
        if rings
    }
    eps = 1e-9
    i0, i1 = math.ceil(min(xs) / spacing - eps), math.floor(max(xs) / spacing + eps)
    j0, j1 = math.ceil(min(ys) / spacing - eps), math.floor(max(ys) / spacing + eps)
    points = []
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            lon, lat = round(i * spacing, 6), round(j * spacing, 6)
            for index, box in boxes.items():
                if _within(box, lon, lat) and point_in_rings(lon, lat, polygons[index]):
                    points.append(GridPoint(lon, lat, ids[index]))
                    break
    return points


def choose_lattice(
    polygons: dict[int, tuple[Ring, ...]],
    ids: Sequence[int],
    spacings: Sequence[float],
    points_min: int,
    points_max: int,
) -> tuple[float, list[GridPoint]] | None:
    """The coarsest spacing whose lattice has between ``points_min`` and ``points_max`` points.

    Args:
        polygons: Rings of each catchment basin.
        ids: Basin ids, one per record.
        spacings: Spacings from coarsest to finest.
        points_min: Fewest points accepted.
        points_max: Most points accepted.

    Returns:
        The spacing and its points, or None when no spacing qualifies (the grid is unbuildable).
    """
    for spacing in spacings:
        points = lattice(polygons, ids, spacing)
        if points_min <= len(points) <= points_max:
            return spacing, points
    return None


# ----------------------------------------------------------------------------------------------
# Building the committed grid
# ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CatchmentGrid:
    """The result of the grid procedure (no points when it is unbuildable)."""

    outlet_hybas_id: int | None
    basins: int
    area_km2: float
    spacing: float | None
    points: list[GridPoint]
    archive_sha256: str
    note: str


def download(url: str, target: Path, http: httpx.Client | None = None) -> str:
    """Download a file once (kept in a cache) and return its SHA-256.

    Args:
        url: The address.
        target: Where to keep it.
        http: HTTP client (injectable for tests).

    Returns:
        The hex SHA-256 of the file.
    """
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        client = http or httpx.Client(timeout=300, follow_redirects=True)
        with client.stream("GET", url) as response, partial.open("wb") as handle:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                handle.write(chunk)
        partial.replace(target)
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_layer(archive: Path, layer: str, folder: Path) -> Path:
    """Extract a layer's ``.shp``, ``.shx`` and ``.dbf`` from a zip archive.

    Args:
        archive: The zip file.
        layer: The layer name, e.g. ``hybas_sa_lev12_v1c``.
        folder: Where to put the files.

    Returns:
        The path of the ``.shp`` file.

    Raises:
        FileNotFoundError: If the archive lacks one of the files.
    """
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zipped:
        names = {Path(n).name.lower(): n for n in zipped.namelist()}
        for suffix in (".shp", ".shx", ".dbf"):
            member = names.get(f"{layer}{suffix}".lower())
            if member is None:
                raise FileNotFoundError(f"{archive.name} has no {layer}{suffix}")
            (folder / f"{layer}{suffix}").write_bytes(zipped.read(member))
    return folder / f"{layer}.shp"


def build_grid(
    layer: HydroBasins,
    anchor: tuple[float, float],
    tolerance: float,
    spacings: Sequence[float],
    points_min: int,
    points_max: int,
    archive_sha256: str,
) -> CatchmentGrid:
    """Run the pre-registered grid procedure on an opened HydroBASINS layer.

    Args:
        layer: The layer.
        anchor: ``(lon, lat)`` of the site's downstream anchor.
        tolerance: Neighbour offset for the outlet search, in degrees.
        spacings: Lattice spacings from coarsest to finest.
        points_min: Fewest grid points accepted.
        points_max: Most grid points accepted.
        archive_sha256: SHA-256 of the HydroBASINS archive, recorded with the grid.

    Returns:
        The grid (no points when unbuildable, with the reason in ``note``).
    """
    outlet = basin_containing(layer, anchor[0], anchor[1], tolerance)
    if outlet is None:
        return CatchmentGrid(None, 0, 0.0, None, [], archive_sha256, "no basin holds the anchor")
    members = upstream_basins(layer.ids, layer.next_down, outlet)
    area = sum(layer.sub_area[i] for i in members)
    chosen = choose_lattice(layer.polygons(members), layer.ids, spacings, points_min, points_max)
    if chosen is None:
        note = f"unbuildable: no spacing gives {points_min}-{points_max} points"
        return CatchmentGrid(layer.ids[outlet], len(members), area, None, [], archive_sha256, note)
    spacing, points = chosen
    return CatchmentGrid(
        layer.ids[outlet], len(members), area, spacing, points, archive_sha256, "built"
    )


def write_grid(grid: CatchmentGrid, path: Path) -> None:
    """Write the grid as CSV (a header only when the grid is unbuildable).

    Args:
        grid: The grid.
        path: The CSV file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(GRID_COLUMNS)
        for k, point in enumerate(grid.points, start=1):
            writer.writerow(
                [
                    f"g{k:02d}",
                    f"{point.lon:.6f}",
                    f"{point.lat:.6f}",
                    grid.spacing,
                    point.hybas_id,
                    grid.outlet_hybas_id,
                    grid.basins,
                    round(grid.area_km2, 1),
                    grid.archive_sha256,
                ]
            )


def read_grid(path: Path) -> list[tuple[str, float, float]]:
    """Read the committed grid.

    Args:
        path: The CSV file.

    Returns:
        ``(point_id, lon, lat)`` per point (empty when the grid is unbuildable).
    """
    with path.open(newline="", encoding="utf-8") as handle:
        return [(r["point_id"], float(r["lon"]), float(r["lat"])) for r in csv.DictReader(handle)]
