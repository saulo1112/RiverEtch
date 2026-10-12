"""The product's model cards: the selected model, refit, with everything a record needs to use it.

After the single test evaluation, the selected candidate is refit with the Magdalena pairs (A1 on
every Colombian pair; A2-A4 keep their USGS pretraining and refit the Colombian adjustment). Its
card holds the parameters, the adjustment, each feature's training range (for abstention), the
interval quantiles recomputed with the Magdalena leave-one-station-out residuals added, the level
of each predicted range (from the test, before the refit) and the metrics. ``parametersHash`` is
the SHA-256 of the parts that decide an estimate, so a registry can anchor the card with each
record. :func:`estimate` applies a card to one scene's features.
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from climate_pipeline.calibration import models
from climate_pipeline.calibration.matchups import Pair
from climate_pipeline.quality import transfer, trees
from climate_pipeline.quality.config import QualityConfig, Target

VERSION = "1"
CRLF, LF = b"\r\n", b"\n"


def file_sha256(path: Path) -> str:
    """The SHA-256 of a text file with LF line endings, whatever the checkout wrote.

    A Windows working copy can hold CRLF where the repository holds LF (deviation 10), so the
    hash is taken over the LF form.

    Args:
        path: The file.

    Returns:
        The hex digest.
    """
    return hashlib.sha256(path.read_bytes().replace(CRLF, LF)).hexdigest()


def _range(pairs: Sequence[Pair], names: Sequence[str]) -> dict[str, list[float]]:
    out = {}
    for n in names:
        values = [p.features.get(n, math.nan) for p in pairs]
        finite = [v for v in values if math.isfinite(v)]
        if finite:
            out[n] = [round(min(finite), 6), round(max(finite), 6)]
    return out


def _finite(v: Any) -> Any:
    """Floats rounded to 4 digits, NaN and infinity as None (the card is strict JSON)."""
    if isinstance(v, float):
        return round(v, 4) if math.isfinite(v) else None
    return v


def _quantiles(estimates: Sequence[float], observed: Sequence[float],
               coverages: Sequence[float]) -> dict[str, Any] | None:  # fmt: skip
    from climate_pipeline.quality.route_a import conformal

    q = conformal(estimates, observed, coverages)
    if q is None:
        return None
    return {"edges": [round(e, 6) for e in q.edges],
            "q": {f"{c:g}": [round(v, 6) if math.isfinite(v) else None for v in q.q[c]]
                  for c in coverages},
            "pooled": [f"{c:g}" for c in sorted(q.pooled)]}  # fmt: skip


def product_card(
    cfg: QualityConfig, target: Target, window: str, product: str, train: Sequence[Pair],
    test: Sequence[Pair], usgs: transfer.UsgsInputs | None, oof: Sequence[float],
    refit: Sequence[float], metrics: Mapping[str, Mapping[str, float]],
    levels: Sequence[Mapping[str, Any]], lab_dir: Path,
    p5: tuple[Sequence[str], Sequence[float]] | None = None,
) -> dict[str, Any]:  # fmt: skip
    """The card of the refit product model of one target.

    Args:
        cfg: Settings.
        target: The target.
        window: The window its pairs used.
        product: The selected candidate.
        train: Colombian training pairs (off the test stream).
        test: Magdalena pairs.
        usgs: The USGS inputs (A2-A4).
        oof: The candidate's leave-one-river-out estimates of ``train``.
        refit: The refit's leave-one-station-out estimates of ``test``.
        metrics: ``loro``, ``test`` and ``refit`` metrics.
        levels: The level rows of each predicted range.
        lab_dir: Where the lab's A4 models are.
        p5: For v2.1's local ridge (P5): its features and penalties (no pretraining).

    Returns:
        The card (JSON-ready).
    """
    every = [*train, *test]
    parameters: dict[str, Any]
    adjustment: dict[str, float] | None = None
    if p5 is not None:
        names, lambdas = list(p5[0]), p5[1]
        use = transfer.usable_rows(every, names)
        lam = transfer.choose_lambda(use, lambda p: p.station, names, lambdas)
        local = transfer.fit_linear(use, names, lam)
        parameters = {"kind": "linear-log", "features": names,
                      "mean": [round(v, 10) for v in local.mean],
                      "scale": [round(v, 10) for v in local.scale],
                      "coefficients": [round(c, 10) for c in local.coefficients],
                      "ridgeLambda": local.ridge_lambda}  # fmt: skip
        ranges = _range(every, names)
    elif product == "A1":
        use = [p for p in every if p.features.get("B8A/B04", math.nan) > 0]
        fit = models.fit_model("A1", target.id, [p.features for p in use],
                               [p.value for p in use], ["B8A/B04"])  # fmt: skip
        parameters = {"kind": "loglog", "features": ["B8A/B04"],
                      "transforms": list(fit.transforms),
                      "coefficients": [round(c, 10) for c in fit.coefficients]}  # fmt: skip
        ranges = {k: [round(a, 6), round(b, 6)] for k, (a, b) in fit.feature_range.items()}
    else:
        if usgs is None:
            raise ValueError(f"{product} needs the USGS pilot")
        model = transfer.pretrained_objects(cfg, usgs, target.id, window)[product]
        adj = transfer.adjustment([model.predict(p.features) for p in every], every,
                                  cfg.selection.adjustment_lambdas,
                                  cfg.selection.adjustment_min_pairs)  # fmt: skip
        adjustment = {"a": round(adj.a, 10), "b": round(adj.b, 10),
                      "ridgeLambda": adj.ridge_lambda}  # fmt: skip
        if isinstance(model, transfer.Linear):
            parameters = {"kind": "linear-log", "features": list(model.names),
                          "mean": [round(v, 10) for v in model.mean],
                          "scale": [round(v, 10) for v in model.scale],
                          "coefficients": [round(c, 10) for c in model.coefficients],
                          "ridgeLambda": model.ridge_lambda}  # fmt: skip
            names = list(model.names)
        else:
            path = lab_dir / f"gbm-{target.id}-{window}.json"
            parameters = {"kind": "lightgbm", "features": list(model.feature_names),
                          "file": path.name,
                          "sha256": file_sha256(path)}  # fmt: skip
            names = list(model.feature_names)
        ranges = _range([*usgs.pairs.get((target.id, window), []), *every], names)
    intervals = _quantiles([*oof, *refit], [p.value for p in every], cfg.intervals.coverages)
    observed = [p.value for p in every]
    decisive = {"parameters": parameters, "adjustment": adjustment, "featureRange": ranges,
                "targetRange": [round(min(observed), 6), round(max(observed), 6)],
                "intervals": intervals}  # fmt: skip
    digest = hashlib.sha256(json.dumps(decisive, sort_keys=True).encode()).hexdigest()
    return {
        "modelId": f"{product}:{target.id}:{window}", "version": VERSION, "target": target.id,
        "unit": target.unit, "window": window, "candidate": product, **decisive,
        "levels": [{k: _finite(v) for k, v in r.items()} for r in levels],
        "metrics": {k: {m: _finite(v) for m, v in d.items() if isinstance(v, int | float)}
                    for k, d in metrics.items()},
        "trainingPairs": {"colombia": len(every),
                          "usgs": len(usgs.pairs.get((target.id, window), [])) if usgs else 0},
        "parametersHash": digest,
    }  # fmt: skip


def card_hash(card: Mapping[str, Any]) -> str:
    """The SHA-256 of a whole card's canonical JSON (what a record names).

    Args:
        card: The card.

    Returns:
        The hex digest.
    """
    return hashlib.sha256(json.dumps(card, sort_keys=True, separators=(",", ":")).encode()
                          ).hexdigest()  # fmt: skip


def estimate(card: Mapping[str, Any], row: Mapping[str, float], lab_dir: Path) -> float:
    """A card's estimate for one scene's features (NaN when a feature is missing).

    Args:
        card: The card.
        row: The scene's features (candidate values and F).
        lab_dir: Where an A4 card's forest lives.

    Returns:
        The estimate in the target's unit.
    """
    p = card["parameters"]
    if p["kind"] == "loglog":
        x = row.get(p["features"][0], math.nan)
        if not (math.isfinite(x) and x > 0):
            return math.nan
        a, b = p["coefficients"]
        return math.exp(a + b * math.log(x))
    if p["kind"] == "ridge-log":
        return _ridge_log(p, row, lab_dir)
    if p["kind"] == "linear-log":
        raw = transfer.Linear(tuple(p["features"]), tuple(p["mean"]), tuple(p["scale"]),
                              tuple(p["coefficients"]), p["ridgeLambda"]).predict(row)  # fmt: skip
    else:
        forest = _forest(lab_dir / p["file"])
        raw = forest.predict(row) if forest is not None else math.nan
    adj = card.get("adjustment") or {"a": 0.0, "b": 1.0}
    return transfer.Adjustment(adj["a"], adj["b"]).apply(raw)


@functools.lru_cache(maxsize=8)
def _forest(path: Path) -> trees.Forest | None:
    """A lab forest, parsed once per run (the files are about 2 MB)."""
    return trees.load(path)


def _ridge_log(p: Mapping[str, Any], row: Mapping[str, float], lab_dir: Path) -> float:
    """v3 and v4's ridge in log space (its station offset is in the intercept).

    ``log_T`` is A4's raw output for the scene; ``g`` is 0, as the scene is the estimate's own day.
    A feature the scene lacks (the day's flow index) makes the estimate NaN, so it abstains.
    """
    values = dict(row)
    if "log_T" in p["features"]:
        forest = _forest(lab_dir / p["tFile"])
        values["log_T"] = forest.log_estimate(row) if forest is not None else math.nan
    if "g" in p["features"]:
        values["g"] = 0.0
    x = [values.get(n, math.nan) for n in p["features"]]
    if not all(math.isfinite(v) for v in x):
        return math.nan
    z = [(v - m) / s for v, m, s in zip(x, p["mean"], p["scale"], strict=True)]
    return math.exp(p["intercept"] + sum(c * v for c, v in zip(p["coefficients"], z, strict=True)))


def interval(card: Mapping[str, Any], value: float, coverage: float) -> tuple[float, float]:
    """The card's interval around an estimate.

    Args:
        card: The card.
        value: The estimate.
        coverage: E.g. 0.9.

    Returns:
        ``(low, high)``; infinite when the card has no finite quantile there.
    """
    q = card.get("intervals")
    if not q or not math.isfinite(value):
        return math.nan, math.nan
    edges = q["edges"]
    k = 0 if value < edges[0] else 1 if value < edges[1] else 2
    width = q["q"].get(f"{coverage:g}", [None] * 3)[k]
    if width is None:
        return 0.0, math.inf
    return value * math.exp(-width), value * math.exp(width)


def level_of(card: Mapping[str, Any], target: Target, value: float) -> tuple[str, float]:
    """The level of the predicted range an estimate falls in, and that range's test MdSA.

    Args:
        card: The card.
        target: The target (its bins).
        value: The estimate.

    Returns:
        ``(level, mdsa)``; the card's overall level for a range it has no row for.
    """
    from climate_pipeline.quality.route_b import bin_label

    rows = {r["predicted_range"]: r for r in card.get("levels", [])}
    overall = rows.get("all", {"level": "none", "mdsa": math.nan})
    if not math.isfinite(value):
        return "none", math.nan
    row = rows.get(bin_label(target.bins, target.bin_of(value)), overall)
    return str(row["level"]), float(row.get("mdsa") or math.nan)


def outside_range(card: Mapping[str, Any], row: Mapping[str, float]) -> str | None:
    """The first feature outside its training range (abstention), if any.

    Args:
        card: The card.
        row: The scene's features.

    Returns:
        The reason, or None.
    """
    for name, (low, high) in card.get("featureRange", {}).items():
        v = row.get(name, math.nan)
        if not (math.isfinite(v) and low <= v <= high):
            return f"{name} outside the training range"
    return None
