"""Quick-look figures (PNG, < 300 KB each): NDTI series, NDTI maps and water masks.

The series show rain and events; the mask figure shows the water frequency each site's reach was
derived from, with its anchors, centerline and sub-reaches. NDTI uses one colormap, labeled
"relative index", and one fixed color stretch per site, so maps of the same site are comparable
with each other and never read as turbidity in physical units.
"""

from __future__ import annotations

import io
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure
from numpy.typing import NDArray

from climate_pipeline.screening.events import CatalogEvent, EventOutcome
from climate_pipeline.screening.mask import RiverGeometry
from climate_pipeline.screening.stage2 import Stage2Result

MAX_PNG_BYTES = 300_000
COLORMAP = "cividis"
INDEX_LABEL = "NDTI (relative index)"
STATUS_COLORS = {"hit": "#b2182b", "miss": "#2166ac", "unobservable": "#878787"}
FREQUENCY_COLORMAP = "Blues"
SUBREACH_COLORS = {"upstream": "#e66101", "downstream": "#5e3c99"}


def save_png(fig: Figure, path: Path, max_bytes: int = MAX_PNG_BYTES) -> int:
    """Save a figure as PNG, lowering the resolution until it fits the size limit.

    Args:
        fig: The figure.
        path: Output file.
        max_bytes: Size limit.

    Returns:
        The file size in bytes.

    Raises:
        ValueError: If even the lowest resolution is too large.
    """
    for dpi in (110, 90, 72, 60, 48):
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight", metadata={"Software": None})
        data = buffer.getvalue()
        if len(data) <= max_bytes:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            plt.close(fig)
            return len(data)
    plt.close(fig)
    raise ValueError(f"{path.name}: cannot fit under {max_bytes} bytes")


def plot_series(
    result: Stage2Result,
    daily_rain: dict[date, float],
    outcomes: Sequence[EventOutcome],
    context_events: Sequence[CatalogEvent],
    threshold: float,
    start: date,
    end: date,
    path: Path,
) -> int:
    """NDTI per sub-reach, the difference's z-score, daily rain and catalog events over time.

    Args:
        result: The site's stage-2 result.
        daily_rain: Daily rain at the site center (local days).
        outcomes: Scored events with their status (window shaded by status).
        context_events: Unscored events (dashed line at their start).
        threshold: |z| threshold.
        start: Period start.
        end: Period end.
        path: Output PNG.

    Returns:
        The file size in bytes.
    """
    usable = result.usable()
    fig, axes = plt.subplots(3, 1, figsize=(10, 6.4), sharex=True, height_ratios=[3, 2, 1.3])
    ax_ndti, ax_z, ax_rain = axes
    times = [s.datetime for s in usable]
    for signal, color, face in (
        ("upstream", "#4d4d4d", "none"),
        ("downstream", "#d6604d", "#d6604d"),
    ):
        values = [s.values[signal] for s in usable]
        ax_ndti.plot(times, values, "o", ms=4, color=color, mfc=face, label=f"{signal} sub-reach")
    flagged = [s for s in usable if s.anomalous(threshold)]
    for s in flagged:
        marker = "^" if s.rain_coincident else "*"
        ax_ndti.plot(
            [s.datetime], [s.values["downstream"]], marker, ms=10, mfc="none", mec="#b2182b"
        )
    ax_ndti.set_ylabel(INDEX_LABEL)
    ax_ndti.legend(loc="upper left", fontsize=8, frameon=False)
    ax_ndti.set_title(
        f"{result.site.name}: NDTI per scene "
        "(relative index; * anomaly, ^ rain-coincident anomaly)",
        fontsize=10,
    )
    z = [s.z.get("delta", math.nan) for s in usable]
    ax_z.plot(times, z, "o", ms=3.5, color="#2166ac")
    for level in (threshold, -threshold):
        ax_z.axhline(level, color="#b2182b", lw=0.8, ls="--")
    ax_z.axhline(0, color="#999999", lw=0.6)
    ax_z.set_ylabel("z (downstream - upstream)", fontsize=8)
    days = sorted(d for d in daily_rain if start <= d <= end)
    ax_rain.bar(
        [datetime(d.year, d.month, d.day) for d in days],
        [daily_rain[d] for d in days],
        width=1.0,
        color="#4393c3",
    )
    ax_rain.set_ylabel("rain mm/day", fontsize=8)
    for outcome in outcomes:
        first = outcome.event.date_start - timedelta(days=2)
        last = outcome.event.date_end + timedelta(days=10)
        for ax in axes:
            ax.axvspan(
                datetime(first.year, first.month, first.day),
                datetime(last.year, last.month, last.day),
                color=STATUS_COLORS.get(outcome.status, "#878787"),
                alpha=0.18,
                lw=0,
            )
        ax_ndti.annotate(
            outcome.event.event_id,
            (datetime(first.year, first.month, first.day), 1.0),
            xycoords=("data", "axes fraction"),
            fontsize=6,
            rotation=90,
            va="top",
        )
    for event in context_events:
        for ax in axes:
            ax.axvline(
                datetime(event.date_start.year, event.date_start.month, event.date_start.day),
                color="#878787",
                lw=0.6,
                ls=":",
            )
    ax_rain.set_xlim(
        datetime(start.year, start.month, start.day), datetime(end.year, end.month, end.day)
    )
    fig.text(
        0.01,
        0.005,
        "Shaded: catalog event windows (red hit, blue miss, grey unobservable). "
        "Levels are comparable only within this site.",
        fontsize=7,
    )
    return save_png(fig, path)


