"""Route A of the water-quality validation v2, Colombian part: pairs, A1, intervals and levels.

Pairs follow D15's matching (local dates, nearest usable scene, replicates as medians, censored
values never fitted). The primary window is +-1 day; +-3 days is a sensitivity allowed only when
the flow was stable between the sample day and the scene day. The test stream (the Magdalena)
never enters a fit before its single evaluation. Selection is leave-one-river-out over the other
streams; the interval quantiles are Mondrian split-conformal quantiles of those out-of-fold log
residuals. Levels come from the test metrics of the model before the refit. A1 needs no USGS data;
A2 and A3 (``quality.transfer``) are pretrained on the USGS pilot and adjusted to Colombian units.
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from climate_pipeline.calibration import models, stats
from climate_pipeline.calibration.fetching import read_stations
from climate_pipeline.calibration.matchups import (
    BANDS,
    Pair,
    Sample,
    SceneRow,
    candidate_values,
    fittable,
    match,
    reduce_replicates,
    samples_from_series,
    samples_from_soda,
)
from climate_pipeline.calibration.stations import number
from climate_pipeline.quality import cards, features, transfer
from climate_pipeline.quality.config import Criteria, QualityConfig, Target

STAT_NAMES = ("window_px", "data_px", "valid_px", "contamination", "glint_share", "b11_median",
              "b11_ok", "ndti_px_median", "bands_read", "sun_zenith")  # fmt: skip
Predictor = Callable[[Sequence[Pair], Sequence[Pair]], list[float]]  # (train, test) -> estimates


@dataclass
class ColombianInputs:
    """The Colombian snapshots, parsed."""

    stations: list[dict[str, str]]
    samples: list[Sample]
    scenes: dict[str, list[SceneRow]]  # "300m", "core"
    flow: dict[str, tuple[str, dict[date, float]]]  # station -> (label, day -> value)
    stream_of: dict[str, str]
    check: list[SceneRow] = field(default_factory=list)  # Planetary Computer, source check
    lab_dir: Path = Path("docs/water-quality/inputs/lab")  # A4's forests (cards name them)


def scenes_from_windows(text: str, window: str) -> list[SceneRow]:
    """Scene windows from ``imagery/windows.csv`` (both sources; ``source`` as the collection).

    Args:
        text: The CSV text.
        window: ``300m`` or ``core``.

    Returns:
        One row per station and acquisition for that window.
    """
    out = []
    for row in csv.DictReader(io.StringIO(text)) if text else []:
        if row["window"] != window:
            continue
        bands = {b: number(row[b]) for b in BANDS}
        out.append(SceneRow(
            station=row["station"], collection=row["source"], key=row["key"],
            day=date.fromisoformat(row["local_date"]), family=row["family"],
            stats={k: number(row.get(k) or "nan") for k in STAT_NAMES}, bands=bands,
            features=candidate_values(bands, None),
        ))  # fmt: skip
    return out


def load(cfg: QualityConfig, root: Path) -> ColombianInputs | None:
    """The Colombian snapshots (None until the value fetch has run).

    Args:
        cfg: Settings.
        root: Repository root.

    Returns:
        The inputs, or None.
    """
    base = root / cfg.outputs.inputs
    windows = base / "imagery" / "windows.csv"
    if not windows.exists() or not (base / "stations" / "stations.csv").exists():
        return None
    stations = [r for r in read_stations(base / "stations" / "stations.csv")
                if r["selected"] == "true"]  # fmt: skip
    point_station = {r["quality_point"]: r["station_id"] for r in stations if r["quality_point"]}
    soda = json.loads((base / "ideam" / "quality-samples.json").read_text(encoding="utf-8"))
    targets = {t.variable: t.id for t in cfg.targets}
    samples = reduce_replicates(samples_from_soda(soda, point_station, targets))
    text = windows.read_text(encoding="utf-8")
    flow: dict[str, tuple[str, dict[date, float]]] = {}
    for r in stations:
        if not r["flow_code"]:
            continue
        path = base / "ideam" / r["flow_label"] / f"{r['flow_code']}-{r['flow_label']}.csv"
        if path.exists():
            series = samples_from_series(path.read_text(encoding="utf-8"), r["station_id"], "flow")
            flow[r["station_id"]] = (r["flow_label"], {s.day: s.value for s in series})
    check = base / "imagery" / "source-check.csv"
    widths = {r["station_id"]: number(r["width_m"]) for r in stations}
    windows_f = features.with_features(
        cfg.features, {w: scenes_from_windows(text, w) for w in ("300m", "core")}, widths
    )
    return ColombianInputs(
        stations=stations, samples=samples, scenes=windows_f, flow=flow,
        stream_of={r["station_id"]: r["stream"] for r in stations},
        check=scenes_from_windows(check.read_text(encoding="utf-8") if check.exists() else "",
                                  "300m"),
        lab_dir=base / "lab",
    )  # fmt: skip


def source_check(cfg: QualityConfig, ci: ColombianInputs) -> dict[str, Any]:
    """The preregistered source check: Planetary Computer minus Earth Search on shared scenes.

    The shift is the median difference of B8A/B04 over the scenes both sources measured (300 m
    window, every guard passed), in units of the robust sigma (1.4826 x MAD) of Earth Search's
    B8A/B04 on those scenes.

    Args:
        cfg: Settings.
        ci: Inputs.

    Returns:
        ``scenes``, ``median_difference``, ``robust_sigma``, ``shift_sigma`` and ``excluded``
        (True: Planetary Computer pairs leave the primary analyses).
    """
    window = cfg.window.as_calibration()
    es = {
        (s.station, s.key): s.features.get("B8A/B04", math.nan)
        for s in ci.scenes["300m"]
        if s.collection == "earth-search" and s.usable(window)
    }
    shared = [
        (s.features.get("B8A/B04", math.nan), es[(s.station, s.key)])
        for s in ci.check
        if s.usable(window) and (s.station, s.key) in es
    ]
    shared = [(a, b) for a, b in shared if math.isfinite(a) and math.isfinite(b)]
    if len(shared) < 3:
        return {
            "scenes": len(shared),
            "median_difference": math.nan,
            "robust_sigma": math.nan,
            "shift_sigma": math.nan,
            "excluded": False,
        }
    diff = float(np.median([a - b for a, b in shared]))
    base = np.array([b for _, b in shared])
    sigma = 1.4826 * float(np.median(np.abs(base - np.median(base))))
    shift = diff / sigma if sigma > 0 else math.inf
    return {
        "scenes": len(shared),
        "median_difference": diff,
        "robust_sigma": sigma,
        "shift_sigma": shift,
        "excluded": abs(shift) > cfg.imagery.source_check.shift_sigma,
    }


def stable(pair: Pair, flow: Mapping[str, tuple[str, Mapping[date, float]]], cfg: QualityConfig,
           ) -> bool:  # fmt: skip
    """Whether a pair may be used: within the primary days, or with stable flow beyond them.

    Args:
        pair: The pair.
        flow: Station -> (label, day -> value); level in cm, as IDEAM publishes it.
        cfg: Settings.

    Returns:
        True when allowed.
    """
    if pair.gap_days <= cfg.matchups.primary_days:
        return True
    label, series = flow.get(pair.station, ("", {}))
    a, b = series.get(pair.sample_day, math.nan), series.get(pair.scene_day, math.nan)
    if not (math.isfinite(a) and math.isfinite(b)):
        return False
    if label == "Q_MEDIA_D":
        return a > 0 and b > 0 and abs(math.log(b / a)) <= cfg.matchups.stable_max_abs_log_q
    return abs(b - a) <= cfg.matchups.stable_max_level_m * 100


def pairs(cfg: QualityConfig, ci: ColombianInputs, target: str, window: str = "300m",
          stable_days: bool = False, without: str = "") -> list[Pair]:  # fmt: skip
    """Fittable pairs of one target: +-1 day, or +-3 days with stable flow.

    Args:
        cfg: Settings.
        ci: Inputs.
        target: Target id.
        window: ``300m`` or ``core``.
        stable_days: Use the sensitivity window with the stability rule.
        without: A source whose scenes are left out (the source check's exclusion).

    Returns:
        The pairs.
    """
    days = cfg.matchups.sensitivity_days if stable_days else cfg.matchups.primary_days
    samples = [s for s in ci.samples if s.target == target]
    scenes = [s for s in ci.scenes[window] if s.collection != without]
    found = match(samples, scenes, days, cfg.window.as_calibration())
    return [p for p in fittable(found) if stable(p, ci.flow, cfg)]


def a1(train: Sequence[Pair], test: Sequence[Pair]) -> list[float]:
    """A1: log-log OLS of the target on B8A/B04, fitted on ``train``.

    Args:
        train: Training pairs.
        test: Pairs to predict.

    Returns:
        Estimates (NaN where the ratio is undefined or there are too few training pairs).
    """
    use = [p for p in train if math.isfinite(p.features.get("B8A/B04", math.nan))
           and p.features["B8A/B04"] > 0]  # fmt: skip
    if len(use) < 3:
        return [math.nan] * len(test)
    fit = models.fit_model("A1", "x", [p.features for p in use], [p.value for p in use],
                           ["B8A/B04"])  # fmt: skip
    return [fit.predict(p.features) for p in test]


def null(train: Sequence[Pair], test: Sequence[Pair]) -> list[float]:
    """M0: the median of the training targets.

    Args:
        train: Training pairs.
        test: Pairs to predict.

    Returns:
        The same value for every test pair.
    """
    median = float(np.median([p.value for p in train])) if train else math.nan
    return [median] * len(test)


def leave_one_group_out(
    pool: Sequence[Pair], group: Callable[[Pair], str], predictor: Predictor,
    fixed: Sequence[Pair] = (),
) -> list[float]:  # fmt: skip
    """Out-of-fold estimates: each group predicted by a fit on the others (plus ``fixed``).

    Args:
        pool: Pairs to cross-validate.
        group: Group of a pair (a stream or a station).
        predictor: The model.
        fixed: Pairs always in the training set (never predicted).

    Returns:
        One estimate per pair of ``pool``, in order.
    """
    out = [math.nan] * len(pool)
    for g in sorted({group(p) for p in pool}):
        held = [k for k, p in enumerate(pool) if group(p) == g]
        train = [*fixed, *(p for p in pool if group(p) != g)]
        for k, value in zip(held, predictor(train, [pool[k] for k in held]), strict=True):
            out[k] = value
    return out


@dataclass(frozen=True)
class Quantiles:
    """Split-conformal quantiles of the log residual, per tercile of the estimate (Mondrian).

    A coverage in ``pooled`` has one quantile over every residual, repeated in each tercile
    (deviation 4: some tercile had too few residuals for a finite Mondrian quantile).
    """

    edges: tuple[float, float]  # upper edges of the first two terciles of the estimate
    q: Mapping[float, tuple[float, float, float]]  # coverage -> quantile per tercile
    pooled: frozenset[float] = frozenset()

    def interval(self, estimate: float, coverage: float) -> tuple[float, float]:
        """The interval of an estimate.

        Args:
            estimate: The estimate.
            coverage: E.g. 0.9.

        Returns:
            ``(low, high)``; infinite when even the pooled residuals were too few.
        """
        k = 0 if estimate < self.edges[0] else 1 if estimate < self.edges[1] else 2
        q = self.q[coverage][k]
        return estimate * math.exp(-q), estimate * math.exp(q)


def conformal(estimates: Sequence[float], observed: Sequence[float],
              coverages: Sequence[float]) -> Quantiles | None:  # fmt: skip
    """Quantiles from out-of-fold estimates (the ceil((n+1)(1-a))-th smallest residual per tercile).

    Where some tercile has too few residuals for a finite quantile at a coverage (fewer than 9 at
    90 %, 4 at 80 %), that coverage uses one quantile over all the residuals (deviation 4).

    Args:
        estimates: Out-of-fold estimates.
        observed: Measured values.
        coverages: E.g. (0.8, 0.9).

    Returns:
        The quantiles, or None without at least 3 valid residuals.
    """
    ok = [(e, o) for e, o in zip(estimates, observed, strict=True)
          if math.isfinite(e) and e > 0 and o > 0]  # fmt: skip
    if len(ok) < 3:
        return None
    est = np.array([e for e, _ in ok])
    res = np.abs(np.log(np.array([o for _, o in ok]) / est))
    edges = (float(np.quantile(est, 1 / 3)), float(np.quantile(est, 2 / 3)))
    tercile = np.where(est < edges[0], 0, np.where(est < edges[1], 1, 2))
    q: dict[float, tuple[float, float, float]] = {}
    pooled = set()
    for c in coverages:
        per = [_rank_quantile(res[tercile == k], c) for k in range(3)]
        if not all(math.isfinite(v) for v in per):
            per = [_rank_quantile(res, c)] * 3
            pooled.add(c)
        q[c] = (per[0], per[1], per[2])
    return Quantiles(edges, q, frozenset(pooled))


def _rank_quantile(residuals: NDArray[np.float64], coverage: float) -> float:
    r = np.sort(residuals)
    rank = math.ceil((len(r) + 1) * coverage)
    return float(r[rank - 1]) if 0 < rank <= len(r) else math.inf


def covered(quantiles: Quantiles | None, estimates: Sequence[float], observed: Sequence[float],
            coverage: float) -> float:  # fmt: skip
    """The share of measured values inside their intervals.

    Args:
        quantiles: The conformal quantiles.
        estimates: Estimates.
        observed: Measured values.
        coverage: Nominal coverage.

    Returns:
        The empirical coverage (NaN without quantiles or valid estimates).
    """
    if quantiles is None:
        return math.nan
    inside = []
    for e, o in zip(estimates, observed, strict=True):
        if math.isfinite(e) and e > 0:
            low, high = quantiles.interval(e, coverage)
            inside.append(low <= o <= high)
    return float(np.mean(inside)) if inside else math.nan


def level(metrics: Mapping[str, float], cfg: QualityConfig, bin_level: bool = False) -> str:
    """The level of a target (or of one range bin) from its test metrics.

    Args:
        metrics: ``n``, ``stations``, ``mdsa``, ``sspb``, ``null_mdsa``, ``coverage90``,
            ``rho_low``.
        cfg: Settings.
        bin_level: A range bin (never ``validated`` on its own pairs count).

    Returns:
        ``validated``, ``estimated``, ``indicative`` or ``none``.
    """
    lv = cfg.levels
    if metrics.get("n", 0) < lv.min_test_pairs:
        return "none"

    def meets(c: Criteria) -> bool:
        cov = metrics.get("coverage90", math.nan)
        return (metrics["mdsa"] <= c.mdsa_max and abs(metrics["sspb"]) <= c.sspb_abs_max
                and metrics["mdsa"] <= c.null_ratio_max * metrics["null_mdsa"]
                and c.coverage_90[0] <= cov <= c.coverage_90[1])  # fmt: skip

    v = lv.validated
    if (not bin_level and meets(v) and metrics["n"] >= (v.min_pairs or 0)
            and metrics.get("stations", 0) >= (v.min_stations or 0)):  # fmt: skip
        return "validated"
    if meets(lv.estimated):
        return "estimated"
    if metrics.get("rho_low", -1) > lv.indicative.lower_bound_min:
        return "indicative"
    return "none"


@dataclass
class Evaluation:
    """One candidate's estimates on the test set, with its metrics."""

    estimates: list[float]
    metrics: dict[str, float] = field(default_factory=dict)


def evaluate(cfg: QualityConfig, test: Sequence[Pair], estimates: Sequence[float],
             null_estimates: Sequence[float], quantiles: Quantiles | None,
             seed: int) -> dict[str, float]:  # fmt: skip
    """Test metrics of a candidate.

    Args:
        cfg: Settings.
        test: Test pairs.
        estimates: Its estimates.
        null_estimates: The null model's estimates.
        quantiles: Its interval quantiles (from training rivers).
        seed: Bootstrap seed.

    Returns:
        ``n``, ``stations``, MdSA, SSPB, MAPE, rho with its interval, the null MdSA and coverages.
    """
    keep = [k for k, e in enumerate(estimates) if math.isfinite(e) and e > 0]
    p = [estimates[k] for k in keep]
    o = [test[k].value for k in keep]
    low, high = stats.block_bootstrap_spearman(p, o, [test[k].scene_key for k in keep],
                                               cfg.selection.bootstrap_resamples, seed,
                                               cfg.selection.confidence)  # fmt: skip
    return {
        "n": float(len(keep)), "stations": float(len({test[k].station for k in keep})),
        "mdsa": stats.mdsa(p, o), "sspb": stats.sspb(p, o), "mape": stats.mape(p, o),
        "rho": stats.spearman(p, o), "rho_low": low, "rho_high": high,
        "null_mdsa": stats.mdsa([null_estimates[k] for k in keep], o),
        "coverage80": covered(quantiles, p, o, 0.8), "coverage90": covered(quantiles, p, o, 0.9),
    }  # fmt: skip


def bin_rows(cfg: QualityConfig, target: Target, candidate: str, test: Sequence[Pair],
             estimates: Sequence[float], null_estimates: Sequence[float],
             quantiles: Quantiles | None, overall: str) -> list[dict[str, Any]]:  # fmt: skip
    """Metrics and level per predicted range (a small bin takes the target's level, capped).

    A bin with fewer test pairs than the minimum takes the target's level, capped at estimated.

    Args:
        cfg: Settings.
        target: The target.
        candidate: Candidate id.
        test: Test pairs.
        estimates: Its estimates.
        null_estimates: The null model's estimates.
        quantiles: Its interval quantiles.
        overall: The target's level.

    Returns:
        One row per bin with at least one estimate.
    """
    from climate_pipeline.quality.route_b import bin_label

    rows = []
    for k in range(len(target.bins) + 1):
        idx = [i for i, e in enumerate(estimates)
               if math.isfinite(e) and e > 0 and target.bin_of(e) == k]  # fmt: skip
        if not idx:
            continue
        sub_test = [test[i] for i in idx]
        m = evaluate(cfg, sub_test, [estimates[i] for i in idx],
                     [null_estimates[i] for i in idx], quantiles, 1)  # fmt: skip
        rated = len(idx) >= cfg.levels.min_bin_pairs
        lv = level(m, cfg, bin_level=True) if rated else (
            "estimated" if overall == "validated" else overall)  # fmt: skip
        rows.append({"target": target.id, "candidate": candidate,
                     "predicted_range": bin_label(target.bins, k), "n": len(idx), "rated": rated,
                     "mdsa": m["mdsa"], "sspb": m["sspb"], "coverage90": m["coverage90"],
                     "level": lv})  # fmt: skip
    return rows


def select(loro: Mapping[str, Mapping[str, float]], cfg: QualityConfig) -> str:
    """The product model: the lowest leave-one-river-out MdSA; within the margin, the simplest.

    Args:
        loro: Candidate -> its leave-one-river-out metrics.
        cfg: Settings (the margin, in MdSA points).

    Returns:
        The candidate id (``A1`` when no candidate has a finite MdSA).
    """
    finite = {c: m["mdsa"] for c, m in loro.items() if math.isfinite(m.get("mdsa", math.nan))}
    if not finite:
        return "A1"
    best = min(finite.values())
    order = [c for c in ("A1", "A2", "A3", "A4") if c in finite]
    return next(c for c in order if finite[c] <= best + cfg.selection.simpler_within_mdsa)


def analyse(
    cfg: QualityConfig, ci: ColombianInputs, adjacency_confirmed: bool = False,
    usgs: transfer.UsgsInputs | None = None,
) -> dict[str, list[dict[str, Any]]]:  # fmt: skip
    """Pairs, the candidates against the null, the product model, intervals and levels.

    Args:
        cfg: Settings.
        ci: Inputs.
        adjacency_confirmed: Route B's verdict: the core window becomes the primary window (the
            preregistered rule), and the 300 m window a sensitivity.
        usgs: The USGS pilot (A2 and A3 need it).

    Returns:
        Table name -> rows.
    """
    from climate_pipeline.quality.route_b import _seed

    lab_dir = ci.lab_dir
    test_stream = cfg.stations.test_stream
    tables: dict[str, list[dict[str, Any]]] = {
        name: [] for name in ("route_a_counts", "route_a_scores", "route_a_intervals",
                              "route_a_levels", "route_a_pairs", "_cards")
    }  # fmt: skip
    check = source_check(cfg, ci)
    tables["route_a_source_check"] = [check]
    without = "planetary-computer" if check["excluded"] else ""

    def stream(p: Pair) -> str:
        return ci.stream_of.get(p.station, "")

    def station(p: Pair) -> str:
        return p.station

    primary, other = ("core", "300m") if adjacency_confirmed else ("300m", "core")
    variants = (("primary", primary, False), ("stable +-3 days", primary, True),
                (f"{other} window", other, False))  # fmt: skip
    for target in cfg.targets:
        for variant, window, wide in variants:
            found = pairs(cfg, ci, target.id, window, wide, without)
            source_of = {(s.station, s.key): s.collection for s in ci.scenes[window]}
            train = [p for p in found if stream(p) != test_stream]
            test = [p for p in found if stream(p) == test_stream]
            sources_found = [source_of.get((p.station, p.scene_key)) for p in found]
            usgs_pairs = len(usgs.pairs.get((target.id, window), [])) if usgs else 0
            tables["route_a_counts"].append({
                "target": target.id, "variant": variant, "window": window,
                "training_pairs": len(train),
                "training_streams": len({stream(p) for p in train}),
                "training_stations": len({p.station for p in train}), "test_pairs": len(test),
                "test_stations": len({p.station for p in test}),
                "planetary_computer_pairs": sources_found.count("planetary-computer"),
                "usgs_pairs": usgs_pairs,
            })  # fmt: skip
            if variant == "primary":
                test_keys = {(p.station, p.sample_day) for p in test}
                tables["route_a_pairs"] += [{
                    "target": target.id, "station": p.station, "stream": stream(p),
                    "sample_day": p.sample_day, "scene_key": p.scene_key,
                    "source": source_of.get((p.station, p.scene_key), ""),
                    "gap_days": p.gap_days, "value": p.value,
                    "split": "test" if (p.station, p.sample_day) in test_keys else "training",
                    "B04": p.features.get("B04", math.nan), "B8A": p.features.get("B8A", math.nan),
                    "B8A/B04": p.features.get("B8A/B04", math.nan),
                } for p in found]  # fmt: skip

            def score(candidate: str, evaluation: str, metrics: Mapping[str, Any],
                      t: str = target.id, v: str = variant) -> None:  # fmt: skip
                tables["route_a_scores"].append({"target": t, "variant": v, "candidate": candidate,
                                                 "evaluation": evaluation, **metrics})  # fmt: skip

            if len(train) < 3 or not test:
                score("A1", "test (Magdalena)", {"status": "insufficient_data",
                                                 "n": float(len(test))})  # fmt: skip
                continue
            candidates: dict[str, Predictor] = {"A1": a1}
            if usgs is not None:
                for cid, model in transfer.pretrained_models(cfg, usgs, target.id, window).items():
                    candidates[cid] = transfer.transfer_predictor(model, cfg)
            seed = _seed(cfg.seed, "route_a", target.id, variant)
            values = [p.value for p in train]
            oof_null = leave_one_group_out(train, stream, null)
            loro: dict[str, dict[str, float]] = {}
            quantiles: dict[str, Quantiles | None] = {}
            oofs: dict[str, list[float]] = {}
            for cid, predictor in candidates.items():
                oofs[cid] = leave_one_group_out(train, stream, predictor)
                quantiles[cid] = conformal(oofs[cid], values, cfg.intervals.coverages)
                loro[cid] = evaluate(cfg, train, oofs[cid], oof_null, quantiles[cid], seed)
                score(cid, "leave-one-river-out", loro[cid])
            product = select(loro, cfg)
            est_null = null(train, test)
            chosen: tuple[list[float], dict[str, float], str] | None = None
            for cid, predictor in candidates.items():
                est = predictor(train, test)
                result = evaluate(cfg, test, est, est_null, quantiles[cid], seed + 1)
                overall = level(result, cfg)
                score(cid, "test (Magdalena)", {"level": overall, "product": cid == product,
                                                **result})  # fmt: skip
                if cid == product:
                    chosen = (est, result, overall)
            score("M0", "test (Magdalena)", evaluate(cfg, test, est_null, est_null, None, seed + 2))
            local = leave_one_group_out(test, station, a1)
            score("A1 local", "Magdalena LOSO (report-only)",
                  evaluate(cfg, test, local, null(test, test), None, seed + 3))  # fmt: skip
            refit = leave_one_group_out(test, station, candidates[product], fixed=train)
            refit_metrics = evaluate(cfg, test, refit, null(test, test), None, seed + 4)
            score(f"{product} refit", "Magdalena LOSO of the refit", refit_metrics)
            q = quantiles[product]
            if q is not None:
                for k in range(3):
                    tables["route_a_intervals"].append({
                        "target": target.id, "variant": variant, "candidate": product,
                        "tercile": k + 1, "upper_edge": q.edges[k] if k < 2 else math.inf,
                        **{f"factor{round(c * 100)}": math.exp(q.q[c][k])
                           for c in cfg.intervals.coverages},
                        "pooled": " ".join(f"{c:g}" for c in sorted(q.pooled)),
                    })  # fmt: skip
            if variant == "primary" and chosen is not None:
                est, result, overall = chosen
                level_rows = [{
                    "target": target.id, "candidate": product, "predicted_range": "all",
                    "n": int(result["n"]), "rated": True, "mdsa": result["mdsa"],
                    "sspb": result["sspb"], "coverage90": result["coverage90"], "level": overall,
                }, *bin_rows(cfg, target, product, test, est, est_null, q, overall)]  # fmt: skip
                tables["route_a_levels"] += level_rows
                tables["_cards"].append(cards.product_card(
                    cfg, target, window, product, train, test, usgs, oofs[product], refit,
                    {"loro": loro[product], "test": result, "refit": refit_metrics},
                    [{k: v for k, v in r.items() if k not in ("target", "candidate")}
                     for r in level_rows],
                    lab_dir,
                ))  # fmt: skip
    return tables


def summary(tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """The Route A headline: per target, the product model's test error and level (primary).

    Args:
        tables: Route A tables.

    Returns:
        JSON-ready summary.
    """
    out: dict[str, Any] = {}
    for row in tables["route_a_scores"]:
        if row["variant"] != "primary" or row["evaluation"] != "test (Magdalena)":
            continue
        if not row.get("product") and row.get("status") != "insufficient_data":
            continue
        mdsa = row.get("mdsa", math.nan)
        out[row["target"]] = {
            "candidate": row["candidate"], "level": row.get("level", row.get("status", "none")),
            "n": int(row.get("n", 0)),
            "mdsa": round(mdsa, 1) if isinstance(mdsa, float) and math.isfinite(mdsa) else None,
        }  # fmt: skip
    return out
