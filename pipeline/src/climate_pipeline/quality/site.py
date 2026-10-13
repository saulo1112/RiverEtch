"""Gauged rivers validated on a temporal lock box: v4's Hermann (section A) and v5's rivers.

A gauged reach has a continuous, approved series at a USGS site. Its pairs are every clear Earth
Search scene with the gauge's value at the overpass (or, for discrete suspended-sediment samples,
on the scene's day). The hydrological years 2019-2023 (2018-12-01..2023-11-30) train and select;
2023-12-01..2026-09-30 is a lock box, evaluated once.

* **H0**: the median of the training values.
* **H1**: log-log OLS on B8A/B04, fitted on the site's training pairs.
* **H2, H3, H4**: A2, A3 and A4 trained on the USGS pilot **without the site's river**, then the
  site adjustment log y = a + b log yhat (lambda by leave-one-year-out in the training years).

Inside the training years each candidate is scored by leave-one-hydrological-year-out; the lowest
MdSA wins, the simpler within 5 points. The winner fitted on the training years is the card, with
no refit, so the lock box's error is the card's own. Intervals are split conformal on the winner's
inner residuals. Levels follow v4's site rules (Hermann) or v5's (every v5 evaluation), which
replace the 97 % coverage ceiling with a cap on the interval's width.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

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
V5_COVERAGE_MIN = 0.80  # v5: 90 % coverage at least this (a conservative interval is valid)
V5_FACTOR_MAX = {"validated": 2.5, "estimated": 3.0}  # v5: the median 90 % interval factor


@dataclass(frozen=True)
class Run:
    """One gauged site and target, validated on its lock box."""

    site: str
    slug: str
    river: str  # the pilot's river group left out of pretraining
    target: str  # turbidity or tss
    unit: str
    lab: str  # A4's folder under inputs/lab ("" when the pilot's own A4 never saw the river)
    seed_keys: tuple[str, ...]
    rule: str = "v4"  # the level rules: v4 (Hermann's turbidity) or v5
    window: str = WINDOW
    basis: str = BASIS

    @property
    def card_path(self) -> str:
        """The card's path under ``results/models/``."""
        return f"{self.slug}/{self.target}.json"


