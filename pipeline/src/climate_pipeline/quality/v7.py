"""Water-quality v7 and v7.1's evaluation (preregistration v7 and v7.1).

Read from v7's snapshots (``fetch_v7``), v6's Landsat windows at the Platte and v6's
water-temperature card:

* **Discharge at the Platte (v7, A):** each clear Sentinel-2 pass's water fraction of the active
  channel, by SCL (Q1) or MNDWI (Q2), in a power law ln Q = a + b ln f with Duan's smearing; the
  null Q0 is the gauge's day-of-year climatology of daily means.
* **Specific conductance at the Platte (v7.1, A):** the same water fraction (the detection
  chosen for discharge), C1 a power law, C2 the same plus an annual harmonic; the null C0 as Q0.
* **Dissolved oxygen at the Platte (v7.1, B):** oxygen saturation (Benson & Krause 1984) at v6's
  Landsat water temperature and the gauge's datum pressure, as it is (O1) or adjusted a + b · C*
  (O2); the null O0 as Q0.
* **Water temperature at Belle Chasse (v7.1, C):** v6's method validated at Baton Rouge (W0, W1,
  W2), approved else provisional values, capped at _estimated_, then applied at Belle Chasse.

Common rules: training is hydrological years 2019 to 2023; the selection leaves one year out
within training; the locked test is hydrological years 2024 and 2025, scored once with the
training fit; the prospective check (from 2025-12-01, provisional values labelled) never enters a
level; an input outside the training pairs' range abstains; intervals are split conformal on the
inner leave-one-year-out residuals.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np

from climate_pipeline.calibration import stats
from climate_pipeline.quality import cards, fetch_v7, v6, variables
from climate_pipeline.quality.config import QualityConfig
from climate_pipeline.sources import usgs

LOCK_START = datetime(2023, 12, 1, tzinfo=UTC)
LOCK_END = datetime(2025, 11, 30, 23, 59, 59, tzinfo=UTC)
PROSPECTIVE_START = datetime(2025, 12, 1, tzinfo=UTC)
CFS_TO_M3S = 0.0283168466
FT_TO_M = 0.3048
CLIMATOLOGY_DAYS = 15
MIN_WATER_PX = 10
RESAMPLES = 2000
COVERAGE_MIN = 0.8
RHO_LOW_MIN = 0.3
VALIDATED_MIN_PAIRS, VALIDATED_MIN_YEARS = 20, 2
# The preregistered thresholds (v7 A; v7.1 A, B and C).
DISCHARGE_LEVELS = {
    "validated": {"mdsa": 30.0, "sspb": 15.0, "null_ratio": 0.8, "factor": 2.0},
    "estimated": {"mdsa": 45.0, "sspb": 25.0, "null_ratio": 1.0, "factor": 2.5},
}
CONDUCTANCE_LEVELS = {
    "validated": {"mdsa": 15.0, "sspb": 10.0, "null_ratio": 0.8, "factor": 1.5},
    "estimated": {"mdsa": 25.0, "sspb": 15.0, "null_ratio": 1.0, "factor": 2.0},
}
OXYGEN_LEVELS = {
    "validated": {"mae": 0.75, "bias": 0.4, "null_ratio": 0.8, "half_width": 1.5},
    "estimated": {"mae": 1.2, "bias": 0.75, "null_ratio": 1.0, "half_width": 2.5},
}
TEMPERATURE_LEVELS = {
    "validated": {"mae": 1.5, "bias": 0.75, "null_ratio": 0.8, "half_width": 3.0},
    "estimated": {"mae": 2.5, "bias": 1.5, "null_ratio": 1.0, "half_width": 4.5},
}
DISCHARGE_MARGIN, CONDUCTANCE_MARGIN, OXYGEN_MARGIN, TEMPERATURE_MARGIN = 5.0, 3.0, 0.3, 0.3

Null = Callable[[datetime], float]


def _nan_scores(n: int, keys: Sequence[str]) -> dict[str, float]:
    return {"n": float(n), **{k: math.nan for k in keys}}


# --- shared helpers -------------------------------------------------------------------------


def value_at(readings: Sequence[usgs.Reading], when: datetime, cfg: QualityConfig,
             provisional_ok: bool) -> tuple[float, str]:  # fmt: skip
    """The gauge's value at an overpass: approved, else (when allowed) provisional.

    Args:
        readings: The site's readings around the overpass.
        when: The overpass.
        cfg: The v2 settings (the overpass rule).
        provisional_ok: Fall back to provisional values.

    Returns:
        ``(value, approval)``; NaN and ``""`` when none qualifies.
    """
    u = cfg.usgs
    for status in ("Approved", "Provisional") if provisional_ok else ("Approved",):
        value, _, _ = usgs.overpass_value(readings, when, u.overpass_median_minutes,
                                          u.overpass_nearest_minutes, status,
                                          u.exclude_qualified)  # fmt: skip
        if math.isfinite(value):
            return value, status
    return math.nan, ""


def _doy_distance(a: int, b: int) -> int:
    d = abs(a - b)
    return min(d, 365 - d)


def daily_null(rows: Sequence[Mapping[str, str]], site: str, parameter: str,
               scale: float = 1.0) -> Null:  # fmt: skip
    """The gauge's day-of-year climatology: the median approved daily mean within ±15 days.

    Args:
        rows: ``daily.csv`` rows (the training years).
        site: The gauge.
        parameter: The parameter code.
        scale: Unit conversion.

    Returns:
        A function of the day.
    """
    values = []
    for r in rows:
        if (r["site_id"] != site or r["parameter"] != parameter or r["approval"] != "Approved"
                or r["qualified"] == "1" or not r["value"]):  # fmt: skip
            continue
        values.append((date.fromisoformat(r["day"]).timetuple().tm_yday, float(r["value"]) * scale))

    def at(when: datetime) -> float:
        day = when.timetuple().tm_yday
        near = [v for d, v in values if _doy_distance(d, day) <= CLIMATOLOGY_DAYS]
        return float(np.median(near)) if near else math.nan

    return at


def _q90(errors: Sequence[float]) -> float:
    return float(np.quantile(errors, 0.9, method="higher")) if errors else math.nan


def log_scores(est: Sequence[float], obs: Sequence[float], blocks: Sequence[Any], factor: float,
               seed: int) -> dict[str, float]:  # fmt: skip
    """MdSA, SSPB, Spearman (with its block-bootstrap lower bound) and the interval coverage.

    Args:
        est: Estimates (NaN: abstained).
        obs: Gauge values.
        blocks: Each pair's hydrological year.
        factor: The 90 % interval factor (NaN: no coverage).
        seed: Bootstrap seed.

    Returns:
        The scores of the finite pairs.
    """
    keep = [k for k, (e, o) in enumerate(zip(est, obs, strict=True))
            if math.isfinite(e) and e > 0 and o > 0]  # fmt: skip
    keys = ("mdsa", "sspb", "rho", "rho_low", "coverage90")
    if len(keep) < 3:
        return _nan_scores(len(keep), keys)
    e, o = [est[k] for k in keep], [obs[k] for k in keep]
    low, _ = stats.block_bootstrap_spearman(e, o, [blocks[k] for k in keep], RESAMPLES, seed)
    errors = np.abs(np.log(np.asarray(e) / np.asarray(o)))
    coverage = float(np.mean(errors <= math.log(factor))) if math.isfinite(factor) else math.nan
    return {"n": float(len(keep)), "mdsa": stats.mdsa(e, o), "sspb": stats.sspb(e, o),
            "rho": stats.spearman(e, o), "rho_low": low, "coverage90": coverage}  # fmt: skip


def ratio_level(lock: Mapping[str, float], years: int, null_mdsa: float, factor: float,
                levels: Mapping[str, Mapping[str, float]]) -> str:  # fmt: skip
    """A level on MdSA (discharge, conductance), as preregistered.

    Args:
        lock: The chosen candidate's locked-test scores.
        years: Hydrological years with an estimate in the locked test.
        null_mdsa: The null's locked-test MdSA.
        factor: The median 90 % interval factor.
        levels: The thresholds per level.

    Returns:
        ``validated``, ``estimated``, ``indicative`` or ``none``.
    """
    for level, t in levels.items():
        if level == "validated" and not (
            lock["n"] >= VALIDATED_MIN_PAIRS and years >= VALIDATED_MIN_YEARS
        ):
            continue
        beats = (lock["mdsa"] <= t["null_ratio"] * null_mdsa if level == "validated"
                 else lock["mdsa"] < null_mdsa)  # fmt: skip
        if (lock["mdsa"] <= t["mdsa"] and abs(lock["sspb"]) <= t["sspb"] and beats
                and lock["coverage90"] >= COVERAGE_MIN and factor <= t["factor"]):  # fmt: skip
            return level
    return "indicative" if lock.get("rho_low", -1.0) > RHO_LOW_MIN else "none"


def absolute_level(lock: Mapping[str, float], years: int, null_mae: float, half_width: float,
                   levels: Mapping[str, Mapping[str, float]]) -> str:  # fmt: skip
    """A level on MAE (oxygen, temperature), as preregistered.

    Args:
        lock: The chosen candidate's locked-test scores.
        years: Hydrological years with an estimate in the locked test.
        null_mae: The null's locked-test MAE.
        half_width: The 90 % half-width.
        levels: The thresholds per level.

    Returns:
        ``validated``, ``estimated``, ``indicative`` or ``none``.
    """
    for level, t in levels.items():
        if level == "validated" and not (
            lock["n"] >= VALIDATED_MIN_PAIRS and years >= VALIDATED_MIN_YEARS
        ):
            continue
        beats = (lock["mae"] <= t["null_ratio"] * null_mae if level == "validated"
                 else lock["mae"] < null_mae)  # fmt: skip
        narrow = lock["coverage90"] >= COVERAGE_MIN and half_width <= t["half_width"]
        if lock["mae"] <= t["mae"] and abs(lock["bias"]) <= t["bias"] and beats and narrow:
            return level
    return "indicative" if lock.get("rho_low", -1.0) > RHO_LOW_MIN else "none"


def _years(pairs: Sequence[Any], est: Sequence[float]) -> int:
    return len({p.year for p, e in zip(pairs, est, strict=True) if math.isfinite(e)})


def _split(pairs: Sequence[Any]) -> tuple[list[Any], list[Any], list[Any]]:
    train = [p for p in pairs if p.time < LOCK_START and p.approval == "Approved"]
    lock = [p for p in pairs if LOCK_START <= p.time <= LOCK_END and p.approval == "Approved"]
    later = [p for p in pairs if p.time >= PROSPECTIVE_START]
    return train, lock, later


# --- the water surface: discharge and conductance --------------------------------------------


@dataclass(frozen=True)
class SurfacePair:
    """A clear Sentinel-2 pass's water fractions and the gauge's value at the overpass."""

    time: datetime
    f_scl: float
    f_mndwi: float
    value: float
    approval: str

    @property
    def year(self) -> int:
        """Its hydrological year."""
        return v6.hydro_year(self.time)

    def f(self, feature: str) -> float:
        """The water fraction by ``scl`` or ``mndwi``."""
        return self.f_scl if feature == "scl" else self.f_mndwi


def surface_pairs(cfg: QualityConfig, data: Mapping[str, Any], parameter: str,
                  scale: float) -> list[SurfacePair]:  # fmt: skip
    """The clear passes with the Platte gauge's value (approved, else provisional, labelled).

    Args:
        cfg: The v2 settings.
        data: v7's snapshots.
        parameter: ``00060`` or ``00095``.
        scale: Unit conversion.

    Returns:
        Pairs, by time.
    """
    readings = v6._readings(data["readings"]).get((fetch_v7.PLATTE_GAUGE, parameter), [])
    out = []
    for r in data["surface"]:
        if r["clear"] != "1" or int(r["clear_px"]) <= 0:
            continue
        clear = int(r["clear_px"])
        f_scl = int(r["scl_water_px"]) / clear
        f_mndwi = (
            int(r["mndwi_water_px"]) / clear if r["mndwi_water_px"] not in ("", "-1") else math.nan
        )
        when = datetime.fromisoformat(r["datetime_utc"])
        value, approval = value_at(readings, when, cfg, provisional_ok=True)
        if math.isfinite(value) and value > 0:
            out.append(SurfacePair(when, f_scl, f_mndwi, value * scale, approval))
    return sorted(out, key=lambda p: p.time)


@dataclass(frozen=True)
class PowerLaw:
    """ln y = a + b ln f (+ an annual harmonic), with Duan's smearing and its fitted range."""

    feature: str
    coefficients: tuple[float, ...]
    smearing: float
    f_min: float
    f_max: float
    harmonic: bool

    def predict(self, f: float, when: datetime) -> float:
        """The estimate, or NaN when ``f`` lies outside the fitted range (abstention)."""
        if not (math.isfinite(f) and f > 0 and self.f_min <= f <= self.f_max):
            return math.nan
        x = [1.0, math.log(f)] + (_harmonic(when) if self.harmonic else [])
        return (
            math.exp(sum(c * v for c, v in zip(self.coefficients, x, strict=True))) * self.smearing
        )


