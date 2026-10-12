import math
from datetime import date
from pathlib import Path

import numpy as np

from climate_pipeline.calibration.matchups import Pair
from climate_pipeline.quality import features, transfer
from climate_pipeline.quality.config import load_quality_config

PIPELINE = Path(__file__).parents[1]
CFG = load_quality_config(PIPELINE / "water-quality.yaml")


def pair(station: str, value: float, **f: float) -> Pair:
    return Pair("turbidity", station, date(2020, 1, 1), f"k{station}{value}", date(2020, 1, 1), 0,
                value, False, "", "05.xx", f, {})  # fmt: skip


def test_feature_set_f_has_the_preregistered_names_and_values() -> None:
    names = features.names(CFG.features)
    assert len(names) == 19 and names[0] == "log_B02" and "log_B8A/B04" in names
    bands = {"B02": 0.02, "B03": 0.04, "B04": 0.08, "B05": 0.09, "B06": 0.08, "B07": 0.08,
             "B08": 0.07, "B8A": 0.06, "B11": 0.01, "B12": 0.005}  # fmt: skip
    f = features.compute(CFG.features, bands, 30.0, 400.0, 0.5)
    assert math.isclose(f["log_B8A/B04"], math.log(0.75))
    assert math.isclose(f["B8A-B11"], 0.05) and f["core_share"] == 0.5
    assert math.isclose(f["log_width_m"], math.log(400.0)) and f["sun_zenith"] == 30.0
    assert f["log_B02"] == math.log(0.02)
    assert features.compute(CFG.features, {**bands, "B8A": -0.1}, 30, 400, 0.5)["log_B8A"] == (
        math.log(CFG.features.floor))  # fmt: skip


def test_linear_fit_recovers_a_power_law() -> None:
    rng = np.random.default_rng(0)
    train = [pair(str(k), float(500 * r**2), x=float(math.log(r)))
             for k, r in enumerate(rng.uniform(0.2, 1.5, 60))]  # fmt: skip
    model = transfer.fit_linear(train, ["x"], 0.0)
    assert math.isclose(model.predict({"x": math.log(1.0)}), 500.0, rel_tol=1e-6)
    assert math.isnan(model.predict({"y": 1.0}))
    assert model.predict_pair(train[0]) == model.predict(train[0].features)


def test_the_adjustment_shrinks_toward_the_identity() -> None:
    est = [10.0, 100.0, 1000.0]
    obs = [20.0, 200.0, 2000.0]  # twice the estimate
    a, b = transfer.fit_adjustment(est, obs, 0.0)
    assert math.isclose(a, math.log(2), abs_tol=1e-9) and math.isclose(b, 1.0, abs_tol=1e-9)
    a_shrunk, _ = transfer.fit_adjustment(est, obs, 1000.0)
    assert 0 < a_shrunk < a
    assert transfer.adjustment(est, [pair("s", v) for v in obs], [0.1], 10) == transfer.Adjustment()


def test_a_pretrained_model_is_adjusted_to_colombian_units() -> None:
    def pretrained(p: Pair) -> float:
        return p.features["fnu"]

    train = [pair(f"s{k % 5}", 1.6 * v, fnu=v) for k, v in enumerate(np.geomspace(20, 900, 15))]
    test = [pair("t", 1.6 * 300.0, fnu=300.0)]
    predict = transfer.transfer_predictor(pretrained, CFG)
    assert math.isclose(predict(train, test)[0], 480.0, rel_tol=0.05)
    assert math.isnan(transfer.Adjustment().apply(-1.0))


def test_lambda_choice_prefers_the_lower_out_of_river_error() -> None:
    rng = np.random.default_rng(1)
    rows = []
    for k in range(80):
        x, noise = rng.normal(), rng.normal(size=5)
        rows.append(pair(f"r{k % 4}", float(math.exp(1 + 0.8 * x)), x=float(x),
                         **{f"n{i}": float(v) for i, v in enumerate(noise)}))  # fmt: skip
    names = ["x", *(f"n{i}" for i in range(5))]
    lam = transfer.choose_lambda(rows, lambda p: p.station, names, [0.01, 1000.0])
    assert lam == 0.01
