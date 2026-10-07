"""River mask, centerline, corridor and sub-reaches derived from the SCL water frequency.

Nothing is drawn by hand. The river is where SCL says "water" in at least a configured share of
the clear observations. The main channel is the 4-connected region joining two approximate
anchors (upstream and downstream, from the site's sources). The centerline is the shortest path
between them, and chainage (distance along the river from the upstream anchor) places two
sub-reaches 5-15 km apart. All loops run over river pixels only, never the whole grid.
"""

from __future__ import annotations

import dataclasses
import heapq
import itertools
import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from climate_pipeline.screening.config import SclConfig, SubreachConfig

BoolArray = NDArray[np.bool_]
FloatArray = NDArray[np.float64]
RowCol = tuple[int, int]


class FrequencyStack:
    """Running counts of SCL water and clear observations per pixel (no stack kept in memory)."""

    def __init__(self, shape: tuple[int, int], scl: SclConfig) -> None:
        """Create empty counts.

        Args:
            shape: Grid shape.
            scl: SCL class settings.
        """
        self.water = np.zeros(shape, dtype=np.int32)
        self.valid = np.zeros(shape, dtype=np.int32)
        self.scenes = 0
        self._excluded = np.array(sorted(set(scl.invalid) | set(scl.nodata)), dtype=np.uint8)
        self._water = np.array(scl.water, dtype=np.uint8)

    def update(self, scl: NDArray[np.generic]) -> None:
        """Add one acquisition's SCL.

        Args:
            scl: SCL classes on the grid.
        """
        valid = ~np.isin(scl, self._excluded)
        self.valid += valid
        self.water += valid & np.isin(scl, self._water)
        self.scenes += 1

    def frequency(self, min_observations: int) -> FloatArray:
        """Share of clear observations classified as water (NaN with too few observations).

        Args:
            min_observations: Minimum clear observations a pixel needs.

        Returns:
            The water frequency per pixel.
        """
        freq = np.full(self.water.shape, np.nan)
        enough = self.valid >= min_observations
        freq[enough] = self.water[enough] / self.valid[enough]
        return freq


def histogram(freq: FloatArray, bins: int = 10) -> list[int]:
    """Counts of pixels per water-frequency bin (pixels with enough observations only).

    Args:
        freq: Water frequency.
        bins: Number of equal bins over [0, 1].

    Returns:
        Pixel counts per bin.
    """
    values = freq[np.isfinite(freq)]
    counts, _ = np.histogram(values, bins=bins, range=(0.0, 1.0))
    return [int(c) for c in counts]


# ----------------------------------------------------------------------------------------------
# Morphology on boolean grids (numpy shifts, no scipy)
# ----------------------------------------------------------------------------------------------


def _shift(mask: BoolArray, dr: int, dc: int) -> BoolArray:
    out = np.zeros_like(mask)
    rows, cols = mask.shape
    src_r = slice(max(0, -dr), rows - max(0, dr))
    dst_r = slice(max(0, dr), rows - max(0, -dr))
    src_c = slice(max(0, -dc), cols - max(0, dc))
    dst_c = slice(max(0, dc), cols - max(0, -dc))
    out[dst_r, dst_c] = mask[src_r, src_c]
    return out


def dilate(mask: BoolArray, steps: int) -> BoolArray:
    """Grow a mask by ``steps`` pixels (8-neighbourhood).

    Args:
        mask: Input mask.
        steps: Number of one-pixel dilations.

    Returns:
        The dilated mask.
    """
    out = mask.copy()
    for _ in range(steps):
        grown = out.copy()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr or dc:
                    grown |= _shift(out, dr, dc)
        out = grown
    return out


def erode(mask: BoolArray, steps: int) -> BoolArray:
    """Shrink a mask by ``steps`` pixels (4-neighbourhood), e.g. to drop mixed bank pixels.

    Args:
        mask: Input mask.
        steps: Number of one-pixel erosions.

    Returns:
        The eroded mask.
    """
    out = mask.copy()
    for _ in range(steps):
        out = out & _shift(out, 1, 0) & _shift(out, -1, 0) & _shift(out, 0, 1) & _shift(out, 0, -1)
    return out


