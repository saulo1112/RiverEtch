"""v3, round 1: the open search to halve the Magdalena turbidity error (preregistration).

The candidate space crosses three training pair sets (±3 days with stable flow, ±7 and ±15 days),
two per-sample aggregations (the nearest scene, the median over the window's scenes) and thirteen
feature sets. The features are drawn from: log B8A/B04 (S), v2.1's four features (S5), the log of
A4's USGS estimate (T), the sample day's flow index (Q) and the flow change between sample and
scene (G). Every candidate is a weighted ridge in log space; λ comes from LOSO on its own training
stations.

The flow index is the station's log discharge (or level in metres, where only the level exists),
standardised by the station's own median and MAD. It is comparable across stations and gauge
types; g is its change from the scene day to the sample day.

Nested leave-one-station-out over the Magdalena stations chooses among the whole space inside
each fold. The outer test units are the Magdalena samples with a pair within ±1 day, or ±3 days
with stable flow (v2.1's main set). Longer matchups only train.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from climate_pipeline.calibration import stats
from climate_pipeline.calibration.config import WindowSettings
from climate_pipeline.calibration.fetching import read_stations
from climate_pipeline.calibration.matchups import Pair, Sample, SceneRow, fittable
from climate_pipeline.quality import features, posthoc, route_a
from climate_pipeline.quality.config import QualityConfig
from climate_pipeline.quality.route_a import ColombianInputs

TARGET = "turbidity"
PAIR_SETS = ("3s", "7", "15")
MAX_DAYS = {"3s": 3, "7": 7, "15": 15}
AGGREGATIONS = ("nearest", "median")
LAMBDAS = (0.1, 1.0, 10.0, 100.0)
FEATURES: dict[str, tuple[str, ...]] = {
    "S": ("log_B8A/B04",), "S5": posthoc.P5_FEATURES, "T": ("log_T",), "Q": ("flow_z",),
    "G": ("g",),
}  # fmt: skip
COMBOS = ("S", "S5", "T", "Q", "S+Q", "S5+Q", "T+Q", "S+G", "S5+G", "T+G", "S+Q+G", "S5+Q+G",
          "T+Q+G")  # fmt: skip
NAMES = ("log_B8A/B04", *posthoc.P5_FEATURES[1:], "log_T", "flow_z", "g")
FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class Candidate:
    """One point of the candidate space."""

    pair_set: str
    aggregation: str
    combo: str

    @property
    def id(self) -> str:
        """``combo|pair set|aggregation``."""
        return f"{self.combo}|{self.pair_set}|{self.aggregation}"

    @property
    def columns(self) -> list[int]:
        """The feature columns in :data:`NAMES`."""
        names = [n for part in self.combo.split("+") for n in FEATURES[part]]
        return [NAMES.index(n) for n in names]

    @property
    def complexity(self) -> tuple[int, int, int, int]:
        """Fewer features, shorter matchups, the nearest scene: simpler."""
        return (len(self.columns), PAIR_SETS.index(self.pair_set),
                AGGREGATIONS.index(self.aggregation), COMBOS.index(self.combo))  # fmt: skip


def space() -> list[Candidate]:
    """Round 1's candidates, simplest first (G only where pairs have gaps).

    Returns:
        The candidates.
    """
    out = [Candidate(ps, agg, combo) for ps in PAIR_SETS for agg in AGGREGATIONS
           for combo in COMBOS if not (ps == "3s" and "G" in combo)]  # fmt: skip
    return sorted(out, key=lambda c: c.complexity)


def flow_index(flow: Mapping[str, tuple[str, Mapping[date, float]]]
               ) -> dict[str, dict[date, float]]:  # fmt: skip
    """Each station's standardised flow (log discharge, or level in metres).

    Args:
        flow: Station -> (label, day -> value).

    Returns:
        Station -> day -> index.
    """
    out = {}
    for station, (label, series) in flow.items():
        values = {d: (math.log(v) if label == "Q_MEDIA_D" else v / 100)
                  for d, v in series.items()
                  if math.isfinite(v) and (v > 0 or label != "Q_MEDIA_D")}  # fmt: skip
        if len(values) < 30:
            continue
        x = np.array(list(values.values()))
        median = float(np.median(x))
        scale = max(1.4826 * float(np.median(np.abs(x - median))), 1e-6)
        out[station] = {d: (v - median) / scale for d, v in values.items()}
    return out


def all_pairs(samples: Sequence[Sample], scenes: Sequence[SceneRow], max_days: int,
              guards: WindowSettings) -> list[Pair]:  # fmt: skip
    """Every usable scene within ``max_days`` of each sample, as pairs.

    Args:
        samples: Samples.
        scenes: Station windows.
        max_days: Largest gap.
        guards: The window guards.

    Returns:
        The fittable pairs.
    """
    by_station: dict[str, list[SceneRow]] = {}
    for scene in scenes:
        if scene.usable(guards):
            by_station.setdefault(scene.station, []).append(scene)
    out = []
    for s in samples:
        for scene in by_station.get(s.station, []):
            gap = abs((scene.day - s.day).days)
            if gap <= max_days:
                out.append(Pair(
                    s.target, s.station, s.day, scene.key, scene.day, gap, s.value, s.censored,
                    s.state, scene.family, scene.features, scene.stats,
                ))  # fmt: skip
    return fittable(out)


@dataclass
class Table:
    """The pairs of one set as arrays."""

    pairs: list[Pair]
    x: FloatArray  # pairs x NAMES
    y: FloatArray  # log value
    station: NDArray[np.str_]
    sample: NDArray[np.int64]  # sample index
    nearest: NDArray[np.bool_]  # the sample's nearest pair in this set


def table(pairs: Sequence[Pair], index: Mapping[str, dict[date, float]],
          t_model: Callable[[Pair], float] | None,
          sample_ids: Mapping[tuple[str, date], int]) -> Table:  # fmt: skip
    """The arrays of a pair set, with the flow and transfer features.

    Args:
        pairs: The pairs.
        index: The flow index.
        t_model: A4's USGS model (None: T is missing).
        sample_ids: (station, sample day) -> sample index.

    Returns:
        The table.
    """
    rows = []
    for p in pairs:
        z = index.get(p.station, {})
        zs, zc = z.get(p.sample_day, math.nan), z.get(p.scene_day, math.nan)
        t = t_model(p) if t_model else math.nan
        log_t = math.log(t) if math.isfinite(t) and t > 0 else math.nan
        bands = [p.features.get(n, math.nan) for n in ("log_B8A/B04", *posthoc.P5_FEATURES[1:])]
        rows.append([*bands, log_t, zs, zs - zc])
    sample = np.array([sample_ids[(p.station, p.sample_day)] for p in pairs], dtype=np.int64)
    gaps = np.array([p.gap_days for p in pairs])
    nearest = np.zeros(len(pairs), dtype=bool)
    for s in set(sample.tolist()):
        idx = np.flatnonzero(sample == s)
        nearest[idx[np.argmin(gaps[idx])]] = True
    return Table(list(pairs), np.array(rows, dtype=np.float64).reshape(len(pairs), len(NAMES)),
                 np.log(np.array([p.value for p in pairs], dtype=np.float64)),
                 np.array([p.station for p in pairs]), sample, nearest)  # fmt: skip


@dataclass(frozen=True)
class Model:
    """A fitted weighted ridge in log space."""

    columns: tuple[int, ...]
    mean: FloatArray
    scale: FloatArray
    coef: FloatArray
    intercept: float

    def predict(self, x: FloatArray) -> FloatArray:
        """Estimates in the target's unit (NaN where a feature is missing).

        Args:
            x: Rows x NAMES.

        Returns:
            One estimate per row.
        """
        z = (x[:, list(self.columns)] - self.mean) / self.scale
        return np.exp(self.intercept + z @ self.coef)


def fit(x: FloatArray, y: FloatArray, w: FloatArray, columns: Sequence[int],
        lam: float) -> Model | None:  # fmt: skip
    """A weighted ridge with an unpenalised intercept on standardised features.

    Args:
        x: Rows x NAMES.
        y: Log targets.
        w: Weights.
        columns: Features used.
        lam: Penalty.

    Returns:
        The model (None with too few usable rows).
    """
    cols = list(columns)
    ok = np.all(np.isfinite(x[:, cols]), axis=1) & np.isfinite(y)
    if ok.sum() < len(cols) + 3:
        return None
    a, b, ww = x[ok][:, cols], y[ok], w[ok]
    mean = np.average(a, axis=0, weights=ww)
    scale = np.sqrt(np.average((a - mean) ** 2, axis=0, weights=ww))
    scale[scale < 1e-9] = 1.0
    z = (a - mean) / scale
    ym = float(np.average(b, weights=ww))
    zw = z * ww[:, None]
    coef = np.linalg.solve(z.T @ zw + lam * np.eye(len(cols)), zw.T @ (b - ym))
    return Model(tuple(cols), mean, scale, coef, ym)


def weights(
    t: Table, rows: NDArray[np.bool_], aggregation: str
) -> tuple[NDArray[np.bool_], FloatArray]:
    """The training rows and weights of an aggregation.

    Args:
        t: The pair set.
        rows: Rows allowed (the training stations).
        aggregation: ``nearest`` (one pair per sample) or ``median`` (all pairs, 1/n each).

    Returns:
        The rows kept and their weights (over all rows).
    """
    keep = rows & t.nearest if aggregation == "nearest" else rows.copy()
    w = np.zeros(len(t.y))
    if keep.any():
        counts = np.bincount(t.sample[keep], minlength=int(t.sample.max()) + 1)
        w[keep] = 1.0 / counts[t.sample[keep]]
    return keep, w


def train(c: Candidate, t: Table, stations: set[str]) -> Model | None:
    """A candidate fitted on some stations, λ by LOSO over them (pair-level MdSA).

    Args:
        c: The candidate.
        t: Its pair set.
        stations: Training stations.

    Returns:
        The model, or None.
    """
    allowed = np.isin(t.station, sorted(stations))
    keep, w = weights(t, allowed, c.aggregation)
    best: tuple[float, float] | None = None
    names = sorted(stations)
    for lam in LAMBDAS:
        oof = np.full(len(t.y), math.nan)
        for s in names:
            held = keep & (t.station == s)
            m = (
                fit(t.x, t.y, np.where(keep & ~held, w, 0.0), c.columns, lam)
                if held.any()
                else None
            )
            if m is not None:
                oof[held] = m.predict(t.x[held])
        valid = keep & np.isfinite(oof)
        if valid.sum() < 5:
            continue
        score = stats.mdsa(list(oof[valid]), list(np.exp(t.y[valid])))
        if best is None or score < best[0]:
            best = (score, lam)
    if best is None:
        return None
    return fit(t.x, t.y, np.where(keep, w, 0.0), c.columns, best[1])


def predict_units(
    model: Model | None, c: Candidate, test: Table, units: Sequence[int], impute: bool = True
) -> list[float]:
    """Estimates for some test samples (their ±3-day stable pairs).

    Where the flow is unknown, its standardised index is imputed as 0 (the station's typical flow,
    no change), so a candidate with Q or G predicts every unit and candidates are compared on the
    same units (deviation 8). The training rows always have real flow.

    Args:
        model: The fitted candidate.
        c: The candidate (its aggregation).
        test: The test pair set.
        units: Sample indices.
        impute: Impute the unknown flow (False: the first run of round 1).

    Returns:
        One estimate per unit.
    """
    if model is None:
        return [math.nan] * len(units)
    x = test.x
    if impute:
        x = x.copy()
        for col in (NAMES.index("flow_z"), NAMES.index("g")):
            x[np.isnan(x[:, col]), col] = 0.0
    est = model.predict(x)
    out = []
    for u in units:
        idx = np.flatnonzero(test.sample == u)
        if c.aggregation == "nearest":
            idx = idx[test.nearest[idx]]
        values = est[idx][np.isfinite(est[idx])]
        out.append(float(np.median(values)) if values.size else math.nan)
    return out


@dataclass
class Data:
    """Round 1's inputs: the pair sets, the test units and their values."""

    tables: dict[str, Table]
    units: dict[str, list[int]]  # Magdalena station -> its test samples
    value: dict[int, float]
    pool: dict[int, Pair]  # each unit's nearest test pair (for stats and clusters)


