"""The feature set F of Route A (preregistered in ``pipeline/water-quality.yaml``).

From each scene's band medians: the log of eight bands and six ratios (floored), B8A - B11 and B11
as they are, the sun zenith angle, the log of the station's channel width and the core share of
the window (core-window water pixels over 300 m-window water pixels). Station ids, coordinates and
dates are never features. A value that cannot be computed is NaN, and a model leaves its row out.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping, Sequence

from climate_pipeline.calibration.matchups import SceneRow
from climate_pipeline.quality.config import Features


def names(spec: Features) -> list[str]:
    """The feature names of F, in order.

    Args:
        spec: The settings' feature set.

    Returns:
        E.g. ``["log_B02", ..., "log_B8A/B04", ..., "B8A-B11", "B11", "sun_zenith", ...]``.
    """
    return [*(f"log_{b}" for b in spec.log_bands), *(f"log_{r}" for r in spec.log_ratios),
            *spec.linear, *spec.geometry]  # fmt: skip


def _band(bands: Mapping[str, float], name: str) -> float:
    return bands.get(name, math.nan)


def compute(spec: Features, bands: Mapping[str, float], sun_zenith: float, width_m: float,
            core_share: float) -> dict[str, float]:  # fmt: skip
    """F for one scene.

    Args:
        spec: The settings' feature set.
        bands: Band medians (reflectance).
        sun_zenith: Degrees.
        width_m: The station's main-channel width.
        core_share: Core-window water pixels over 300 m-window water pixels.

    Returns:
        Feature name -> value.
    """
    out: dict[str, float] = {}

    def floored_log(v: float) -> float:
        return math.log(max(v, spec.floor)) if math.isfinite(v) else math.nan

    for b in spec.log_bands:
        out[f"log_{b}"] = floored_log(_band(bands, b))
    for r in spec.log_ratios:
        num, den = r.split("/")
        a, c = _band(bands, num), _band(bands, den)
        ok = math.isfinite(a) and math.isfinite(c)
        out[f"log_{r}"] = floored_log(max(a, spec.floor) / max(c, spec.floor)) if ok else math.nan
    for item in spec.linear:
        if "-" in item:
            first, second = item.split("-")
            out[item] = _band(bands, first) - _band(bands, second)
        else:
            out[item] = _band(bands, item)
    geometry = {"sun_zenith": sun_zenith,
                "log_width_m": math.log(width_m) if width_m > 0 else math.nan,
                "core_share": core_share}  # fmt: skip
    for g in spec.geometry:
        out[g] = geometry[g]
    return out


def with_features(spec: Features, windows: Mapping[str, Sequence[SceneRow]],
                  widths: Mapping[str, float]) -> dict[str, list[SceneRow]]:  # fmt: skip
    """Every window's scenes with F added to their features.

    Args:
        spec: The settings' feature set.
        windows: ``"300m"`` and ``"core"`` scenes of the same acquisitions.
        widths: Station -> main-channel width (m).

    Returns:
        The same windows, each scene's features extended with F.
    """
    full = {(s.station, s.key): s.stats.get("valid_px", math.nan) for s in windows["300m"]}
    core = {(s.station, s.key): s.stats.get("valid_px", math.nan) for s in windows["core"]}
    out = {}
    for name, scenes in windows.items():
        rows = []
        for s in scenes:
            k = (s.station, s.key)
            total = full.get(k, math.nan)
            share = (
                core.get(k, math.nan) / total if math.isfinite(total) and total > 0 else math.nan
            )
            f = compute(spec, s.bands, s.stats.get("sun_zenith", math.nan),
                        widths.get(s.station, math.nan), share)  # fmt: skip
            rows.append(dataclasses.replace(s, features={**s.features, **f}))
        out[name] = rows
    return out