HERMANN = Run(SITE, SLUG, RIVER, TARGET, UNIT, LAB, ("v4", "site", SITE))


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
        pairs: A site's pairs.

    Returns:
        ``(train, lock)``, each in date order.
    """
    ordered = sorted(pairs, key=lambda p: (p.sample_day, p.scene_key))
    train = [p for p in ordered if TRAIN[0] <= p.sample_day <= TRAIN[1]]
    lock = [p for p in ordered if LOCK[0] <= p.sample_day <= LOCK[1]]
    return train, lock


def without_river(usgs: transfer.UsgsInputs, river: str, forest: trees.Forest | None,
                  target: str = TARGET, window: str = WINDOW) -> transfer.UsgsInputs:  # fmt: skip
    """The pilot without one river's sites, with the lab's A4 trained the same way.

    Args:
        usgs: The pilot.
        river: The river left out.
        forest: A4 without that river (None: no A4).
        target: A4's target.
        window: A4's window.

    Returns:
        The reduced inputs.
    """
    pairs = {k: [p for p in v if usgs.river_of.get(p.station, p.station) != river]
             for k, v in usgs.pairs.items()}  # fmt: skip
    forests = {(target, window): forest} if forest is not None else {}
    return transfer.UsgsInputs(pairs, dict(usgs.river_of), forests)


def site_level(metrics: Mapping[str, float], cfg: QualityConfig, years: int,
               rule: str = "v4") -> str:  # fmt: skip
    """A level under the site rules: the station count becomes a count of years.

    v4 wants the 90 % coverage in [80 %, 97 %]. v5 wants it at least 80 % and caps the median 90 %
    interval factor (2.5 to validate, 3.0 to estimate).

    Args:
        metrics: ``n``, ``mdsa``, ``sspb``, ``null_mdsa``, ``coverage90``, ``rho_low`` and, for v5,
            ``interval_factor90``.
        cfg: Settings (the thresholds of v2's levels).
        years: Hydrological years among the scored pairs.
        rule: ``v4`` or ``v5``.

    Returns:
        ``validated``, ``estimated``, ``indicative`` or ``none``.
    """
    lv = cfg.levels
    if metrics.get("n", 0) < lv.min_test_pairs or not math.isfinite(metrics.get("mdsa", math.nan)):
        return "none"
    cov = metrics.get("coverage90", math.nan)
    factor = metrics.get("interval_factor90", math.nan)

    def meets(c: Any, level: str) -> bool:
        if rule == "v5":
            covered = cov >= V5_COVERAGE_MIN and factor <= V5_FACTOR_MAX[level]
        else:
            covered = c.coverage_90[0] <= cov <= c.coverage_90[1]
        ratio = metrics["mdsa"] <= c.null_ratio_max * metrics["null_mdsa"]
        return bool(metrics["mdsa"] <= c.mdsa_max and abs(metrics["sspb"]) <= c.sspb_abs_max
                    and ratio and covered)  # fmt: skip

    v = lv.validated
    if (
        meets(v, "validated")
        and metrics["n"] >= (v.min_pairs or 0)
        and years >= VALIDATED_MIN_YEARS
    ):
        return "validated"
    if meets(lv.estimated, "estimated"):
        return "estimated"
    if metrics.get("rho_low", -1) > lv.indicative.lower_bound_min:
        return "indicative"
    return "none"


def interval_factor(
    q: Quantiles | None, estimates: Sequence[float], coverage: float = 0.9
) -> float:
    """The median factor of the intervals (high / estimate) over some estimates.

    Args:
        q: The conformal quantiles.
        estimates: Estimates.
        coverage: The interval's coverage.

    Returns:
        The median factor (NaN without quantiles or estimates).
    """
    if q is None:
        return math.nan
    factors = [q.interval(e, coverage)[1] / e for e in estimates if math.isfinite(e) and e > 0]
    return float(np.median(factors)) if factors else math.nan


def level_rows(cfg: QualityConfig, target: Target, lock: Sequence[Pair], est: Sequence[float],
               null: Sequence[float], q: Quantiles | None, seed: int, rule: str = "v4"
               ) -> list[dict[str, Any]]:  # fmt: skip
    """The lock box's level overall and per predicted range (a small range: capped overall).

    Args:
        cfg: Settings.
        target: The target (its bins, read in the site's unit).
        lock: Lock-box pairs.
        est: The card's estimates.
        null: H0's estimates.
        q: The card's conformal quantiles.
        seed: Bootstrap seed.
        rule: ``v4`` or ``v5`` (which also reports the interval factor).

    Returns:
        The ``all`` row first, then one row per range with an estimate.
    """
    from climate_pipeline.quality.route_b import bin_label

    def scored(idx: Sequence[int], s: int) -> tuple[dict[str, float], int]:
        m = route_a.evaluate(cfg, [lock[i] for i in idx], [est[i] for i in idx],
                             [null[i] for i in idx], q, s)  # fmt: skip
        if rule == "v5":
            m["interval_factor90"] = interval_factor(q, [est[i] for i in idx])
        return m, len({year(lock[i]) for i in idx})

    valid = [i for i, e in enumerate(est) if math.isfinite(e) and e > 0]
    overall_m, overall_years = scored(valid, seed)
    overall = site_level(overall_m, cfg, overall_years, rule)
    rows = [_row("all", overall_m, True, overall, overall_years, rule)]
    for b in range(len(target.bins) + 1):
        idx = [i for i in valid if target.bin_of(est[i]) == b]
        if not idx:
            continue
        m, years = scored(idx, seed + b + 1)
        rated = len(idx) >= cfg.levels.min_bin_pairs
        capped = "estimated" if overall == "validated" else overall
        lv = site_level(m, cfg, years, rule) if rated else capped
        rows.append(_row(bin_label(target.bins, b), m, rated, lv, years, rule))
    return rows


def _row(label: str, m: Mapping[str, float], rated: bool, lv: str, years: int,
         rule: str = "v4") -> dict[str, Any]:  # fmt: skip
    row = {"predicted_range": label, "n": int(m["n"]), "years": years, "rated": rated,
           "mdsa": m["mdsa"], "sspb": m["sspb"], "rho_low": m["rho_low"],
           "null_mdsa": m["null_mdsa"], "coverage90": m["coverage90"]}  # fmt: skip
    if rule == "v5":
        row["interval_factor90"] = m["interval_factor90"]
    row["level"] = lv
    return row


def candidates(cfg: QualityConfig, other: transfer.UsgsInputs, target: str = TARGET,
               window: str = WINDOW) -> dict[str, Predictor]:  # fmt: skip
    """H1-H4 as predictors ``(train, test) -> estimates``.

    Args:
        cfg: Settings.
        other: The pilot without the site's river.
        target: The target.
        window: The window.

    Returns:
        Candidate -> predictor, simplest first.
    """
    out: dict[str, Predictor] = {"H1": route_a.a1}
    pretrained = transfer.pretrained_models(cfg, other, target, window)
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
         metrics: Mapping[str, Mapping[str, float]], lab_dir: Path,
         run: Run = HERMANN) -> dict[str, Any]:  # fmt: skip
    """The card of the selected candidate, fitted on the training years (no refit).

    Args:
        cfg: Settings.
        target: The target.
        pick: The selected candidate.
        train: The site's training pairs.
        other: The pilot without the site's river.
        oof: The candidate's inner leave-one-year-out estimates of ``train``.
        levels: The lock box's level rows.
        metrics: ``inner`` and ``lockbox`` metrics.
        lab_dir: The lab's models (A4's file is relative to it).
        run: The site and target.

    Returns:
        The card (JSON-ready).
    """
    w = run.window
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
        model = transfer.pretrained_objects(cfg, other, run.target, w)[PRETRAINED[pick]]
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
            name = f"gbm-{run.target}-{w}.json"
            relative = f"{run.lab}/{name}" if run.lab else name
            parameters = {"kind": "lightgbm", "features": list(model.feature_names),
                          "file": relative,
                          "sha256": cards.file_sha256(lab_dir / relative)}  # fmt: skip
            names = list(model.feature_names)
        ranges = cards._range([*other.pairs.get((run.target, w), []), *train], names)
    observed = [p.value for p in train]
    decisive = {"parameters": parameters, "adjustment": adjustment, "featureRange": ranges,
                "targetRange": [round(min(observed), 6), round(max(observed), 6)],
                "intervals": cards._quantiles(oof, observed, cfg.intervals.coverages)}  # fmt: skip
    digest = hashlib.sha256(json.dumps(decisive, sort_keys=True).encode()).hexdigest()
    return {
        "modelId": f"{pick}:{target.id}:{w}:{run.slug}", "version": cards.VERSION,
        "target": target.id, "unit": run.unit, "window": w, "candidate": pick, "basis": run.basis,
        "site": run.site, "lockbox": [LOCK[0].isoformat(), LOCK[1].isoformat()],
        "training": [TRAIN[0].isoformat(), TRAIN[1].isoformat()], **decisive,
        "levels": [{k: cards._finite(v) for k, v in r.items()} for r in levels],
        "metrics": {k: {m: cards._finite(v) for m, v in d.items() if isinstance(v, int | float)}
                    for k, d in metrics.items()},
        "trainingPairs": {"site": len(train),
                          "usgs": len(other.pairs.get((run.target, w), []))},
        "parametersHash": digest,
    }  # fmt: skip


def lab_forest(root: Path, cfg: QualityConfig, run: Run = HERMANN) -> trees.Forest | None:
    """A4 without the site's river, checked against the lab's own predictions.

    Args:
        root: Repository root.
        cfg: Settings.
        run: The site and target.

    Returns:
        The forest (None before the lab has trained it).

    Raises:
        ValueError: When the numpy evaluator disagrees with LightGBM.
    """
    from climate_pipeline.quality.lab import TOLERANCE

    base = root / cfg.outputs.inputs / "lab"
    path = (base / run.lab if run.lab else base) / f"gbm-{run.target}-{run.window}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    forest = trees.from_dump(data["model"])
    gap = trees.check(forest, data["check"]["rows"], data["check"]["raw"])
    if gap > TOLERANCE:
        raise ValueError(f"{path.name}: the evaluator differs from LightGBM by {gap:g}")
    return forest


@dataclass
class Evaluation:
    """One run's rows and card."""

    scores: list[dict[str, Any]]
    levels: list[dict[str, Any]]
    inner: list[dict[str, Any]]
    card: dict[str, Any]
    # The chosen candidate's inner log errors, ln(estimate / observed) (v6's chain reads them).
    inner_log_errors: list[float] = field(default_factory=list)


def evaluate(cfg: QualityConfig, root: Path, usgs: transfer.UsgsInputs, run: Run,
             pairs: Sequence[Pair]) -> Evaluation:  # fmt: skip
    """Select in the training years, score every candidate on the lock box, write the card.

    Args:
        cfg: Settings.
        root: Repository root.
        usgs: The USGS pilot (pretraining).
        run: The site and target.
        pairs: The site's pairs of that target (core window).

    Returns:
        The rows and the card.
    """
    from climate_pipeline.quality.route_b import _seed

    target = cfg.target(run.target)
    train, lock = split(pairs)
    other = without_river(usgs, run.river, lab_forest(root, cfg, run), run.target, run.window)
    options = candidates(cfg, other, run.target, run.window)
    seed = _seed(cfg.seed, *run.seed_keys)
    observed = [p.value for p in train]
    oofs = {c: route_a.leave_one_group_out(train, year, f) for c, f in options.items()}
    inner = {c: _valid_mdsa(e, train) for c, e in oofs.items()}
    pick = posthoc.choose(inner, cfg.selection.simpler_within_mdsa, ORDER)
    base = {"site": run.site, "target": run.target, "unit": run.unit, "window": run.window}
    inner_rows = [{**base, "candidate": c, "inner_loyo_mdsa": inner[c], "chosen": c == pick}
                  for c in options]  # fmt: skip
    null = route_a.null(train, lock)
    quantiles = {c: route_a.conformal(e, observed, cfg.intervals.coverages)
                 for c, e in oofs.items()}  # fmt: skip
    estimates = {c: f(train, lock) for c, f in options.items()}
    counts = {"training_pairs": len(train), "lockbox_pairs": len(lock),
              "training_years": len({year(p) for p in train}),
              "lockbox_years": len({year(p) for p in lock}),
              "usgs_pairs_without_river": len(other.pairs.get(
                  (run.target, run.window), []))}  # fmt: skip
    scores: list[dict[str, Any]] = []

    def score(label: str, est: Sequence[float], q: Quantiles | None, s: int) -> dict[str, float]:
        m = route_a.evaluate(cfg, lock, est, null, q, s)
        scores.append({**base, "candidate": label, "evaluation": "lock box", **m})
        return m

    score("H0", null, None, seed)
    lock_metrics = {c: score(c, estimates[c], quantiles[c], seed + 1 + k)
                    for k, c in enumerate(options)}  # fmt: skip
    for k, (cid, source) in enumerate(PRETRAINED.items()):  # report-only: no site adjustment
        model = transfer.pretrained_objects(cfg, other, run.target, run.window).get(source)
        if model is not None:
            score(
                f"{cid} without the site adjustment (other rivers only)",
                [model.predict(p.features) for p in lock],
                None,
                seed + 10 + k,
            )
    rows = level_rows(cfg, target, lock, estimates[pick], null, quantiles[pick], seed + 20,
                      run.rule)  # fmt: skip
    levels = [{**base, "candidate": pick, **r} for r in rows]
    scores[0].update(counts)
    inner_m = route_a.evaluate(cfg, train, oofs[pick], route_a.leave_one_group_out(
        train, year, route_a.null), quantiles[pick], seed + 30)  # fmt: skip
    the_card = card(cfg, target, pick, train, other, oofs[pick], rows,
                    {"inner": inner_m, "lockbox": lock_metrics[pick]},
                    root / cfg.outputs.inputs / "lab", run)  # fmt: skip
    errors = [math.log(e / p.value) for e, p in zip(oofs[pick], train, strict=True)
              if e > 0 and p.value > 0]  # fmt: skip
    return Evaluation(scores, levels, inner_rows, the_card, errors)


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
    tables: dict[str, list[dict[str, Any]]] = {"site_scores": [], "site_levels": [],
                                               "site_inner": []}  # fmt: skip
    hermann = transfer.load_usgs(cfg, root, folder=FOLDER)
    if hermann is None or usgs is None:
        tables["site_scores"].append({"site": SITE, "status": "no snapshot yet"})
        return tables
    pairs = [p for p in hermann.pairs.get((TARGET, WINDOW), []) if p.station == SITE]
    result = evaluate(cfg, root, usgs, HERMANN, pairs)
    tables["site_inner"] += result.inner
    tables["site_scores"] += result.scores
    tables["site_levels"] += result.levels
    tables["_site_cards"] = [{"path": CARD, "card": result.card}]
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
