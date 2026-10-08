import hashlib
import struct
import zipfile
from pathlib import Path

import httpx
import pytest

from climate_pipeline.validation.grid import (
    HydroBasins,
    basin_containing,
    build_grid,
    choose_lattice,
    download,
    extract_layer,
    point_in_rings,
    read_dbf,
    read_grid,
    upstream_basins,
    write_grid,
)

Ring = list[tuple[float, float]]


def square(x0: float, y0: float, x1: float, y1: float) -> Ring:
    return [(x0, y0), (x0, y1), (x1, y1), (x1, y0), (x0, y0)]


# Toy basins: A is the outlet; B drains to A, C to B, E (with a hole) to A; D is another sink.
BASINS = [
    (1, 0, 40.0, 10.0, [square(0.05, 0.05, 1.05, 1.05)]),
    (2, 1, 20.0, 10.0, [square(1.05, 0.05, 2.05, 1.05)]),
    (3, 2, 10.0, 10.0, [square(1.05, 1.05, 2.05, 2.05)]),
    (4, 0, 10.0, 10.0, [square(0.05, 1.05, 1.05, 2.05)]),
    (5, 1, 10.0, 10.0, [square(-0.95, 0.05, 0.05, 1.05), square(-0.7, 0.35, -0.2, 0.75)]),
]


def write_dbf(path: Path, rows: list[tuple[int, int, float, float]]) -> None:
    fields = [("HYBAS_ID", 11, 0), ("NEXT_DOWN", 11, 0), ("UP_AREA", 13, 1), ("SUB_AREA", 13, 1)]
    record_size = 1 + sum(f[1] for f in fields)
    header_size = 32 + 32 * len(fields) + 1
    out = bytearray(struct.pack("<B3BIHH20x", 3, 126, 10, 8, len(rows), header_size, record_size))
    for name, length, decimals in fields:
        out += struct.pack("<11sc4xBB14x", name.encode(), b"N", length, decimals)
    out += b"\x0d"
    for row in rows:
        out += b" "
        for value, (_, length, decimals) in zip(row, fields, strict=True):
            out += f"{value:>{length}.{decimals}f}".encode()
    out += b"\x1a"
    path.write_bytes(bytes(out))


