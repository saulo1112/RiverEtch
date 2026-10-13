"""Water-quality v6's evaluation (preregistration v6): the SSC chain and water temperature.

Read from v6's snapshots (``variables.fetch``) and v5's turbidity evaluations:

* **Link 2 of the SSC chain**, per demo gauge: each discrete sample paired with the gauge's
  turbidity at its time (the overpass rule, approved, unqualified); ratings R1 (ln SSC on ln
  turbidity, Duan's smearing) and R2 (plus ln discharge), chosen by leave-one-hydrological-year-out
  MdSA in the training years with the 5-point margin, then scored once on the lock box. The
  chain's 90 % interval sums the two links' log errors (link 1's inner residuals, link 2's
  leave-one-year-out residuals), taken as independent. Its level follows the preregistered
  `chained_rating` rule.
* **The end-to-end check** (report-only): v5's lock-box SSC pairs on a clear pass's local day,
  the turbidity card then the rating, against the sample.
* **Water temperature at the Platte**: each Landsat pass's clear-water surface temperature paired
  with the gauge's 00010; W0 (the training pairs' day-of-year climatology, ±15 days), W1 (the
  product) and W2 (a linear site adjustment), W1 or W2 chosen by leave-one-year-out MAE with the
  0.3 °C margin, scored once on the lock box; a split-conformal 90 % half-width.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from climate_pipeline.calibration import stats
from climate_pipeline.quality import cards, variables
from climate_pipeline.quality.config import QualityConfig
from climate_pipeline.sources import usgs

LOCK_START = datetime(2023, 12, 1, tzinfo=UTC)
LOCK_END = datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC)
STATUSES = {"accepted", "approved"}
RATINGS = ("R1", "R2")
THERMAL = ("W1", "W2")
CLIMATOLOGY_DAYS = 15
MIN_WATER_PX = 10
RESAMPLES = 2000
# The preregistered rules (v6, A and C).
SSC_RULE = {"min_pairs": 20, "min_years": 2, "mdsa_max": 30.0, "sspb_abs_max": 15.0,
            "null_ratio_max": 0.8, "factor_max": 3.0, "rho_low_min": 0.3}  # fmt: skip
TEMPERATURE_LEVELS: dict[str, dict[str, float]] = {
    "validated": {"mae": 1.5, "bias": 0.75, "null_ratio": 0.8, "half_width": 3.0},
    "estimated": {"mae": 2.5, "bias": 1.5, "null_ratio": 1.0, "half_width": 4.5},
}
TEMPERATURE_COMMON = {"min_pairs": 20.0, "min_years": 2.0, "coverage_min": 0.8,
                      "rho_low_min": 0.3}  # fmt: skip


def hydro_year(when: datetime) -> int:
    """The hydrological year (December to November) of a time."""
    return when.year + (1 if when.month == 12 else 0)


def _readings(rows: Sequence[Mapping[str, str]]) -> dict[tuple[str, str], list[usgs.Reading]]:
    out: dict[tuple[str, str], list[usgs.Reading]] = {}
    for r in rows:
        out.setdefault((r["site_id"], r["parameter"]), []).append(usgs.Reading(
            datetime.fromisoformat(r["time"]), float(r["value"]), r["approval"],
            r["qualified"] == "1"))  # fmt: skip
    return out


def _at(readings: Sequence[usgs.Reading], when: datetime, cfg: QualityConfig) -> float:
    u = cfg.usgs
    value, _, _ = usgs.overpass_value(readings, when, u.overpass_median_minutes,
                                      u.overpass_nearest_minutes, "Approved",
                                      u.exclude_qualified)  # fmt: skip
    return value


@dataclass(frozen=True)
class RatingPair:
    """A discrete SSC sample and the gauge's readings at its time."""

    site: str
    time: datetime
    ssc: float
    turbidity: float
    discharge: float

    @property
    def year(self) -> int:
        """Its hydrological year."""
        return hydro_year(self.time)


