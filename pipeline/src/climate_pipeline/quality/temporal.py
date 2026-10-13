"""v4, section B: Magdalena round 3 (exploratory), a known station validated forward in time.

The product runs at stations with history, so the error that matters is a known station's on dates
it has not seen. The outer folds are hydrological years (December to November): in a fold every
pair of any set whose sample falls in that year leaves training, at every station (IDEAM samples
several stations in one campaign). Inside the training years, leave-one-hydrological-year-out
chooses among the whole space; the winner is fitted on the training years and predicts the held-out
year. The test units are v3's 31 (±3 days with stable flow, nearest scene).

The space crosses feature sets (S5, T, T+G, S5+G, with the preregistered flow change g), pair sets,
aggregations, a station effect (none, or per-station offsets ridge-penalised with λs 10 or 1),
training-pair quality (all, or strict) and the feature penalty λ. Every candidate is a weighted
ridge in log space (each sample 1/n), with an unpenalised intercept.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
from numpy.typing import NDArray

from climate_pipeline.calibration import stats
from climate_pipeline.quality import cards, posthoc, route_a, search
from climate_pipeline.quality.config import QualityConfig
from climate_pipeline.quality.search import NAMES, PAIR_SETS, Data, Table

FloatArray = NDArray[np.float64]
COMBOS = ("S5", "T", "T+G", "S5+G")
AGGREGATIONS = ("nearest", "median")
STATION = (None, 10.0, 1.0)  # no effect, then weaker effects (simplest first)
QUALITY = ("all", "strict")
LAMBDAS = (100.0, 10.0, 1.0, 0.1)  # the larger penalty is simpler
STRICT = {"max_gap_days": 7, "min_valid_px": 50, "max_glint_share": 0.1}
BASIS = "post_hoc_temporal_magdalena"
ESTIMATE_STATION = "23207040"  # San Pablo, the reach's estimate station
MIN_EARLIER_YEARS = 3  # forward chaining: years with units before the predicted one


@dataclass(frozen=True)
class Candidate:
    """One point of round 3's space."""

    combo: str
    pair_set: str
    aggregation: str
    station_lambda: float | None
    quality: str
    lam: float

    @property
    def id(self) -> str:
        """``combo|pair set|aggregation|station effect|quality|λ``."""
        st = "none" if self.station_lambda is None else f"s{self.station_lambda:g}"
        return f"{self.combo}|{self.pair_set}|{self.aggregation}|{st}|{self.quality}|{self.lam:g}"

    @property
    def columns(self) -> list[int]:
        """The feature columns in :data:`search.NAMES`."""
        names = [n for part in self.combo.split("+") for n in search.FEATURES[part]]
        return [NAMES.index(n) for n in names]

    @property
    def complexity(self) -> tuple[int, ...]:
        """Simpler first: fewer features, shorter matchups, the nearest scene, then the rest.

        The rest: a weaker station effect, all pairs, the larger penalty.
        """
        return (len(self.columns), PAIR_SETS.index(self.pair_set),
                AGGREGATIONS.index(self.aggregation), STATION.index(self.station_lambda),
                QUALITY.index(self.quality), LAMBDAS.index(self.lam),
                COMBOS.index(self.combo))  # fmt: skip


def space() -> list[Candidate]:
    """Round 3's candidates, simplest first (G only where the pairs have gaps).

    Returns:
        The candidates.
    """
    out = [Candidate(combo, ps, agg, st, q, lam)
           for ps in PAIR_SETS for combo in COMBOS for agg in AGGREGATIONS for st in STATION
           for q in QUALITY for lam in LAMBDAS
           if not (ps == "3s" and "G" in combo)]  # fmt: skip
    return sorted(out, key=lambda c: c.complexity)


