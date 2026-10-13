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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# A compiled tree: per node (feature, threshold, left, right); a leaf is (-1, value, -1, -1).
Compiled = tuple[tuple[int, float, int, int], ...]


def _compile(tree: Mapping[str, Any]) -> Compiled:
    nodes: list[tuple[int, float, int, int]] = []

    def visit(node: Mapping[str, Any]) -> int:
        k = len(nodes)
        if "leaf_value" in node:
            nodes.append((-1, float(node["leaf_value"]), -1, -1))
            return k
        if node.get("decision_type", "<=") != "<=":
            raise ValueError(f"unsupported split {node.get('decision_type')}")
        nodes.append((0, 0.0, 0, 0))
        left = visit(node["left_child"])
        right = visit(node["right_child"])
        nodes[k] = (int(node["split_feature"]), float(node["threshold"]), left, right)
        return k

    visit(tree)
    return tuple(nodes)


@dataclass(frozen=True)
class Forest:
    """A LightGBM regression model on log(target).

    The trees are compiled to flat tuples once, and each distinct feature row is evaluated once
    (the same leaves are summed in the same order, so the result is unchanged).
    """

    feature_names: tuple[str, ...]
    trees: tuple[Mapping[str, Any], ...]
    _compiled: tuple[Compiled, ...] = field(init=False, repr=False, compare=False)
    _memo: dict[tuple[float, ...], float] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        """Compile the trees (a frozen dataclass sets the field through ``object``)."""
        object.__setattr__(self, "_compiled", tuple(_compile(t) for t in self.trees))

    def log_estimate(self, row: Mapping[str, float]) -> float:
        """The model's raw output for one row (log space).

        Args:
            row: Features.

        Returns:
            The sum of the leaves reached (NaN when a feature is missing).
        """
        x = tuple(row.get(n, math.nan) for n in self.feature_names)
        if not all(math.isfinite(v) for v in x):
            return math.nan
        cached = self._memo.get(x)
        if cached is not None:
            return cached
        total = 0.0
        for nodes in self._compiled:
            feature, value, left, right = nodes[0]
            while feature >= 0:
                feature, value, left, right = nodes[left if x[feature] <= value else right]
            total += value
        self._memo[x] = total
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
