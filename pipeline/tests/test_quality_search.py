import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from climate_pipeline.calibration.matchups import Pair
from climate_pipeline.quality import search
from climate_pipeline.quality.config import load_quality_config

PIPELINE = Path(__file__).parents[1]
CFG = load_quality_config(PIPELINE / "water-quality.yaml")


def test_the_space_has_g_only_with_gaps_and_starts_simple() -> None:
    cands = search.space()
    assert len(cands) == 2 * 7 + 2 * 2 * 13
    assert not any(c.pair_set == "3s" and "G" in c.combo for c in cands)
    assert cands[0].combo in ("S", "T", "Q") and cands[0].pair_set == "3s"
    assert cands == sorted(cands, key=lambda c: c.complexity)


def test_the_weighted_ridge_recovers_a_power_law() -> None:
    rng = np.random.default_rng(0)
    x = np.full((50, len(search.NAMES)), np.nan)
    x[:, 0] = rng.uniform(-1.5, 0.5, 50)
    y = 5.0 + 2.0 * x[:, 0]
    model = search.fit(x, y, np.ones(50), [0], 1e-9)
    assert model is not None
    assert np.allclose(np.log(model.predict(x)), y, atol=1e-6)
    assert search.fit(x[:3], y[:3], np.ones(3), [0], 1.0) is None


def test_the_flow_index_is_standardised_per_station() -> None:
    days = [date(2020, 1, 1) + timedelta(days=k) for k in range(60)]
    flow = {"q": ("Q_MEDIA_D", {d: 100.0 * (1 + k % 3) for k, d in enumerate(days)}),
            "h": ("NV_MEDIA_D", {d: 300.0 + k for k, d in enumerate(days)}),
            "short": ("Q_MEDIA_D", {days[0]: 5.0})}  # fmt: skip
    index = search.flow_index(flow)
    assert set(index) == {"q", "h"}
    assert math.isclose(float(np.median(list(index["h"].values()))), 0.0, abs_tol=0.05)


def synthetic() -> search.Data:
    rng = np.random.default_rng(4)
    pairs: list[Pair] = []
    ids: dict[tuple[str, date], int] = {}
    for s in range(5):
        for k in range(10):
            day = date(2020, 1, 1) + timedelta(days=40 * k + s)
            ids[(f"st{s}", day)] = len(ids)
            ratio = float(rng.uniform(0.2, 1.3))
            value = float(150 * ratio**2)
            for gap in (0, 5, 12):
                scene_ratio = ratio * float(np.exp(rng.normal(0, 0.02 * gap)))
                pairs.append(Pair("turbidity", f"st{s}", day, f"k{s}{k}{gap}",
                                  day + timedelta(days=gap), gap, value, False, "", "05.xx",
                                  {"log_B8A/B04": math.log(scene_ratio)}, {}))  # fmt: skip
    tables = {ps: search.table([p for p in pairs if p.gap_days <= search.MAX_DAYS[ps]
                                and (ps != "3s" or p.gap_days <= 1)], {}, None, ids)
              for ps in search.PAIR_SETS}  # fmt: skip
    test = tables["3s"]
    units: dict[str, list[int]] = {}
    pool = {}
    for k, p in enumerate(test.pairs):
        u = int(test.sample[k])
        pool[u] = p
        units.setdefault(p.station, []).append(u)
    return search.Data(tables, units, {u: p.value for u, p in pool.items()}, pool)


def test_nested_loso_finds_a_clean_relation() -> None:
    d = synthetic()
    cands = [c for c in search.space() if c.combo == "S"]
    result, order, plain = search.nested(CFG, d, cands)
    est = [result.estimates[k] for k in range(len(order))]
    obs = [d.value[u] for u in order]
    mdsa = 100 * (math.exp(float(np.median(np.abs(np.log(np.array(est) / np.array(obs)))))) - 1)
    assert mdsa < 5 and set(result.chosen) == {f"st{s}" for s in range(5)}
    assert plain and min(plain.values()) < 5