@dataclass(frozen=True)
class Model:
    """A weighted ridge in log space with optional per-station offsets."""

    columns: tuple[int, ...]
    mean: FloatArray
    scale: FloatArray
    coef: FloatArray
    intercept: float
    offsets: Mapping[str, float] = field(default_factory=dict)

    def predict(self, x: FloatArray, stations: NDArray[np.str_]) -> FloatArray:
        """Estimates in the target's unit (an unseen station's offset is 0, the pool).

        Args:
            x: Rows x NAMES.
            stations: Each row's station.

        Returns:
            One estimate per row (NaN where a feature is missing).
        """
        z = (x[:, list(self.columns)] - self.mean) / self.scale
        off = np.array([self.offsets.get(str(s), 0.0) for s in stations], dtype=np.float64)
        return np.asarray(np.exp(self.intercept + z @ self.coef + off), dtype=np.float64)


def fit(t: Table, keep: NDArray[np.bool_], w: FloatArray, c: Candidate) -> Model | None:
    """The weighted ridge of one candidate on some rows.

    Args:
        t: The pair set.
        keep: Training rows.
        w: Their weights.
        c: The candidate.

    Returns:
        The model (None with too few usable rows).
    """
    cols = c.columns
    ok = keep & (w > 0) & np.all(np.isfinite(t.x[:, cols]), axis=1) & np.isfinite(t.y)
    if ok.sum() < len(cols) + 3:
        return None
    a, b, ww = t.x[ok][:, cols], t.y[ok], w[ok]
    total = ww.sum()
    mean = (a * ww[:, None]).sum(axis=0) / total
    scale = np.sqrt((((a - mean) ** 2) * ww[:, None]).sum(axis=0) / total)
    scale[scale < 1e-9] = 1.0
    z = (a - mean) / scale
    blocks = [np.ones((len(b), 1)), z]
    penalty = [0.0, *([c.lam] * len(cols))]
    names: list[str] = []
    if c.station_lambda is not None:
        names = sorted(set(t.station[ok].tolist()))
        index = {s: k for k, s in enumerate(names)}
        one_hot = np.zeros((len(b), len(names)))
        one_hot[np.arange(len(b)), [index[str(s)] for s in t.station[ok]]] = 1.0
        blocks.append(one_hot)
        penalty += [c.station_lambda] * len(names)
    design = np.hstack(blocks)
    weighted = design.T * ww
    solution = np.linalg.solve(weighted @ design + np.diag(penalty), weighted @ b)
    coef = solution[1 : 1 + len(cols)]
    offsets = {s: float(v) for s, v in zip(names, solution[1 + len(cols) :], strict=True)}
    return Model(tuple(cols), mean, scale, coef, float(solution[0]), offsets)


def strict_rows(t: Table) -> NDArray[np.bool_]:
    """The rows that pass the strict pair-quality rule.

    Args:
        t: The pair set.

    Returns:
        A row mask.
    """
    return np.array([p.gap_days <= STRICT["max_gap_days"]
                     and p.stats.get("valid_px", math.nan) >= STRICT["min_valid_px"]
                     and p.stats.get("glint_share", math.nan) <= STRICT["max_glint_share"]
                     for p in t.pairs], dtype=bool)  # fmt: skip


@dataclass
class Search:
    """Round 3's data, its units' years and a cache of fits."""

    d: Data
    unit_year: dict[int, int]
    strict: dict[str, NDArray[np.bool_]]
    fits: dict[tuple[str, frozenset[int], frozenset[int]], Model | None] = field(
        default_factory=dict, repr=False
    )

    def model(self, c: Candidate, years_out: frozenset[int],
              samples_out: frozenset[int] = frozenset()) -> Model | None:  # fmt: skip
        """A candidate fitted without some hydrological years and samples (cached).

        Args:
            c: The candidate.
            years_out: Years whose pairs leave training.
            samples_out: Samples whose pairs leave training.

        Returns:
            The model, or None.
        """
        key = (c.id, years_out, samples_out)
        if key not in self.fits:
            t = self.d.tables[c.pair_set]
            allowed = ~np.isin(t.year, sorted(years_out)) & ~np.isin(t.sample, sorted(samples_out))
            if c.quality == "strict":
                allowed &= self.strict[c.pair_set]
            keep, w = search.weights(t, allowed, c.aggregation)
            self.fits[key] = fit(t, keep, w, c)
        return self.fits[key]

    def predict(self, model: Model | None, c: Candidate, units: Sequence[int]) -> list[float]:
        """Estimates of some units (their ±3-day stable pairs; unknown g is 0, deviation 8).

        Args:
            model: The fitted candidate.
            c: The candidate (its aggregation).
            units: Unit (sample) indices.

        Returns:
            One estimate per unit.
        """
        if model is None:
            return [math.nan] * len(units)
        test = self.d.tables["3s"]
        x = test.x.copy()
        col = NAMES.index("g")
        x[np.isnan(x[:, col]), col] = 0.0
        out = []
        for u in units:
            idx = np.flatnonzero(test.sample == u)
            if c.aggregation == "nearest":
                idx = idx[test.nearest[idx]]
            values = model.predict(x[idx], test.station[idx])
            values = values[np.isfinite(values)]
            out.append(float(np.median(values)) if values.size else math.nan)
        return out

    def units_of(self, years: set[int], samples_out: frozenset[int] = frozenset()) -> list[int]:
        """The units of some years (in station order), without some samples.

        Args:
            years: Hydrological years.
            samples_out: Units to leave out.

        Returns:
            Unit indices.
        """
        return [u for s in sorted(self.d.units) for u in self.d.units[s]
                if self.unit_year[u] in years and u not in samples_out]  # fmt: skip