def close(mask: BoolArray, steps: int) -> BoolArray:
    """Morphological closing (8-neighbourhood): fills gaps up to ``2 * steps`` pixels wide.

    Args:
        mask: Input mask.
        steps: Closing radius in pixels.

    Returns:
        The closed mask (a superset of the input).
    """
    if steps <= 0:
        return mask.copy()
    return ~dilate(~dilate(mask, steps), steps) | mask


def upsample2(mask: BoolArray) -> BoolArray:
    """A 20 m mask on the nested 10 m grid (each pixel becomes 2 x 2).

    Args:
        mask: Mask on the 20 m grid.

    Returns:
        Mask on the 10 m grid.
    """
    return np.repeat(np.repeat(mask, 2, axis=0), 2, axis=1)


# ----------------------------------------------------------------------------------------------
# Graph steps over river pixels
# ----------------------------------------------------------------------------------------------


def snap(mask: BoolArray, rc: RowCol, radius_px: float) -> tuple[RowCol, float] | None:
    """The mask pixel nearest to a point, within a radius.

    Args:
        mask: Where snapping is allowed.
        rc: Row and column of the point (may be outside the grid).
        radius_px: Search radius in pixels.

    Returns:
        The snapped pixel and its distance in pixels, or None if none is close enough.
    """
    r0, c0 = rc
    rad = math.ceil(radius_px)
    rows, cols = mask.shape
    top, bottom = max(0, r0 - rad), min(rows, r0 + rad + 1)
    left, right = max(0, c0 - rad), min(cols, c0 + rad + 1)
    if top >= bottom or left >= right:
        return None
    rr, cc = np.nonzero(mask[top:bottom, left:right])
    if rr.size == 0:
        return None
    d2 = (rr + top - r0) ** 2 + (cc + left - c0) ** 2
    best = int(np.argmin(d2))
    dist = math.sqrt(float(d2[best]))
    if dist > radius_px:
        return None
    return (int(rr[best] + top), int(cc[best] + left)), dist


def component(mask: BoolArray, seed: RowCol) -> BoolArray:
    """The 4-connected region of ``mask`` containing ``seed``.

    Four-connectivity keeps pits and floodplain lakes that touch the river only diagonally out.

    Args:
        mask: Candidate pixels.
        seed: A pixel inside the mask.

    Returns:
        The connected region.
    """
    return connected_to(mask, [seed])


def connected_to(mask: BoolArray, seeds: Sequence[RowCol]) -> BoolArray:
    """The 4-connected regions of ``mask`` that contain any of the seeds.

    Args:
        mask: Candidate pixels.
        seeds: Pixels to grow from (those outside the mask are ignored).

    Returns:
        The connected regions.
    """
    out = np.zeros_like(mask)
    rows, cols = mask.shape
    queue = deque(seed for seed in seeds if mask[seed])
    for seed in queue:
        out[seed] = True
    while queue:
        r, c = queue.popleft()
        for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if 0 <= nr < rows and 0 <= nc < cols and mask[nr, nc] and not out[nr, nc]:
                out[nr, nc] = True
                queue.append((nr, nc))
    return out


def candidates(mask: BoolArray, rc: RowCol, radius_px: float) -> list[tuple[RowCol, float]]:
    """Mask pixels within a radius of a point, nearest first.

    Args:
        mask: Allowed pixels.
        rc: Row and column of the point (may be outside the grid).
        radius_px: Search radius in pixels.

    Returns:
        Pixels with their distances in pixels.
    """
    r0, c0 = rc
    rad = math.ceil(radius_px)
    rows, cols = mask.shape
    top, bottom = max(0, r0 - rad), min(rows, r0 + rad + 1)
    left, right = max(0, c0 - rad), min(cols, c0 + rad + 1)
    if top >= bottom or left >= right:
        return []
    rr, cc = np.nonzero(mask[top:bottom, left:right])
    d = np.sqrt((rr + top - r0) ** 2.0 + (cc + left - c0) ** 2.0)
    order = np.argsort(d, kind="stable")
    return [
        ((int(rr[i] + top), int(cc[i] + left)), float(d[i])) for i in order if d[i] <= radius_px
    ]