def _harmonic(when: datetime) -> list[float]:
    angle = 2 * math.pi * when.timetuple().tm_yday / 365.25
    return [math.sin(angle), math.cos(angle)]


def fit_power(pairs: Sequence[SurfacePair], feature: str, harmonic: bool) -> PowerLaw | None:
    """OLS in log space with Duan's smearing (None with too few usable pairs).

    Args:
        pairs: Training pairs.
        feature: ``scl`` or ``mndwi``.
        harmonic: Add the annual harmonic.

    Returns:
        The fit.
    """
    use = [p for p in pairs if math.isfinite(p.f(feature)) and p.f(feature) > 0 and p.value > 0]
    if len(use) < (5 if harmonic else 3):
        return None
    x = np.array([[1.0, math.log(p.f(feature))] + (_harmonic(p.time) if harmonic else [])
                  for p in use])  # fmt: skip
    y = np.log([p.value for p in use])
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    smearing = float(np.mean(np.exp(y - x @ coef)))
    fs = [p.f(feature) for p in use]
    return PowerLaw(feature, tuple(float(c) for c in coef), smearing, min(fs), max(fs), harmonic)


def loyo_power(pairs: Sequence[SurfacePair], feature: str, harmonic: bool) -> list[float]:
    """Each pair's estimate by a fit without its hydrological year (NaN: abstained).

    Args:
        pairs: Training pairs.
        feature: ``scl`` or ``mndwi``.
        harmonic: Add the annual harmonic.

    Returns:
        One estimate per pair.
    """
    out = [math.nan] * len(pairs)
    for y in sorted({p.year for p in pairs}):
        model = fit_power([p for p in pairs if p.year != y], feature, harmonic)
        if model is None:
            continue
        for k, p in enumerate(pairs):
            if p.year == y:
                out[k] = model.predict(p.f(feature), p.time)
    return out