def _mdsa(estimates: Mapping[int, float], value: Mapping[int, float]) -> float:
    ok = [(e, value[u]) for u, e in estimates.items() if math.isfinite(e) and e > 0]
    return stats.mdsa([e for e, _ in ok], [o for _, o in ok]) if len(ok) >= 5 else math.inf


def pick(scores: Mapping[str, float], candidates: Sequence[Candidate], margin: float) -> Candidate:
    """The lowest MdSA; within ``margin`` points, the simplest.

    Args:
        scores: Candidate id -> MdSA.
        candidates: The space, simplest first.
        margin: MdSA points.

    Returns:
        The candidate.
    """
    finite = {k: v for k, v in scores.items() if math.isfinite(v)}
    if not finite:
        return candidates[0]
    best = min(finite.values())
    return next(c for c in candidates if c.id in finite and finite[c.id] <= best + margin)


def inner(s: Search, candidates: Sequence[Candidate], years: Sequence[int],
          years_out: frozenset[int], samples_out: frozenset[int], margin: float
          ) -> tuple[Candidate, dict[int, float]]:  # fmt: skip
    """Leave-one-year-out over ``years`` (with ``years_out`` and ``samples_out`` always out).

    Args:
        s: The search.
        candidates: The space.
        years: The inner folds (years with units).
        years_out: Years never trained on here.
        samples_out: Samples never trained on or scored here.
        margin: MdSA points.

    Returns:
        The winner and its inner estimates (unit -> estimate).
    """
    estimates: dict[str, dict[int, float]] = {}
    for c in candidates:
        est: dict[int, float] = {}
        for y in years:
            units = s.units_of({y}, samples_out)
            model = s.model(c, years_out | {y}, samples_out)
            est.update(zip(units, s.predict(model, c, units), strict=True))
        estimates[c.id] = est
    winner = pick({k: _mdsa(v, s.d.value) for k, v in estimates.items()}, candidates, margin)
    return winner, estimates[winner.id]


@dataclass
class Outer:
    """Held-out estimates of one scheme, with the null, the choices and interval hits."""

    estimates: dict[int, float] = field(default_factory=dict)
    null: dict[int, float] = field(default_factory=dict)
    inside: dict[float, dict[int, bool | None]] = field(default_factory=dict)
    chosen: dict[str, str] = field(default_factory=dict)