def snap_connected(
    river: BoolArray, upstream: RowCol, downstream: RowCol, radius_px: float
) -> tuple[tuple[RowCol, float], tuple[RowCol, float], BoolArray] | str:
    """Snap both anchors onto one 4-connected river region.

    A pond, a reservoir or a tributary can lie closer to an anchor than the main channel, so the
    anchors are not snapped independently: regions are tried from the one nearest the upstream
    anchor outwards, and the first that also comes within the radius of the downstream anchor is
    used.

    Args:
        river: River mask.
        upstream: Upstream anchor pixel.
        downstream: Downstream anchor pixel.
        radius_px: Snapping radius in pixels.

    Returns:
        The snapped anchors with their distances (pixels) and the region, or why it failed (with
        ``{radius}`` standing for the radius).
    """
    up = candidates(river, upstream, radius_px)
    down = candidates(river, downstream, radius_px)
    if not up:
        return "upstream anchor not within {radius} of the river mask"
    if not down:
        return "downstream anchor not within {radius} of the river mask"
    tried = np.zeros_like(river)
    for rc, dist in up:
        if tried[rc]:
            continue
        region = component(river, rc)
        tried |= region
        match = next(((d_rc, d) for d_rc, d in down if region[d_rc]), None)
        if match is not None:
            return (rc, dist), match, region
    return "anchors are not connected by the river mask"


_SQRT2 = math.sqrt(2.0)
_STEPS = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc]


def shortest_path(region: BoolArray, start: RowCol, goal: RowCol) -> list[RowCol] | None:
    """Shortest 8-connected path inside a region (diagonals only around a river corner).

    A diagonal step is allowed only when one of the two orthogonal pixels it passes is also in
    the region, so the path never cuts across a land corner.

    Args:
        region: Allowed pixels.
        start: First pixel.
        goal: Last pixel.

    Returns:
        The path from start to goal, or None if they are not connected.
    """
    rows, cols = region.shape
    dist: dict[RowCol, float] = {start: 0.0}
    prev: dict[RowCol, RowCol] = {}
    heap: list[tuple[float, RowCol]] = [(0.0, start)]
    while heap:
        d, node = heapq.heappop(heap)
        if node == goal:
            break
        if d > dist.get(node, math.inf):
            continue
        r, c = node
        for dr, dc in _STEPS:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols and region[nr, nc]):
                continue
            if dr and dc and not (region[r + dr, c] or region[r, c + dc]):
                continue
            nd = d + (_SQRT2 if dr and dc else 1.0)
            if nd < dist.get((nr, nc), math.inf):
                dist[(nr, nc)] = nd
                prev[(nr, nc)] = node
                heapq.heappush(heap, (nd, (nr, nc)))
    if goal not in dist:
        return None
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return path


def path_chainage(path: Sequence[RowCol], resolution: float) -> FloatArray:
    """Distance along a path from its first pixel, in meters.

    Args:
        path: Pixels in order.
        resolution: Pixel size in meters.

    Returns:
        Cumulative distance per path pixel.
    """
    steps = [0.0] + [
        math.hypot(b[0] - a[0], b[1] - a[1]) * resolution for a, b in itertools.pairwise(path)
    ]
    return np.cumsum(np.array(steps, dtype=np.float64))


