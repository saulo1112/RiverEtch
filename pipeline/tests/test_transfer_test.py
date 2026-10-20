"""The test on rivers the model never saw (preregistration-transfer.md), on synthetic pairs: the
folds, what each fold may train on, the preregistered interval and classes, the pooled display
rule, and the outputs. The real run reads the lock boxes once; these tests never do."""

import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from climate_pipeline.calibration.matchups import Pair
from climate_pipeline.quality import route_a
from climate_pipeline.quality import transfer_test as t
from climate_pipeline.quality.config import load_quality_config

CFG = load_quality_config(Path(__file__).parents[1] / "water-quality.yaml")


def pair(station: str, day: date, value: float) -> Pair:
    return Pair("turbidity", station, day, f"s_{station}_{day}", day, 0, value, False, "", "",
                {"f": 1.0}, {})  # fmt: skip


def data() -> t.Data:
    pairs = []
    for station in ("A1", "A2", "B1"):
        for k in range(40):
            pairs.append(pair(station, date(2019, 1, 1) + timedelta(days=30 * k), 10.0 + k))
            pairs.append(pair(station, date(2024, 1, 1) + timedelta(days=15 * k), 20.0 + k))
    return t.Data(pairs, {"A1": "ALPHA", "A2": "ALPHA", "B1": "BETA"}, ["f"])


def test_the_folds_are_the_nine_groups_two_joined_pairs_and_all() -> None:
    folds = t.folds()
    assert [f.name for f in folds[:9]] == ["atchafalaya", "columbia", "connecticut", "mississippi",
                                           "missouri", "ohio", "platte", "san-joaquin",
                                           "willamette"]  # fmt: skip
    assert [(f.name, f.report_only) for f in folds[9:11]] == [
        ("mississippi-atchafalaya", True), ("columbia-willamette", True)]  # fmt: skip
    assert folds[-1] == t.Fold("all", ())


def test_a_fold_trains_on_other_groups_training_years_only() -> None:
    d = data()
    rows = d.training(("ALPHA",))
    assert {p.station for p in rows} == {"B1"}
    assert all(p.sample_day <= date(2023, 11, 30) for p in rows)
    assert len(d.training()) == 3 * len([p for p in d.pairs if p.station == "A1"
                                         and p.sample_day < date(2023, 12, 1)])  # fmt: skip


def test_the_interval_is_one_pooled_90th_percentile() -> None:
    m = t.Model(forest=None, q90=math.log(2.0), chosen={}, n_train=10)  # type: ignore[arg-type]
    q = m.quantiles()
    assert q.interval(10.0, 0.9) == pytest.approx((5.0, 20.0))
    assert q.interval(1000.0, 0.9) == pytest.approx((500.0, 2000.0))  # no terciles
    assert route_a.covered(q, [10.0, 10.0, 10.0], [20.0, 20.1, 4.9], 0.9) == pytest.approx(1 / 3)


def test_the_classes_are_under_30_30_to_100_and_100_and_over() -> None:
    assert [t._class(v) for v in (29.9, 30.0, 99.9, 100.0)] == [0, 1, 1, 2]


def test_the_pooled_result_decides_what_the_ungauged_reach_shows() -> None:
    pairs = [pair("S", date(2024, 1, 1) + timedelta(days=k), 10.0 * (k + 1)) for k in range(30)]
    good = [(p, p.value * 1.1, math.log(1.5)) for p in pairs]  # ranks preserved: indicative
    out = t._pooled(CFG, good, ["S"], {"S": 40.0})
    assert out["n"] == 30 and out["coverage90_inside"] == 30 and out["ungauged_shows_class"]
    assert out["ungauged_display"].startswith("class")
    noise = [(p, 50.0 + (17 * k % 30), math.log(1.5)) for k, p in enumerate(pairs)]  # no order
    assert not t._pooled(CFG, noise, ["S"], {"S": 40.0})["ungauged_shows_class"]