def rating_pairs(cfg: QualityConfig, data: Mapping[str, Sequence[Mapping[str, str]]]
                 ) -> dict[str, list[RatingPair]]:  # fmt: skip
    """Each gauge's samples with an approved turbidity at their time (discharge when there is one).

    Args:
        cfg: The v2 settings (the overpass rule).
        data: v6's snapshots.

    Returns:
        Site -> pairs, by time.
    """
    readings = _readings(data["readings"])
    out: dict[str, list[RatingPair]] = {}
    for row in data["ssc"]:
        when = variables.sample_time(row)
        if when is None or row.get("status", "").strip().lower() not in STATUSES:
            continue
        try:
            ssc = float(row["value"])
        except ValueError:
            continue
        site = row["site_id"]
        turbidity = _at(readings.get((site, variables.TURBIDITY), []), when, cfg)
        if not (ssc > 0 and turbidity > 0):
            continue
        discharge = _at(readings.get((site, variables.DISCHARGE), []), when, cfg)
        out.setdefault(site, []).append(RatingPair(site, when, ssc, turbidity, discharge))
    return {s: sorted(p, key=lambda x: x.time) for s, p in out.items()}


@dataclass(frozen=True)
class Rating:
    """ln SSC = a + b ln T (+ c ln Q), with Duan's smearing factor."""

    coefficients: tuple[float, ...]
    smearing: float
    with_discharge: bool

    def predict(self, turbidity: float, discharge: float = math.nan) -> float:
        """The rating's SSC (mg/L), NaN when an input is missing."""
        x = [1.0, math.log(turbidity) if turbidity > 0 else math.nan]
        if self.with_discharge:
            x.append(math.log(discharge) if discharge > 0 else math.nan)
        value = sum(c * v for c, v in zip(self.coefficients, x, strict=True))
        return math.exp(value) * self.smearing if math.isfinite(value) else math.nan


def fit_rating(pairs: Sequence[RatingPair], with_discharge: bool) -> Rating | None:
    """OLS in log space with Duan's smearing factor (None for fewer than 3 usable pairs).

    Args:
        pairs: Training pairs.
        with_discharge: R2 (else R1).

    Returns:
        The rating.
    """
    use = [p for p in pairs if not with_discharge or p.discharge > 0]
    if len(use) < 3:
        return None
    x = np.array([[1.0, math.log(p.turbidity)] + ([math.log(p.discharge)] if with_discharge
                                                  else []) for p in use])  # fmt: skip
    y = np.log([p.ssc for p in use])
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    smearing = float(np.mean(np.exp(y - x @ coef)))
    return Rating(tuple(float(c) for c in coef), smearing, with_discharge)


def _predict(rating: Rating | None, pairs: Sequence[RatingPair]) -> list[float]:
    return [math.nan if rating is None else rating.predict(p.turbidity, p.discharge) for p in pairs]


def loyo(pairs: Sequence[RatingPair], with_discharge: bool) -> list[float]:
    """Each pair's estimate by a rating fitted without its hydrological year.

    Args:
        pairs: Training pairs.
        with_discharge: R2 (else R1).

    Returns:
        One estimate per pair.
    """
    out = [math.nan] * len(pairs)
    for y in sorted({p.year for p in pairs}):
        rating = fit_rating([p for p in pairs if p.year != y], with_discharge)
        for k, p in enumerate(pairs):
            if p.year == y and rating is not None:
                out[k] = rating.predict(p.turbidity, p.discharge)
    return out


def _finite(est: Sequence[float], obs: Sequence[float]) -> tuple[list[float], list[float]]:
    keep = [(e, o) for e, o in zip(est, obs, strict=True) if e > 0 and o > 0]
    return [e for e, _ in keep], [o for _, o in keep]


def scores(est: Sequence[float], obs: Sequence[float], blocks: Sequence[Any], seed: int
           ) -> dict[str, float]:  # fmt: skip
    """MdSA, SSPB, Spearman and its 95 % lower bound (resampling blocks) of the finite pairs.

    Args:
        est: Estimates.
        obs: Observations.
        blocks: The block of each pair (its hydrological year).
        seed: Bootstrap seed.

    Returns:
        The scores (NaN without pairs).
    """
    keep = [k for k, (e, o) in enumerate(zip(est, obs, strict=True)) if e > 0 and o > 0]
    e, o = [est[k] for k in keep], [obs[k] for k in keep]
    if len(keep) < 3:
        return {"n": float(len(keep)), "mdsa": math.nan, "sspb": math.nan, "rho": math.nan,
                "rho_low": math.nan}  # fmt: skip
    low, _ = stats.block_bootstrap_spearman(e, o, [blocks[k] for k in keep], RESAMPLES, seed)
    return {"n": float(len(keep)), "mdsa": stats.mdsa(e, o), "sspb": stats.sspb(e, o),
            "rho": stats.spearman(e, o), "rho_low": low}  # fmt: skip


