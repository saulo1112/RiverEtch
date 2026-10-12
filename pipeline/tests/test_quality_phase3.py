import math
from datetime import date

import numpy as np

from climate_pipeline.calibration.matchups import Pair
from climate_pipeline.quality import phase3


def pair(station: str, value: float, **f: float) -> Pair:
    return Pair("turbidity", station, date(2020, 1, 1), f"k{station}{value}", date(2020, 1, 1), 0,
                value, False, "", "05.xx", f, {})  # fmt: skip


def test_the_sensor_adjustment_recovers_an_offset_between_sensors() -> None:
    rng = np.random.default_rng(2)
    est = np.exp(rng.uniform(2, 6, 60))
    sensor = (np.arange(60) % 2).astype(float)
    obs = np.exp(0.3 + 0.9 * np.log(est) + 0.5 * sensor)
    a, b, gamma = phase3.fit_sensor_adjustment(list(est), list(obs), list(sensor), 1e-9)
    assert math.isclose(a, 0.3, abs_tol=1e-6) and math.isclose(b, 0.9, abs_tol=1e-6)
    assert math.isclose(gamma, 0.5, abs_tol=1e-6)


def test_a_pooled_model_learns_the_sensor_term() -> None:
    train = []
    for k, r in enumerate(np.geomspace(0.2, 1.5, 40)):
        s = float(k % 2)
        value = float(300 * r**2 * math.exp(0.4 * s))
        train.append(pair(f"s{k % 5}", value, **{"log_B8A/B04": math.log(r),
                                                  phase3.SENSOR: s}))  # fmt: skip
    predict = phase3.linear([phase3.RATIO, phase3.SENSOR])
    landsat, sentinel = predict(train, [pair("t", 1.0, **{"log_B8A/B04": 0.0, phase3.SENSOR: 1.0}),
                                        pair("t", 1.0, **{"log_B8A/B04": 0.0,
                                                          phase3.SENSOR: 0.0})])  # fmt: skip
    assert math.isclose(sentinel, 300.0, rel_tol=1e-6)
    assert math.isclose(landsat / sentinel, math.exp(0.4), rel_tol=1e-6)


def test_pairs_get_the_sensor_flag() -> None:
    (flagged,) = phase3.flagged([pair("s", 1.0, x=1.0)], 0.0)
    assert flagged.features == {"x": 1.0, phase3.SENSOR: 0.0}