def run_fold(s: Search, cfg: QualityConfig, candidates: Sequence[Candidate], label: str,
             predict: Sequence[int], train_years: Sequence[int], years_out: frozenset[int],
             samples_out: frozenset[int], out: Outer) -> None:  # fmt: skip
    """One outer fold: select inside the training years, fit, predict, interval and null.

    Args:
        s: The search.
        cfg: Settings.
        candidates: The space.
        label: The fold's name (for the choices).
        predict: The units to predict.
        train_years: Years with units that may train and select.
        years_out: Years that never train in this fold.
        samples_out: Samples that never train in this fold.
        out: Where the results go.
    """
    margin = cfg.selection.simpler_within_mdsa
    winner, inner_est = inner(s, candidates, train_years, years_out, samples_out, margin)
    out.chosen[label] = winner.id
    model = s.model(winner, years_out, samples_out)
    values = s.predict(model, winner, predict)
    train_units = sorted(inner_est)
    q = route_a.conformal([inner_est[u] for u in train_units],
                          [s.d.value[u] for u in train_units], cfg.intervals.coverages)  # fmt: skip
    median = float(np.median([s.d.value[u] for u in train_units])) if train_units else math.nan
    for u, v in zip(predict, values, strict=True):
        out.estimates[u], out.null[u] = v, median
        for c in cfg.intervals.coverages:
            out.inside.setdefault(c, {})[u] = posthoc._hit(q, v, s.d.value[u], c)


def primary(s: Search, cfg: QualityConfig, candidates: Sequence[Candidate]) -> Outer:
    """Leave-one-hydrological-year-out, the primary scheme.

    Args:
        s: The search.
        cfg: Settings.
        candidates: The space.

    Returns:
        The held-out estimates.
    """
    out = Outer()
    years = sorted(set(s.unit_year.values()))
    for y in years:
        run_fold(s, cfg, candidates, str(y), s.units_of({y}), [x for x in years if x != y],
                 frozenset({y}), frozenset(), out)  # fmt: skip
    return out


def one_sample_out(s: Search, cfg: QualityConfig, candidates: Sequence[Candidate]) -> Outer:
    """Sensitivity: each unit held out alone (its sample's pairs leave training).

    Args:
        s: The search.
        cfg: Settings.
        candidates: The space.

    Returns:
        The held-out estimates.
    """
    out = Outer()
    years = sorted(set(s.unit_year.values()))
    for u in sorted(s.unit_year):
        run_fold(s, cfg, candidates, str(u), [u], years, frozenset(), frozenset({u}), out)
    return out


def forward(s: Search, cfg: QualityConfig, candidates: Sequence[Candidate]) -> Outer:
    """Sensitivity: each year predicted from earlier years only.

    Args:
        s: The search.
        cfg: Settings.
        candidates: The space.

    Returns:
        The held-out estimates (years with too few earlier years are skipped).
    """
    out = Outer()
    years = sorted(set(s.unit_year.values()))
    every = {int(v) for t in s.d.tables.values() for v in t.year.tolist()}
    for k, y in enumerate(years):
        if k < MIN_EARLIER_YEARS:
            continue
        later = frozenset(v for v in every if v >= y)
        run_fold(s, cfg, candidates, str(y), s.units_of({y}), years[:k], later, frozenset(),
                 out)  # fmt: skip
    return out


def as_nested(s: Search, o: Outer, units: Sequence[int],
              coverages: Sequence[float]) -> posthoc.Nested:  # fmt: skip
    """An outer result in v2.1's form (for its metrics and level rows).

    Args:
        s: The search.
        o: The outer result.
        units: The units, in order.
        coverages: The interval coverages.

    Returns:
        The nested result.
    """
    return posthoc.Nested(
        [o.estimates.get(u, math.nan) for u in units],
        [o.null.get(u, math.nan) for u in units],
        dict(o.chosen),
        {c: [o.inside.get(c, {}).get(u) for u in units] for c in coverages},
    )


