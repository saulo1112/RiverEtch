import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from climate_pipeline.calibration.matchups import Pair
from climate_pipeline.quality import cards, search, temporal
from climate_pipeline.quality.config import load_quality_config

PIPELINE = Path(__file__).parents[1]
CFG = load_quality_config(PIPELINE / "water-quality.yaml")
OFFSETS = {"st0": 0.4, "st1": -0.3, "st2": 0.0, "st3": 0.2}


def synthetic() -> search.Data:
    """Four stations with their own offsets, samples over six hydrological years."""
    rng = np.random.default_rng(5)
    pairs: list[Pair] = []
    ids: dict[tuple[str, date], int] = {}
    for s, offset in enumerate(OFFSETS.values()):
        for k in range(18):
            day = date(2016, 1, 10) + timedelta(days=120 * k + 3 * s)
            ids[(f"st{s}", day)] = len(ids)
            ratio = float(rng.uniform(0.2, 1.3))
            value = float(150 * ratio**2 * math.exp(offset))
            for gap in (0, 5, 12):
                f = {"log_B8A/B04": math.log(ratio), "log_B04/B03": 0.1 * ratio,
                     "log_B04/B02": 0.2 * ratio, "B8A-B11": 0.01 * ratio}  # fmt: skip
                pairs.append(Pair("turbidity", f"st{s}", day, f"k{s}{k}{gap}",
                                  day + timedelta(days=gap), gap, value, False, "", "05.xx", f,
                                  {"valid_px": 100.0, "glint_share": 0.0}))  # fmt: skip
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
    return search.Data(tables, units, {u: p.value for u, p in pool.items()}, pool,
                       {s: [s] for s in units})  # fmt: skip


def setup() -> temporal.Search:
    d = synthetic()
    years = {u: p.sample_day.year + (p.sample_day.month == 12) for u, p in d.pool.items()}
    return temporal.Search(d, years, {ps: temporal.strict_rows(t) for ps, t in d.tables.items()})


def test_the_space_has_g_only_with_gaps_and_starts_simple() -> None:
    space = temporal.space()
    assert len(space) == 480 and len({c.id for c in space}) == 480
    assert not any(c.pair_set == "3s" and "G" in c.combo for c in space)
    first = space[0]
    assert (first.combo, first.pair_set, first.station_lambda, first.quality, first.lam) == (
        "T", "3s", None, "all", 100.0)  # fmt: skip


def test_station_offsets_are_recovered() -> None:
    s = setup()
    c = temporal.Candidate("S5", "3s", "nearest", 0.01, "all", 0.01)
    model = s.model(c, frozenset())
    assert model is not None and s.model(c, frozenset()) is model
    centred = {k: v - np.mean(list(model.offsets.values())) for k, v in model.offsets.items()}
    truth = {k: v - np.mean(list(OFFSETS.values())) for k, v in OFFSETS.items()}
    for station, value in truth.items():
        assert math.isclose(centred[station], value, abs_tol=0.05)


def test_the_year_out_scheme_learns_a_known_station() -> None:
    s = setup()
    space = [c for c in temporal.space() if c.combo == "S5" and c.pair_set == "3s"
             and c.quality == "all" and c.lam == 0.1]  # fmt: skip
    plain = [c for c in space if c.station_lambda is None]
    with_station = temporal.primary(s, CFG, space)
    without = temporal.primary(s, CFG, plain)

    def mdsa(o: temporal.Outer) -> float:
        est = np.array([o.estimates[u] for u in sorted(o.estimates)])
        obs = np.array([s.d.value[u] for u in sorted(o.estimates)])
        return float(100 * (math.exp(float(np.median(np.abs(np.log(est / obs))))) - 1))

    assert mdsa(with_station) < 5 < mdsa(without)
    assert set(with_station.chosen) == {str(y) for y in s.unit_year.values()}
    fwd = temporal.forward(s, CFG, space)
    assert fwd.estimates and min(s.unit_year[u] for u in fwd.estimates) > min(s.unit_year.values())


def test_the_ridge_card_reproduces_the_model() -> None:
    s = setup()
    c = temporal.Candidate("S5", "3s", "nearest", 1.0, "all", 0.1)
    model = s.model(c, frozenset())
    assert model is not None
    units = sorted(s.unit_year)
    inner = dict(zip(units, s.predict(model, c, units), strict=True))
    card = temporal.ridge_card(s.d, c.pair_set, c.id, model, "st0", inner,
                               [{"predicted_range": "all", "level": "indicative"}], {}, CFG,
                               temporal.BASIS, "R3:test")  # fmt: skip
    u = s.d.units["st0"][0]
    p = s.d.pool[u]
    expected = s.predict(model, c, [u])[0]
    assert math.isclose(cards.estimate(card, p.features, PIPELINE), expected, rel_tol=1e-6)
    r1 = {"levels": [{"predicted_range": "all", "level": "none"}]}
    assert temporal.product_card(r1, card) is card
    assert temporal.product_card(r1, {**card, "levels": r1["levels"]}) is r1
