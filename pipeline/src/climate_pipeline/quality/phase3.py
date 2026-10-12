"""Phase 3: the Landsat 8/9 candidates and sensitivities (preregistration, checkpoint 2).

* **The Landsat set:** L1 (log-log OLS on NIR/red, Colombian Landsat pairs off the Magdalena) and
  L2 (A2's USGS model on Landsat NIR/red, then the Colombian adjustment). Selection is by LORO
  over the Colombian rivers off the Magdalena; the chosen one is evaluated once on the Magdalena
  Landsat pairs, with v2's levels.
* **The pooled sensitivity:** A1 and A2 on Sentinel-2 and Landsat pairs together, with a sensor
  term: log y = alpha + beta log r + gamma [Landsat] (A1), and the adjustment
  log y = a + b log yhat + gamma [Landsat] (A2, ridge toward the identity and no offset).
* **v2.1 with Landsat:** the Magdalena pairs of both sensors, with the sensor term in P1, P2 and
  P5 (P3 and P4 need the red-edge bands), scored by v2.1's nested LOSO.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from climate_pipeline.calibration import stats
from climate_pipeline.calibration.matchups import Pair, SceneRow
from climate_pipeline.quality import features, posthoc, route_a, transfer
from climate_pipeline.quality.config import QualityConfig
from climate_pipeline.quality.route_a import ColombianInputs, Predictor

SENSOR = "sensor_landsat"  # 1 for Landsat, 0 for Sentinel-2
RATIO = "log_B8A/B04"
LAMBDAS = (0.1, 1.0, 10.0)


def load(cfg: QualityConfig, root: Path) -> dict[str, list[SceneRow]] | None:
    """The Landsat windows with the feature set F and the sensor flag (None before the fetch).

    Args:
        cfg: Settings.
        root: Repository root.

    Returns:
        Window -> scenes.
    """
    inputs = root / cfg.outputs.inputs / "landsat"
    path = inputs / "windows.csv"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    scenes = {w: route_a.scenes_from_windows(text, w) for w in ("300m", "core")}
    stations = csv.DictReader(io.StringIO((inputs / "stations.csv").read_text(encoding="utf-8")))
    widths = {r["station_id"]: float(r["width_m"]) for r in stations if r["width_m"]}
    full = features.with_features(cfg.features, scenes, widths)
    return {w: [dataclasses.replace(s, features={**s.features, SENSOR: 1.0}) for s in rows]
            for w, rows in full.items()}  # fmt: skip


def flagged(pairs: Sequence[Pair], value: float) -> list[Pair]:
    """The pairs with the sensor flag set.

    Args:
        pairs: Pairs.
        value: 1 for Landsat, 0 for Sentinel-2.

    Returns:
        Copies with ``sensor_landsat``.
    """
    return [dataclasses.replace(p, features={**p.features, SENSOR: value}) for p in pairs]


def linear(names: Sequence[str], lambdas: Sequence[float] = (0.0,)) -> Predictor:
    """A log-space ridge on ``names`` (lambda by LOSO when several are given).

    Args:
        names: Features.
        lambdas: Penalties.

    Returns:
        The predictor.
    """

    def predict(train: Sequence[Pair], test: Sequence[Pair]) -> list[float]:
        use = transfer.usable_rows(train, names)
        if len(use) < len(names) + 2:
            return [math.nan] * len(test)
        lam = (transfer.choose_lambda(use, posthoc.station, names, lambdas) if len(lambdas) > 1
               else lambdas[0])  # fmt: skip
        model = transfer.fit_linear(use, names, lam)
        return [model.predict(p.features) for p in test]

    return predict


def fit_sensor_adjustment(
    estimates: Sequence[float], observed: Sequence[float], sensors: Sequence[float], lam: float,
) -> tuple[float, float, float]:  # fmt: skip
    """The adjustment log y = a + b log yhat + gamma s, a ridge on (a, b - 1, gamma).

    Args:
        estimates: Pretrained estimates.
        observed: Measured values.
        sensors: 1 for Landsat, 0 for Sentinel-2.
        lam: Penalty.

    Returns:
        ``(a, b, gamma)``.
    """
    x = np.log(np.asarray(estimates, dtype=np.float64))
    z = np.log(np.asarray(observed, dtype=np.float64)) - x
    design = np.column_stack([np.ones_like(x), x, np.asarray(sensors, dtype=np.float64)])
    coef = np.linalg.solve(design.T @ design + lam * np.eye(3), design.T @ z)
    return float(coef[0]), float(1 + coef[1]), float(coef[2])


def sensor_adjusted(pretrained: Callable[[Pair], float]) -> Predictor:
    """A pretrained model with the adjustment and sensor term, lambda by LOSO.

    Args:
        pretrained: The USGS model of one pair.

    Returns:
        The predictor.
    """

    def apply(coef: tuple[float, float, float], e: float, s: float) -> float:
        return (math.exp(coef[0] + coef[1] * math.log(e) + coef[2] * s)
                if math.isfinite(e) and e > 0 else math.nan)  # fmt: skip

    def predict(train: Sequence[Pair], test: Sequence[Pair]) -> list[float]:
        ok = [(pretrained(p), p) for p in train]
        ok = [(e, p) for e, p in ok if math.isfinite(e) and e > 0]
        if len(ok) < 10:
            return [math.nan] * len(test)
        best: tuple[float, float] | None = None
        for lam in sorted(LAMBDAS, reverse=True):
            oof = []
            for e, p in ok:
                rest = [(e2, p2) for e2, p2 in ok if p2.station != p.station]
                flags = [q.features.get(SENSOR, 0.0) for _, q in rest]
                coef = fit_sensor_adjustment([x for x, _ in rest], [q.value for _, q in rest],
                                             flags, lam)  # fmt: skip
                oof.append(apply(coef, e, p.features.get(SENSOR, 0.0)))
            score = stats.mdsa(oof, [p.value for _, p in ok])
            if math.isfinite(score) and (best is None or score < best[0]):
                best = (score, lam)
        lam = best[1] if best else max(LAMBDAS)
        coef = fit_sensor_adjustment([e for e, _ in ok], [p.value for _, p in ok],
                                     [p.features.get(SENSOR, 0.0) for _, p in ok], lam)  # fmt: skip
        return [apply(coef, pretrained(p), p.features.get(SENSOR, 0.0)) for p in test]

    return predict


def summary(tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """The Landsat set's test and v2.1 with Landsat, per target (primary or stable pairs).

    Args:
        tables: The run's tables.

    Returns:
        Target -> ``test`` (candidate, level, mdsa, n) and ``v21_with_landsat`` (mdsa, level, n).
    """
    out: dict[str, Any] = {}
    for r in tables.get("landsat_scores", []):
        if "mdsa" not in r:
            continue
        entry = out.setdefault(r["target"], {})
        if (
            r["set"] == "landsat"
            and r["variant"] == "primary"
            and r["evaluation"].startswith("test")
        ):
            entry["test"] = {"candidate": r["candidate"], "level": r["level"],
                             "mdsa": round(r["mdsa"], 1), "n": int(r["n"])}  # fmt: skip
        if r["set"].startswith("v2.1"):
            lv = f"{r['level']} (post hoc)" if r["level"] != "none" else "none"
            entry["v21_with_landsat"] = {"level": lv, "mdsa": round(r["mdsa"], 1),
                                         "n": int(r["n"])}  # fmt: skip
    return out


def analyse(cfg: QualityConfig, ci: ColombianInputs, scenes: dict[str, list[SceneRow]],
            adjacency_confirmed: bool,
            usgs: transfer.UsgsInputs | None) -> dict[str, list[dict[str, Any]]]:  # fmt: skip
    """Every Phase 3 table.

    Args:
        cfg: Settings.
        ci: The Colombian (Sentinel-2) inputs.
        scenes: The Landsat windows.
        adjacency_confirmed: Route B's rule (the core window is primary).
        usgs: The USGS inputs (A2's model).

    Returns:
        ``landsat_counts``, ``landsat_scores`` and ``landsat_levels``.
    """
    from climate_pipeline.quality.route_b import _seed

    window = "core" if adjacency_confirmed else "300m"
    test_stream = cfg.stations.test_stream
    landsat_ci = dataclasses.replace(ci, scenes=scenes)
    tables: dict[str, list[dict[str, Any]]] = {
        "landsat_counts": [],
        "landsat_scores": [],
        "landsat_levels": [],
    }

    def stream(p: Pair) -> str:
        return ci.stream_of.get(p.station, p.station)

    for target in cfg.targets:
        pretrained = transfer.pretrained_models(cfg, usgs, target.id, window) if usgs else {}
        for variant, wide in (("primary", False), ("stable +-3 days", True)):
            lp = route_a.pairs(cfg, landsat_ci, target.id, window, wide)
            sp = flagged(route_a.pairs(cfg, ci, target.id, window, wide), 0.0)
            ltrain = [p for p in lp if stream(p) != test_stream]
            ltest = [p for p in lp if stream(p) == test_stream]
            strain = [p for p in sp if stream(p) != test_stream]
            stest = [p for p in sp if stream(p) == test_stream]
            seed = _seed(cfg.seed, "landsat", target.id, variant)
            base = {"target": target.id, "variant": variant, "window": window}
            tables["landsat_counts"].append({
                **base, "landsat_training_pairs": len(ltrain),
                "landsat_training_streams": len({stream(p) for p in ltrain}),
                "landsat_test_pairs": len(ltest),
                "landsat_test_stations": len({p.station for p in ltest}),
            })  # fmt: skip
            sets: dict[str, dict[str, Predictor]] = {
                "landsat": {"L1": route_a.a1},
                "pooled (sensor term)": {"A1+s": linear([RATIO, SENSOR])},
            }
            if "A2" in pretrained:
                sets["landsat"]["L2"] = transfer.transfer_predictor(pretrained["A2"], cfg)
                sets["pooled (sensor term)"]["A2+s"] = sensor_adjusted(pretrained["A2"])
            for name, options in sets.items():
                train, test = ((ltrain, ltest) if name == "landsat"
                               else ([*strain, *ltrain], [*stest, *ltest]))  # fmt: skip
                if len({stream(p) for p in train}) < 2 or len(test) < cfg.levels.min_test_pairs:
                    tables["landsat_scores"].append({**base, "set": name,
                                                     "status": "insufficient_data"})  # fmt: skip
                    continue
                values = [p.value for p in train]
                oof_null = route_a.leave_one_group_out(train, stream, route_a.null)
                loro = {}
                quantiles = {}
                for cid, f in options.items():
                    oof = route_a.leave_one_group_out(train, stream, f)
                    quantiles[cid] = route_a.conformal(oof, values, cfg.intervals.coverages)
                    loro[cid] = route_a.evaluate(cfg, train, oof, oof_null, quantiles[cid], seed)
                    tables["landsat_scores"].append({**base, "set": name, "candidate": cid,
                                                     "evaluation": "leave-one-river-out",
                                                     **loro[cid]})  # fmt: skip
                order = list(options)
                finite = {c: m["mdsa"] for c, m in loro.items() if math.isfinite(m["mdsa"])}
                chosen = (next(c for c in order if c in finite and finite[c]
                               <= min(finite.values()) + cfg.selection.simpler_within_mdsa)
                          if finite else order[0])  # fmt: skip
                est = options[chosen](train, test)
                nul = route_a.null(train, test)
                m = route_a.evaluate(cfg, test, est, nul, quantiles[chosen], seed + 1)
                lv = route_a.level(m, cfg) if name == "landsat" and variant == "primary" else ""
                tables["landsat_scores"].append({**base, "set": name, "candidate": chosen,
                                                 "evaluation": "test (Magdalena)", **m,
                                                 "level": lv})  # fmt: skip
                if lv:
                    tables["landsat_levels"] += route_a.bin_rows(
                        cfg, target, chosen, test, est, nul, quantiles[chosen], lv
                    )
            if variant == "stable +-3 days":
                pool = [*stest, *ltest]
                options = {"P1": linear([RATIO, SENSOR])}
                if "A2" in pretrained:
                    options["P2"] = sensor_adjusted(pretrained["A2"])
                options["P5"] = linear([*posthoc.P5_FEATURES, SENSOR], posthoc.P5_LAMBDAS)
                if len({p.station for p in pool}) >= 3:
                    result = posthoc.nested(cfg, pool, options, order=list(options))
                    m = posthoc.metrics(cfg, pool, result, list(range(len(pool))), seed + 5)
                    rows = posthoc.level_rows(cfg, target, pool, result, seed + 5)
                    tables["landsat_scores"].append({
                        **base, "set": "v2.1 with Landsat (sensor term)",
                        "candidate": "nested selection", "evaluation": "nested LOSO (post hoc)",
                        **m, "level": rows[0]["level"],
                    })  # fmt: skip
    return tables
