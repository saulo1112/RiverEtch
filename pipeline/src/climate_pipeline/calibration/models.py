"""Calibration models (Stage 3), published semi-analytical models (Stage 4) and abstention.

Targets are fitted in log space: water-quality variables are roughly log-normal. A feature
enters as its logarithm when it is positive on every training pair, else linearly (NDTI can be
negative). Ridge keeps the intercept unpenalized and is used only when there are enough pairs
per feature. Every choice uses training pairs only; the hold-out is scored once, at the end.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from climate_pipeline.calibration.config import Stage3, WindowSettings
from climate_pipeline.calibration.stats import mape, mdsa, sspb

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class Fit:
    """A fitted log-space linear model."""

    model_id: str
    target: str
    features: tuple[str, ...]
    transforms: tuple[str, ...]  # "log" or "linear", per feature
    coefficients: tuple[float, ...]  # intercept first
    ridge_lambda: float
    feature_range: dict[str, tuple[float, float]]
    target_range: tuple[float, float]
    loo_predictions: tuple[float, ...]
    n_train: int

    def card(self, unit: str, metrics: Mapping[str, float]) -> dict[str, Any]:
        """The model card (JSON-ready), with the hash of its parameters.

        Args:
            unit: The target's unit.
            metrics: Training and hold-out metrics.

        Returns:
            The card.
        """
        params = {
            "modelId": self.model_id,
            "target": self.target,
            "features": list(self.features),
            "transforms": list(self.transforms),
            "coefficients": [round(c, 10) for c in self.coefficients],
            "ridgeLambda": self.ridge_lambda,
            "featureRange": {
                k: [round(a, 6), round(b, 6)] for k, (a, b) in self.feature_range.items()
            },
            "targetRange": [round(self.target_range[0], 6), round(self.target_range[1], 6)],
        }  # fmt: skip
        digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
        return {
            **params,
            "version": "1",
            "unit": unit,
            "nTrain": self.n_train,
            "parametersHash": digest,
            "metrics": {k: round(v, 4) if math.isfinite(v) else None for k, v in metrics.items()},
        }

    def predict(self, row: Mapping[str, float]) -> float:
        """Predict the target for one feature row.

        Args:
            row: Feature values.

        Returns:
            The prediction (NaN when a feature is missing or not positive under a log transform).
        """
        x = _row(row, self.features, self.transforms)
        if x is None:
            return math.nan
        return float(math.exp(self.coefficients[0] + float(np.dot(self.coefficients[1:], x))))


def transforms_for(rows: Sequence[Mapping[str, float]], features: Sequence[str]) -> tuple[str, ...]:
    """``log`` for a feature positive on every row, else ``linear``.

    Args:
        rows: Training feature rows.
        features: Feature names.

    Returns:
        One transform per feature.
    """
    return tuple(
        "log" if all(math.isfinite(r[f]) and r[f] > 0 for r in rows) else "linear" for f in features
    )


def _row(
    row: Mapping[str, float], features: Sequence[str], transforms: Sequence[str]
) -> FloatArray | None:
    out = []
    for f, t in zip(features, transforms, strict=True):
        v = row.get(f, math.nan)
        if not math.isfinite(v) or (t == "log" and v <= 0):
            return None
        out.append(math.log(v) if t == "log" else v)
    return np.asarray(out, dtype=np.float64)


def _solve(x: FloatArray, y: FloatArray, ridge_lambda: float) -> FloatArray:
    """Intercept-plus-slopes least squares; the intercept is never penalized."""
    xm, ym = x.mean(axis=0), y.mean()
    xc, yc = x - xm, y - ym
    gram = xc.T @ xc + ridge_lambda * np.eye(x.shape[1])
    slopes = np.linalg.solve(gram, xc.T @ yc)
    return np.concatenate([[ym - float(xm @ slopes)], slopes])


def loo_predictions(x: FloatArray, y: FloatArray, ridge_lambda: float) -> FloatArray:
    """Leave-one-out predictions in log space (exact refits).

    Args:
        x: Design without intercept (n x k).
        y: log targets.
        ridge_lambda: Ridge penalty (0 for OLS).

    Returns:
        One out-of-fold prediction per row.
    """
    n = len(y)
    out = np.empty(n)
    for i in range(n):
        keep = np.arange(n) != i
        beta = _solve(x[keep], y[keep], ridge_lambda)
        out[i] = beta[0] + float(x[i] @ beta[1:])
    return out


def fit_model(
    model_id: str,
    target: str,
    rows: Sequence[Mapping[str, float]],
    values: Sequence[float],
    features: Sequence[str],
    ridge_lambda: float = 0.0,
) -> Fit:
    """Fit log(target) on the features, with exact LOO predictions.

    Args:
        model_id: Identifier.
        target: Target id.
        rows: Training feature rows.
        values: Training target values (positive).
        features: Feature names.
        ridge_lambda: Ridge penalty (0 for OLS).

    Returns:
        The fit.

    Raises:
        ValueError: If a row cannot be transformed or a value is not positive.
    """
    transforms = transforms_for(rows, features)
    design = [_row(r, features, transforms) for r in rows]
    if any(d is None for d in design) or any(not (v > 0) for v in values):
        raise ValueError(f"{model_id}: a training row or value cannot be used")
    x = np.vstack([d for d in design if d is not None])
    y = np.log(np.asarray(values, dtype=np.float64))
    beta = _solve(x, y, ridge_lambda)
    loo = np.exp(loo_predictions(x, y, ridge_lambda))
    return Fit(
        model_id=model_id,
        target=target,
        features=tuple(features),
        transforms=transforms,
        coefficients=tuple(float(b) for b in beta),
        ridge_lambda=ridge_lambda,
        feature_range={f: (min(r[f] for r in rows), max(r[f] for r in rows)) for f in features},
        target_range=(float(min(values)), float(max(values))),
        loo_predictions=tuple(float(p) for p in loo),
        n_train=len(values),
    )


@dataclass
class Calibration:
    """The Stage 3 outcome for one target."""

    target: str
    status: str  # "passed", "failed", "insufficient_data" or "not_run"
    reasons: list[str] = field(default_factory=list)
    fits: list[Fit] = field(default_factory=list)
    chosen: Fit | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    holdout_predictions: list[float] = field(default_factory=list)


def calibrate(
    target: str,
    train_rows: Sequence[Mapping[str, float]],
    train_values: Sequence[float],
    holdout_rows: Sequence[Mapping[str, float]],
    holdout_values: Sequence[float],
    top_features: Sequence[str],
    cfg: Stage3,
) -> Calibration:
    """Fit the candidate models, pick one on training LOO, score it once on the hold-out.

    Args:
        target: Target id.
        train_rows: Training feature rows.
        train_values: Training targets (positive, not censored).
        holdout_rows: Hold-out feature rows.
        holdout_values: Hold-out targets.
        top_features: The Stage 1 top candidates (training only), best first.
        cfg: Criteria.

    Returns:
        The outcome, with every fit and the criteria's reasons.
    """
    result = Calibration(target=target, status="not_run")
    if len(holdout_values) < cfg.min_holdout:
        result.status = "insufficient_data"
        result.reasons.append(f"{len(holdout_values)} hold-out pairs, {cfg.min_holdout} needed")
        return result
    for k, feature in enumerate(top_features[:2], start=1):
        result.fits.append(
            fit_model(f"{target}:M{k}:{feature}", target, train_rows, train_values, [feature])
        )
    pair = list(top_features[:2])
    if len(pair) == 2 and len(train_values) >= cfg.ridge_min_per_feature * 2:
        best = None
        for lam in cfg.ridge_lambdas:
            fit = fit_model(
                f"{target}:M3:ridge:{lam:g}", target, train_rows, train_values, pair, lam
            )
            score = mdsa(fit.loo_predictions, train_values)
            if best is None or score < best[0]:
                best = (score, fit)
        if best is not None:
            result.fits.append(best[1])
    chosen = min(result.fits, key=lambda f: mdsa(f.loo_predictions, train_values))
    result.chosen = chosen
    preds = [chosen.predict(r) for r in holdout_rows]
    result.holdout_predictions = preds
    median = float(np.median(train_values))
    null_loo = [
        float(np.median([v for j, v in enumerate(train_values) if j != i]))
        for i in range(len(train_values))
    ]
    m = result.metrics
    m["loo_mdsa"] = mdsa(chosen.loo_predictions, train_values)
    m["loo_sspb"] = sspb(chosen.loo_predictions, train_values)
    m["loo_mape"] = mape(chosen.loo_predictions, train_values)
    m["null_loo_mdsa"] = mdsa(null_loo, train_values)
    m["holdout_mdsa"] = mdsa(preds, holdout_values)
    m["holdout_sspb"] = sspb(preds, holdout_values)
    m["holdout_mape"] = mape(preds, holdout_values)
    m["null_holdout_mdsa"] = mdsa([median] * len(holdout_values), holdout_values)
    checks = [
        (m["loo_mdsa"] <= cfg.mdsa_max, f"LOO MdSA {m['loo_mdsa']:.1f} % > {cfg.mdsa_max:g} %"),
        (m["holdout_mdsa"] <= cfg.mdsa_max,
         f"hold-out MdSA {m['holdout_mdsa']:.1f} % > {cfg.mdsa_max:g} %"),
        (abs(m["loo_sspb"]) <= cfg.sspb_abs_max,
         f"|LOO SSPB| {abs(m['loo_sspb']):.1f} % > {cfg.sspb_abs_max:g} %"),
        (abs(m["holdout_sspb"]) <= cfg.sspb_abs_max,
         f"|hold-out SSPB| {abs(m['holdout_sspb']):.1f} % > {cfg.sspb_abs_max:g} %"),
        (m["loo_mdsa"] <= cfg.null_ratio_max * m["null_loo_mdsa"],
         "LOO MdSA not below 0.8 x the null model's"),
        (m["holdout_mdsa"] <= cfg.null_ratio_max * m["null_holdout_mdsa"],
         "hold-out MdSA not below 0.8 x the null model's"),
    ]  # fmt: skip
    result.reasons = [text for ok, text in checks if not ok]
    result.status = "passed" if not result.reasons else "failed"
    return result


def abstain_reason(
    fit: Fit,
    row: Mapping[str, float],
    stats: Mapping[str, float],
    window: WindowSettings,
) -> str | None:
    """Why a calibrated model must not give a value for this scene (None: it may).

    Args:
        fit: The chosen model.
        row: The scene's features.
        stats: The scene's window statistics: ``glint_share``, ``contamination``, ``valid_px``,
            ``b11_ok`` (1 or 0) and ``bands_read`` (0 when SCL alone ruled the window out).
        window: Window settings.

    Returns:
        The reason, or None.
    """
    if reason := window_abstain_reason(stats, window):
        return reason
    for f in fit.features:
        low, high = fit.feature_range[f]
        v = row.get(f, math.nan)
        if not (math.isfinite(v) and low <= v <= high):
            return f"{f} outside the training range"
    return None


def window_abstain_reason(stats: Mapping[str, float], window: WindowSettings) -> str | None:
    """Why a window's statistics rule out any value, whatever the model (None: they do not).

    Args:
        stats: The window statistics: ``glint_share``, ``contamination``, ``valid_px``, ``b11_ok``
            (1 or 0) and ``bands_read`` (0 when SCL alone ruled the window out).
        window: Window settings.

    Returns:
        The reason, or None.
    """
    if not stats.get("bands_read", 1.0) >= 1:
        return "window too cloudy to measure"
    if stats.get("b11_ok", 0.0) < 1:
        return "failed water-B11 check"
    if stats.get("valid_px", 0.0) < window.min_valid_px:
        return f"fewer than {window.min_valid_px} valid pixels"
    if stats.get("contamination", 1.0) > window.max_contamination:
        return f"contamination above {window.max_contamination:g}"
    if stats.get("glint_share", 1.0) > window.abstain_glint_share:
        return f"glint share above {window.abstain_glint_share:g}"
    return None


def uncertainty_band(value: float, loo_mdsa: float) -> tuple[float, float]:
    """The ``loo_mdsa_band`` interval: value / (1 + MdSA) to value x (1 + MdSA).

    Args:
        value: The prediction.
        loo_mdsa: The model's LOO MdSA, percent.

    Returns:
        ``(low, high)``.
    """
    factor = 1 + loo_mdsa / 100
    return value / factor, value * factor


# ----------------------------------------------------------------------------------------------
# Published semi-analytical models (Stage 4, report-only)
# ----------------------------------------------------------------------------------------------


def nechad(rho_w: float, a: float, c: float) -> float:
    """Nechad et al. single-band model: A rho_w / (1 - rho_w / C).

    Args:
        rho_w: Water-leaving reflectance (here: L2A surface reflectance, a stated approximation).
        a: Calibration coefficient A.
        c: Calibration coefficient C.

    Returns:
        The estimate (NaN outside the model's domain).
    """
    if not math.isfinite(rho_w) or rho_w <= 0 or rho_w >= c:
        return math.nan
    return a * rho_w / (1 - rho_w / c)


def dogliotti_switch(
    rho_red: float,
    rho_nir: float,
    red: tuple[float, float],
    nir: tuple[float, float],
    low: float = 0.05,
    high: float = 0.07,
) -> float:
    """Dogliotti et al. (2015) turbidity: red model below ``low``, NIR above ``high``, blended.

    Args:
        rho_red: Red reflectance.
        rho_nir: NIR reflectance.
        red: ``(A, C)`` of the red band.
        nir: ``(A, C)`` of the NIR band.
        low: Red reflectance below which the red model is used.
        high: Red reflectance above which the NIR model is used.

    Returns:
        The estimate (NaN outside the domain).
    """
    t_red, t_nir = nechad(rho_red, *red), nechad(rho_nir, *nir)
    if not math.isfinite(rho_red):
        return math.nan
    if rho_red < low:
        return t_red
    if rho_red > high:
        return t_nir
    w = (rho_red - low) / (high - low)
    return (1 - w) * t_red + w * t_nir
