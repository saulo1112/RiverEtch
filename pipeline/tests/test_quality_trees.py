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
    forest = trees.Forest(("a",), ({"decision_type": "==", "split_feature": 0, "threshold": 1.0,
                                    "left_child": leaf, "right_child": leaf},))  # fmt: skip
    with pytest.raises(ValueError, match="unsupported split"):
        forest.log_estimate({"a": 0.0})
