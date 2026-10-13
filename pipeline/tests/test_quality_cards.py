import copy
import hashlib
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from climate_pipeline.calibration.matchups import Pair
from climate_pipeline.quality import cards, transfer
from climate_pipeline.quality.config import load_quality_config

PIPELINE = Path(__file__).parents[1]
CFG = load_quality_config(PIPELINE / "water-quality.yaml")
TURBIDITY = CFG.target("turbidity")
LEVELS = [
    {"predicted_range": "all", "n": 8, "rated": True, "mdsa": 10.0, "level": "estimated"},
    {"predicted_range": "100-300", "n": 8, "rated": True, "mdsa": 20.0, "level": "indicative"},
    {"predicted_range": ">=1000", "n": 2, "rated": False, "mdsa": math.nan, "level": "none"},
]


def pair(station: str, value: float, **f: float) -> Pair:
    return Pair("turbidity", station, date(2020, 1, 1), f"k{station}{value}", date(2020, 1, 1), 0,
                value, False, "", "05.xx", f, {})  # fmt: skip


def a1_card(levels: list[dict[str, Any]] = LEVELS) -> dict[str, Any]:
    rng = np.random.default_rng(1)
    every = [pair(f"s{k % 6}", float(300 * r**2 * math.exp(rng.normal(0, 0.05))),
                  **{"B8A/B04": float(r)})
             for k, r in enumerate(rng.uniform(0.2, 1.5, 24))]  # fmt: skip
    train, test = every[:16], every[16:]
    metrics = {"loro": {"n": 16, "mdsa": 12.0}, "test": {"n": 8, "mdsa": 10.0},
               "refit": {"n": 8, "mdsa": math.nan}}  # fmt: skip
    return cards.product_card(CFG, TURBIDITY, "300m", "A1", train, test, None,
                              [p.value * 1.1 for p in train], [p.value * 0.9 for p in test],
                              metrics, levels, Path("unused"))  # fmt: skip


def test_an_a1_card_reproduces_its_power_law_and_is_strict_json() -> None:
    card = a1_card()
    assert card["modelId"] == "A1:turbidity:300m" and card["unit"] == TURBIDITY.unit
    assert math.isclose(cards.estimate(card, {"B8A/B04": 1.0}, Path()), 300.0, rel_tol=0.05)
    assert math.isnan(cards.estimate(card, {"B04": 1.0}, Path()))
    assert card["metrics"]["test"]["n"] == 8 and card["metrics"]["refit"]["mdsa"] is None
    assert card["trainingPairs"] == {"colombia": 24, "usgs": 0}
    json.dumps(card, allow_nan=False)


def test_a_card_abstains_outside_its_training_range() -> None:
    card = a1_card()
    low, high = card["featureRange"]["B8A/B04"]
    assert cards.outside_range(card, {"B8A/B04": (low + high) / 2}) is None
    assert "B8A/B04" in str(cards.outside_range(card, {"B8A/B04": high * 2}))
    assert cards.outside_range(card, {}) is not None


def test_a_card_rates_each_predicted_range() -> None:
    card = a1_card()
    assert cards.level_of(card, TURBIDITY, 150.0) == ("indicative", 20.0)
    assert cards.level_of(card, TURBIDITY, 50.0) == ("estimated", 10.0)  # no row: the overall
    level, mdsa = cards.level_of(card, TURBIDITY, 2000.0)
    assert level == "none" and math.isnan(mdsa)
    assert cards.level_of(card, TURBIDITY, math.nan)[0] == "none"


def test_a_tercile_too_small_for_90_percent_pools_the_residuals() -> None:
    card = a1_card()  # 24 residuals, 8 per tercile: the 90 % rank (9) is out of reach
    assert card["intervals"]["pooled"] == ["0.9"]
    assert len(set(card["intervals"]["q"]["0.9"])) == 1
    for coverage in (0.8, 0.9):
        low, high = cards.interval(card, 100.0, coverage)
        assert 0 < low < 100.0 < high < math.inf
    unbounded = {**card, "intervals": {**card["intervals"], "q": {"0.9": [None] * 3}}}
    assert cards.interval(unbounded, 100.0, 0.9) == (0.0, math.inf)
    assert all(math.isnan(v) for v in cards.interval(card, math.nan, 0.8))


def test_the_parameters_hash_ignores_the_report_but_the_card_hash_does_not() -> None:
    card = a1_card()
    relevelled = a1_card([{**LEVELS[0], "level": "validated"}])
    assert relevelled["parametersHash"] == card["parametersHash"]
    assert cards.card_hash(relevelled) != cards.card_hash(card)
    assert cards.card_hash(copy.deepcopy(card)) == cards.card_hash(card)


def test_a_pretrained_card_carries_the_colombian_adjustment() -> None:
    def ratio_pair(station: str, value: float, r: float) -> Pair:
        return pair(station, value, **{"log_B8A/B04": math.log(r)})

    usgs_pairs = [ratio_pair(f"u{k % 5}", float(200 * r**1.5), float(r))
                  for k, r in enumerate(np.geomspace(0.2, 1.5, 30))]  # fmt: skip
    usgs = transfer.UsgsInputs({("turbidity", "300m"): usgs_pairs},
                               {f"u{k}": f"RIVER{k}" for k in range(5)})  # fmt: skip
    colombia = [ratio_pair(f"c{k % 4}", float(1.6 * 200 * r**1.5), float(r))
                for k, r in enumerate(np.geomspace(0.3, 1.2, 14))]  # fmt: skip
    train, test = colombia[:10], colombia[10:]
    card = cards.product_card(CFG, TURBIDITY, "300m", "A2", train, test, usgs,
                              [p.value for p in train], [p.value for p in test], {}, [],
                              Path("unused"))  # fmt: skip
    assert card["parameters"]["kind"] == "linear-log" and card["adjustment"]["a"] > 0
    assert card["trainingPairs"] == {"colombia": 14, "usgs": 30}
    raw = 200.0  # the USGS model at B8A/B04 = 1
    adjusted = cards.estimate(card, {"log_B8A/B04": 0.0}, Path())
    assert raw * 1.3 < adjusted < raw * 1.7


def test_the_file_hash_ignores_crlf(tmp_path: Path) -> None:
    lf, crlf = tmp_path / "lf.json", tmp_path / "crlf.json"
    lf.write_bytes(b'{"a": 1}\n{"b": 2}\n')
    crlf.write_bytes(b'{"a": 1}\r\n{"b": 2}\r\n')
    assert cards.file_sha256(lf) == cards.file_sha256(crlf)
    assert cards.file_sha256(lf) == hashlib.sha256(lf.read_bytes()).hexdigest()


def test_a_training_extreme_is_inside_its_rounded_range() -> None:
    card = {"featureRange": {"log_width_m": [5.186827, round(math.log(772.5), 6)]}}
    assert cards.outside_range(card, {"log_width_m": math.log(772.5)}) is None
    assert cards.outside_range(card, {"log_width_m": math.log(780.0)}) is not None