def dogliotti_offsets(s: Search, cfg: QualityConfig, radcor: Mapping[tuple[str, date], float]
                      ) -> tuple[list[int], list[float], list[float]]:  # fmt: skip
    """Report-only: Dogliotti 2015 on RAdCor with a common offset and station offsets (LOYO).

    log y = log D + c + o_s; λs from {none, 1, 10} by the inner leave-one-year-out.

    Args:
        s: The search.
        cfg: Settings.
        radcor: (station, sample day) -> Dogliotti on RAdCor.

    Returns:
        The units with RAdCor, their held-out estimates and the null's.
    """
    units = [u for u in sorted(s.unit_year)
             if math.isfinite(radcor.get((s.d.pool[u].station, s.d.pool[u].sample_day),
                                         math.nan))]  # fmt: skip
    dog = {u: radcor[(s.d.pool[u].station, s.d.pool[u].sample_day)] for u in units}
    resid = {u: math.log(s.d.value[u] / dog[u]) for u in units if dog[u] > 0}

    def fit_offsets(train: Sequence[int], lam: float | None) -> Callable[[int], float]:
        r = np.array([resid[u] for u in train])
        common = float(r.mean()) if len(r) else 0.0
        offsets: dict[str, float] = {}
        if lam is not None:
            for st in {s.d.pool[u].station for u in train}:
                rs = [resid[u] - common for u in train if s.d.pool[u].station == st]
                offsets[st] = float(sum(rs) / (len(rs) + lam))
        return lambda u: dog[u] * math.exp(common + offsets.get(s.d.pool[u].station, 0.0))

    years = sorted({s.unit_year[u] for u in resid})
    est: list[float] = []
    nulls: list[float] = []
    kept = [u for u in units if u in resid]
    for u in kept:
        y = s.unit_year[u]
        train_years = [x for x in years if x != y]
        best: tuple[float, float | None] | None = None
        for lam in (None, 10.0, 1.0):
            inner_est = {}
            for iy in train_years:
                tr = [v for v in resid if s.unit_year[v] not in (y, iy)]
                f = fit_offsets(tr, lam)
                inner_est.update({v: f(v) for v in resid if s.unit_year[v] == iy})
            score = _mdsa(inner_est, s.d.value)
            if best is None or score < best[0] - 1e-12:
                best = (score, lam)
        train = [v for v in resid if s.unit_year[v] != y]
        est.append(fit_offsets(train, best[1] if best else None)(u))
        nulls.append(float(np.median([s.d.value[v] for v in train])) if train else math.nan)
    return kept, est, nulls


def ridge_card(d: Data, pair_set: str, candidate: str, model: Model, station: str,
               inner_est: Mapping[int, float], levels: Sequence[Mapping[str, Any]],
               metrics: Mapping[str, Mapping[str, float]], cfg: QualityConfig, basis: str,
               model_id: str) -> dict[str, Any]:  # fmt: skip
    """The card of a ridge in log space at one station (its offset folded into the intercept).

    In operation the scene is the sample's own day, so g is 0; log_T comes from A4.

    Args:
        d: The data (the training pair set's feature ranges and values).
        pair_set: The candidate's training pair set.
        candidate: The candidate's id.
        model: The fitted model.
        station: The reach's estimate station.
        inner_est: The selection's inner estimates (the interval's residuals).
        levels: The level rows.
        metrics: Named metric sets.
        cfg: Settings.
        basis: The card's basis.
        model_id: Its id.

    Returns:
        The card (JSON-ready).
    """
    names = [NAMES[k] for k in model.columns]
    t = d.tables[pair_set]
    ranges: dict[str, list[float]] = {}
    for k, n in zip(model.columns, names, strict=True):
        if n in ("log_T", "g", "flow_z"):
            continue
        col = t.x[:, k][np.isfinite(t.x[:, k])]
        if col.size:
            ranges[n] = [round(float(col.min()), 6), round(float(col.max()), 6)]
    units = sorted(inner_est)
    observed = [d.value[u] for u in units]
    offset = float(model.offsets.get(station, 0.0))
    parameters = {"kind": "ridge-log", "features": names,
                  "mean": [round(float(v), 10) for v in model.mean],
                  "scale": [round(float(v), 10) for v in model.scale],
                  "coefficients": [round(float(v), 10) for v in model.coef],
                  "intercept": round(model.intercept + offset, 10),
                  "stationOffset": round(offset, 10), "tFile": "gbm-turbidity-core.json",
                  "operational": "g = 0 (the scene is the estimate's own day)"}  # fmt: skip
    values = [p.value for p in t.pairs]
    decisive = {"parameters": parameters, "adjustment": None, "featureRange": ranges,
                "targetRange": [round(min(values), 6), round(max(values), 6)],
                "intervals": cards._quantiles([inner_est[u] for u in units], observed,
                                              cfg.intervals.coverages)}  # fmt: skip
    digest = hashlib.sha256(json.dumps(decisive, sort_keys=True).encode()).hexdigest()
    return {
        "modelId": model_id, "version": cards.VERSION, "target": search.TARGET,
        "unit": cfg.target(search.TARGET).unit, "window": "core", "candidate": candidate,
        "basis": basis, "station": station, **decisive,
        "levels": [{k: cards._finite(v) for k, v in r.items()} for r in levels],
        "metrics": {k: {m: cards._finite(v) for m, v in d.items() if isinstance(v, int | float)}
                    for k, d in metrics.items()},
        "parametersHash": digest,
    }  # fmt: skip