def data(cfg: QualityConfig, ci: ColombianInputs, scenes: Sequence[SceneRow],
         t_model: Callable[[Pair], float] | None) -> Data:  # fmt: skip
    """The Magdalena turbidity pair sets and test units.

    Args:
        cfg: Settings.
        ci: The Colombian inputs (samples, flow, streams).
        scenes: Every core-window scene (v2's and the extended fetch's).
        t_model: A4's USGS model.

    Returns:
        The data.
    """
    test_stream = cfg.stations.test_stream
    samples = [s for s in ci.samples if s.target == TARGET
               and ci.stream_of.get(s.station) == test_stream]  # fmt: skip
    ids = {(s.station, s.day): k for k, s in enumerate(samples)}
    index = flow_index(ci.flow)
    guards = cfg.window.as_calibration()
    tables = {}
    for ps in PAIR_SETS:
        found = all_pairs(samples, scenes, MAX_DAYS[ps], guards)
        if ps == "3s":
            found = [p for p in found if route_a.stable(p, ci.flow, cfg)]
        tables[ps] = table(found, index, t_model, ids)
    test = tables["3s"]
    units: dict[str, list[int]] = {}
    pool: dict[int, Pair] = {}
    for k, p in enumerate(test.pairs):
        u = int(test.sample[k])
        if test.nearest[k]:
            pool[u] = p
            units.setdefault(p.station, []).append(u)
    return Data(tables, units, {u: p.value for u, p in pool.items()}, pool)


