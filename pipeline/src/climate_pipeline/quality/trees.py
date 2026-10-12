"""A4's gradient-boosted trees, evaluated with numpy from LightGBM's JSON dump.

LightGBM runs only in the separate lab environment (``pipeline/lab``); the pipeline reads the model
it exports (``Booster.dump_model()``) and sums the leaves itself, so ``uv.lock`` never needs
LightGBM. A test checks the evaluator against the lab's own predictions. Only numerical splits
with ``<=`` are supported, which is all a regression on finite features produces.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Forest:
    """A LightGBM regression model on log(target)."""

    feature_names: tuple[str, ...]
    trees: tuple[Mapping[str, Any], ...]

    def log_estimate(self, row: Mapping[str, float]) -> float:
        """The model's raw output for one row (log space).

        Args:
            row: Features.

        Returns:
            The sum of the leaves reached (NaN when a feature is missing).
        """
        x = [row.get(n, math.nan) for n in self.feature_names]
        if not all(math.isfinite(v) for v in x):
            return math.nan
        total = 0.0
        for tree in self.trees:
            node = tree
            while "leaf_value" not in node:
                if node.get("decision_type", "<=") != "<=":
                    raise ValueError(f"unsupported split {node.get('decision_type')}")
                go_left = x[int(node["split_feature"])] <= float(node["threshold"])
                node = node["left_child"] if go_left else node["right_child"]
            total += float(node["leaf_value"])
        return total

    def predict(self, row: Mapping[str, float]) -> float:
        """The estimate for one row.

        Args:
            row: Features.

        Returns:
            exp of the raw output.
        """
        raw = self.log_estimate(row)
        return math.exp(raw) if math.isfinite(raw) else math.nan


def from_dump(dump: Mapping[str, Any]) -> Forest:
    """A forest from LightGBM's ``dump_model()`` dictionary.

    Args:
        dump: The dump.

    Returns:
        The forest.
    """
    names = tuple(str(n) for n in dump["feature_names"])
    trees = tuple(t["tree_structure"] for t in dump["tree_info"])
    return Forest(names, trees)


def load(path: Path) -> Forest | None:
    """The forest saved by the lab (None when absent).

    Args:
        path: The model JSON (``{"model": <dump>, ...}``).

    Returns:
        The forest, or None.
    """
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return from_dump(data["model"])


def check(forest: Forest, rows: Sequence[Mapping[str, float]], expected: Sequence[float]) -> float:
    """The largest absolute difference with the lab's raw predictions.

    Args:
        forest: The forest.
        rows: Feature rows.
        expected: LightGBM's raw (log-space) predictions of those rows.

    Returns:
        The largest difference (about 1e-12 when they agree).
    """
    return max((abs(forest.log_estimate(r) - e) for r, e in zip(rows, expected, strict=True)),
               default=0.0)  # fmt: skip