def evaluate_power(*, target: str, unit: str, slug: str, site: str, pairs: Sequence[SurfacePair],
                   candidates: Mapping[str, tuple[str, bool]], null: Null,
                   levels: Mapping[str, Mapping[str, float]], margin: float, seed: int,
                   aoi_sha256: str) -> dict[str, Any]:  # fmt: skip
    """One water-surface target: selection, locked test, interval, level, prospective check, card.

    Args:
        target: ``discharge`` or ``specific_conductance``.
        unit: Its unit.
        slug: The reach.
        site: The gauge.
        pairs: Its pairs (every approval state).
        candidates: Id -> (water detection, harmonic), simplest first.
        null: The day-of-year climatology.
        levels: The preregistered thresholds.
        margin: The selection margin, MdSA points.
        seed: Bootstrap seed.
        aoi_sha256: The active channel's hash (written in the card).

    Returns:
        ``inner``, ``scores`` and ``level`` rows, the ``card`` and the chosen ``feature``.
    """
    train, lock, later = _split(pairs)
    order = list(candidates)
    inner_est = {c: loyo_power(train, *candidates[c]) for c in order}
    obs_train = [p.value for p in train]
    common = [k for k in range(len(train))
              if all(math.isfinite(inner_est[c][k]) for c in order)]  # fmt: skip
    inner = {c: (stats.mdsa([inner_est[c][k] for k in common], [obs_train[k] for k in common])
                 if len(common) >= 3 else math.nan) for c in order}  # fmt: skip
    pick = v6._choose(inner, margin, order)
    feature, harmonic = candidates[pick]
    model = fit_power(train, feature, harmonic)
    errors = [abs(math.log(e / o)) for e, o in zip(inner_est[pick], obs_train, strict=True)
              if math.isfinite(e) and e > 0 and o > 0]  # fmt: skip
    factor = math.exp(_q90(errors)) if errors else math.nan
    obs = [p.value for p in lock]
    blocks = [p.year for p in lock]

    def estimates(candidate: str, rows: Sequence[SurfacePair]) -> list[float]:
        fit = fit_power(train, *candidates[candidate])
        return [math.nan if fit is None else fit.predict(p.f(fit.feature), p.time) for p in rows]

    lock_est = {c: estimates(c, lock) for c in order}
    lock_scores = {c: log_scores(lock_est[c], obs, blocks, factor if c == pick else math.nan,
                                 seed + 1 + k) for k, c in enumerate(order)}  # fmt: skip
    null_scores = log_scores([null(p.time) for p in lock], obs, blocks, math.nan, seed)
    years = _years(lock, lock_est[pick])
    abstained = sum(1 for e in lock_est[pick] if not math.isfinite(e))
    level = ratio_level(lock_scores[pick], years, null_scores["mdsa"], factor, levels)
    later_est = estimates(pick, later)
    later_scores = log_scores(later_est, [p.value for p in later], [p.year for p in later],
                              factor, seed + 9)  # fmt: skip
    provisional = sum(1 for p, e in zip(later, later_est, strict=True)
                      if math.isfinite(e) and p.approval == "Provisional")  # fmt: skip

    base = {"site": site, "slug": slug, "target": target, "unit": unit}
    inner_rows = [{**base, "candidate": c, "pairs": len(common), "inner_loyo_mdsa": inner[c],
                   "chosen": c == pick} for c in order]  # fmt: skip
    score_rows: list[dict[str, Any]] = [
        {**base, "candidate": "day-of-year climatology (null)", "evaluation": "lock box",
         **null_scores},
        *[{**base, "candidate": c, "evaluation": "lock box" if c == pick
           else "lock box (not chosen, report-only)", "training_pairs": len(train),
           "lockbox_years": years if c == pick else _years(lock, lock_est[c]), **lock_scores[c]}
          for c in order],
        {**base, "candidate": pick, "evaluation": "prospective, report-only (from 2025-12-01)",
         "provisional": provisional, **later_scores},
    ]  # fmt: skip
    level_row = {**base, "candidate": pick, "level": level, "lockbox_years": years,
                 "abstained": abstained, "interval_factor90": factor,
                 "null_mdsa": null_scores["mdsa"], **lock_scores[pick]}  # fmt: skip
    card = None
    if model is not None:
        decisive = {
            "kind": "water-surface-power-law", "feature": f"water_fraction_{feature}",
            "coefficients": [round(c, 10) for c in model.coefficients],
            "smearing": round(model.smearing, 10), "harmonic": harmonic,
            "fittedRange": {"min": round(model.f_min, 8), "max": round(model.f_max, 8)},
            "activeChannelSha256": aoi_sha256, "intervalFactor90": round(factor, 6),
        }  # fmt: skip
        card = {
            "modelId": f"{pick}:{target}:{slug}", "version": "1", "target": target, "unit": unit,
            "candidate": pick, "basis": "preregistered_lockbox_site", "site": site, **decisive,
            "levels": [v6._round({"predicted_range": "all", "level": level,
                                  "mdsa": lock_scores[pick]["mdsa"], "n": lock_scores[pick]["n"],
                                  "interval_factor90": factor})],
            "metrics": {"lockbox": v6._round(lock_scores[pick]),
                        "null_lockbox": v6._round(null_scores)},
            "trainingPairs": {"site": len(train)}, "parametersHash": v6._hash(decisive),
        }  # fmt: skip
    return {"inner": [v6._round(r) for r in inner_rows],
            "scores": [v6._round(r) for r in score_rows], "level": v6._round(level_row),
            "card": card, "feature": feature, "lock": lock, "lock_est": lock_est[pick]}  # fmt: skip