def _mdsa(estimates: Mapping[int, float], value: Mapping[int, float]) -> float:
    ok = [(e, value[u]) for u, e in estimates.items() if math.isfinite(e) and e > 0]
    return stats.mdsa([e for e, _ in ok], [o for _, o in ok]) if len(ok) >= 5 else math.inf


def loso(c: Candidate, d: Data, stations: Sequence[str], impute: bool = True) -> dict[int, float]:
    """A candidate's leave-one-station-out estimates of the units of ``stations``.

    Args:
        c: The candidate.
        d: The data.
        stations: The stations (each predicted by a fit on the others).
        impute: Impute the unknown flow (see :func:`predict_units`).

    Returns:
        Unit -> estimate.
    """
    out: dict[int, float] = {}
    rest = set(stations)
    for s in stations:
        model = train(c, d.tables[c.pair_set], rest - {s})
        for u, e in zip(d.units[s], predict_units(model, c, d.tables["3s"], d.units[s], impute),
                        strict=True):  # fmt: skip
            out[u] = e
    return out


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


def nested(cfg: QualityConfig, d: Data, candidates: Sequence[Candidate], impute: bool = True
           ) -> tuple[posthoc.Nested, list[int], dict[str, float]]:  # fmt: skip
    """Nested LOSO over the whole space; also each candidate's plain LOSO MdSA (report-only).

    Args:
        cfg: Settings.
        d: The data.
        candidates: The space.
        impute: Impute the unknown flow (see :func:`predict_units`).

    Returns:
        The held-out estimates (with the null and interval hits), the unit order and each
        candidate's plain LOSO MdSA over every station.
    """
    stations = sorted(d.units)
    order = [u for s in stations for u in d.units[s]]
    pos = {u: k for k, u in enumerate(order)}
    n = len(order)
    est, nul = [math.nan] * n, [math.nan] * n
    inside: dict[float, list[bool | None]] = {c: [None] * n for c in cfg.intervals.coverages}
    chosen: dict[str, str] = {}
    margin = cfg.selection.simpler_within_mdsa
    for s in stations:
        rest = [x for x in stations if x != s]
        inner = {c.id: loso(c, d, rest, impute) for c in candidates}
        winner = pick({k: _mdsa(v, d.value) for k, v in inner.items()}, candidates, margin)
        chosen[s] = winner.id
        model = train(winner, d.tables[winner.pair_set], set(rest))
        values = predict_units(model, winner, d.tables["3s"], d.units[s], impute)
        train_units = [u for x in rest for u in d.units[x]]
        observed = [d.value[u] for u in train_units]
        q = route_a.conformal([inner[winner.id][u] for u in train_units], observed,
                              cfg.intervals.coverages)  # fmt: skip
        median = float(np.median([d.value[u] for u in train_units]))
        for u, v in zip(d.units[s], values, strict=True):
            k = pos[u]
            est[k], nul[k] = v, median
            for c in cfg.intervals.coverages:
                inside[c][k] = posthoc._hit(q, v, d.value[u], c)
    plain = {c.id: _mdsa(loso(c, d, stations, impute), d.value) for c in candidates}
    return posthoc.Nested(est, nul, chosen, inside), order, plain


