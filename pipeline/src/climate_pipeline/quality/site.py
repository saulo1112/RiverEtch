"""v4, section A: the Missouri River at Hermann, validated on a temporal lock box (preregistration).

The second demo reach has a continuous, approved turbidity gauge (USGS 06934500, FNU). Its pairs
are every clear Earth Search scene with the gauge's value at the overpass. The hydrological years
2019-2023 (2018-12-01..2023-11-30) train and select; 2023-12-01..2026-09-30 is a lock box,
evaluated once.

* **H0**: the median of the training values.
* **H1**: log-log OLS on B8A/B04, fitted on Hermann's training pairs.
* **H2, H3, H4**: A2, A3 and A4 trained on the USGS pilot **without the Missouri's sites**, then
  the site adjustment log y = a + b log yhat (lambda by leave-one-year-out in the training years).

Inside the training years each candidate is scored by leave-one-hydrological-year-out; the lowest
MdSA wins, the simpler within 5 points. The winner fitted on the training years is the card, with
no refit, so the lock box's error is the card's own. Intervals are split conformal on the winner's
inner residuals; the levels follow the site rules of the preregistration (v4, A).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from climate_pipeline.calibration import models, stats
from climate_pipeline.calibration.matchups import Pair
from climate_pipeline.quality import cards, posthoc, route_a, transfer, trees
from climate_pipeline.quality.config import QualityConfig, Target
from climate_pipeline.quality.route_a import Predictor, Quantiles

SITE = "USGS-06934500"
SLUG = "missouri-hermann"
RIVER = "MISSOURI"
FOLDER = "usgs-hermann"
TARGET, WINDOW, UNIT = "turbidity", "core", "FNU"
TRAIN = (date(2018, 12, 1), date(2023, 11, 30))
LOCK = (date(2023, 12, 1), date(2026, 9, 30))
ORDER = ("H1", "H2", "H3", "H4")  # simplest first
PRETRAINED = {"H2": "A2", "H3": "A3", "H4": "A4"}
LAB = "no-missouri"  # inputs/lab/<LAB>/gbm-turbidity-core.json: A4 without the Missouri
BASIS = "preregistered_lockbox_site"
CARD = f"{SLUG}/{TARGET}.json"  # under results/models/
VALIDATED_MIN_YEARS = 2


def year(p: Pair) -> str:
    """The hydrological year of a pair (December opens the next).

    Args:
        p: The pair.

    Returns:
        E.g. ``"2021"``.
    """
    return posthoc.hydrological_year(p)


def split(pairs: Sequence[Pair]) -> tuple[list[Pair], list[Pair]]:
    """The training years and the lock box.

    Args:
        pairs: Hermann's pairs.

    Returns:
        ``(train, lock)``, each in date order.
    """
    ordered = sorted(pairs, key=lambda p: (p.sample_day, p.scene_key))
    train = [p for p in ordered if TRAIN[0] <= p.sample_day <= TRAIN[1]]
    lock = [p for p in ordered if LOCK[0] <= p.sample_day <= LOCK[1]]
    return train, lock


def without_river(usgs: transfer.UsgsInputs, river: str,
                  forest: trees.Forest | None) -> transfer.UsgsInputs:  # fmt: skip
    """The pilot without one river's sites, with the lab's A4 trained the same way.

    Args:
        usgs: The pilot.
        river: The river left out.
        forest: A4 without that river (None: no A4).

    Returns:
        The reduced inputs.
    """
    pairs = {k: [p for p in v if usgs.river_of.get(p.station, p.station) != river]
             for k, v in usgs.pairs.items()}  # fmt: skip
    forests = {(TARGET, WINDOW): forest} if forest is not None else {}
    return transfer.UsgsInputs(pairs, dict(usgs.river_of), forests)


def site_level(metrics: Mapping[str, float], cfg: QualityConfig, years: int) -> str:
    """A level under the site rules (v4, A): the station count becomes a count of years.

    Args:
        metrics: ``n``, ``mdsa``, ``sspb``, ``null_mdsa``, ``coverage90``, ``rho_low``.
        cfg: Settings (the thresholds of v2's levels).
        years: Hydrological years among the scored pairs.

    Returns:
        ``validated``, ``estimated``, ``indicative`` or ``none``.
    """
    lv = cfg.levels
    if metrics.get("n", 0) < lv.min_test_pairs or not math.isfinite(metrics.get("mdsa", math.nan)):
        return "none"
    cov = metrics.get("coverage90", math.nan)

    def meets(c: Any) -> bool:
        return bool(metrics["mdsa"] <= c.mdsa_max and abs(metrics["sspb"]) <= c.sspb_abs_max
                    and metrics["mdsa"] <= c.null_ratio_max * metrics["null_mdsa"]
                    and c.coverage_90[0] <= cov <= c.coverage_90[1])  # fmt: skip

    v = lv.validated
    if meets(v) and metrics["n"] >= (v.min_pairs or 0) and years >= VALIDATED_MIN_YEARS:
        return "validated"
    if meets(lv.estimated):
        return "estimated"
    if metrics.get("rho_low", -1) > lv.indicative.lower_bound_min:
        return "indicative"
    return "none"


def level_rows(cfg: QualityConfig, target: Target, lock: Sequence[Pair], est: Sequence[float],
               null: Sequence[float], q: Quantiles | None, seed: int
               ) -> list[dict[str, Any]]:  # fmt: skip
    """The lock box's level overall and per predicted range (a small range: capped overall).

    Args:
        cfg: Settings.
        target: The target (its bins, read in FNU here).
        lock: Lock-box pairs.
        est: The card's estimates.
        null: H0's estimates.
        q: The card's conformal quantiles.
        seed: Bootstrap seed.

    Returns:
        The ``all`` row first, then one row per range with an estimate.
    """
    from climate_pipeline.quality.route_b import bin_label

    def scored(idx: Sequence[int], s: int) -> tuple[dict[str, float], int]:
        m = route_a.evaluate(cfg, [lock[i] for i in idx], [est[i] for i in idx],
                             [null[i] for i in idx], q, s)  # fmt: skip
        return m, len({year(lock[i]) for i in idx})

    valid = [i for i, e in enumerate(est) if math.isfinite(e) and e > 0]
    overall_m, overall_years = scored(valid, seed)
    overall = site_level(overall_m, cfg, overall_years)
    rows = [_row("all", overall_m, True, overall, overall_years)]
    for b in range(len(target.bins) + 1):
        idx = [i for i in valid if target.bin_of(est[i]) == b]
        if not idx:
            continue
        m, years = scored(idx, seed + b + 1)
        rated = len(idx) >= cfg.levels.min_bin_pairs
        capped = "estimated" if overall == "validated" else overall
        rows.append(_row(bin_label(target.bins, b), m, rated,
                         site_level(m, cfg, years) if rated else capped, years))  # fmt: skip
    return rows


def _row(label: str, m: Mapping[str, float], rated: bool, lv: str, years: int) -> dict[str, Any]:
    return {"predicted_range": label, "n": int(m["n"]), "years": years, "rated": rated,
            "mdsa": m["mdsa"], "sspb": m["sspb"], "rho_low": m["rho_low"],
            "null_mdsa": m["null_mdsa"], "coverage90": m["coverage90"], "level": lv}  # fmt: skip


def candidates(cfg: QualityConfig, other: transfer.UsgsInputs) -> dict[str, Predictor]:
    """H1-H4 as predictors ``(train, test) -> estimates``.

    Args:
        cfg: Settings.
        other: The pilot without the Missouri.

    Returns:
        Candidate -> predictor, simplest first.
    """
    out: dict[str, Predictor] = {"H1": route_a.a1}
    pretrained = transfer.pretrained_models(cfg, other, TARGET, WINDOW)
    for cid, source in PRETRAINED.items():
        if source in pretrained:
            out[cid] = transfer.transfer_predictor(pretrained[source], cfg, group=year)
    return out


def _valid_mdsa(estimates: Sequence[float], pairs: Sequence[Pair]) -> float:
    ok = [(e, p.value) for e, p in zip(estimates, pairs, strict=True)
          if math.isfinite(e) and e > 0]  # fmt: skip
    return stats.mdsa([e for e, _ in ok], [o for _, o in ok]) if len(ok) >= 5 else math.inf


def card(cfg: QualityConfig, target: Target, pick: str, train: Sequence[Pair],
         other: transfer.UsgsInputs, oof: Sequence[float], levels: Sequence[Mapping[str, Any]],
         metrics: Mapping[str, Mapping[str, float]], lab_dir: Path) -> dict[str, Any]:  # fmt: skip
    """The card of the selected candidate, fitted on the training years (no refit).

    Args:
        cfg: Settings.
        target: The target.
        pick: The selected candidate.
        train: Hermann's training pairs.
        other: The pilot without the Missouri.
        oof: The candidate's inner leave-one-year-out estimates of ``train``.
        levels: The lock box's level rows.
        metrics: ``inner`` and ``lockbox`` metrics.
        lab_dir: The lab's models (A4's file is relative to it).

    Returns:
        The card (JSON-ready).
    """
    parameters: dict[str, Any]
    adjustment: dict[str, float] | None = None
    if pick == "H1":
        use = [p for p in train if p.features.get("B8A/B04", math.nan) > 0]
        fit = models.fit_model("H1", target.id, [p.features for p in use],
                               [p.value for p in use], ["B8A/B04"])  # fmt: skip
        parameters = {"kind": "loglog", "features": ["B8A/B04"],
                      "transforms": list(fit.transforms),
                      "coefficients": [round(c, 10) for c in fit.coefficients]}  # fmt: skip
        ranges = {k: [round(a, 6), round(b, 6)] for k, (a, b) in fit.feature_range.items()}
    else:
        model = transfer.pretrained_objects(cfg, other, TARGET, WINDOW)[PRETRAINED[pick]]
        adj = transfer.adjustment([model.predict(p.features) for p in train], train,
                                  cfg.selection.adjustment_lambdas,
                                  cfg.selection.adjustment_min_pairs, year)  # fmt: skip
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
            path = lab_dir / LAB / f"gbm-{TARGET}-{WINDOW}.json"
            parameters = {"kind": "lightgbm", "features": list(model.feature_names),
                          "file": f"{LAB}/{path.name}",
                          "sha256": cards.file_sha256(path)}  # fmt: skip
            names = list(model.feature_names)
        ranges = cards._range([*other.pairs.get((TARGET, WINDOW), []), *train], names)
    observed = [p.value for p in train]
    decisive = {"parameters": parameters, "adjustment": adjustment, "featureRange": ranges,
                "targetRange": [round(min(observed), 6), round(max(observed), 6)],
                "intervals": cards._quantiles(oof, observed, cfg.intervals.coverages)}  # fmt: skip
    digest = hashlib.sha256(json.dumps(decisive, sort_keys=True).encode()).hexdigest()
    return {
        "modelId": f"{pick}:{target.id}:{WINDOW}:{SLUG}", "version": cards.VERSION,
        "target": target.id, "unit": UNIT, "window": WINDOW, "candidate": pick, "basis": BASIS,
        "site": SITE, "lockbox": [LOCK[0].isoformat(), LOCK[1].isoformat()],
        "training": [TRAIN[0].isoformat(), TRAIN[1].isoformat()], **decisive,
        "levels": [{k: cards._finite(v) for k, v in r.items()} for r in levels],
        "metrics": {k: {m: cards._finite(v) for m, v in d.items() if isinstance(v, int | float)}
                    for k, d in metrics.items()},
        "trainingPairs": {"site": len(train),
                          "usgs": len(other.pairs.get((TARGET, WINDOW), []))},
        "parametersHash": digest,
    }  # fmt: skip


def lab_forest(root: Path, cfg: QualityConfig) -> trees.Forest | None:
    """A4 without the Missouri, checked against the lab's own predictions.

    Args:
        root: Repository root.
        cfg: Settings.

    Returns:
        The forest (None before the lab has trained it).

    Raises:
        ValueError: When the numpy evaluator disagrees with LightGBM.
    """
    from climate_pipeline.quality.lab import TOLERANCE

    path = root / cfg.outputs.inputs / "lab" / LAB / f"gbm-{TARGET}-{WINDOW}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    forest = trees.from_dump(data["model"])
    gap = trees.check(forest, data["check"]["rows"], data["check"]["raw"])
    if gap > TOLERANCE:
        raise ValueError(f"{path.name}: the evaluator differs from LightGBM by {gap:g}")
    return forest


def analyse(cfg: QualityConfig, root: Path,
            usgs: transfer.UsgsInputs | None) -> dict[str, list[dict[str, Any]]]:  # fmt: skip
    """Section A's tables and the Hermann card (under ``_site_cards``).

    Args:
        cfg: Settings.
        root: Repository root.
        usgs: The USGS pilot (pretraining).

    Returns:
        ``site_scores``, ``site_levels``, ``site_inner`` and the card.
    """
    from climate_pipeline.quality.route_b import _seed

    tables: dict[str, list[dict[str, Any]]] = {"site_scores": [], "site_levels": [],
                                               "site_inner": []}  # fmt: skip
    hermann = transfer.load_usgs(cfg, root, folder=FOLDER)
    if hermann is None or usgs is None:
        tables["site_scores"].append({"site": SITE, "status": "no snapshot yet"})
        return tables
    target = cfg.target(TARGET)
    pairs = [p for p in hermann.pairs.get((TARGET, WINDOW), []) if p.station == SITE]
    train, lock = split(pairs)
    other = without_river(usgs, RIVER, lab_forest(root, cfg))
    options = candidates(cfg, other)
    seed = _seed(cfg.seed, "v4", "site", SITE)
    observed = [p.value for p in train]
    oofs = {c: route_a.leave_one_group_out(train, year, f) for c, f in options.items()}
    inner = {c: _valid_mdsa(e, train) for c, e in oofs.items()}
    pick = posthoc.choose(inner, cfg.selection.simpler_within_mdsa, ORDER)
    base = {"site": SITE, "target": TARGET, "unit": UNIT, "window": WINDOW}
    tables["site_inner"] += [{**base, "candidate": c, "inner_loyo_mdsa": inner[c],
                              "chosen": c == pick} for c in options]  # fmt: skip
    null = route_a.null(train, lock)
    quantiles = {c: route_a.conformal(e, observed, cfg.intervals.coverages)
                 for c, e in oofs.items()}  # fmt: skip
    estimates = {c: f(train, lock) for c, f in options.items()}
    counts = {"training_pairs": len(train), "lockbox_pairs": len(lock),
              "training_years": len({year(p) for p in train}),
              "lockbox_years": len({year(p) for p in lock}),
              "usgs_pairs_without_river": len(other.pairs.get((TARGET, WINDOW), []))}  # fmt: skip

    def score(label: str, est: Sequence[float], q: Quantiles | None, s: int) -> dict[str, float]:
        m = route_a.evaluate(cfg, lock, est, null, q, s)
        tables["site_scores"].append({**base, "candidate": label, "evaluation": "lock box",
                                      **m})  # fmt: skip
        return m

    score("H0", null, None, seed)
    lock_metrics = {c: score(c, estimates[c], quantiles[c], seed + 1 + k)
                    for k, c in enumerate(options)}  # fmt: skip
    for k, (cid, source) in enumerate(PRETRAINED.items()):  # report-only: no site adjustment
        model = transfer.pretrained_objects(cfg, other, TARGET, WINDOW).get(source)
        if model is not None:
            score(
                f"{cid} without the site adjustment (other rivers only)",
                [model.predict(p.features) for p in lock],
                None,
                seed + 10 + k,
            )
    rows = level_rows(cfg, target, lock, estimates[pick], null, quantiles[pick], seed + 20)
    tables["site_levels"] += [{**base, "candidate": pick, **r} for r in rows]
    tables["site_scores"][0].update(counts)
    inner_m = route_a.evaluate(cfg, train, oofs[pick], route_a.leave_one_group_out(
        train, year, route_a.null), quantiles[pick], seed + 30)  # fmt: skip
    tables["_site_cards"] = [{"path": CARD, "card": card(
        cfg, target, pick, train, other, oofs[pick], rows,
        {"inner": inner_m, "lockbox": lock_metrics[pick]},
        root / cfg.outputs.inputs / "lab")}]  # fmt: skip
    return tables


def summary(tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """The lock box's result: the selected candidate, its MdSA and level.

    Args:
        tables: The run's tables.

    Returns:
        ``site``, ``candidate``, ``mdsa``, ``n`` and ``level`` (empty before the snapshot).
    """
    rows = [r for r in tables.get("site_levels", []) if r.get("predicted_range") == "all"]
    if not rows:
        return {}
    r = rows[0]
    return {"site": SITE, "candidate": r["candidate"], "mdsa": round(r["mdsa"], 1),
            "n": int(r["n"]), "level": r["level"], "unit": UNIT}  # fmt: skip