def terciles(cfg: QualityConfig, data: Mapping[str, Any], lock: Sequence[SurfacePair],
             lock_est: Sequence[float]) -> list[dict[str, Any]]:  # fmt: skip
    """Report-only: the error by tercile of the gauge's discharge, and the passes skipped.

    The locked test's error in each tercile of the gauge's discharge, and the share of passes the
    clear rule skipped in the same terciles (approved discharge, up to the lock box's end).

    Args:
        cfg: The v2 settings.
        data: v7's snapshots.
        lock: The discharge's locked-test pairs.
        lock_est: Their estimates.

    Returns:
        One row per tercile.
    """
    if len(lock) < 3:
        return [{"status": "too few locked-test pairs"}]
    low, high = (float(q) for q in np.quantile([p.value for p in lock], [1 / 3, 2 / 3]))

    def tercile(q: float) -> int:
        return 0 if q <= low else (1 if q <= high else 2)

    readings = v6._readings(data["readings"]).get((fetch_v7.PLATTE_GAUGE, fetch_v7.DISCHARGE), [])
    seen: list[list[int]] = [[0, 0], [0, 0], [0, 0]]
    for r in data["surface"]:
        when = datetime.fromisoformat(r["datetime_utc"])
        if when > LOCK_END:
            continue
        value, _ = value_at(readings, when, cfg, provisional_ok=False)
        if math.isfinite(value) and value > 0:
            t = tercile(value * CFS_TO_M3S)
            seen[t][0] += 1
            seen[t][1] += int(r["clear"] != "1")
    rows = []
    names = (f"≤ {low:.0f} m³/s", f"{low:.0f} to {high:.0f} m³/s", f"> {high:.0f} m³/s")
    for t, name in enumerate(names):
        e = [x for p, x in zip(lock, lock_est, strict=True) if tercile(p.value) == t]
        o = [p.value for p, x in zip(lock, lock_est, strict=True) if tercile(p.value) == t]
        e2, o2 = v6._finite(e, o)
        rows.append(v6._round({
            "target": "discharge", "tercile": name, "lockbox_pairs": len(o),
            "estimated": len(e2), "mdsa": stats.mdsa(e2, o2) if len(e2) >= 3 else math.nan,
            "passes": seen[t][0], "skipped_by_clear_rule": seen[t][1],
            "skipped_share": seen[t][1] / seen[t][0] if seen[t][0] else math.nan,
        }))  # fmt: skip
    return rows


