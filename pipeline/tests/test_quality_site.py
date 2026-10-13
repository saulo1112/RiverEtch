import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from climate_pipeline.calibration.matchups import Pair
from climate_pipeline.contract import observation_v2 as v2
from climate_pipeline.quality import cards, route_a, site, transfer
from climate_pipeline.quality.config import load_quality_config

PIPELINE = Path(__file__).parents[1]
CFG = load_quality_config(PIPELINE / "water-quality.yaml")


def pair(station: str, day: date, value: float, ratio: float) -> Pair:
    f = {"B8A/B04": ratio, "log_B8A/B04": math.log(ratio)}
    return Pair("turbidity", station, day, f"k{station}{day}", day, 0, value, False, "", "05.xx",
                f, {})  # fmt: skip


def series(station: str, start: date, n: int, seed: int) -> list[Pair]:
    rng = np.random.default_rng(seed)
    out = []
    for k in range(n):
        ratio = float(rng.uniform(0.2, 1.4))
        noise = float(np.exp(rng.normal(0, 0.1)))
        out.append(pair(station, start + timedelta(days=30 * k), 80 * ratio**2 * noise, ratio))
    return out


def test_the_split_puts_december_2023_in_the_lock_box() -> None:
    days = (date(2018, 11, 30), date(2018, 12, 1), date(2023, 11, 30), date(2023, 12, 1),
            date(2026, 9, 30), date(2026, 10, 1))  # fmt: skip
    pairs = [pair(site.SITE, d, 10.0, 0.5) for d in days]
    train, lock = site.split(pairs)
    assert [p.sample_day for p in train] == [date(2018, 12, 1), date(2023, 11, 30)]
    assert [p.sample_day for p in lock] == [date(2023, 12, 1), date(2026, 9, 30)]
    assert site.year(train[0]) == "2019" and site.year(lock[0]) == "2024"


def test_the_river_and_its_sites_leave_the_pilot() -> None:
    usgs = transfer.UsgsInputs({("turbidity", "core"): [*series("m1", date(2020, 1, 1), 3, 1),
                                                         *series("o1", date(2020, 1, 1), 3, 2)]},
                               {"m1": "MISSOURI", "o1": "OHIO"})  # fmt: skip
    other = site.without_river(usgs, "MISSOURI", None)
    assert {p.station for p in other.pairs[("turbidity", "core")]} == {"o1"}
    assert other.forests == {} and len(usgs.pairs[("turbidity", "core")]) == 6


def test_the_site_levels_count_years_not_stations() -> None:
    good = {"n": 40.0, "mdsa": 30.0, "sspb": 5.0, "null_mdsa": 100.0, "coverage90": 0.9,
            "rho_low": 0.6}  # fmt: skip
    assert site.site_level(good, CFG, 3) == "validated"
    assert site.site_level(good, CFG, 1) == "estimated"
    assert site.site_level({**good, "mdsa": 55.0}, CFG, 3) == "estimated"
    assert site.site_level({**good, "mdsa": 80.0}, CFG, 3) == "indicative"
    assert site.site_level({**good, "coverage90": 1.0}, CFG, 3) == "indicative"
    assert site.site_level({**good, "n": 3.0}, CFG, 3) == "none"


def test_a_clean_site_relation_reaches_a_level_and_a_valid_card() -> None:
    train = series(site.SITE, date(2018, 12, 15), 58, 3)
    lock = series(site.SITE, date(2023, 12, 15), 30, 4)
    options = {"H1": route_a.a1}
    oof = route_a.leave_one_group_out(train, site.year, options["H1"])
    observed = [p.value for p in train]
    q = route_a.conformal(oof, observed, CFG.intervals.coverages)
    est = options["H1"](train, lock)
    null = route_a.null(train, lock)
    rows = site.level_rows(CFG, CFG.target("turbidity"), lock, est, null, q, 7)
    assert rows[0]["predicted_range"] == "all" and rows[0]["level"] == "validated"
    usgs = transfer.UsgsInputs({("turbidity", "core"): []}, {})
    card = site.card(CFG, CFG.target("turbidity"), "H1", train, usgs, oof, rows,
                     {"inner": {}, "lockbox": {}}, PIPELINE)  # fmt: skip
    assert card["unit"] == "FNU" and card["basis"] == site.BASIS
    value = cards.estimate(card, lock[0].features, PIPELINE)
    assert math.isclose(value, est[0], rel_tol=1e-6)
    low, high = cards.interval(card, value, 0.9)
    estimate = v2.Estimate.model_validate({
        "target": "turbidity", "unit": card["unit"], "level": "validated", "value": value,
        "interval": {"low": low, "high": high, "coverage": 0.9,
                     "method": "mondrian_split_conformal_log"},
        "validRange": tuple(card["targetRange"]), "modelId": card["modelId"],
        "modelVersion": card["version"], "modelCardSha256": cards.card_hash(card),
        "basis": card["basis"],
    })  # fmt: skip
    assert estimate.basis == "preregistered_lockbox_site"
