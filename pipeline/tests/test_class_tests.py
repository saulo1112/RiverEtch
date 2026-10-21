"""The class tests' counting, on synthetic pairs (the real run reads the committed models once)."""

from __future__ import annotations

from pathlib import Path

import pytest

from climate_pipeline.contract import observation_v2 as v2
from climate_pipeline.quality import class_tests as ct

ROOT = Path(__file__).resolve().parents[2]


def test_the_classes_follow_the_records_edges() -> None:
    assert [ct.klass(v, ct.THREE) for v in (29.9, 30.0, 99.9, 100.0)] == [0, 1, 1, 2]
    assert [ct.klass(v, ct.FOUR) for v in (29.9, 30.0, 49.9, 50.0, 99.9, 100.0)] == [
        0, 1, 1, 2, 2, 3]  # fmt: skip
    # The three classes are the records' own.
    labels = list(v2.FNU_CLASSES)
    for v in (5.0, 30.0, 64.0, 100.0, 420.0):
        assert labels[ct.klass(v, ct.THREE)] == v2.fnu_class(v)


def test_the_most_common_class_and_its_tie() -> None:
    assert ct.mode([40.0, 45.0, 10.0], ct.THREE) == 1
    assert ct.mode([10.0, 40.0], ct.THREE) == 0, "a tie goes to the lower class"


def test_the_exact_one_sided_mcnemar() -> None:
    assert ct.mcnemar_one_sided(5, 0) == pytest.approx(1 / 32)
    assert ct.mcnemar_one_sided(3, 3) == pytest.approx(42 / 64)
    assert ct.mcnemar_one_sided(0, 0) == 1.0


def synthetic() -> ct.Pooled:
    # Two similar sites in two groups; the model is right on A's four pairs, wrong on B's two.
    pairs = [
        ct.Scored("A", "GA", 40.0, 41.0),
        ct.Scored("A", "GA", 60.0, 55.0),
        ct.Scored("A", "GA", 20.0, 25.0),
        ct.Scored("A", "GA", 120.0, 130.0),
        ct.Scored("B", "GB", 45.0, 150.0),
        ct.Scored("B", "GB", 35.0, 10.0),
    ]
    training = {"A": [40.0, 42.0, 60.0], "B": [70.0, 80.0, 20.0], "C": [5.0, 6.0, 7.0]}
    return ct.Pooled(pairs, training, {"A": "GA", "B": "GB", "C": "GC"}, ["A", "B"])


def test_four_classes_counts_the_model_the_baseline_and_the_pass_rule() -> None:
    result = ct.four_classes(None, ROOT, synthetic())  # type: ignore[arg-type]
    pooled = result["summary"]
    # Model classes (30/50/100): A right on all four; B wrong on both.
    assert pooled["model_matched"] == 4
    # A's guess is B's training mode (50 to 100: class 2); B's is A's (30 to 50: class 1).
    by_site = {r["site"]: r for r in result["rows"]}
    assert by_site["A"]["baseline_class"] == 2 and by_site["B"]["baseline_class"] == 1
    assert pooled["baseline_matched"] == 1 + 2  # A: 60; B: 45 and 35
    assert (pooled["model_only"], pooled["baseline_only"]) == (3, 2)
    assert pooled["p_value"] == pytest.approx(ct.mcnemar_one_sided(3, 2))
    assert pooled["passes"] is False
    assert pooled["two_or_more_away"] == 1  # B's 45 read as 150: class 1 against 3
    assert pooled["label"] == "decided after seeing the result"


def test_five_classes_count_the_split_on_its_own_and_pass_only_on_both() -> None:
    assert [ct.klass(v, ct.FIVE) for v in (14.9, 15.0, 29.9, 30.0, 50.0, 100.0)] == [
        0, 1, 1, 2, 3, 4]  # fmt: skip
    labels = list(v2.FNU_CLASSES_FIVE)
    for v in (3.0, 15.0, 29.0, 30.0, 64.0, 100.0):
        assert labels[ct.klass(v, ct.FIVE)] == v2.fnu_class(v, v2.FNU_CLASS_EDGES_FIVE)
    result = ct.five_classes(None, ROOT, synthetic())  # type: ignore[arg-type]
    s = result["summary"]
    # Five classes (15/30/50/100): A right on all four (its 20 read as 25: both 15 to 30); B not.
    assert s["model_matched"] == 4
    # The split: only A's 20 (read as 25) has both under 30; the model says 15 to 30, right. Its
    # baseline: B's training values under 30 (20: 15 to 30), right too, so b = c = 0.
    assert (s["split_n"], s["split_model_matched"], s["split_baseline_matched"]) == (1, 1, 1)
    assert s["split_p_value"] == 1.0
    assert s["passes"] is False, "the split did not beat guessing"
    assert s["alpha"] == pytest.approx(0.05 / 3)
    assert [b["gauge"] for b in result["bins"]] == [0, 1, 3, 1, 1]
    assert [b["estimate"] for b in result["bins"]] == [1, 1, 1, 1, 2]
    assert s["four_class_matched"] == 4


def test_the_three_class_baselines_use_other_rivers_all_rivers_and_the_own_river() -> None:
    result = ct.class_baseline(None, ROOT, synthetic())  # type: ignore[arg-type]
    s = result["summary"]
    assert s["model_matched"] == 4 + 0
    # B1 (the other similar sites): both guess 30 to 100.
    assert s["b1_matched"] == 2 + 2  # A: 40, 60; B: 45, 35
    # B2 (every site not in the group): A from B and C (under 30 wins), B from A and C (under 30).
    assert s["b2_matched"] == 1 + 0
    # B3 (the group's own): A's 30-100, B's 30-100.
    assert s["b3_matched"] == 2 + 2
    assert s["b1_split"] == {"model_only": 2, "b1_only": 2}


def test_a_test_runs_only_against_its_frozen_preregistration(tmp_path: Path) -> None:
    (tmp_path / "docs/ledgers").mkdir(parents=True)
    (tmp_path / "docs/ledgers/frozen-artifacts.jsonl").write_text("", encoding="utf-8")
    prereg = tmp_path / ct.FOUR_PREREGISTRATION
    prereg.parent.mkdir(parents=True)
    prereg.write_text("not frozen\n", encoding="utf-8")
    with pytest.raises(ValueError, match="is not the file frozen"):
        ct.run(None, tmp_path, "four-classes")  # type: ignore[arg-type]