def analyse(
    cfg: QualityConfig, ci: ColombianInputs, scenes: Sequence[SceneRow],
    t_model: Callable[[Pair], float] | None, radcor: Mapping[tuple[str, date], float],
) -> dict[str, list[dict[str, Any]]]:  # fmt: skip
    """Round 1's tables.

    Args:
        cfg: Settings.
        ci: The Colombian inputs.
        scenes: Every core-window scene.
        t_model: A4's USGS model.
        radcor: (station, sample day) -> Dogliotti 2015 on ACOLITE RAdCor.

    Returns:
        ``v3_scores``, ``v3_levels``, ``v3_choices`` and ``v3_candidates``.
    """
    from climate_pipeline.quality.route_b import _seed

    d = data(cfg, ci, scenes, t_model)
    tables: dict[str, list[dict[str, Any]]] = {
        "v3_scores": [],
        "v3_levels": [],
        "v3_choices": [],
        "v3_candidates": [],
    }
    counts: dict[str, Any] = {f"pairs_{ps}": len(t.pairs) for ps, t in d.tables.items()}
    counts["samples_in_15"] = len(set(d.tables["15"].sample.tolist()))
    if len(d.units) < 3:
        tables["v3_scores"].append({"round": 1, "status": "insufficient_data", **counts})
        return tables
    candidates = space()
    seed = _seed(cfg.seed, "v3", "round1")
    first, first_order, _ = nested(cfg, d, candidates, impute=False)
    first_pool = [d.pool[u] for u in first_order]
    fm = posthoc.metrics(cfg, first_pool, first, list(range(len(first_pool))), seed)
    tables["v3_scores"].append({"round": 1, "evaluation": "nested LOSO, first run (units without "
                                "flow dropped; superseded by deviation 8)", **fm})  # fmt: skip
    result, order, plain = nested(cfg, d, candidates)
    pool = [d.pool[u] for u in order]
    m = posthoc.metrics(cfg, pool, result, list(range(len(pool))), seed)
    rows = posthoc.level_rows(cfg, cfg.target(TARGET), pool, result, seed)
    tables["v3_scores"].append({"round": 1, "evaluation": "nested LOSO (whole space)", **m,
                                "level": rows[0]["level"], "candidates": len(candidates),
                                **counts})  # fmt: skip
    both = [k for k, p in enumerate(pool)
            if math.isfinite(radcor.get((p.station, p.sample_day), math.nan))]  # fmt: skip
    if len(both) >= 5:
        sub = [pool[k] for k in both]
        phys = [radcor[(p.station, p.sample_day)] for p in sub]
        l2a = [result.estimates[k] for k in both]
        mix = [math.sqrt(a * b) if a > 0 and b > 0 else math.nan
               for a, b in zip(l2a, phys, strict=True)]  # fmt: skip
        null = [result.null[k] for k in both]
        for label, values in (("ensemble with RAdCor (geometric mean)", mix),
                              ("L2A nested, same pairs", l2a),
                              ("Dogliotti on RAdCor, same pairs", phys)):  # fmt: skip
            scored = route_a.evaluate(cfg, sub, values, null, None, seed)
            tables["v3_scores"].append({"round": 1, "evaluation": label, **scored})
    tables["v3_levels"] += [{"round": 1, **r} for r in rows]
    tables["v3_choices"] += [{"round": 1, "held_out_station": s, "chosen": c}
                             for s, c in result.chosen.items()]  # fmt: skip
    ranked = sorted(plain.items(), key=lambda kv: kv[1])
    tables["v3_candidates"] += [{"round": 1, "candidate": k, "plain_loso_mdsa": v,
                                 "note": "report-only: chosen with hindsight"}
                                for k, v in ranked[:15]]  # fmt: skip
    return tables