# --- Landsat: dissolved oxygen and temperature -----------------------------------------------


def saturation(t_c: float, pressure_atm: float) -> float:
    """Oxygen solubility in fresh water, mg/L (Benson & Krause 1984, as in USGS DOTABLES).

    Args:
        t_c: Water temperature, °C.
        pressure_atm: Barometric pressure, atm.

    Returns:
        The saturation concentration.
    """
    t = t_c + 273.15
    ln_c = (-139.34411 + 1.575701e5 / t - 6.642308e7 / t**2 + 1.243800e10 / t**3
            - 8.621949e11 / t**4)  # fmt: skip
    pwv = math.exp(11.8571 - 3840.70 / t - 216961.0 / t**2)
    theta = 0.000975 - 1.426e-5 * t_c + 6.436e-8 * t_c**2
    factor = ((1 - pwv / pressure_atm) * (1 - theta * pressure_atm)
              / ((1 - pwv) * (1 - theta)))  # fmt: skip
    return math.exp(ln_c) * pressure_atm * factor


def pressure_at(altitude_m: float) -> float:
    """The standard-atmosphere pressure at an altitude, atm.

    Args:
        altitude_m: Metres above sea level.

    Returns:
        The pressure.
    """
    return float((1 - 2.25577e-5 * altitude_m) ** 5.25588)


@dataclass(frozen=True)
class LinearPair:
    """A Landsat pass's input (temperature, or oxygen saturation) and the gauge's value."""

    time: datetime
    x: float
    value: float
    approval: str

    @property
    def year(self) -> int:
        """Its hydrological year."""
        return v6.hydro_year(self.time)


def linear_predict(candidate: str, train: Sequence[LinearPair], pairs: Sequence[LinearPair],
                   null: Null | None = None) -> list[float]:  # fmt: skip
    """A candidate's estimates of ``pairs``, fitted on ``train``; NaN outside the training range.

    Candidates: ``*0`` the null (``null``, else v6's training-pair climatology), ``*1`` the input as
    it is, ``*2`` a + b · input.

    Args:
        candidate: E.g. ``O1`` or ``W2``.
        train: Training pairs.
        pairs: Pairs to estimate.
        null: The null's climatology (``O0``); None: v6's (``W0``).

    Returns:
        Estimates.
    """
    kind = candidate[-1]
    if kind == "0":
        if null is not None:
            return [null(p.time) for p in pairs]
        thermal = [v6.ThermalPair(p.time, p.x, p.value, MIN_WATER_PX) for p in train]
        return [v6.climatology(thermal, p.time) for p in pairs]
    if len(train) < 3:
        return [math.nan] * len(pairs)
    lo, hi = min(p.x for p in train), max(p.x for p in train)
    a, b = (0.0, 1.0) if kind == "1" else _linear_fit(train)
    return [a + b * p.x if lo <= p.x <= hi else math.nan for p in pairs]


def _linear_fit(train: Sequence[LinearPair]) -> tuple[float, float]:
    x = np.array([[1.0, p.x] for p in train])
    coef, *_ = np.linalg.lstsq(x, np.array([p.value for p in train]), rcond=None)
    return float(coef[0]), float(coef[1])


def linear_loyo(candidate: str, pairs: Sequence[LinearPair], null: Null | None) -> list[float]:
    """Each pair's estimate without its hydrological year.

    Args:
        candidate: The candidate.
        pairs: Training pairs.
        null: As :func:`linear_predict`.

    Returns:
        One estimate per pair.
    """
    out = [math.nan] * len(pairs)
    for y in sorted({p.year for p in pairs}):
        rest = [p for p in pairs if p.year != y]
        idx = [k for k, p in enumerate(pairs) if p.year == y]
        values = linear_predict(candidate, rest, [pairs[k] for k in idx], null)
        for k, v in zip(idx, values, strict=True):
            out[k] = v
    return out


