"""v2.1: the post-hoc calibration on the Magdalena (preregistration, checkpoint 2 decisions).

The frozen test was used once by v2. Here five predeclared candidates are fitted on Magdalena
pairs, and the error that counts comes from nested leave-one-station-out (LOSO). For each held-out
station, the candidates are scored by LOSO over the other stations, the best is chosen (within 5
MdSA points, the simpler), fitted on the other stations and asked to predict the held-out one. The
held-out predictions measure the whole procedure, selection included. Intervals come from the
chosen candidate's inner residuals. A level here is always labelled post hoc and is never
_validated_. Leave-one-year-out (hydrological years, December to November) is report-only.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from climate_pipeline.calibration import stats
from climate_pipeline.calibration.matchups import Pair
from climate_pipeline.quality import cards, route_a, transfer
from climate_pipeline.quality.config import QualityConfig, Target
from climate_pipeline.quality.route_a import ColombianInputs, Predictor, Quantiles

BASIS = "post_hoc_nested_loso_magdalena"
ORDER = ("P1", "P2", "P3", "P4", "P5")  # simplest first
P5_FEATURES = ("log_B8A/B04", "log_B04/B03", "log_B04/B02", "B8A-B11")
P5_LAMBDAS = (0.1, 1.0, 10.0, 100.0)
PRETRAINED = {"P2": "A2", "P3": "A3", "P4": "A4"}


def station(p: Pair) -> str:
    """The LOSO group of a pair.

    Args:
        p: The pair.

    Returns:
        Its station.
    """
    return p.station


def hydrological_year(p: Pair) -> str:
    """The leave-one-year-out group: December starts the next hydrological year.

    Args:
        p: The pair.

    Returns:
        E.g. ``"2021"`` for 2020-12-01..2021-11-30.
    """
    return str(p.sample_day.year + (1 if p.sample_day.month == 12 else 0))


def p5_predictor(train: Sequence[Pair], test: Sequence[Pair]) -> list[float]:
    """P5: ridge in log space on four features, lambda by LOSO on ``train``.

    Args:
        train: Training pairs.
        test: Pairs to predict.

    Returns:
        Estimates (NaN where a feature is missing or with too few pairs).
    """
    use = transfer.usable_rows(train, P5_FEATURES)
    if len(use) < len(P5_FEATURES) + 2:
        return [math.nan] * len(test)
    lam = transfer.choose_lambda(use, station, P5_FEATURES, P5_LAMBDAS)
    model = transfer.fit_linear(use, P5_FEATURES, lam)
    return [model.predict(p.features) for p in test]


def candidates(cfg: QualityConfig, usgs: transfer.UsgsInputs | None, target: str,
               window: str) -> dict[str, Predictor]:  # fmt: skip
    """The predeclared candidates that can run (P2-P4 need the USGS models).

    Args:
        cfg: Settings.
        usgs: The USGS inputs.
        target: Target id.
        window: The window.

    Returns:
        Candidate id -> predictor, in the order of simplicity.
    """
    out: dict[str, Predictor] = {"P1": route_a.a1}
    pretrained = transfer.pretrained_models(cfg, usgs, target, window) if usgs else {}
    for cid, source in PRETRAINED.items():
        if source in pretrained:
            out[cid] = transfer.transfer_predictor(pretrained[source], cfg)
    out["P5"] = p5_predictor
    return out


def choose(scores: Mapping[str, float], margin: float, order: Sequence[str] = ORDER) -> str:
    """The lowest MdSA; within ``margin`` points, the simplest.

    Args:
        scores: Candidate -> inner MdSA.
        margin: MdSA points.
        order: The candidates, simplest first.

    Returns:
        The candidate (the simplest when none has a finite score).
    """
    finite = {c: s for c, s in scores.items() if math.isfinite(s)}
    if not finite:
        return order[0]
    best = min(finite.values())
    return next(c for c in order if c in finite and finite[c] <= best + margin)


@dataclass
class Nested:
    """The held-out predictions of the whole procedure."""

    estimates: list[float]
    null: list[float]
    chosen: dict[str, str]  # held-out group -> candidate
    inside: dict[float, list[bool | None]]  # coverage -> per pair (None without an estimate)


def nested(
    cfg: QualityConfig, pool: Sequence[Pair], options: Mapping[str, Predictor],
    group: Callable[[Pair], str] = station, order: Sequence[str] = ORDER,
) -> Nested:  # fmt: skip
    """Nested leave-one-group-out: inner selection by LOSO over stations, outer held-out groups.

    Args:
        cfg: Settings.
        pool: The Magdalena pairs.
        options: Candidate -> predictor.
        group: The outer group (stations; hydrological years for the sensitivity).
        order: The candidates, simplest first.

    Returns:
        The held-out estimates, the null's, the choice per group and interval hits.
    """
    n = len(pool)
    est, nul = [math.nan] * n, [math.nan] * n
    inside: dict[float, list[bool | None]] = {c: [None] * n for c in cfg.intervals.coverages}
    chosen: dict[str, str] = {}
    for g in sorted({group(p) for p in pool}):
        held = [k for k, p in enumerate(pool) if group(p) == g]
        train = [p for p in pool if group(p) != g]
        test = [pool[k] for k in held]
        observed = [p.value for p in train]
        inner = {c: route_a.leave_one_group_out(train, station, f) for c, f in options.items()}
        pick = choose({c: stats.mdsa(*_valid(e, observed)) for c, e in inner.items()},
                      cfg.selection.simpler_within_mdsa, order)  # fmt: skip
        chosen[g] = pick
        q = route_a.conformal(inner[pick], observed, cfg.intervals.coverages)
        values = options[pick](train, test)
        medians = route_a.null(train, test)
        for k, v, m in zip(held, values, medians, strict=True):
            est[k], nul[k] = v, m
            for c in cfg.intervals.coverages:
                inside[c][k] = _hit(q, v, pool[k].value, c)
    return Nested(est, nul, chosen, inside)


def _valid(
    estimates: Sequence[float], observed: Sequence[float]
) -> tuple[list[float], list[float]]:
    ok = [(e, o) for e, o in zip(estimates, observed, strict=True) if math.isfinite(e) and e > 0]
    return [e for e, _ in ok], [o for _, o in ok]


def _hit(q: Quantiles | None, estimate: float, observed: float, coverage: float) -> bool | None:
    if q is None or not (math.isfinite(estimate) and estimate > 0):
        return None
    low, high = q.interval(estimate, coverage)
    return low <= observed <= high


def metrics(cfg: QualityConfig, pool: Sequence[Pair], result: Nested, idx: Sequence[int],
            seed: int) -> dict[str, float]:  # fmt: skip
    """The nested metrics of some pairs (all, or one predicted range).

    Args:
        cfg: Settings.
        pool: The pairs.
        result: The nested predictions.
        idx: Which pairs.
        seed: Bootstrap seed.

    Returns:
        The metrics, with the coverages from the held-out intervals.
    """
    sub = [pool[k] for k in idx]
    m = route_a.evaluate(cfg, sub, [result.estimates[k] for k in idx],
                         [result.null[k] for k in idx], None, seed)  # fmt: skip
    for c in cfg.intervals.coverages:
        hits = [bool(result.inside[c][k]) for k in idx if result.inside[c][k] is not None]
        m[f"coverage{round(c * 100)}"] = sum(hits) / len(hits) if hits else math.nan
    return m


def level_rows(cfg: QualityConfig, target: Target, pool: Sequence[Pair], result: Nested,
               seed: int) -> list[dict[str, Any]]:  # fmt: skip
    """The post-hoc level overall and per predicted range.

    Args:
        cfg: Settings.
        target: The target.
        pool: The pairs.
        result: The nested predictions.
        seed: Bootstrap seed.

    Returns:
        The ``all`` row first, then one row per range with an estimate.
    """
    from climate_pipeline.quality.route_b import bin_label

    valid = [k for k, e in enumerate(result.estimates) if math.isfinite(e) and e > 0]
    overall_m = metrics(cfg, pool, result, valid, seed)
    overall = route_a.level(overall_m, cfg, bin_level=True)
    rows = [_row("all", overall_m, True, overall)]
    for b in range(len(target.bins) + 1):
        idx = [k for k in valid if target.bin_of(result.estimates[k]) == b]
        if not idx:
            continue
        m = metrics(cfg, pool, result, idx, seed + b + 1)
        rated = len(idx) >= cfg.levels.min_bin_pairs
        rows.append(_row(bin_label(target.bins, b), m, rated,
                         route_a.level(m, cfg, bin_level=True) if rated else overall))  # fmt: skip
    return rows


def _row(label: str, m: Mapping[str, float], rated: bool, lv: str) -> dict[str, Any]:
    return {"predicted_range": label, "n": int(m["n"]), "rated": rated, "mdsa": m["mdsa"],
            "sspb": m["sspb"], "rho_low": m["rho_low"], "coverage90": m["coverage90"],
            "level": lv}  # fmt: skip


VARIANTS = (("main", True, None), ("+-1 day only", False, None), ("300m window", True, "300m"))


def analyse(
    cfg: QualityConfig, ci: ColombianInputs, adjacency_confirmed: bool,
    usgs: transfer.UsgsInputs | None, lab_dir: Path,
) -> dict[str, list[dict[str, Any]]]:  # fmt: skip
    """Every v2.1 table and the post-hoc model card of each target.

    Args:
        cfg: Settings.
        ci: The Colombian inputs.
        adjacency_confirmed: Route B's adjacency rule (the core window is primary).
        usgs: The USGS inputs.
        lab_dir: The lab's A4 models (for the cards).

    Returns:
        ``posthoc_scores``, ``posthoc_levels``, ``posthoc_choices`` and ``_posthoc_cards``.
    """
    from climate_pipeline.quality.route_b import _seed

    primary = "core" if adjacency_confirmed else "300m"
    test_stream = cfg.stations.test_stream
    tables: dict[str, list[dict[str, Any]]] = {
        "posthoc_scores": [],
        "posthoc_levels": [],
        "posthoc_choices": [],
        "_posthoc_cards": [],
    }
    for target in cfg.targets:
        for variant, wide, window_override in VARIANTS:
            window = window_override or primary
            found = route_a.pairs(cfg, ci, target.id, window, wide)
            pool = [p for p in found if ci.stream_of.get(p.station) == test_stream]
            options = candidates(cfg, usgs, target.id, window)
            seed = _seed(cfg.seed, "posthoc", target.id, variant)
            base = {"target": target.id, "variant": variant, "window": window}
            if len({p.station for p in pool}) < 3:
                tables["posthoc_scores"].append({**base, "evaluation": "nested LOSO",
                                                 "status": "insufficient_data"})  # fmt: skip
                continue
            result = nested(cfg, pool, options)
            m = metrics(cfg, pool, result, list(range(len(pool))), seed)
            rows = level_rows(cfg, target, pool, result, seed)
            tables["posthoc_scores"].append({**base, "evaluation": "nested LOSO", **m,
                                             "level": rows[0]["level"]})  # fmt: skip
            if variant == "main":
                years = nested(cfg, pool, options, hydrological_year)
                ym = metrics(cfg, pool, years, list(range(len(pool))), seed + 7)
                tables["posthoc_scores"].append({**base, "evaluation": "nested leave-one-year-out "
                                                 "(report-only)", **ym})  # fmt: skip
                tables["posthoc_levels"] += [{"target": target.id, **r} for r in rows]
                tables["posthoc_choices"] += [
                    {"target": target.id, "held_out_station": g, "chosen": c}
                    for g, c in result.chosen.items()
                ]
                tables["_posthoc_cards"].append(
                    final_card(
                        cfg, target, window, pool, options, usgs, result.estimates, m, rows, lab_dir
                    )
                )
    return tables


def summary(tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """The post-hoc level, error and chosen model of each target (main pairs).

    Args:
        tables: The run's tables.

    Returns:
        Target -> ``level``, ``mdsa``, ``n`` (nested LOSO).
    """
    out: dict[str, Any] = {}
    for r in tables.get("posthoc_scores", []):
        if r.get("variant") == "main" and r.get("evaluation") == "nested LOSO" and "mdsa" in r:
            lv = f"{r['level']} (post hoc)" if r["level"] != "none" else "none"
            out[r["target"]] = {"level": lv, "mdsa": round(r["mdsa"], 1), "n": int(r["n"])}
    return out


def final_card(
    cfg: QualityConfig, target: Target, window: str, pool: Sequence[Pair],
    options: Mapping[str, Predictor], usgs: transfer.UsgsInputs | None,
    held_out: Sequence[float], nested_metrics: Mapping[str, float],
    rows: Sequence[Mapping[str, Any]], lab_dir: Path,
) -> dict[str, Any]:  # fmt: skip
    """The published post-hoc model: the same selection on every pair, fitted on all of them.

    Args:
        cfg: Settings.
        target: The target.
        window: The window.
        pool: Every Magdalena pair of the main set.
        options: The candidates.
        usgs: The USGS inputs.
        held_out: The nested held-out estimates (the intervals' residuals).
        nested_metrics: The nested LOSO metrics (the error that counts).
        rows: The post-hoc level rows.
        lab_dir: The lab's A4 models.

    Returns:
        The card, with ``basis`` set and its ``parametersHash``.
    """
    observed = [p.value for p in pool]
    inner = {c: route_a.leave_one_group_out(pool, station, f) for c, f in options.items()}
    pick = choose({c: stats.mdsa(*_valid(e, observed)) for c, e in inner.items()},
                  cfg.selection.simpler_within_mdsa)  # fmt: skip
    levels = [{k: v for k, v in r.items() if k != "rho_low"} for r in rows]
    product = "A1" if pick == "P1" else PRETRAINED.get(pick, pick)
    card = cards.product_card(cfg, target, window, product, [], pool, usgs, [], held_out,
                              {"nested_loso": nested_metrics}, levels, lab_dir,
                              p5=(P5_FEATURES, P5_LAMBDAS) if pick == "P5" else None)  # fmt: skip
    return {
        **card,
        "modelId": f"{pick}:{target.id}:{window}:posthoc",
        "candidate": pick,
        "basis": BASIS,
    }