@dataclass(frozen=True)
class MapPanel:
    """One NDTI map to show."""

    title: str
    ndti: NDArray[np.float64]


def site_stretch(values: Sequence[float]) -> tuple[float, float]:
    """A fixed color range for all maps of a site, from its sub-reach medians.

    Args:
        values: NDTI medians of the site's usable scenes.

    Returns:
        ``(vmin, vmax)``.
    """
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        return (-0.3, 0.3)
    lo, hi = np.percentile(finite, [2, 98])
    return float(lo) - 0.05, float(hi) + 0.05


def plot_maps(
    site_name: str,
    panels: Sequence[MapPanel],
    window: tuple[slice, slice],
    stretch: tuple[float, float],
    path: Path,
) -> int:
    """NDTI maps side by side with one colormap and one fixed stretch.

    Args:
        site_name: Title prefix.
        panels: Maps to show (same grid).
        window: Rows and columns to show (around the sub-reaches).
        stretch: ``(vmin, vmax)``.
        path: Output PNG.

    Returns:
        The file size in bytes.
    """
    rows = window[0].stop - window[0].start
    cols = window[1].stop - window[1].start
    wide = cols > 1.5 * rows
    shape = (len(panels), 1) if wide else (1, len(panels))
    aspect = rows / max(cols, 1)
    size = (
        (9.0, 1.0 + len(panels) * (7.5 * aspect + 0.7))
        if wide
        else (3.6 * len(panels), 1.2 + 3.4 * min(aspect, 1.5))
    )
    fig, grid = plt.subplots(*shape, figsize=size, squeeze=False)
    axes = grid[:, 0] if wide else grid[0]
    image = None
    for ax, panel in zip(axes, panels, strict=True):
        data = panel.ndti[window]
        step = max(1, math.ceil(max(data.shape) / 700))
        image = ax.imshow(
            np.ma.masked_invalid(data[::step, ::step]),
            cmap=COLORMAP,
            vmin=stretch[0],
            vmax=stretch[1],
            interpolation="nearest",
        )
        ax.set_title(panel.title, fontsize=8)
        ax.set_xticks([])
        ax.set_yticks([])
    if image is not None:
        bar = fig.colorbar(image, ax=list(axes), shrink=0.8)
        bar.set_label(INDEX_LABEL)
    fig.suptitle(
        f"{site_name}: NDTI maps (relative index, fixed stretch for this site)", fontsize=9
    )
    return save_png(fig, path)


def plot_mask(
    title: str,
    frequency: NDArray[np.float64],
    geometry: RiverGeometry,
    anchors: dict[str, tuple[int, int]],
    path: Path,
) -> int:
    """The water frequency of a site's AOI with its derived reach, to check anchors by eye.

    Args:
        title: Figure title (site and mask source).
        frequency: The water-frequency layer the mask came from (20 m grid; NaN = too few
            observations).
        geometry: The derived geometry (river region, centerline, sub-reaches), possibly failed.
        anchors: Configured anchor positions as (row, col), by name.
        path: Output PNG.

    Returns:
        The file size in bytes.
    """
    step = max(1, math.ceil(max(frequency.shape) / 600))
    # Steps of 0.1 keep the PNG small and match the histogram bins of the summary.
    shown = np.floor(frequency[::step, ::step] * 10) / 10
    rows, cols = shown.shape
    fig, ax = plt.subplots(figsize=(7.0, 0.8 + 6.2 * min(rows / max(cols, 1), 1.6)))
    image = ax.imshow(
        np.ma.masked_invalid(shown),
        cmap=FREQUENCY_COLORMAP,
        vmin=0,
        vmax=1,
        interpolation="nearest",
    )
    if math.isfinite(geometry.threshold):
        ax.contour(
            (frequency[::step, ::step] >= geometry.threshold).astype(float),
            levels=[0.5],
            colors="#999999",
            linewidths=0.5,
        )
    for sub in geometry.subreaches:
        ax.contour(
            sub.mask[::step, ::step].astype(float),
            levels=[0.5],
            colors=SUBREACH_COLORS.get(sub.name, "black"),
            linewidths=1.2,
        )
        ax.plot([], [], color=SUBREACH_COLORS.get(sub.name, "black"), label=f"{sub.name} sub-reach")
    if geometry.centerline:
        line = np.array(geometry.centerline, dtype=float) / step
        ax.plot(line[:, 1], line[:, 0], color="#d01c8b", linewidth=0.8, label="centerline")
        ax.plot(
            [line[0, 1], line[-1, 1]],
            [line[0, 0], line[-1, 0]],
            "o",
            color="#d01c8b",
            markersize=4,
            label="snapped anchors",
        )
    for name, (row, col) in anchors.items():
        ax.plot(col / step, row / step, "x", color="black", markersize=7)
        ax.annotate(name, (col / step, row / step), fontsize=7, xytext=(4, 4),
                    textcoords="offset points")  # fmt: skip
    ax.plot([], [], "x", color="black", label="configured anchors")
    ax.legend(loc="lower right", fontsize=7, framealpha=0.8)
    ax.set_xticks([])
    ax.set_yticks([])
    threshold = f"threshold {geometry.threshold:g}" if math.isfinite(geometry.threshold) else ""
    status = f"failed: {geometry.failed}" if geometry.failed else "reach derived"
    ax.set_title(f"{title}\n{status}; {threshold} (grey outline)", fontsize=8)
    bar = fig.colorbar(image, ax=ax, shrink=0.7)
    bar.set_label("water frequency (share of clear observations)")
    return save_png(fig, path)