def test_the_outputs_and_their_manifest(tmp_path: Path) -> None:
    root = tmp_path
    (root / t.PREREGISTRATION).parent.mkdir(parents=True)
    (root / t.PREREGISTRATION).write_bytes(b"# preregistration\n")
    for fold in t.folds():
        (root / t.MODELS / fold.name).mkdir(parents=True)
        (root / t.MODELS / fold.name / t.MODEL_FILE).write_bytes(b"{}")
    row: dict[str, Any] = {"fold": "platte", "report_only": False, "site": "S", "group": "PLATTE",
                           "candidate": "A4", "n": 30.0, "mdsa": 33.3333, "sspb": -1.0,
                           "rho_low": 0.5, "null_mdsa": 60.0, "no_local_data_mdsa": 80.0,
                           "coverage90": 0.9, "interval_factor90": 2.0, "class_agreement": 20,
                           "level": "estimated"}  # fmt: skip
    pooled = t._pooled(CFG, [(pair("S", date(2024, 1, k + 1), 10.0 * (k + 1)), 10.0 * (k + 1),
                              0.5) for k in range(25)], ["S"], {"S": 40.0})  # fmt: skip
    fold_row = {"fold": "platte", "held_out": "PLATTE", "q90": 0.69}
    written = t.write({"scores": [row], "levels": [row], "folds": [fold_row], "pooled": pooled},
                      root, root / t.RESULTS)  # fmt: skip
    assert [p.name for p in written][-1] == "MANIFEST"
    manifest = (root / t.RESULTS / "MANIFEST").read_text(encoding="utf-8").splitlines()
    assert len(manifest) == 6 and all(len(line.split("  ")[0]) == 64 for line in manifest)
    assert "33.3333" in (root / t.RESULTS / "transfer_scores.csv").read_text(encoding="utf-8")
    page = (root / t.RESULTS / "transfer.md").read_text(encoding="utf-8")
    assert "run once" in page.replace("\n", " ") and "class agreement: 25 of 25" in page
    provenance = json.loads((root / t.RESULTS / "provenance.json").read_text(encoding="utf-8"))
    assert set(provenance["models_sha256"]) == {f.name for f in t.folds()}


def test_quality_run_keeps_the_transfer_results(tmp_path: Path) -> None:
    from climate_pipeline.quality.report import fresh

    out = tmp_path / "results"
    (out / "transfer").mkdir(parents=True)
    (out / "transfer" / "MANIFEST").write_text("kept\n", encoding="utf-8")
    (out / "v5_levels.csv").write_text("old\n", encoding="utf-8")
    fresh(out)
    assert sorted(p.name for p in out.iterdir()) == ["transfer"]
    assert (out / "transfer" / "MANIFEST").read_text(encoding="utf-8") == "kept\n"
    fresh(tmp_path / "new")  # a missing folder is created
    assert (tmp_path / "new").is_dir()


def test_the_records_classes_are_the_tests() -> None:
    from climate_pipeline.contract import observation_v2 as v2

    assert v2.FNU_CLASS_EDGES == t.CLASS_EDGES
    assert [v2.fnu_class(v) for v in (29.9, 30.0, 99.9, 100.0)] == [
        "under_30", "30_to_100", "30_to_100", "100_and_over"]  # fmt: skip
    assert v2.fnu_class(math.nan) is None and v2.fnu_class(0.0) is None


def test_the_ungauged_card_is_never_replaced_by_a_different_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from climate_pipeline.quality import ungauged

    monkeypatch.setattr(ungauged, "card", lambda cfg, root, reach=ungauged.REACH: {"a": 1})
    path = ungauged.write(CFG, tmp_path)
    assert ungauged.verify(CFG, tmp_path) == [] and ungauged.write(CFG, tmp_path) == path
    monkeypatch.setattr(ungauged, "card", lambda cfg, root, reach=ungauged.REACH: {"a": 2})
    with pytest.raises(FileExistsError, match="never replaced"):
        ungauged.write(CFG, tmp_path)
    assert ungauged.verify(CFG, tmp_path) == [
        "docs/water-quality/ungauged/mississippi-st-joseph/turbidity.json: differs from its "
        "recomputation"]  # fmt: skip