def evaluate_linear(*, target: str, unit: str, slug: str, site: str, pairs: Sequence[LinearPair],
                    candidates: Sequence[str], null: Null | None,
                    levels: Mapping[str, Mapping[str, float]], margin: float, seed: int,
                    cap: str | None = None, approvals: frozenset[str] = frozenset({"Approved"}),
                    ) -> dict[str, Any]:  # fmt: skip
    """One absolute-error target (oxygen, temperature): selection, locked test, level and fit.

    Args:
        target: ``dissolved_oxygen`` or ``water_temperature``.
        unit: Its unit.
        slug: The reach.
        site: The gauge the test uses.
        pairs: Its pairs (every approval state).
        candidates: The null first, then the candidates, simplest first.
        null: The null's climatology (None: v6's training-pair climatology).
        levels: The preregistered thresholds.
        margin: The selection margin, in the target's unit.
        seed: Bootstrap seed.
        cap: The highest level allowed (None: no cap).
        approvals: Approval states the training and the locked test accept.

    Returns:
        ``inner``, ``scores`` and ``level`` rows, the chosen candidate, its fit, half-width and
        input range.
    """
    train = [p for p in pairs if p.time < LOCK_START and p.approval in approvals]
    lock = [p for p in pairs if LOCK_START <= p.time <= LOCK_END and p.approval in approvals]
    later = [p for p in pairs if p.time >= PROSPECTIVE_START]
    obs_train = [p.value for p in train]
    blocks_train = [p.year for p in train]
    inner_est = {c: linear_loyo(c, train, null) for c in candidates}
    inner_mae = {c: v6.thermal_scores(e, obs_train, blocks_train, math.nan, seed)["mae"]
                 for c, e in inner_est.items()}  # fmt: skip
    fitted = list(candidates[1:])
    pick = v6._choose({c: inner_mae[c] for c in fitted}, margin, fitted)
    errors = [abs(e - o) for e, o in zip(inner_est[pick], obs_train, strict=True)
              if math.isfinite(e)]  # fmt: skip
    half = _q90(errors)
    obs = [p.value for p in lock]
    blocks = [p.year for p in lock]
    lock_est = {c: linear_predict(c, train, lock, null) for c in candidates}
    lock_scores = {
        c: v6.thermal_scores(
            lock_est[c], obs, blocks, half if c == pick else math.nan, seed + 1 + k
        )
        for k, c in enumerate(candidates)
    }
    years = _years(lock, lock_est[pick])
    level = absolute_level(lock_scores[pick], years, lock_scores[candidates[0]]["mae"], half,
                           levels)  # fmt: skip
    capped = level
    if cap is not None and level == "validated":
        capped = cap
    later_est = linear_predict(pick, train, later, null)
    later_scores = v6.thermal_scores(later_est, [p.value for p in later],
                                     [p.year for p in later], half, seed + 9)  # fmt: skip
    provisional = sum(1 for p, e in zip(later, later_est, strict=True)
                      if math.isfinite(e) and p.approval == "Provisional")  # fmt: skip
    a, b = (0.0, 1.0) if pick.endswith("1") or len(train) < 3 else _linear_fit(train)
    lo = min((p.x for p in train), default=math.nan)
    hi = max((p.x for p in train), default=math.nan)
    base = {"site": site, "slug": slug, "target": target, "unit": unit}
    inner_rows = [{**base, "candidate": c, "pairs": len(train), "inner_loyo_mae": inner_mae[c],
                   "chosen": c == pick} for c in candidates]  # fmt: skip
    score_rows: list[dict[str, Any]] = [
        *[{**base, "candidate": c, "evaluation": "lock box" if c in (pick, candidates[0])
           else "lock box (not chosen, report-only)", "training_pairs": len(train),
           "lockbox_years": _years(lock, lock_est[c]), **lock_scores[c]} for c in candidates],
        {**base, "candidate": pick, "evaluation": "prospective, report-only (from 2025-12-01)",
         "provisional": provisional, **later_scores},
    ]  # fmt: skip
    level_row = {**base, "candidate": pick, "level": capped, "level_before_cap": level,
                 "half_width90": half, "null_mae": lock_scores[candidates[0]]["mae"],
                 "lockbox_years": years,
                 "provisional_in_lockbox": sum(1 for p in lock if p.approval == "Provisional"),
                 **lock_scores[pick]}  # fmt: skip
    return {"inner": [v6._round(r) for r in inner_rows],
            "scores": [v6._round(r) for r in score_rows], "level": v6._round(level_row),
            "pick": pick, "a": a, "b": b, "half": half, "range": (lo, hi), "lock": lock_scores,
            "null_mae": lock_scores[candidates[0]]["mae"], "years": years, "train": len(train),
            "capped": capped}  # fmt: skip


def _st_rows(rows: Sequence[Mapping[str, str]], site: str) -> list[tuple[datetime, float]]:
    out = []
    for r in rows:
        if r["site_id"] != site or int(r["water_px"]) < MIN_WATER_PX or not r["st_k"]:
            continue
        st = float(r["st_k"])
        if math.isfinite(st):
            out.append((datetime.fromisoformat(r["datetime_utc"]), st - 273.15))
    return sorted(out)