def _choose(inner: Mapping[str, float], margin: float, order: Sequence[str]) -> str:
    finite = {c: v for c, v in inner.items() if math.isfinite(v)}
    if not finite:
        return order[0]
    best = min(finite.values())
    return next(c for c in order if c in finite and finite[c] <= best + margin)


def _log_errors(est: Sequence[float], obs: Sequence[float]) -> list[float]:
    return [math.log(e / o) for e, o in zip(est, obs, strict=True) if e > 0 and o > 0]


def chain_quantiles(link1: Sequence[float], link2: Sequence[float]) -> tuple[float, float]:
    """The 5th and 95th percentiles of the sum of the two links' log errors (every pairing).

    Args:
        link1: Link 1's log errors (estimate over observation).
        link2: Link 2's.

    Returns:
        ``(q05, q95)``; NaN without errors.
    """
    if not link1 or not link2:
        return math.nan, math.nan
    total = (np.asarray(link1)[:, None] + np.asarray(link2)[None, :]).ravel()
    return float(np.percentile(total, 5)), float(np.percentile(total, 95))


def ssc_level(link1_level: str, lock: Mapping[str, float], years: int, null_mdsa: float,
              factor: float) -> str:  # fmt: skip
    """The chain's level under the preregistered rule (never validated).

    Args:
        link1_level: The turbidity card's overall level.
        lock: Link 2's lock-box scores.
        years: Hydrological years in link 2's lock box.
        null_mdsa: The training median's lock-box MdSA.
        factor: The chain's 90 % interval factor.

    Returns:
        ``estimated``, ``indicative`` or ``none``.
    """
    r = SSC_RULE
    if (
        link1_level in ("validated", "estimated")
        and lock["n"] >= r["min_pairs"]
        and years >= r["min_years"]
        and lock["mdsa"] <= r["mdsa_max"]
        and abs(lock["sspb"]) <= r["sspb_abs_max"]
        and lock["mdsa"] <= r["null_ratio_max"] * null_mdsa
        and factor <= r["factor_max"]
    ):
        return "estimated"  # fmt: skip
    if lock.get("rho_low", -1.0) > r["rho_low_min"]:
        return "indicative"
    return "none"


