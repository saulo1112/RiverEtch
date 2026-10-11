"""A4 of the water-quality validation v2: LightGBM on the feature set F, in its own environment.

Run it with the lab's environment, never the pipeline's (README.md), from ``pipeline/lab``::

    uv run python train_gbm.py ../out/lab

For each ``<target>-<window>.csv`` that ``climate-pipeline quality export-lab`` wrote, with its
``.json`` spec (feature names, grid, seed), it chooses the configuration with the lowest
leave-one-river-out MdSA over the USGS rivers (ties: the smaller model), fits it on every pair,
and writes ``docs/water-quality/inputs/lab/gbm-<target>-<window>.json``: the LightGBM dump, the
choice, the out-of-river scores and the raw predictions of the first rows (the pipeline's numpy
evaluator is checked against them). Training is deterministic: one thread and the fixed seed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import sys
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np

CHECK_ROWS = 25


def mdsa(predicted: np.ndarray, observed: np.ndarray) -> float:
    """Median symmetric accuracy, percent (as the pipeline's ``stats.mdsa``).

    Args:
        predicted: Estimates (positive).
        observed: Measured values (positive).

    Returns:
        MdSA in percent.
    """
    q = np.log(predicted / observed)
    return float(100 * (math.exp(float(np.median(np.abs(q)))) - 1))


def fit(x: np.ndarray, y: np.ndarray, config: dict[str, Any], seed: int) -> lgb.Booster:
    """One deterministic LightGBM regression on log(target).

    Args:
        x: Features.
        y: log(target).
        config: ``num_leaves``, ``min_data_in_leaf``, ``n_estimators``, ``learning_rate``.
        seed: Seed.

    Returns:
        The booster.
    """
    params = {
        "objective": "regression", "num_leaves": config["num_leaves"],
        "min_data_in_leaf": config["min_data_in_leaf"], "learning_rate": config["learning_rate"],
        "num_threads": 1, "deterministic": True, "force_row_wise": True, "seed": seed,
        "verbosity": -1,
    }  # fmt: skip
    data = lgb.Dataset(x, label=y, free_raw_data=False)
    return lgb.train(params, data, num_boost_round=config["n_estimators"])


def train_one(table: Path, out: Path) -> dict[str, Any]:
    """Choose, fit and export the model of one target and window.

    Args:
        table: ``<target>-<window>.csv`` (``group``, ``value`` and the features).
        out: Output folder.

    Returns:
        A short summary.
    """
    spec = json.loads(table.with_suffix(".json").read_text(encoding="utf-8"))
    names = spec["features"]
    with table.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    x = np.array([[float(r[n]) for n in names] for r in rows])
    y = np.log(np.array([float(r["value"]) for r in rows]))
    groups = np.array([r["group"] for r in rows])
    grid = spec["grid"]
    configs = [
        {"num_leaves": a, "min_data_in_leaf": b, "n_estimators": c,
         "learning_rate": grid["learning_rate"]}
        for a, b, c in itertools.product(sorted(grid["num_leaves"]),
                                         sorted(grid["min_data_in_leaf"], reverse=True),
                                         sorted(grid["n_estimators"]))
    ]  # fmt: skip
    scores = []
    for config in configs:
        oof = np.full(len(y), np.nan)
        for g in sorted(set(groups)):
            held = groups == g
            if (~held).sum() < config["min_data_in_leaf"]:
                continue
            booster = fit(x[~held], y[~held], config, spec["seed"])
            oof[held] = booster.predict(x[held])
        ok = np.isfinite(oof)
        score = mdsa(np.exp(oof[ok]), np.exp(y[ok])) if ok.any() else math.inf
        scores.append({**config, "loro_mdsa": round(score, 4), "n": int(ok.sum())})
    best = min(range(len(configs)), key=lambda k: (scores[k]["loro_mdsa"], k))
    booster = fit(x, y, configs[best], spec["seed"])
    dump = booster.dump_model()
    dump["feature_names"] = names
    result = {
        "target": spec["target"], "window": spec["window"], "features": names,
        "chosen": configs[best], "scores": scores, "n_train": len(y),
        "table_sha256": hashlib.sha256(table.read_bytes()).hexdigest(),
        "lightgbm": lgb.__version__, "seed": spec["seed"],
        "check": {"rows": [dict(zip(names, map(float, x[k]), strict=True))
                           for k in range(min(CHECK_ROWS, len(y)))],
                  "raw": [float(v) for v in booster.predict(x[:CHECK_ROWS])]},
        "model": dump,
    }  # fmt: skip
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"gbm-{spec['target']}-{spec['window']}.json"
    path.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"file": path.name, "chosen": configs[best], "loro_mdsa": scores[best]["loro_mdsa"]}


def main() -> int:
    """Train every exported table.

    Returns:
        The exit code.
    """
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("tables", type=Path, help="folder written by quality export-lab")
    parser.add_argument("--out", type=Path,
                        default=here.parent.parent / "docs/water-quality/inputs/lab")  # fmt: skip
    args = parser.parse_args()
    tables = sorted(args.tables.glob("*.csv"))
    if not tables:
        print(f"no tables in {args.tables}")
        return 1
    for table in tables:
        print(json.dumps(train_one(table, args.out)), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
