"""Route A's transfer models: pretrained on the USGS pilot, adjusted to Colombian units.

* **A2** is a log-log OLS on B8A/B04 fitted on USGS pairs.
* **A3** is a ridge in log space on the feature set F (standardized; the intercept is never
  penalized), its lambda chosen by leave-one-river-out over the USGS rivers.
* **The Colombian adjustment**, log y = a + b log yhat, is a ridge on (a, b - 1): with few
  Colombian pairs it stays near the identity. Its lambda is chosen by leave-one-station-out over
  the Colombian training pairs it is fitted on; under the minimum number of pairs it is the
  identity.

The USGS turbidity is in FNU and the Colombian in NTU: only the adjustment maps one to the other.
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from climate_pipeline.calibration import stats
from climate_pipeline.calibration.fetching import read_stations
from climate_pipeline.calibration.matchups import Pair, SceneRow
from climate_pipeline.calibration.stations import number
from climate_pipeline.quality import features, trees
from climate_pipeline.quality.config import QualityConfig

FloatArray = NDArray[np.float64]
Predictor = Callable[[Sequence[Pair], Sequence[Pair]], list[float]]


@dataclass(frozen=True)
class Linear:
    """A linear model of log(target) on standardized features."""

    names: tuple[str, ...]
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    coefficients: tuple[float, ...]  # intercept first
    ridge_lambda: float

    def predict(self, row: Mapping[str, float]) -> float:
        """The estimate for one feature row.

        Args:
            row: Features.

        Returns:
            The estimate (NaN when a feature is missing).
        """
        x = [row.get(n, math.nan) for n in self.names]
        if not all(math.isfinite(v) for v in x):
            return math.nan
        z = [(v - m) / s for v, m, s in zip(x, self.mean, self.scale, strict=True)]
        return math.exp(self.coefficients[0] + float(np.dot(self.coefficients[1:], z)))

    def predict_pair(self, pair: Pair) -> float:
        """The estimate for one pair (from its features).

        Args:
            pair: The pair.

        Returns:
            The estimate.
        """
        return self.predict(pair.features)


def usable_rows(pairs: Sequence[Pair], names: Sequence[str]) -> list[Pair]:
    """Pairs whose features are all finite and whose value is positive.

    Args:
        pairs: Pairs.
        names: Feature names.

    Returns:
        The usable pairs.
    """
    return [p for p in pairs if p.value > 0
            and all(math.isfinite(p.features.get(n, math.nan)) for n in names)]  # fmt: skip


def fit_linear(pairs: Sequence[Pair], names: Sequence[str], ridge_lambda: float) -> Linear:
    """Ridge (or OLS at lambda 0) of log(value) on standardized features.

    Args:
        pairs: Usable training pairs.
        names: Feature names.
        ridge_lambda: Penalty on the standardized slopes.

    Returns:
        The model.
    """
    x = np.array([[p.features[n] for n in names] for p in pairs], dtype=np.float64)
    y = np.log(np.array([p.value for p in pairs], dtype=np.float64))
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1.0
    z = (x - mean) / scale
    gram = z.T @ z + ridge_lambda * np.eye(len(names))
    slopes = np.linalg.solve(gram, z.T @ (y - y.mean()))
    return Linear(tuple(names), tuple(map(float, mean)), tuple(map(float, scale)),
                  (float(y.mean()), *map(float, slopes)), ridge_lambda)  # fmt: skip


def group_out(pairs: Sequence[Pair], group: Callable[[Pair], str],
              fit: Callable[[Sequence[Pair]], Callable[[Pair], float]]) -> list[float]:  # fmt: skip
    """Out-of-fold estimates: each group predicted by a model fitted on the others.

    Args:
        pairs: Pairs.
        group: Group of a pair.
        fit: Fits on training pairs and returns a predictor of one pair.

    Returns:
        One estimate per pair, in order.
    """
    out = [math.nan] * len(pairs)
    for g in sorted({group(p) for p in pairs}):
        train = [p for p in pairs if group(p) != g]
        if len(train) < 3:
            continue
        predict = fit(train)
        for k, p in enumerate(pairs):
            if group(p) == g:
                out[k] = predict(p)
    return out


def choose_lambda(pairs: Sequence[Pair], group: Callable[[Pair], str], names: Sequence[str],
                  lambdas: Sequence[float]) -> float:  # fmt: skip
    """The ridge lambda with the lowest leave-one-group-out MdSA (ties to the larger lambda).

    Args:
        pairs: Usable pairs.
        group: Group (a river).
        names: Feature names.
        lambdas: Candidates.

    Returns:
        The chosen lambda.
    """
    best: tuple[float, float] | None = None
    for lam in sorted(lambdas, reverse=True):

        def fit(train: Sequence[Pair], lam: float = lam) -> Callable[[Pair], float]:
            return fit_linear(train, names, lam).predict_pair

        oof = group_out(pairs, group, fit)
        score = stats.mdsa(oof, [p.value for p in pairs])
        if math.isfinite(score) and (best is None or score < best[0]):
            best = (score, lam)
    return best[1] if best else max(lambdas)


def fit_adjustment(estimates: Sequence[float], observed: Sequence[float],
                   ridge_lambda: float) -> tuple[float, float]:  # fmt: skip
    """The adjustment log y = a + b log yhat, a ridge on (a, b - 1).

    Args:
        estimates: Pretrained estimates.
        observed: Colombian values.
        ridge_lambda: Penalty on a and b - 1.

    Returns:
        ``(a, b)``.
    """
    x = np.log(np.asarray(estimates, dtype=np.float64))
    z = np.log(np.asarray(observed, dtype=np.float64)) - x
    lhs = np.array([[len(x) + ridge_lambda, x.sum()], [x.sum(), (x * x).sum() + ridge_lambda]])
    a, c = np.linalg.solve(lhs, np.array([z.sum(), (x * z).sum()]))
    return float(a), float(1 + c)


@dataclass(frozen=True)
class Adjustment:
    """The fitted Colombian adjustment."""

    a: float = 0.0
    b: float = 1.0
    ridge_lambda: float = math.nan

    def apply(self, estimate: float) -> float:
        """Map a pretrained estimate to Colombian units.

        Args:
            estimate: The pretrained estimate.

        Returns:
            The adjusted estimate.
        """
        if not (math.isfinite(estimate) and estimate > 0):
            return math.nan
        return math.exp(self.a + self.b * math.log(estimate))


def adjustment(estimates: Sequence[float], pairs: Sequence[Pair], lambdas: Sequence[float],
               min_pairs: int, group: Callable[[Pair], str] | None = None
               ) -> Adjustment:  # fmt: skip
    """The Colombian adjustment, lambda by leave-one-station-out (identity under the minimum).

    Args:
        estimates: Pretrained estimates of ``pairs``.
        pairs: Colombian training pairs.
        lambdas: Candidate penalties.
        min_pairs: Fewer valid pairs: the identity.
        group: The cross-validation group of a pair (default: its station; v4's single site
            uses its hydrological year).

    Returns:
        The adjustment.
    """
    ok = [(e, p) for e, p in zip(estimates, pairs, strict=True) if math.isfinite(e) and e > 0]
    if len(ok) < min_pairs:
        return Adjustment()
    best: tuple[float, float] | None = None
    key = group or (lambda p: p.station)
    stations = sorted({key(p) for _, p in ok})
    rests = {s: [(e2, p2) for e2, p2 in ok if key(p2) != s] for s in stations}
    for lam in sorted(lambdas, reverse=True):
        fits = {s: fit_adjustment([x for x, _ in r], [q.value for _, q in r], lam)
                for s, r in rests.items() if len(r) >= 2}  # fmt: skip
        oof = []
        for e, p in ok:
            if key(p) not in fits:
                oof.append(math.nan)
                continue
            a, b = fits[key(p)]
            oof.append(math.exp(a + b * math.log(e)))
        score = stats.mdsa(oof, [p.value for _, p in ok])
        if math.isfinite(score) and (best is None or score < best[0]):
            best = (score, lam)
    lam = best[1] if best else max(lambdas)
    a, b = fit_adjustment([e for e, _ in ok], [p.value for _, p in ok], lam)
    return Adjustment(a, b, lam)


def transfer_predictor(pretrained: Callable[[Pair], float], cfg: QualityConfig,
                       group: Callable[[Pair], str] | None = None) -> Predictor:  # fmt: skip
    """A Route A predictor: the pretrained model, adjusted on the Colombian training pairs.

    Args:
        pretrained: The USGS-trained model of one pair.
        cfg: Settings (the adjustment's lambdas and minimum).
        group: The adjustment's cross-validation group (default: the station).

    Returns:
        ``(colombian_train, test) -> estimates``.
    """
    sel = cfg.selection

    def predict(train: Sequence[Pair], test: Sequence[Pair]) -> list[float]:
        adj = adjustment([pretrained(p) for p in train], train, sel.adjustment_lambdas,
                         sel.adjustment_min_pairs, group)  # fmt: skip
        return [adj.apply(pretrained(p)) for p in test]

    return predict


@dataclass
class UsgsInputs:
    """The USGS pilot's pairs per target and window, and each site's river."""

    pairs: dict[tuple[str, str], list[Pair]]  # (target, window) -> pairs
    river_of: dict[str, str]
    forests: dict[tuple[str, str], trees.Forest] = field(default_factory=dict)  # A4, from the lab
    fitted: dict[tuple[str, str, int], dict[str, Pretrained]] = field(
        default_factory=dict, repr=False, compare=False
    )  # pretrained_objects, computed once per target, window and forest


def load_usgs(cfg: QualityConfig, root: Path, folder: str = "usgs",
              sites_file: str = "usgs/sites.csv",
              turbidity_file: str = "turbidity.csv") -> UsgsInputs | None:  # fmt: skip
    """The USGS pilot's pairs (None until its value fetch has run).

    Turbidity pairs join each clear scene with its overpass value; SSC pairs join a sample with a
    scene of the same UTC date at its site.

    Args:
        cfg: Settings.
        root: Repository root.
        folder: The snapshot folder under the inputs (v4's second reach: ``usgs-hermann``).
        sites_file: The site list under the inputs (default: the pilot's; v5 has its own).
        turbidity_file: The overpass values joined as ``turbidity`` (v5's surrogate SSC reuses the
            join with ``ssc-surrogate.csv``).

    Returns:
        The inputs, or None.
    """
    from climate_pipeline.quality.route_a import scenes_from_windows

    base = root / cfg.outputs.inputs / folder
    if not (base / "windows.csv").exists() or not (base / turbidity_file).exists():
        return None
    site_list = root / cfg.outputs.inputs / sites_file
    sites = [r for r in read_stations(site_list) if r["selected"] == "true"]
    widths = {r["site_id"]: number(r["width_m"]) for r in sites}
    text = (base / "windows.csv").read_text(encoding="utf-8")
    windows = features.with_features(
        cfg.features, {w: scenes_from_windows(text, w) for w in ("300m", "core")}, widths
    )
    guards = cfg.window.as_calibration()
    turbidity = list(csv.DictReader(io.StringIO((base / turbidity_file).read_text("utf-8"))))
    ssc_path = base / "ssc.csv"
    ssc = (
        list(csv.DictReader(io.StringIO(ssc_path.read_text("utf-8")))) if ssc_path.exists() else []
    )
    out: dict[tuple[str, str], list[Pair]] = {}
    for window, scenes in windows.items():
        by_key: dict[tuple[str, str], SceneRow] = {(s.station, s.key): s for s in scenes
                                                    if s.usable(guards)}  # fmt: skip
        by_day: dict[tuple[str, str], SceneRow] = {}
        for s in by_key.values():
            by_day.setdefault((s.station, s.key.split("_")[1]), s)
        rows = []
        for t in turbidity:
            value = number(t["value"])
            scene = by_key.get((t["site_id"], t["key"]))
            if scene is not None and math.isfinite(value) and value > 0:
                rows.append(_pair("turbidity", scene, value))
        out[("turbidity", window)] = rows
        rows = []
        for t in ssc:
            value = number(t["value"])
            scene = by_day.get((t["site_id"], t["date"]))
            if scene is not None and math.isfinite(value) and value > 0:
                rows.append(_pair("tss", scene, value))
        out[("tss", window)] = rows
    return UsgsInputs(out, {r["site_id"]: r["river"] for r in sites})


def _pair(target: str, scene: SceneRow, value: float) -> Pair:
    return Pair(target, scene.station, scene.day, scene.key, scene.day, 0, value, False, "",
                scene.family, scene.features, scene.stats)  # fmt: skip


Pretrained = Linear | trees.Forest


def pretrained_objects(cfg: QualityConfig, usgs: UsgsInputs, target: str, window: str
                       ) -> dict[str, Pretrained]:  # fmt: skip
    """A2 and A3 fitted on the USGS pairs of one target and window, and the lab's A4.

    Args:
        cfg: Settings.
        usgs: The USGS inputs.
        target: Target id.
        window: ``300m`` or ``core``.

    Returns:
        Candidate id -> pretrained model (empty under the minimum of USGS pairs).
    """
    key = (target, window, id(usgs.forests.get((target, window))))
    if key not in usgs.fitted:
        usgs.fitted[key] = _pretrained_objects(cfg, usgs, target, window)
    return dict(usgs.fitted[key])


def _pretrained_objects(cfg: QualityConfig, usgs: UsgsInputs, target: str, window: str
                        ) -> dict[str, Pretrained]:  # fmt: skip
    pairs = usgs.pairs.get((target, window), [])

    def river(p: Pair) -> str:
        return usgs.river_of.get(p.station, p.station)

    out: dict[str, Pretrained] = {}
    ratio = usable_rows(pairs, ["log_B8A/B04"])
    if len(ratio) >= cfg.budgets.min_usgs_pairs:
        out["A2"] = fit_linear(ratio, ["log_B8A/B04"], 0.0)
    names = features.names(cfg.features)
    full = usable_rows(pairs, names)
    if len(full) >= cfg.budgets.min_usgs_pairs:
        lam = choose_lambda(full, river, names, cfg.selection.ridge_lambdas)
        out["A3"] = fit_linear(full, names, lam)
    forest = usgs.forests.get((target, window))
    if forest is not None:
        out["A4"] = forest
    return out


def pretrained_models(cfg: QualityConfig, usgs: UsgsInputs, target: str, window: str
                      ) -> dict[str, Callable[[Pair], float]]:  # fmt: skip
    """The pretrained models as predictors of one pair.

    Args:
        cfg: Settings.
        usgs: The USGS inputs.
        target: Target id.
        window: ``300m`` or ``core``.

    Returns:
        Candidate id -> pretrained model of one pair.
    """
    out: dict[str, Callable[[Pair], float]] = {}
    for cid, model in pretrained_objects(cfg, usgs, target, window).items():

        def predict(p: Pair, m: Pretrained = model) -> float:
            return m.predict(p.features)

        out[cid] = predict
    return out
