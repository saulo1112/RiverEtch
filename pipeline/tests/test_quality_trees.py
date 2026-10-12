import json
import math
from pathlib import Path

import pytest

from climate_pipeline.quality import trees

FIXTURE = Path(__file__).parent / "fixtures" / "gbm-synthetic.json"


def test_the_numpy_evaluator_reproduces_lightgbm() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    forest = trees.from_dump(data["model"])
    assert forest.feature_names == ("a", "b", "c") and len(forest.trees) == 15
    assert trees.check(forest, data["check"]["rows"], data["check"]["raw"]) < 1e-9
    row = data["check"]["rows"][0]
    assert math.isclose(forest.predict(row), math.exp(data["check"]["raw"][0]), rel_tol=1e-9)
    assert math.isnan(forest.predict({"a": 1.0}))


def test_load_reads_the_lab_file(tmp_path: Path) -> None:
    assert trees.load(tmp_path / "missing.json") is None
    forest = trees.load(FIXTURE)
    assert forest is not None and len(forest.trees) == 15


def test_unsupported_splits_are_refused() -> None:
    leaf = {"leaf_value": 1.0}
    with pytest.raises(ValueError, match="unsupported split"):
        trees.Forest(("a",), ({"decision_type": "==", "split_feature": 0, "threshold": 1.0,
                               "left_child": leaf, "right_child": leaf},))  # fmt: skip


def _walk(forest: trees.Forest, row: dict[str, float]) -> float:
    x = [row[n] for n in forest.feature_names]
    total = 0.0
    for node in forest.trees:
        while "leaf_value" not in node:
            go_left = x[int(node["split_feature"])] <= float(node["threshold"])
            node = node["left_child"] if go_left else node["right_child"]
        total += float(node["leaf_value"])
    return total


def test_the_compiled_trees_give_the_dict_walk_bit_for_bit() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    forest = trees.from_dump(data["model"])
    for row in data["check"]["rows"]:
        assert forest.log_estimate(row) == _walk(forest, row)
        assert forest.log_estimate(dict(row)) == _walk(forest, row)  # the memo, again