def analyse(cfg: QualityConfig, d: Data, radcor: Mapping[tuple[str, date], float]
            ) -> dict[str, list[dict[str, Any]]]:  # fmt: skip
    """Round 3's tables and card (under ``_round3_card``).

    Args:
        cfg: Settings.
        d: The Magdalena data with the preregistered flow features.
        radcor: (station, sample day) -> Dogliotti on RAdCor.

    Returns:
        ``v4_round3_scores``, ``v4_round3_levels`` and ``v4_round3_choices``.
    """
    from climate_pipeline.quality.route_b import _seed

    tables: dict[str, list[dict[str, Any]]] = {"v4_round3_scores": [], "v4_round3_levels": [],
                                               "v4_round3_choices": []}  # fmt: skip
    if len(d.units) < 3:
        tables["v4_round3_scores"].append({"round": 3, "status": "insufficient_data"})
        return tables
    unit_year = {u: p.sample_day.year + (p.sample_day.month == 12) for u, p in d.pool.items()}
    s = Search(d, unit_year, {ps: strict_rows(t) for ps, t in d.tables.items()})
    candidates = space()
    seed = _seed(cfg.seed, "v4", "round3")
    units = [u for st in sorted(d.units) for u in d.units[st]]
    pool = [d.pool[u] for u in units]
    coverages = cfg.intervals.coverages
    target = cfg.target(search.TARGET)

    def scored(label: str, o: Outer, k: int, extra: Mapping[str, Any] | None = None
               ) -> tuple[posthoc.Nested, dict[str, float]]:  # fmt: skip
        held = [u for u in units if u in o.estimates]
        nested = as_nested(s, o, held, coverages)
        sub = [d.pool[u] for u in held]
        m = posthoc.metrics(cfg, sub, nested, list(range(len(sub))), seed + k)
        tables["v4_round3_scores"].append({"round": 3, "evaluation": label, **m,
                                           **(extra or {})})  # fmt: skip
        return nested, m

    main = primary(s, cfg, candidates)
    nested, _ = scored("nested leave-one-hydrological-year-out (whole space)", main, 0)
    rows = posthoc.level_rows(cfg, target, pool, nested, seed)
    tables["v4_round3_scores"][-1].update({"level": rows[0]["level"],
                                           "candidates": len(candidates),
                                           "years": len(set(unit_year.values()))})  # fmt: skip
    tables["v4_round3_levels"] += [{"round": 3, **r} for r in rows]
    tables["v4_round3_choices"] += [{"round": 3, "scheme": "leave-one-year-out", "held_out": k,
                                     "chosen": v} for k, v in main.chosen.items()]  # fmt: skip
    sp = [u for u in units if d.pool[u].station == ESTIMATE_STATION]
    if sp:
        sub = [d.pool[u] for u in sp]
        m = route_a.evaluate(cfg, sub, [main.estimates[u] for u in sp],
                             [main.null[u] for u in sp], None, seed + 1)  # fmt: skip
        label = "San Pablo (23207040) units of the primary scheme (not rated)"
        tables["v4_round3_scores"].append({"round": 3, "evaluation": label, **m})
    scored("sensitivity: one sample out within its station", one_sample_out(s, cfg, candidates),
           2)  # fmt: skip
    fwd = forward(s, cfg, candidates)
    scored("sensitivity: forward chaining (earlier years only)", fwd, 3)
    tables["v4_round3_choices"] += [{"round": 3, "scheme": "forward chaining", "held_out": k,
                                     "chosen": v} for k, v in fwd.chosen.items()]  # fmt: skip
    hindsight = ("T+G", "7", "nearest", 10.0, "all")
    form = [
        c
        for c in candidates
        if (c.combo, c.pair_set, c.aggregation, c.station_lambda, c.quality) == hindsight
    ]
    scored("report-only: T+G, ±7 days, nearest, offsets λs 10 (form chosen with hindsight)",
           primary(s, cfg, form), 4)  # fmt: skip
    kept, est, nulls = dogliotti_offsets(s, cfg, radcor)
    if len(kept) >= 5:
        m = route_a.evaluate(cfg, [d.pool[u] for u in kept], est, nulls, None, seed + 5)
        tables["v4_round3_scores"].append({"round": 3, "evaluation": "report-only: Dogliotti "
                                           "2015 on RAdCor with station offsets, leave-one-year-"
                                           "out", **m})  # fmt: skip
    all_years = sorted(set(unit_year.values()))
    winner, inner_est = inner(s, candidates, all_years, frozenset(), frozenset(),
                              cfg.selection.simpler_within_mdsa)  # fmt: skip
    model = s.model(winner, frozenset())
    if model is not None:
        card = ridge_card(d, winner.pair_set, winner.id, model, ESTIMATE_STATION, inner_est,
                          rows, {"round3": tables["v4_round3_scores"][0]}, cfg, BASIS,
                          f"R3:{search.TARGET}:core:magdalena")  # fmt: skip
        tables["_round3_card"] = [card]
    return tables