def oxygen_pairs(
    cfg: QualityConfig,
    v6_rows: Sequence[Mapping[str, str]],
    data: Mapping[str, Any],
    temperature_card: Mapping[str, Any],
    pressure: float,
) -> list[LinearPair]:
    """The Platte's Landsat passes: oxygen saturation at the card's temperature, and the gauge.

    Args:
        cfg: The v2 settings.
        v6_rows: v6's thermal windows at the Platte.
        data: v7's snapshots (the oxygen readings).
        temperature_card: v6's water-temperature card.
        pressure: The gauge's datum pressure, atm.

    Returns:
        Pairs, by time.
    """
    p = temperature_card["parameters"]
    readings = v6._readings(data["readings"]).get((fetch_v7.PLATTE_GAUGE, fetch_v7.OXYGEN), [])
    out = []
    site = variables.GAUGES[variables.THERMAL_REACH]
    for when, st_c in _st_rows(v6_rows, site):
        t = float(p["a"]) + float(p["b"]) * st_c
        value, approval = value_at(readings, when, cfg, provisional_ok=True)
        if math.isfinite(value):
            out.append(LinearPair(when, saturation(t, pressure), value, approval))
    return out


def temperature_pairs(cfg: QualityConfig, data: Mapping[str, Any]) -> list[LinearPair]:
    """Baton Rouge's Landsat passes and its gauge's temperature (approved, else provisional).

    Args:
        cfg: The v2 settings.
        data: v7's snapshots.

    Returns:
        Pairs, by time.
    """
    readings = v6._readings(data["readings"]).get((fetch_v7.BATON_ROUGE, fetch_v7.TEMPERATURE), [])
    out = []
    for when, st_c in _st_rows(data["thermal"], fetch_v7.BATON_ROUGE):
        value, approval = value_at(readings, when, cfg, provisional_ok=True)
        if math.isfinite(value):
            out.append(LinearPair(when, st_c, value, approval))
    return out


def _altitude_m(data: Mapping[str, Any], site: str) -> float:
    row = next((r for r in data["sites"] if r["site_id"] == site), None)
    try:
        return float(row["altitude_ft"]) * FT_TO_M if row else math.nan
    except ValueError:
        return math.nan


def _site_name(data: Mapping[str, Any], site: str) -> str:
    return next((str(r["name"]) for r in data["sites"] if r["site_id"] == site), site)


def _linear_card(result: Mapping[str, Any], *, model_id: str, target: str, unit: str, site: str,
                 basis: str, extra: Mapping[str, Any]) -> dict[str, Any]:  # fmt: skip
    lo, hi = result["range"]
    decisive = {
        **extra,
        "parameters": {"a": round(result["a"], 8), "b": round(result["b"], 8)},
        "inputRange": {"min": round(lo, 6), "max": round(hi, 6)},
        "minWaterPixels": MIN_WATER_PX,
        "halfWidth90": round(result["half"], 6),
    }
    lock = result["lock"][result["pick"]]
    return {
        "modelId": model_id, "version": "1", "target": target, "unit": unit,
        "candidate": result["pick"], "basis": basis, "site": site, **decisive,
        "levels": [v6._round({"predicted_range": "all", "level": result["capped"],
                              "mae": lock["mae"], "n": lock["n"]})],
        "metrics": {"lockbox": v6._round(lock),
                    "null_lockbox": v6._round({"mae": result["null_mae"]})},
        "trainingPairs": {"site": result["train"]}, "parametersHash": v6._hash(decisive),
    }  # fmt: skip


def belle_chasse_check(cfg: QualityConfig, data: Mapping[str, Any],
                       result: Mapping[str, Any]) -> dict[str, Any]:  # fmt: skip
    """Report-only: Belle Chasse's estimates against Baton Rouge's gauge on the same pass.

    Args:
        cfg: The v2 settings.
        data: v7's snapshots.
        result: Baton Rouge's evaluation (the fit and its range).

    Returns:
        The row.
    """
    readings = v6._readings(data["readings"]).get((fetch_v7.BATON_ROUGE, fetch_v7.TEMPERATURE), [])
    lo, hi = result["range"]
    est, obs = [], []
    for when, st_c in _st_rows(data["thermal"], fetch_v7.BELLE_GAUGE):
        value, _ = value_at(readings, when, cfg, provisional_ok=True)
        if math.isfinite(value) and lo <= st_c <= hi:
            est.append(result["a"] + result["b"] * st_c)
            obs.append(value)
    err = np.array(est) - np.array(obs) if est else np.array([])
    return v6._round({
        "site": fetch_v7.BELLE_GAUGE, "slug": fetch_v7.BELLE, "target": "water_temperature",
        "unit": "°C", "candidate": result["pick"],
        "evaluation": "report-only: Belle Chasse's estimate against Baton Rouge's gauge, same pass",
        "n": float(len(est)), "mae": float(np.mean(np.abs(err))) if est else math.nan,
        "bias": float(np.mean(err)) if est else math.nan,
    })  # fmt: skip


# --- the evaluation --------------------------------------------------------------------------