def _hash(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _round(row: Mapping[str, Any]) -> dict[str, Any]:
    return {k: (round(v, 4) if isinstance(v, float) and math.isfinite(v) else
                (None if isinstance(v, float) else v)) for k, v in row.items()}  # fmt: skip


def evaluate_ssc(cfg: QualityConfig, slug: str, site: str, pairs: Sequence[RatingPair],
                 link1: Mapping[str, Any], seed: int,
                 end_to_end: Sequence[tuple[float, float]]) -> dict[str, Any]:  # fmt: skip
    """One gauge's SSC chain: link 2's selection and lock box, the chain's interval and level.

    Args:
        cfg: The v2 settings.
        slug: The reach.
        site: The gauge.
        pairs: Its rating pairs.
        link1: ``card`` (the turbidity card), ``card_path`` and ``residuals`` (its inner log
            errors).
        seed: Seed of the bootstraps.
        end_to_end: (turbidity estimate, sample) of the lock-box samples on a clear pass's day.

    Returns:
        ``inner``, ``scores`` and ``level`` rows and the ``card``.
    """
    train = [p for p in pairs if p.time < LOCK_START]
    lock = [p for p in pairs if LOCK_START <= p.time <= LOCK_END]
    both = [p for p in train if p.discharge > 0]  # the common subset for the selection
    inner_est = {c: loyo(both, c == "R2") for c in RATINGS}
    inner = {c: stats.mdsa(*_finite(e, [p.ssc for p in both])) if len(both) >= 3 else math.nan
             for c, e in inner_est.items()}  # fmt: skip
    pick = _choose(inner, cfg.selection.simpler_within_mdsa, RATINGS)
    rating = fit_rating(train, pick == "R2")
    null_value = float(np.median([p.ssc for p in train])) if train else math.nan
    obs = [p.ssc for p in lock]
    blocks = [p.year for p in lock]
    lock_scores = scores(_predict(rating, lock), obs, blocks, seed)
    null_scores = scores([null_value] * len(lock), obs, blocks, seed + 1)
    years = len({p.year for p in lock if p.ssc > 0})
    link2_errors = _log_errors(loyo(train, pick == "R2"), [p.ssc for p in train])
    q05, q95 = chain_quantiles(link1["residuals"], link2_errors)
    factor = math.exp((q95 - q05) / 2) if math.isfinite(q05) else math.nan
    link1_level = next((r["level"] for r in link1["card"].get("levels", [])
                        if r["predicted_range"] == "all"), "none")  # fmt: skip
    level = ssc_level(link1_level, lock_scores, years, null_scores["mdsa"], factor)
    e2e_est = [math.nan if rating is None else rating.predict(t) for t, _ in end_to_end]
    e2e_obs = [o for _, o in end_to_end]
    e2e = scores(e2e_est, e2e_obs, list(range(len(e2e_obs))), seed + 2)
    base = {"site": site, "slug": slug, "target": "ssc", "unit": "mg/L"}
    inner_rows = [{**base, "candidate": c, "pairs": len(both), "inner_loyo_mdsa": inner[c],
                   "chosen": c == pick} for c in RATINGS]  # fmt: skip
    score_rows = [
        {**base, "candidate": "median of the training samples", "evaluation": "lock box",
         **null_scores},
        {**base, "candidate": pick, "evaluation": "lock box (link 2: the gauge's rating)",
         "training_pairs": len(train), "lockbox_years": years, **lock_scores},
        {**base, "candidate": f"turbidity card, then {pick}",
         "evaluation": "end to end, report-only (lock-box samples on a clear pass's day)", **e2e},
    ]  # fmt: skip
    level_row = {**base, "candidate": pick, "link1_level": link1_level,
                 "lockbox_n": lock_scores["n"],
                 "lockbox_years": years, "mdsa": lock_scores["mdsa"], "sspb": lock_scores["sspb"],
                 "null_mdsa": null_scores["mdsa"], "rho_low": lock_scores["rho_low"],
                 "interval_factor90": factor, "level": level}  # fmt: skip
    card = None
    if rating is not None:
        decisive = {
            "kind": "chained-rating", "link1": {"card": link1["card_path"],
                                                "sha256": cards.card_hash(link1["card"])},
            "rating": {"candidate": pick,
                       "coefficients": [round(c, 10) for c in rating.coefficients],
                       "smearing": round(rating.smearing, 10),
                       "features": ["ln_turbidity", *(["ln_discharge"] if rating.with_discharge
                                                     else [])]},
            "interval90": {"logErrorQ05": round(q05, 6), "logErrorQ95": round(q95, 6)},
        }  # fmt: skip
        card = {
            "modelId": f"chain:ssc:{slug}", "version": "1", "target": "ssc", "unit": "mg/L",
            "candidate": pick, "basis": "chained_rating", "site": site, **decisive,
            "levels": [_round({"predicted_range": "all", "level": level,
                               "mdsa": lock_scores["mdsa"],
                               "n": lock_scores["n"], "interval_factor90": factor})],
            "metrics": {"rating_lockbox": _round(lock_scores), "rating_null": _round(null_scores),
                        "end_to_end_report_only": _round(e2e)},
            "trainingPairs": {"site": len(train)}, "parametersHash": _hash(decisive),
        }  # fmt: skip
    return {"inner": [_round(r) for r in inner_rows], "scores": [_round(r) for r in score_rows],
            "level": _round(level_row), "card": card}  # fmt: skip


@dataclass(frozen=True)
class ThermalPair:
    """A Landsat pass's clear-water surface temperature and the gauge's water temperature."""

    time: datetime
    st_c: float
    gauge_c: float
    water_px: int

    @property
    def year(self) -> int:
        """Its hydrological year."""
        return hydro_year(self.time)


def thermal_pairs(cfg: QualityConfig, data: Mapping[str, Sequence[Mapping[str, str]]]
                  ) -> list[ThermalPair]:  # fmt: skip
    """The Platte's Landsat passes with at least 10 clear-water pixels and an approved gauge value.

    Args:
        cfg: The v2 settings.
        data: v6's snapshots.

    Returns:
        Pairs, by time.
    """
    site = variables.GAUGES[variables.THERMAL_REACH]
    readings = _readings(data["readings"]).get((site, variables.TEMPERATURE), [])
    out = []
    for row in data["thermal"]:
        st = float(row["st_k"]) if row["st_k"] else math.nan
        if int(row["water_px"]) < MIN_WATER_PX or not math.isfinite(st):
            continue
        when = datetime.fromisoformat(row["datetime_utc"])
        gauge = _at(readings, when, cfg)
        if math.isfinite(gauge):
            out.append(ThermalPair(when, st - 273.15, gauge, int(row["water_px"])))
    return sorted(out, key=lambda p: p.time)


def climatology(train: Sequence[ThermalPair], when: datetime) -> float:
    """The mean gauge temperature of the training pairs within ±15 days of the day of year.

    Args:
        train: Training pairs.
        when: The day.

    Returns:
        The mean, or NaN without such a pair.
    """
    day = when.timetuple().tm_yday
    near = [p.gauge_c for p in train
            if min(abs(p.time.timetuple().tm_yday - day),
                   365 - abs(p.time.timetuple().tm_yday - day)) <= CLIMATOLOGY_DAYS]  # fmt: skip
    return float(np.mean(near)) if near else math.nan


def _thermal_fit(train: Sequence[ThermalPair]) -> tuple[float, float]:
    x = np.array([[1.0, p.st_c] for p in train])
    coef, *_ = np.linalg.lstsq(x, np.array([p.gauge_c for p in train]), rcond=None)
    return float(coef[0]), float(coef[1])


def thermal_predict(candidate: str, train: Sequence[ThermalPair],
                    pairs: Sequence[ThermalPair]) -> list[float]:  # fmt: skip
    """W0, W1 or W2's estimates of ``pairs``, fitted on ``train``.

    Args:
        candidate: ``W0``, ``W1`` or ``W2``.
        train: Training pairs.
        pairs: Pairs to estimate.

    Returns:
        Estimates in °C.
    """
    if candidate == "W0":
        return [climatology(train, p.time) for p in pairs]
    if candidate == "W1":
        return [p.st_c for p in pairs]
    if len(train) < 3:
        return [math.nan] * len(pairs)
    a, b = _thermal_fit(train)
    return [a + b * p.st_c for p in pairs]


def thermal_loyo(candidate: str, pairs: Sequence[ThermalPair]) -> list[float]:
    """Each pair's estimate without its hydrological year.

    Args:
        candidate: ``W0``, ``W1`` or ``W2``.
        pairs: Training pairs.

    Returns:
        One estimate per pair.
    """
    out = [math.nan] * len(pairs)
    for y in sorted({p.year for p in pairs}):
        rest = [p for p in pairs if p.year != y]
        idx = [k for k, p in enumerate(pairs) if p.year == y]
        for k, v in zip(idx, thermal_predict(candidate, rest, [pairs[k] for k in idx]),
                        strict=True):  # fmt: skip
            out[k] = v
    return out


def thermal_scores(est: Sequence[float], obs: Sequence[float], blocks: Sequence[Any],
                   half_width: float, seed: int) -> dict[str, float]:  # fmt: skip
    """MAE, bias, RMSE, coverage of ±``half_width``, Spearman and its lower bound, in °C.

    Args:
        est: Estimates.
        obs: Gauge values.
        blocks: Each pair's hydrological year.
        half_width: The 90 % interval's half-width (NaN: no coverage).
        seed: Bootstrap seed.

    Returns:
        The scores.
    """
    keep = [k for k, e in enumerate(est) if math.isfinite(e)]
    if len(keep) < 3:
        return {"n": float(len(keep)), "mae": math.nan, "bias": math.nan, "rmse": math.nan,
                "coverage90": math.nan, "rho": math.nan, "rho_low": math.nan}  # fmt: skip
    err = np.array([est[k] - obs[k] for k in keep])
    e, o = [est[k] for k in keep], [obs[k] for k in keep]
    low, _ = stats.block_bootstrap_spearman(e, o, [blocks[k] for k in keep], RESAMPLES, seed)
    return {
        "n": float(len(keep)), "mae": float(np.mean(np.abs(err))), "bias": float(np.mean(err)),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "coverage90": float(np.mean(np.abs(err) <= half_width)) if math.isfinite(half_width)
        else math.nan,
        "rho": stats.spearman(e, o), "rho_low": low,
    }  # fmt: skip


def temperature_level(lock: Mapping[str, float], years: int, null_mae: float,
                      half_width: float) -> str:  # fmt: skip
    """Water temperature's level under the preregistered rule.

    Args:
        lock: The chosen candidate's lock-box scores.
        years: Hydrological years in the lock box.
        null_mae: W0's lock-box MAE.
        half_width: The 90 % half-width.

    Returns:
        ``validated``, ``estimated``, ``indicative`` or ``none``.
    """
    r = TEMPERATURE_COMMON
    common = (lock["n"] >= r["min_pairs"] and years >= r["min_years"]
              and lock["coverage90"] >= r["coverage_min"])  # fmt: skip
    for level, t in TEMPERATURE_LEVELS.items():
        ratio_ok = (lock["mae"] <= t["null_ratio"] * null_mae if level == "validated"
                    else lock["mae"] < null_mae)  # fmt: skip
        if (common and lock["mae"] <= t["mae"] and abs(lock["bias"]) <= t["bias"] and ratio_ok
                and half_width <= t["half_width"]):  # fmt: skip
            return level
    if lock.get("rho_low", -1.0) > r["rho_low_min"]:
        return "indicative"
    return "none"


def evaluate_temperature(cfg: QualityConfig, pairs: Sequence[ThermalPair], seed: int
                         ) -> dict[str, Any]:  # fmt: skip
    """Water temperature at the Platte: selection, lock box, interval, level and card.

    Args:
        cfg: The v2 settings.
        pairs: The thermal pairs.
        seed: Seed of the bootstraps.

    Returns:
        ``inner``, ``scores`` and ``level`` rows and the ``card``.
    """
    slug = variables.THERMAL_REACH
    site = variables.GAUGES[slug]
    train = [p for p in pairs if p.time < LOCK_START]
    lock = [p for p in pairs if LOCK_START <= p.time <= LOCK_END]
    obs_train = [p.gauge_c for p in train]
    inner_est = {c: thermal_loyo(c, train) for c in ("W0", *THERMAL)}
    inner_mae = {c: thermal_scores(e, obs_train, [p.year for p in train], math.nan, seed)["mae"]
                 for c, e in inner_est.items()}  # fmt: skip
    pick = _choose({c: inner_mae[c] for c in THERMAL}, 0.3, THERMAL)
    errors = [abs(e - o) for e, o in zip(inner_est[pick], obs_train, strict=True)
              if math.isfinite(e)]  # fmt: skip
    half = float(np.quantile(errors, 0.9, method="higher")) if errors else math.nan
    obs = [p.gauge_c for p in lock]
    blocks = [p.year for p in lock]
    lock_scores = {c: thermal_scores(thermal_predict(c, train, lock), obs, blocks,
                                     half if c == pick else math.nan, seed + 1 + k)
                   for k, c in enumerate(("W0", *THERMAL))}  # fmt: skip
    years = len({p.year for p in lock})
    level = temperature_level(lock_scores[pick], years, lock_scores["W0"]["mae"], half)
    base = {"site": site, "slug": slug, "target": "water_temperature", "unit": "°C"}
    inner_rows = [{**base, "candidate": c, "pairs": len(train), "inner_loyo_mae": inner_mae[c],
                   "chosen": c == pick} for c in ("W0", *THERMAL)]  # fmt: skip
    score_rows = [{**base, "candidate": c, "evaluation": "lock box", "lockbox_years": years,
                   "training_pairs": len(train), **s} for c, s in lock_scores.items()]  # fmt: skip
    level_row = {**base, "candidate": pick, "half_width90": half, **lock_scores[pick],
                 "null_mae": lock_scores["W0"]["mae"], "lockbox_years": years,
                 "level": level}  # fmt: skip
    a, b = _thermal_fit(train) if pick == "W2" and len(train) >= 3 else (0.0, 1.0)
    decisive = {"kind": "thermal-linear", "source": "landsat-c2-l2 ST_B10 (lwir11)",
                "parameters": {"a": round(a, 8), "b": round(b, 8)},
                "minWaterPixels": MIN_WATER_PX, "halfWidth90": round(half, 6)}  # fmt: skip
    card = {
        "modelId": f"{pick}:water_temperature:core:{slug}", "version": "1",
        "target": "water_temperature", "unit": "°C", "candidate": pick,
        "basis": "preregistered_lockbox_site", "site": site, **decisive,
        "levels": [_round({"predicted_range": "all", "level": level,
                           "mae": lock_scores[pick]["mae"], "n": lock_scores[pick]["n"]})],
        "metrics": {"lockbox": _round(lock_scores[pick]),
                    "null_lockbox": _round(lock_scores["W0"])},
        "trainingPairs": {"site": len(train)}, "parametersHash": _hash(decisive),
    }  # fmt: skip
    return {"inner": [_round(r) for r in inner_rows], "scores": [_round(r) for r in score_rows],
            "level": _round(level_row), "card": card}  # fmt: skip


def analyse(cfg: QualityConfig, root: Path, link1: Mapping[str, Mapping[str, Any]],
            end_to_end: Mapping[str, Sequence[tuple[float, float]]]
            ) -> dict[str, list[dict[str, Any]]]:  # fmt: skip
    """v6's tables and cards (under ``_v6_cards``).

    Args:
        cfg: The v2 settings.
        root: Repository root.
        link1: Per reach, its turbidity card, card path and inner log errors (from v5).
        end_to_end: Per reach, (turbidity estimate, sample) of the lock-box samples on a clear
            pass's day.

    Returns:
        ``v6_rating_inner``, ``v6_scores``, ``v6_levels``, ``v6_temperature_inner``.
    """
    from climate_pipeline.quality.route_b import _seed

    tables: dict[str, list[dict[str, Any]]] = {
        "v6_rating_inner": [],
        "v6_scores": [],
        "v6_levels": [],
        "v6_temperature_inner": [],
    }
    data = variables.load(root, cfg)
    if data is None:
        tables["v6_scores"].append({"status": "v6 not fetched yet"})
        return tables
    pairs = rating_pairs(cfg, data)
    out_cards: list[dict[str, Any]] = []
    for slug, site in variables.GAUGES.items():
        if slug not in link1:
            tables["v6_scores"].append({"site": site, "slug": slug, "status": "no turbidity card"})
            continue
        result = evaluate_ssc(cfg, slug, site, pairs.get(site, []), link1[slug],
                              _seed(cfg.seed, "v6", site), end_to_end.get(slug, []))  # fmt: skip
        tables["v6_rating_inner"] += result["inner"]
        tables["v6_scores"] += result["scores"]
        tables["v6_levels"].append(result["level"])
        if result["card"] is not None:
            out_cards.append({"path": f"{slug}/ssc.json", "card": result["card"]})
    thermal = evaluate_temperature(cfg, thermal_pairs(cfg, data),
                                   _seed(cfg.seed, "v6", "temperature"))  # fmt: skip
    tables["v6_temperature_inner"] = thermal["inner"]
    tables["v6_scores"] += thermal["scores"]
    tables["v6_levels"].append(thermal["level"])
    out_cards.append({"path": f"{variables.THERMAL_REACH}/water_temperature.json",
                      "card": thermal["card"]})  # fmt: skip
    tables["_v6_cards"] = out_cards
    return tables


def summary(tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """v6's levels, for summary.json.

    Args:
        tables: Every table.

    Returns:
        Each target's level per reach.
    """
    return {f"{r['slug']}/{r['target']}": {"level": r.get("level"), "candidate": r.get("candidate")}
            for r in tables.get("v6_levels", []) if "slug" in r}  # fmt: skip