def write_shapefile(stem: Path, polygons: list[list[Ring]]) -> None:
    records = []
    for rings in polygons:
        points = [p for ring in rings for p in ring]
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        parts, start = [], 0
        for ring in rings:
            parts.append(start)
            start += len(ring)
        content = struct.pack(
            "<i4d2i", 5, min(xs), min(ys), max(xs), max(ys), len(rings), len(points)
        )
        content += struct.pack(f"<{len(parts)}i", *parts)
        content += b"".join(struct.pack("<2d", *p) for p in points)
        records.append(content)

    def header(length_bytes: int) -> bytes:
        return struct.pack(">i5ii", 9994, 0, 0, 0, 0, 0, length_bytes // 2) + struct.pack(
            "<ii8d", 1000, 5, 0, 0, 0, 0, 0, 0, 0, 0
        )

    body, index, offset = bytearray(), bytearray(), 100
    for number, content in enumerate(records, start=1):
        body += struct.pack(">ii", number, len(content) // 2) + content
        index += struct.pack(">ii", offset // 2, len(content) // 2)
        offset += 8 + len(content)
    stem.with_suffix(".shp").write_bytes(header(100 + len(body)) + body)
    stem.with_suffix(".shx").write_bytes(header(100 + len(index)) + index)


@pytest.fixture
def layer(tmp_path: Path) -> HydroBasins:
    stem = tmp_path / "toy_lev12"
    write_shapefile(stem, [b[4] for b in BASINS])
    write_dbf(stem.with_suffix(".dbf"), [(b[0], b[1], b[2], b[3]) for b in BASINS])
    return HydroBasins.open(stem.with_suffix(".shp"))


def test_the_layer_reads_attributes_and_bounding_boxes(layer: HydroBasins, tmp_path: Path) -> None:
    assert layer.ids == [1, 2, 3, 4, 5]
    assert layer.next_down == [0, 1, 2, 0, 1]
    assert layer.up_area[0] == 40.0
    assert layer.bboxes[1] == (1.05, 0.05, 2.05, 1.05)
    rows = read_dbf(tmp_path / "toy_lev12.dbf", ("HYBAS_ID",))
    assert [r["HYBAS_ID"] for r in rows] == [1, 2, 3, 4, 5]
    with pytest.raises(KeyError):
        read_dbf(tmp_path / "toy_lev12.dbf", ("PFAF_ID",))


def test_points_inside_respect_holes(layer: HydroBasins) -> None:
    rings = layer.polygons([4])[4]
    assert point_in_rings(-0.9, 0.5, rings)
    assert not point_in_rings(-0.45, 0.55, rings)  # in the hole
    assert layer.containing(1.5, 1.5) == [2]
    assert layer.containing(-0.45, 0.55) == []


def test_the_outlet_is_the_largest_upstream_basin_near_the_anchor(layer: HydroBasins) -> None:
    # The anchor lies in A, 0.005 deg from B: both are candidates, A drains more.
    assert basin_containing(layer, 1.045, 0.5, 0.01) == 0
    assert basin_containing(layer, 9.0, 9.0, 0.01) is None
    assert upstream_basins(layer.ids, layer.next_down, 0) == [0, 1, 2, 4]
    assert upstream_basins(layer.ids, layer.next_down, 2) == [2]


def test_the_lattice_takes_the_coarsest_spacing_with_enough_points(layer: HydroBasins) -> None:
    members = upstream_basins(layer.ids, layer.next_down, 0)
    polygons = layer.polygons(members)
    chosen = choose_lattice(polygons, layer.ids, (1.2, 0.6, 0.3), 6, 12)
    assert chosen is not None
    spacing, points = chosen
    assert spacing == 0.6 and len(points) == 8
    assert (-0.6, 0.6) not in {(p.lon, p.lat) for p in points}  # in the hole
    assert (0.6, 1.2) not in {(p.lon, p.lat) for p in points}  # in D, another sink
    assert choose_lattice(polygons, layer.ids, (1.2, 0.6), 50, 60) is None


def test_the_grid_is_written_and_read_back(layer: HydroBasins, tmp_path: Path) -> None:
    grid = build_grid(layer, (0.5, 0.5), 0.01, (1.2, 0.6, 0.3), 6, 12, "abc")
    assert grid.outlet_hybas_id == 1 and grid.basins == 4 and grid.area_km2 == 40.0
    path = tmp_path / "rain-grid.csv"
    write_grid(grid, path)
    points = read_grid(path)
    assert len(points) == 8 and points[0][0] == "g01"
    unbuildable = build_grid(layer, (0.5, 0.5), 0.01, (1.2,), 6, 12, "abc")
    assert unbuildable.points == [] and unbuildable.note.startswith("unbuildable")
    write_grid(unbuildable, path)
    assert read_grid(path) == []


def test_the_archive_is_downloaded_once_and_its_layer_extracted(tmp_path: Path) -> None:
    payload = tmp_path / "src.zip"
    with zipfile.ZipFile(payload, "w") as zipped:
        for suffix in (".shp", ".shx", ".dbf"):
            zipped.writestr(f"folder/HYBAS_TOY{suffix}", b"x")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=payload.read_bytes())

    http = httpx.Client(transport=httpx.MockTransport(handler))
    target = tmp_path / "cache" / "hybas_toy.zip"
    first = download("https://hydro.test/hybas_toy.zip", target, http)
    second = download("https://hydro.test/hybas_toy.zip", target, http)
    assert first == second == hashlib.sha256(payload.read_bytes()).hexdigest()
    assert len(calls) == 1
    shp = extract_layer(target, "hybas_toy", tmp_path / "layer")
    assert shp.name == "hybas_toy.shp" and shp.with_suffix(".dbf").exists()
    with pytest.raises(FileNotFoundError):
        extract_layer(target, "other", tmp_path / "layer")
