"""The bridge to the lab environment (``pipeline/lab``), where A4's LightGBM is trained.

``export`` writes, per target and window, the USGS pairs with the feature set F and a spec (feature
names, the preregistered grid, the seed): the lab needs neither the pipeline nor its settings.
``forests`` reads the models the lab saved under the inputs and checks the numpy evaluator against
the lab's own predictions before A4 may use them.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from climate_pipeline.quality import features, transfer, trees
from climate_pipeline.quality.config import QualityConfig

WINDOWS = ("300m", "core")
TOLERANCE = 1e-6  # log units: the evaluator must reproduce LightGBM's raw output


def export(cfg: QualityConfig, usgs: transfer.UsgsInputs, out: Path,
           only: set[tuple[str, str]] | None = None) -> list[Path]:  # fmt: skip
    """The lab's training tables and specs.

    Args:
        cfg: Settings.
        usgs: The USGS pilot's pairs.
        out: Folder (e.g. ``pipeline/out/lab``).
        only: Some (target, window) tables (v4 and v5's site cards need the core window).

    Returns:
        The tables written.
    """
    names = features.names(cfg.features)
    gbm = cfg.selection.gbm
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for target in cfg.targets:
        for window in WINDOWS:
            if only is not None and (target.id, window) not in only:
                continue
            rows = transfer.usable_rows(usgs.pairs.get((target.id, window), []), names)
            if len(rows) < cfg.budgets.min_usgs_pairs:
                continue
            path = out / f"{target.id}-{window}.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(["group", "value", *names])
                for p in rows:
                    writer.writerow([usgs.river_of.get(p.station, p.station), repr(p.value),
                                     *(repr(p.features[n]) for n in names)])  # fmt: skip
            spec = {"target": target.id, "window": window, "features": names, "seed": cfg.seed,
                    "grid": {"num_leaves": list(gbm.num_leaves),
                             "min_data_in_leaf": list(gbm.min_data_in_leaf),
                             "n_estimators": list(gbm.n_estimators),
                             "learning_rate": gbm.learning_rate}}  # fmt: skip
            path.with_suffix(".json").write_text(json.dumps(spec, indent=1) + "\n",
                                                 encoding="utf-8")  # fmt: skip
            written.append(path)
    return written


def forests(cfg: QualityConfig, root: Path) -> dict[tuple[str, str], trees.Forest]:
    """The lab's models that pass the evaluator check.

    Args:
        cfg: Settings.
        root: Repository root.

    Returns:
        (target, window) -> forest.

    Raises:
        ValueError: When the numpy evaluator disagrees with the lab's predictions.
    """
    out: dict[tuple[str, str], trees.Forest] = {}
    base = root / cfg.outputs.inputs / "lab"
    for target in cfg.targets:
        for window in WINDOWS:
            path = base / f"gbm-{target.id}-{window}.json"
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            forest = trees.from_dump(data["model"])
            gap = trees.check(forest, data["check"]["rows"], data["check"]["raw"])
            if gap > TOLERANCE:
                raise ValueError(f"{path.name}: the evaluator differs from LightGBM by {gap:g}")
            out[(target.id, window)] = forest
    return out