def nearest_on_path(
    pixels: NDArray[np.int64], path: NDArray[np.int64], chunk: int | None = None
) -> tuple[NDArray[np.int64], FloatArray]:
    """For each pixel, the index of the nearest path pixel and the distance to it (pixels).

    Args:
        pixels: ``(n, 2)`` rows and columns.
        path: ``(k, 2)`` rows and columns of the centerline.
        chunk: Pixels per block (default: sized to keep about 4 million distances per block).

    Returns:
        Indices into ``path`` and Euclidean distances in pixels.
    """
    if chunk is None:
        chunk = max(64, 4_000_000 // max(len(path), 1))
    index = np.empty(len(pixels), dtype=np.int64)
    dist = np.empty(len(pixels), dtype=np.float64)
    path_f = path.astype(np.float64)
    for start in range(0, len(pixels), chunk):
        block = pixels[start : start + chunk].astype(np.float64)
        d2 = ((block[:, None, :] - path_f[None, :, :]) ** 2).sum(axis=2)
        best = np.argmin(d2, axis=1)
        index[start : start + chunk] = best
        dist[start : start + chunk] = np.sqrt(d2[np.arange(len(block)), best])
    return index, dist


def land_ring(sub: BoolArray, river: BoolArray, inner_px: float, outer_px: float) -> BoolArray:
    """Land pixels whose Euclidean distance to a sub-reach lies in ``[inner_px, outer_px]``.

    Args:
        sub: The sub-reach.
        river: River mask (excluded from the ring).
        inner_px: Inner distance in pixels.
        outer_px: Outer distance in pixels.

    Returns:
        The ring.
    """
    ring = np.zeros_like(sub)
    points = np.argwhere(sub).astype(np.int64)
    if points.size == 0:
        return ring
    pad = math.ceil(outer_px)
    top, left = max(0, int(points[:, 0].min()) - pad), max(0, int(points[:, 1].min()) - pad)
    bottom = min(sub.shape[0], int(points[:, 0].max()) + pad + 1)
    right = min(sub.shape[1], int(points[:, 1].max()) + pad + 1)
    land = np.argwhere(~river[top:bottom, left:right]).astype(np.int64) + np.array([top, left])
    if land.size == 0:
        return ring
    _, dist = nearest_on_path(land, points)
    keep = land[(dist >= inner_px) & (dist <= outer_px)]
    ring[keep[:, 0], keep[:, 1]] = True
    return ring


# ----------------------------------------------------------------------------------------------
# Sub-reach placement
# ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Placement:
    """Where the two sub-reaches sit along the river, in meters of chainage."""

    upstream: tuple[float, float]
    downstream: tuple[float, float]
    confluence_inside: bool
    confluence_between: bool

    @property
    def separation_m(self) -> float:
        """Center-to-center distance along the river."""
        return (sum(self.downstream) - sum(self.upstream)) / 2


def place_subreaches(
    reach_length_m: float, confluences_m: Sequence[float], cfg: SubreachConfig
) -> Placement | None:
    """Place the sub-reaches near the target separation, avoiding confluences.

    The upstream sub-reach sits as close below the upstream anchor as possible; a confluence
    inside a sub-reach (plus buffer) is avoided when any placement allows it, else flagged.

    Args:
        reach_length_m: Length of the centerline.
        confluences_m: Chainage of tributary confluences on the centerline.
        cfg: Sub-reach settings.

    Returns:
        The placement, or None if the reach is too short for the minimum separation.
    """
    length, step = cfg.length_m, 250.0

    def hits(window: tuple[float, float]) -> bool:
        lo, hi = window[0] - cfg.confluence_buffer_m, window[1] + cfg.confluence_buffer_m
        return any(lo <= x <= hi for x in confluences_m)

    def make(up_start: float, separation: float) -> Placement | None:
        up = (up_start, up_start + length)
        down_start = up_start + separation
        down = (down_start, down_start + length)
        if down[1] > reach_length_m:
            return None
        between = any(up[1] < x < down[0] for x in confluences_m)
        return Placement(up, down, hits(up) or hits(down), between)

    candidates: list[tuple[float, Placement]] = []
    up_start = cfg.start_offset_m
    while up_start + length + cfg.separation_min_m <= reach_length_m:
        separation = cfg.separation_min_m
        while separation <= cfg.separation_max_m + 1e-9:
            placement = make(up_start, separation)
            if placement is not None:
                cost = abs(separation - cfg.separation_target_m) + 2 * (
                    up_start - cfg.start_offset_m
                )
                if placement.confluence_inside:
                    cost += 1e9
                candidates.append((cost, placement))
            separation += step
        up_start += step
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


# ----------------------------------------------------------------------------------------------
# The whole derivation
# ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Subreach:
    """One sub-reach on the 20 m grid."""

    name: str
    chainage_m: tuple[float, float]
    mask: BoolArray
    land_ring: BoolArray


@dataclass(frozen=True)
class RiverGeometry:
    """The derived river and sub-reaches of one site (or why the derivation failed)."""

    resolution: float
    threshold: float
    frequency_histogram: list[int]
    failed: str | None
    river_mask: BoolArray
    corridor: BoolArray | None = None
    centerline: list[RowCol] = field(default_factory=list)
    reach_length_m: float = 0.0
    anchor_shifts_m: dict[str, float] = field(default_factory=dict)
    placement: Placement | None = None
    subreaches: tuple[Subreach, ...] = ()
    width_px_10m: dict[str, float] = field(default_factory=dict)
    width_px_10m_raw: dict[str, float] = field(default_factory=dict)
    confluence_chainage_m: dict[str, float] = field(default_factory=dict)


def derive_geometry(
    freq: FloatArray,
    *,
    resolution: float,
    thresholds: Sequence[float],
    upstream: RowCol,
    downstream: RowCol,
    center: RowCol,
    confluences: dict[str, RowCol],
    excluded: BoolArray | None,
    snap_radius_m: float,
    corridor_half_width_m: float,
    erosion_px_10m: int,
    land_ring_m: tuple[float, float],
    subreach: SubreachConfig,
    bridge_gap_px: int = 0,
) -> RiverGeometry:
    """Derive the river, centerline, corridor and sub-reaches from the water frequency.

    Thresholds are tried in order (the first is the pre-registered one, the rest a documented
    fallback for rivers SCL rarely calls water); the first that connects the anchors is used.

    Args:
        freq: Water frequency on the 20 m grid.
        resolution: Grid resolution in meters.
        thresholds: Water-frequency thresholds, in the order to try.
        upstream: Upstream anchor pixel.
        downstream: Downstream anchor pixel.
        center: Site center pixel (only its snapping distance is reported).
        confluences: Tributary confluence pixels by name.
        excluded: Pixels never part of the river (pits, lakes), if any.
        snap_radius_m: How far anchors may be moved onto the mask.
        corridor_half_width_m: Corridor half-width around the centerline.
        erosion_px_10m: Bank erosion on the 10 m grid before measuring width.
        land_ring_m: Inner and outer distance of the land ring around each sub-reach.
        subreach: Sub-reach settings.
        bridge_gap_px: Gaps in the mask up to twice this many pixels (bridges, rapids) are
            bridged for connectivity and the centerline only; sub-reach pixels stay river pixels.

    Returns:
        The geometry; ``failed`` says why when no usable sub-reaches exist.
    """
    hist = histogram(freq)
    radius = snap_radius_m / resolution
    last_failure = "no threshold given"
    for threshold in thresholds:
        river = np.nan_to_num(freq, nan=0.0) >= threshold
        if excluded is not None:
            river &= ~excluded
        connected = close(river, bridge_gap_px)
        if excluded is not None:
            connected &= ~excluded
        found = snap_connected(connected, upstream, downstream, radius)
        if isinstance(found, str):
            last_failure = found.replace("{radius}", f"{snap_radius_m:.0f} m")
            continue
        snapped_up, snapped_down, region = found
        path = shortest_path(region, snapped_up[0], snapped_down[0])
        if path is None:
            last_failure = "no path between the anchors"
            continue
        return _finish(
            freq, river, region, path, threshold, hist, resolution, radius,
            snapped_up[1], snapped_down[1], center, confluences,
            corridor_half_width_m, erosion_px_10m, land_ring_m, subreach,
        )  # fmt: skip
    return RiverGeometry(resolution, thresholds[-1] if thresholds else math.nan, hist, last_failure,
                         np.zeros(freq.shape, dtype=bool))  # fmt: skip


def _finish(
    freq: FloatArray,
    river: BoolArray,
    region: BoolArray,
    path: list[RowCol],
    threshold: float,
    hist: list[int],
    resolution: float,
    radius: float,
    up_shift_px: float,
    down_shift_px: float,
    center: RowCol,
    confluences: dict[str, RowCol],
    corridor_half_width_m: float,
    erosion_px_10m: int,
    land_ring_m: tuple[float, float],
    cfg: SubreachConfig,
) -> RiverGeometry:
    chainage = path_chainage(path, resolution)
    length = float(chainage[-1])
    path_arr = np.array(path, dtype=np.int64)
    # Bridged gap pixels connect the channel but are not water: only river pixels can be corridor.
    pixels = np.argwhere(region & river).astype(np.int64)
    nearest, dist = nearest_on_path(pixels, path_arr)
    keep = dist * resolution <= corridor_half_width_m
    band = np.zeros(region.shape, dtype=bool)
    corridor_chain = np.full(region.shape, np.nan)
    kept = pixels[keep]
    band[kept[:, 0], kept[:, 1]] = True
    corridor_chain[kept[:, 0], kept[:, 1]] = chainage[nearest[keep]]
    # Main channel only: water inside the band but joined to the river only outside it (a pit or
    # pond linked by a long ditch, a loop of a tributary) is not corridor.
    corridor = connected_to(band, path)
    corridor_chain[~corridor] = np.nan

    shifts = {
        "upstream_anchor": up_shift_px * resolution,
        "downstream_anchor": down_shift_px * resolution,
    }
    snapped_center = snap(river, center, radius)
    shifts["center"] = snapped_center[1] * resolution if snapped_center else math.inf

    confluence_m: dict[str, float] = {}
    for name, rc in confluences.items():
        snapped = snap(corridor, rc, radius)
        if snapped is not None:
            confluence_m[name] = float(corridor_chain[snapped[0]])

    base = RiverGeometry(
        resolution, threshold, hist, None, river, corridor, path, length, shifts,
        confluence_chainage_m=confluence_m,
    )  # fmt: skip
    placement = place_subreaches(length, list(confluence_m.values()), cfg)
    if placement is None:
        return dataclasses.replace(
            base, failed=f"reach is {length / 1000:.1f} km, too short for the sub-reaches"
        )

    subreaches = []
    widths: dict[str, float] = {}
    raw_widths: dict[str, float] = {}
    for name, (lo, hi) in (("upstream", placement.upstream), ("downstream", placement.downstream)):
        sub = corridor & (corridor_chain >= lo) & (corridor_chain <= hi)
        if not sub.any():
            return dataclasses.replace(base, failed=f"{name} sub-reach is empty")
        ring = land_ring(sub, river, land_ring_m[0] / resolution, land_ring_m[1] / resolution)
        subreaches.append(Subreach(name, (lo, hi), sub, ring))
        fine = upsample2(sub)
        length_px10 = (hi - lo) / 10.0
        raw_widths[name] = float(fine.sum()) / length_px10
        widths[name] = float(erode(fine, erosion_px_10m).sum()) / length_px10
    return dataclasses.replace(
        base,
        placement=placement,
        subreaches=tuple(subreaches),
        width_px_10m=widths,
        width_px_10m_raw=raw_widths,
    )