def analyse(cfg: QualityConfig, root: Path, temperature_card: Mapping[str, Any] | None
            ) -> dict[str, list[dict[str, Any]]]:  # fmt: skip
    """v7's tables and cards (under ``_v7_cards``).

    Args:
        cfg: The v2 settings.
        root: Repository root.
        temperature_card: v6's water-temperature card at the Platte (oxygen's input).

    Returns:
        ``v7_inner``, ``v7_scores``, ``v7_levels`` and ``v7_terciles``.
    """
    from climate_pipeline.quality.route_b import _seed

    tables: dict[str, list[dict[str, Any]]] = {
        "v7_inner": [], "v7_scores": [], "v7_levels": [], "v7_terciles": [],
    }  # fmt: skip
    data = fetch_v7.load(root, cfg)
    if data is None:
        tables["v7_scores"].append({"status": "v7 not fetched yet"})
        return tables
    out_cards: list[dict[str, Any]] = []
    slug, site = fetch_v7.PLATTE, fetch_v7.PLATTE_GAUGE
    daily = data["daily"]
    aoi_sha = str(data["aoi"].get("maskSha256", ""))

    discharge = evaluate_power(
        target="discharge", unit="m³/s", slug=slug, site=site,
        pairs=surface_pairs(cfg, data, fetch_v7.DISCHARGE, CFS_TO_M3S),
        candidates={"Q1": ("scl", False), "Q2": ("mndwi", False)},
        null=daily_null(daily, site, fetch_v7.DISCHARGE, CFS_TO_M3S), levels=DISCHARGE_LEVELS,
        margin=DISCHARGE_MARGIN, seed=_seed(cfg.seed, "v7", "discharge"), aoi_sha256=aoi_sha,
    )  # fmt: skip
    conductance = evaluate_power(
        target="specific_conductance", unit="µS/cm", slug=slug, site=site,
        pairs=surface_pairs(cfg, data, fetch_v7.CONDUCTANCE, 1.0),
        candidates={"C1": (discharge["feature"], False), "C2": (discharge["feature"], True)},
        null=daily_null(daily, site, fetch_v7.CONDUCTANCE), levels=CONDUCTANCE_LEVELS,
        margin=CONDUCTANCE_MARGIN, seed=_seed(cfg.seed, "v7", "conductance"), aoi_sha256=aoi_sha,
    )  # fmt: skip
    for result, name in ((discharge, "discharge"), (conductance, "specific_conductance")):
        tables["v7_inner"] += result["inner"]
        tables["v7_scores"] += result["scores"]
        tables["v7_levels"].append(result["level"])
        if result["card"] is not None:
            out_cards.append({"path": f"{slug}/{name}.json", "card": result["card"]})
    tables["v7_terciles"] = terciles(cfg, data, discharge["lock"], discharge["lock_est"])

    v6_data = variables.load(root, cfg)
    altitude = _altitude_m(data, site)
    if temperature_card is not None and v6_data is not None and math.isfinite(altitude):
        pressure = pressure_at(altitude)
        oxygen = evaluate_linear(
            target="dissolved_oxygen", unit="mg/L", slug=slug, site=site,
            pairs=oxygen_pairs(cfg, v6_data["thermal"], data, temperature_card, pressure),
            candidates=("O0", "O1", "O2"), null=daily_null(daily, site, fetch_v7.OXYGEN),
            levels=OXYGEN_LEVELS, margin=OXYGEN_MARGIN, seed=_seed(cfg.seed, "v7", "oxygen"),
        )  # fmt: skip
        tables["v7_inner"] += oxygen["inner"]
        tables["v7_scores"] += oxygen["scores"]
        tables["v7_levels"].append(oxygen["level"])
        out_cards.append({"path": f"{slug}/dissolved_oxygen.json", "card": _linear_card(
            oxygen, model_id=f"{oxygen['pick']}:dissolved_oxygen:{slug}",
            target="dissolved_oxygen", unit="mg/L", site=site,
            basis="preregistered_lockbox_site",
            extra={"kind": "oxygen-saturation", "equation": "Benson & Krause 1984 (USGS DOTABLES)",
                   "pressureAtm": round(pressure, 6), "altitudeM": round(altitude, 3),
                   "temperatureCard": {"modelId": temperature_card["modelId"],
                                       "sha256": cards.card_hash(temperature_card)}},
        )})  # fmt: skip
    else:
        missing = "no temperature card, v6 windows or altitude"
        tables["v7_levels"].append({"target": "dissolved_oxygen", "slug": slug, "status": missing})

    temperature = evaluate_linear(
        target="water_temperature", unit="°C", slug=fetch_v7.BELLE, site=fetch_v7.BATON_ROUGE,
        pairs=temperature_pairs(cfg, data), candidates=("W0", "W1", "W2"), null=None,
        levels=TEMPERATURE_LEVELS, margin=TEMPERATURE_MARGIN,
        seed=_seed(cfg.seed, "v7", "temperature"), cap="estimated",
        approvals=frozenset({"Approved", "Provisional"}),
    )  # fmt: skip
    tables["v7_inner"] += temperature["inner"]
    tables["v7_scores"] += temperature["scores"]
    tables["v7_scores"].append(belle_chasse_check(cfg, data, temperature))
    tables["v7_levels"].append(temperature["level"])
    out_cards.append({"path": f"{fetch_v7.BELLE}/water_temperature.json", "card": _linear_card(
        temperature, model_id=f"{temperature['pick']}:water_temperature:core:{fetch_v7.BELLE}",
        target="water_temperature", unit="°C", site=fetch_v7.BELLE_GAUGE,
        basis="preregistered_lockbox_upstream_site",
        extra={"kind": "thermal-linear", "source": "landsat-c2-l2 ST_B10 (lwir11)",
               "validationSite": fetch_v7.BATON_ROUGE,
               "validationSiteName": _site_name(data, fetch_v7.BATON_ROUGE),
               "validatedAgainst": "approved values, else provisional",
               "levelCap": "estimated"},
    )})  # fmt: skip
    tables["_v7_cards"] = out_cards
    return tables


def summary(tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """v7's levels, for summary.json.

    Args:
        tables: Every table.

    Returns:
        Each target's level per reach.
    """
    return {f"{r['slug']}/{r['target']}": {"level": r.get("level"), "candidate": r.get("candidate")}
            for r in tables.get("v7_levels", []) if "slug" in r and "level" in r}  # fmt: skip
