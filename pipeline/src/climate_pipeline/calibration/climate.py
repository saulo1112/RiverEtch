"""Stage 5: does rain or hydrology explain the reach's signal, and does the satellite see them?

5a fits, per signal, a season model (harmonics of the day of year) and a season + rain model,
both validated leave-one-hydrological-year-out; the skill is computed on the out-of-fold
predictions. A label is given only for a signal whose own model passed. 5b relates water extent
to same-day discharge or level per station. 5c compares climate phases (ENSO from the ONI) with
hydrological-year blocks. Nothing here reads a value the preregistration did not name.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
from numpy.typing import NDArray

from climate_pipeline.calibration.config import Climate, Enso, Width
from climate_pipeline.calibration.stats import (
    block_bootstrap_spearman,
    block_permutation_p,
    spearman,
)

FloatArray = NDArray[np.float64]
SEASON_CENTER = {"DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6, "JJA": 7,
                 "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12}  # fmt: skip


def hydrological_year(day: date, start_month: int) -> int:
    """The hydrological year a day belongs to, named by the year it ends in.

    Args:
        day: The day.
        start_month: First month (12: December to November).

    Returns:
        E.g. 2019 for 2018-12-05 with a December start.
    """
    return day.year + 1 if start_month > 1 and day.month >= start_month else day.year


def season_design(days: Sequence[date], harmonics: int) -> FloatArray:
    """Intercept and ``harmonics`` sine/cosine pairs of the day of year.

    Args:
        days: Days.
        harmonics: Number of harmonics.

    Returns:
        The design matrix.
    """
    t = np.array([d.timetuple().tm_yday for d in days], dtype=np.float64) / 365.25
    cols = [np.ones_like(t)]
    for k in range(1, harmonics + 1):
        cols += [np.sin(2 * math.pi * k * t), np.cos(2 * math.pi * k * t)]
    return np.column_stack(cols)


def rain_sums(daily: Mapping[date, float], day: date, windows: Sequence[int]) -> list[float]:
    """log1p of the rain summed over each window ending on the day (NaN if a day is missing).

    Args:
        daily: Day -> mm.
        day: The acquisition's local day.
        windows: Window lengths in days.

    Returns:
        One value per window.
    """
    out = []
    for w in windows:
        values = [daily.get(day - timedelta(days=k), math.nan) for k in range(w)]
        out.append(math.log1p(sum(values)) if all(math.isfinite(v) for v in values) else math.nan)
    return out


def out_of_fold(x: FloatArray, y: FloatArray, folds: Sequence[int]) -> FloatArray:
    """Least-squares predictions for each fold from a fit on the other folds.

    Args:
        x: Design matrix.
        y: Targets.
        folds: Fold of each row.

    Returns:
        Out-of-fold predictions (NaN where a fold's complement cannot be fitted).
    """
    f = np.asarray(folds)
    out = np.full(len(y), np.nan)
    for fold in np.unique(f):
        train = f != fold
        if train.sum() <= x.shape[1]:
            continue
        beta, *_ = np.linalg.lstsq(x[train], y[train], rcond=None)
        out[~train] = x[~train] @ beta
    return out


@dataclass
class SignalModel:
    """5a outcome for one signal."""

    signal: str
    n: int
    skill: float
    status: str  # "passed", "weak" or "insufficient_data"
    skill_chirps: float = math.nan
    skill_with_discharge: float = math.nan
    ar1: float = math.nan
    sigma: float = math.nan
    expected: dict[date, float] = field(default_factory=dict)

    def residual_z(self, day: date, value: float) -> float:
        """(observed - expected) / the robust sigma of the out-of-fold residuals.

        Args:
            day: The scene's day.
            value: Its observed value.

        Returns:
            The residual z (NaN without an expectation).
        """
        expected = self.expected.get(day, math.nan)
        if not (math.isfinite(expected) and self.sigma > 0):
            return math.nan
        return (value - expected) / self.sigma


def _skill(
    days: Sequence[date],
    y: FloatArray,
    extra: FloatArray,
    cfg: Climate,
) -> tuple[float, FloatArray]:
    folds = [hydrological_year(d, cfg.hydrological_year_start_month) for d in days]
    season = season_design(days, cfg.harmonics)
    full = np.column_stack([season, extra])
    pred_s, pred_f = out_of_fold(season, y, folds), out_of_fold(full, y, folds)
    ok = np.isfinite(pred_s) & np.isfinite(pred_f)
    sse_s = float(((y[ok] - pred_s[ok]) ** 2).sum())
    sse_f = float(((y[ok] - pred_f[ok]) ** 2).sum())
    return (1 - sse_f / sse_s if sse_s > 0 else math.nan), pred_f


def fit_signal(
    signal: str,
    observations: Sequence[tuple[date, float]],
    rain: Mapping[date, float],
    cfg: Climate,
    chirps: Mapping[date, float] | None = None,
    discharge: Mapping[date, float] | None = None,
) -> SignalModel:
    """5a for one signal: season vs season + rain, leave-one-hydrological-year-out.

    Args:
        signal: ``upstream``, ``downstream`` or ``delta``.
        observations: ``(day, value)`` of the usable scenes.
        rain: Catchment-mean daily rain (Open-Meteo), day -> mm.
        cfg: Climate settings.
        chirps: CHIRPS catchment-mean daily rain (sensitivity).
        discharge: Daily discharge near the reach (report-only regressor).

    Returns:
        The model, with out-of-fold expectations for the scenes it could use.
    """
    rows = [
        (d, v, rain_sums(rain, d, cfg.rain_windows_days))
        for d, v in observations
        if math.isfinite(v)
    ]
    rows = [r for r in rows if all(math.isfinite(x) for x in r[2])]
    hys = {hydrological_year(d, cfg.hydrological_year_start_month) for d, _, _ in rows}
    if len(rows) < 3 * (1 + 2 * cfg.harmonics + len(cfg.rain_windows_days)) or len(hys) < 3:
        return SignalModel(signal, len(rows), math.nan, "insufficient_data")
    days = [d for d, _, _ in rows]
    y = np.array([v for _, v, _ in rows])
    extra = np.array([r[2] for r in rows])
    skill, pred = _skill(days, y, extra, cfg)
    resid = y - pred
    ok = np.isfinite(resid)
    med = float(np.median(resid[ok]))
    sigma = max(1.4826 * float(np.median(np.abs(resid[ok] - med))), 1e-9)
    order = np.argsort([d.toordinal() for d in days])
    r_sorted = resid[order][np.isfinite(resid[order])]
    ar1 = float(np.corrcoef(r_sorted[:-1], r_sorted[1:])[0, 1]) if r_sorted.size > 3 else math.nan
    model = SignalModel(
        signal, len(rows), skill, "passed" if skill >= cfg.skill_min else "weak", ar1=ar1,
        sigma=sigma, expected={d: float(p) for d, p in zip(days, pred, strict=True)
                               if math.isfinite(p)},
    )  # fmt: skip
    if chirps is not None:
        alt = [rain_sums(chirps, d, cfg.rain_windows_days) for d in days]
        keep = [k for k, a in enumerate(alt) if all(math.isfinite(x) for x in a)]
        if len(keep) > 3 * extra.shape[1]:
            model.skill_chirps, _ = _skill(
                [days[k] for k in keep], y[keep], np.array([alt[k] for k in keep]), cfg
            )
    if discharge is not None:
        q = [discharge.get(d, math.nan) for d in days]
        keep = [k for k, v in enumerate(q) if math.isfinite(v) and v > 0]
        if len(keep) > 3 * (extra.shape[1] + 1):
            more = np.column_stack([extra[keep], np.log([q[k] for k in keep])])
            model.skill_with_discharge, _ = _skill([days[k] for k in keep], y[keep], more, cfg)
    return model


def label(
    anomalous_signals: Sequence[tuple[str, float]],
    models: Mapping[str, SignalModel],
    day: date,
    values: Mapping[str, float],
    label_z: float,
) -> dict[str, object]:
    """The climate context of one scene, by the preregistered rule.

    Args:
        anomalous_signals: ``(signal, D0 z)`` of the signals the D0 rule flagged.
        models: 5a model per signal.
        day: The scene's day.
        values: Signal -> observed value.
        label_z: |residual z| below which an anomaly is explained by climate.

    Returns:
        Fields of the observation record's ``climateContext``.
    """
    if not anomalous_signals:
        passed = any(m.status == "passed" for m in models.values())
        return {
            "status": "passed" if passed else "weak",
            "label": "normal" if passed else "not_evaluated",
            "rule": "no D0 anomaly" if passed else "no signal's season-and-rain model passed",
        }
    signal = max(anomalous_signals, key=lambda s: abs(s[1]))[0]
    model = models.get(signal)
    if model is None or model.status != "passed":
        return {"status": "weak", "signal": signal, "label": "not_evaluated",
                "rule": f"the {signal} season-and-rain model did not pass"}  # fmt: skip
    z = model.residual_z(day, values.get(signal, math.nan))
    if not math.isfinite(z):
        return {"status": "weak", "signal": signal, "label": "not_evaluated",
                "rule": "no out-of-fold expectation for this scene"}  # fmt: skip
    return {
        "status": "passed", "signal": signal, "model_id": f"5a-{signal}",
        "expected": round(model.expected[day], 4),
        "residual": round(values[signal] - model.expected[day], 4), "residual_z": round(z, 2),
        "label": "explained_by_climate" if abs(z) < label_z else "unexplained",
        "rule": f"|residual z| < {label_z:g}: explained_by_climate; otherwise unexplained",
    }  # fmt: skip


# ----------------------------------------------------------------------------------------------
# 5b: water extent against discharge or level
# ----------------------------------------------------------------------------------------------


def extent_flow(
    extents: Sequence[tuple[date, float]],
    series: Mapping[date, float],
    cfg: Width,
    seed: int,
    lag: int = 0,
) -> dict[str, float | int]:
    """Spearman of water extent against same-day (or lagged) discharge, month-block bootstrap.

    Args:
        extents: ``(day, extent km2)`` of the usable scenes.
        series: Day -> discharge (or level).
        cfg: Criteria.
        seed: Random seed.
        lag: Days the series is shifted (report-only when not 0).

    Returns:
        ``n``, ``rho``, ``low``, ``high``.
    """
    pairs = [
        (e, series.get(d - timedelta(days=lag), math.nan), (d.year, d.month)) for d, e in extents
    ]
    pairs = [p for p in pairs if math.isfinite(p[0]) and math.isfinite(p[1])]
    x, y = [p[0] for p in pairs], [p[1] for p in pairs]
    rho = spearman(x, y)
    low, high = block_bootstrap_spearman(x, y, [p[2] for p in pairs], cfg.resamples, seed)
    return {"n": len(pairs), "rho": rho, "low": low, "high": high}


# ----------------------------------------------------------------------------------------------
# 5c: ENSO phases
# ----------------------------------------------------------------------------------------------


def parse_oni(text: str) -> list[tuple[int, int, float]]:
    """The ONI table: ``(year, centre month, anomaly)`` per overlapping three-month season.

    Args:
        text: NOAA CPC ``oni.ascii.txt`` (``SEAS YR TOTAL ANOM``).

    Returns:
        Rows in file order.
    """
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] in SEASON_CENTER and re.fullmatch(r"\d{4}", parts[1]):
            out.append((int(parts[1]), SEASON_CENTER[parts[0]], float(parts[3])))
    return out


def enso_months(oni: Sequence[tuple[int, int, float]], cfg: Enso) -> dict[tuple[int, int], str]:
    """Month -> ``el_nino``, ``la_nina`` or ``neutral`` by the operational rule.

    A month is in a phase when its centred season belongs to a run of at least
    ``min_consecutive_seasons`` seasons all at or beyond the threshold.

    Args:
        oni: :func:`parse_oni` rows.
        cfg: Threshold and run length.

    Returns:
        The phase of every month in the table.
    """
    phases = {(y, m): "neutral" for y, m, _ in oni}
    for name, sign in (("el_nino", 1.0), ("la_nina", -1.0)):
        run: list[tuple[int, int]] = []
        for y, m, v in [*oni, (0, 0, 0.0)]:
            if y and sign * v >= cfg.threshold:
                run.append((y, m))
                continue
            if len(run) >= cfg.min_consecutive_seasons:
                for key in run:
                    phases[key] = name
            run = []
    return phases


def year_phases(phases: Mapping[tuple[int, int], str], start_month: int) -> dict[int, str]:
    """Hydrological year -> the phase of the majority of its months (a tie is neutral).

    Args:
        phases: Month phases.
        start_month: First month of the hydrological year.

    Returns:
        The phase of each hydrological year.
    """
    counts: dict[int, dict[str, int]] = {}
    for (y, m), phase in phases.items():
        hy = hydrological_year(date(y, m, 1), start_month)
        counts.setdefault(hy, {}).setdefault(phase, 0)
        counts[hy][phase] += 1
    out = {}
    for hy, c in counts.items():
        top = max(c.values())
        winners = [p for p, n in c.items() if n == top]
        out[hy] = winners[0] if len(winners) == 1 else "neutral"
    return out


def monthly_anomalies(observations: Sequence[tuple[date, float]]) -> list[tuple[date, float]]:
    """Each value minus the median of its calendar month (all years).

    Args:
        observations: ``(day, value)``.

    Returns:
        ``(day, anomaly)``.
    """
    by_month: dict[int, list[float]] = {}
    for d, v in observations:
        if math.isfinite(v):
            by_month.setdefault(d.month, []).append(v)
    medians = {m: float(np.median(v)) for m, v in by_month.items()}
    return [(d, v - medians[d.month]) for d, v in observations if math.isfinite(v)]


def enso_test(
    observations: Sequence[tuple[date, float]],
    month_phase: Mapping[tuple[int, int], str],
    cfg: Climate,
    seed: int,
    alternative: str,
) -> dict[str, object]:
    """La Niña minus El Niño mean anomaly, permuting hydrological-year phases; episodes scored.

    Args:
        observations: ``(day, value)``.
        month_phase: Month -> phase.
        cfg: Climate settings.
        seed: Random seed.
        alternative: ``greater`` (La Niña above El Niño, as for water extent) or ``two-sided``.

    Returns:
        The test, the per-episode hits and misses, and the neutral-year false alarms.
    """
    anomalies = monthly_anomalies(observations)
    if not anomalies:
        return {"n": 0}
    values = np.array([a for _, a in anomalies])
    sigma = 1.4826 * float(np.median(np.abs(values - np.median(values))))
    start = cfg.hydrological_year_start_month
    hy_phase = year_phases(month_phase, start)
    blocks = [hydrological_year(d, start) for d, _ in anomalies]
    labels = [hy_phase.get(b, "neutral") for b in blocks]
    diff, p = block_permutation_p(
        values.tolist(), labels, blocks, "la_nina", "el_nino", cfg.enso.permutations, seed,
        alternative,
    )  # fmt: skip
    magnitude = cfg.enso.magnitude_sigma * sigma
    episodes: list[dict[str, object]] = []
    current: tuple[str, list[float], date] | None = None
    for d, a in sorted(anomalies):
        phase = month_phase.get((d.year, d.month), "neutral")
        if current and current[0] == phase:
            current[1].append(a)
            continue
        if current and current[0] != "neutral":
            episodes.append(_episode(current, magnitude, alternative))
        current = (phase, [a], d)
    if current and current[0] != "neutral":
        episodes.append(_episode(current, magnitude, alternative))
    neutral_years: dict[int, list[float]] = {}
    for b, lab, a in zip(blocks, labels, values.tolist(), strict=True):
        if lab == "neutral":
            neutral_years.setdefault(b, []).append(a)
    false_alarms = sum(1 for v in neutral_years.values() if abs(float(np.mean(v))) > magnitude)
    return {
        "n": len(anomalies), "sigma": sigma, "diff_la_nina_minus_el_nino": diff, "p": p,
        "alternative": alternative, "episodes": episodes, "false_alarms": false_alarms,
        "neutral_years": len(neutral_years),
        "n_la_nina": labels.count("la_nina"), "n_el_nino": labels.count("el_nino"),
    }  # fmt: skip


def _episode(
    current: tuple[str, list[float], date], magnitude: float, alternative: str
) -> dict[str, object]:
    phase, anomalies, first = current
    mean = float(np.mean(anomalies))
    moved = abs(mean) > magnitude
    if alternative == "greater":
        expected = 1 if phase == "la_nina" else -1
        outcome = "hit" if moved and math.copysign(1, mean) == expected else "miss"
    else:
        outcome = ("up" if mean > 0 else "down") if moved else "no move"
    return {"phase": phase, "start": first.isoformat(), "n": len(anomalies),
            "mean_anomaly": round(mean, 6), "outcome": outcome}  # fmt: skip