def scenes(cfg: QualityConfig, root: Path, ci: ColombianInputs) -> list[SceneRow] | None:
    """The core-window scenes of v2 and of the extended fetch (None before that fetch).

    Args:
        cfg: Settings.
        root: Repository root.
        ci: The Colombian inputs (v2's scenes, with F).

    Returns:
        The scenes, each station and acquisition once.
    """
    inputs = root / cfg.outputs.inputs
    path = inputs / "imagery" / "windows-extended.csv"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    extra = {w: route_a.scenes_from_windows(text, w) for w in ("300m", "core")}
    stations = read_stations(inputs / "stations" / "stations.csv")
    widths = {r["station_id"]: float(r["width_m"]) for r in stations if r["width_m"]}
    full = features.with_features(cfg.features, extra, widths)["core"]
    seen = {(s.station, s.key) for s in ci.scenes["core"]}
    return [*ci.scenes["core"], *(s for s in full if (s.station, s.key) not in seen)]


def summary(tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Each round's nested error and level.

    Args:
        tables: The run's tables.

    Returns:
        ``round <n>`` -> ``mdsa``, ``level``, ``n``.
    """
    out: dict[str, Any] = {}
    for r in tables.get("v3_scores", []):
        if r.get("evaluation") == "nested LOSO (whole space)":
            lv = f"{r['level']} (post hoc)" if r["level"] != "none" else "none"
            out[f"round {r['round']}"] = {"mdsa": round(r["mdsa"], 1), "level": lv,
                                          "n": int(r["n"])}  # fmt: skip
    return out