LEVEL_ORDER = ("none", "indicative", "estimated", "validated")


def summary(tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Round 3's primary error and level, and round 1's of record (deviation 9).

    Args:
        tables: The run's tables.

    Returns:
        ``round 3`` and ``round 1 (of record)``, each with ``mdsa``, ``level`` and ``n``.
    """
    out: dict[str, Any] = {}
    for key, name, evaluation in (
        ("round 3", "v4_round3_scores", "nested leave-one-hydrological-year-out (whole space)"),
        ("round 1 (of record)", "v3_record_scores", "nested LOSO (whole space)"),
    ):
        for r in tables.get(name, []):
            if r.get("evaluation") == evaluation:
                lv = f"{r['level']} (post hoc)" if r.get("level", "none") != "none" else "none"
                out[key] = {"mdsa": round(r["mdsa"], 1), "level": lv, "n": int(r["n"])}
    return out


def round1_card(cfg: QualityConfig, d: Data, plain: Mapping[str, float],
                levels: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:  # fmt: skip
    """Round 1's card of record (deviation 9): the same selection on every station, then a fit.

    Args:
        cfg: Settings.
        d: The Magdalena data with the preregistered flow features.
        plain: Each candidate's plain-LOSO MdSA over every station.
        levels: Round 1's level rows of record.

    Returns:
        The card (None without a model).
    """
    candidates = search.space()
    chosen = search.pick(plain, candidates, cfg.selection.simpler_within_mdsa)
    stations = sorted(d.units)
    fitted = search.trained(chosen, d, d.stations(stations))
    if fitted is None:
        return None
    model = Model(fitted.columns, fitted.mean, fitted.scale, fitted.coef, fitted.intercept)
    loso = search.loso(chosen, d, stations)
    return ridge_card(d, chosen.pair_set, chosen.id, model, ESTIMATE_STATION, loso, levels, {},
                      cfg, posthoc.BASIS, f"R1:{search.TARGET}:core:magdalena")  # fmt: skip


def product_card(round1: Mapping[str, Any] | None, round3: Mapping[str, Any] | None
                 ) -> Mapping[str, Any] | None:  # fmt: skip
    """The Magdalena reach's turbidity card: round 3's when its level is at least indicative.

    Args:
        round1: Round 1's card of record.
        round3: Round 3's card.

    Returns:
        The chosen card (v4, B).
    """

    def overall(card: Mapping[str, Any] | None) -> str:
        rows = [r for r in (card or {}).get("levels", []) if r.get("predicted_range") == "all"]
        return str(rows[0]["level"]) if rows else "none"

    if round3 is not None and LEVEL_ORDER.index(overall(round3)) >= 1:
        return round3
    return round1
