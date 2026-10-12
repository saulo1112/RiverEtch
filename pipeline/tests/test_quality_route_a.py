import math
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from climate_pipeline.calibration.matchups import Pair, Sample, SceneRow, candidate_values
from climate_pipeline.quality import route_a
from climate_pipeline.quality.config import load_quality_config

PIPELINE = Path(__file__).parents[1]
CFG = load_quality_config(PIPELINE / "water-quality.yaml")
STATS = {"valid_px": 50.0, "contamination": 0.0, "b11_ok": 1.0, "glint_share": 0.0,
         "bands_read": 1.0}  # fmt: skip


def pair(station: str, value: float, gap: int = 0, day: date = date(2020, 1, 10)) -> Pair:
    return Pair("turbidity", station, day, "k", day + timedelta(days=gap), gap, value, False, "",
                "05.xx", {"B8A/B04": 1.0}, STATS)  # fmt: skip


def scene(station: str, day: date, ratio: float) -> SceneRow:
    red = 0.08
    bands = {"B02": 0.03, "B03": 0.05, "B04": red, "B05": red, "B06": red, "B07": red,
             "B08": red * ratio, "B8A": red * ratio, "B11": 0.01, "B12": 0.005}  # fmt: skip
    return SceneRow(station, "earth-search", f"sentinel-2a_{day}_R025", day, "05.xx", STATS,
                    bands, candidate_values(bands, None))  # fmt: skip


def test_stable_flow_rule() -> None:
    q = {"s": ("Q_MEDIA_D", {date(2020, 1, 10): 100.0, date(2020, 1, 13): 108.0})}
    assert route_a.stable(pair("s", 1, gap=1), {}, CFG)
    assert route_a.stable(pair("s", 1, gap=3), q, CFG)  # |ln(1.08)| = 0.077
    q["s"][1][date(2020, 1, 13)] = 120.0
    assert not route_a.stable(pair("s", 1, gap=3), q, CFG)
    level = {"s": ("NV_MEDIA_D", {date(2020, 1, 10): 300.0, date(2020, 1, 13): 309.0})}
    assert route_a.stable(pair("s", 1, gap=3), level, CFG)  # 9 cm
    assert not route_a.stable(pair("s", 1, gap=3), {}, CFG)


def test_leave_one_group_out_never_sees_the_held_group() -> None:
    pool = [pair("a", 10.0), pair("a", 10.0), pair("b", 1000.0)]

    def mean(train: Sequence[Pair], test: Sequence[Pair]) -> list[float]:
        return [float(np.mean([p.value for p in train]))] * len(test)

    assert route_a.leave_one_group_out(pool, lambda p: p.station, mean) == [1000.0, 1000.0, 10.0]
    fixed = [pair("z", 1.0)]
    out = route_a.leave_one_group_out(pool, lambda p: p.station, mean, fixed)
    assert out[2] == 7.0


def test_conformal_quantiles_cover_their_own_residuals() -> None:
    rng = np.random.default_rng(1)
    estimates = np.exp(rng.uniform(1, 7, 300))
    observed = estimates * np.exp(rng.normal(0, 0.4, 300))
    q = route_a.conformal(list(estimates), list(observed), (0.8, 0.9))
    assert q is not None
    assert route_a.covered(q, list(estimates), list(observed), 0.9) >= 0.9
    low, high = q.interval(100.0, 0.9)
    assert math.isclose(low * high, 100.0**2)
    assert route_a.conformal([1.0, math.nan], [1.0, 2.0], (0.9,)) is None


def test_small_terciles_fall_back_to_one_pooled_quantile() -> None:
    estimates = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
    observed = [e * f for e, f in zip(estimates, [1.1, 0.8, 1.3, 0.9, 1.5, 1.2], strict=True)]
    q = route_a.conformal(estimates, observed, (0.8, 0.9))
    assert q is not None and q.pooled == {0.8, 0.9}
    assert math.isclose(q.q[0.8][0], math.log(1.5) - 1e-12, abs_tol=1e-9)  # the 6th of 6
    assert q.q[0.9] == (math.inf,) * 3  # rank 7 of 6: even the pooled quantile is unbounded


def test_levels_follow_the_preregistered_criteria() -> None:
    good = {"n": 30.0, "stations": 5.0, "mdsa": 40.0, "sspb": 10.0, "null_mdsa": 150.0,
            "coverage90": 0.9, "rho_low": 0.5}  # fmt: skip
    assert route_a.level(good, CFG) == "validated"
    assert route_a.level({**good, "stations": 3.0}, CFG) == "estimated"
    assert route_a.level(good, CFG, bin_level=True) == "estimated"
    assert route_a.level({**good, "mdsa": 70.0}, CFG) == "indicative"
    assert route_a.level({**good, "mdsa": 70.0, "rho_low": 0.1}, CFG) == "none"
    assert route_a.level({**good, "coverage90": 0.6}, CFG) == "indicative"
    assert route_a.level({**good, "n": 5.0}, CFG) == "none"


def test_route_a_trains_off_the_magdalena_and_tests_on_it() -> None:
    samples, scenes, stream_of = [], [], {}
    rng = np.random.default_rng(3)
    for s, stream in enumerate(["CAUCA"] * 4 + ["SINU"] * 4 + ["MAGDALENA"] * 5):
        station = f"{stream.lower()}{s}"
        stream_of[station] = stream
        for k in range(6):
            day = date(2019, 1, 1) + timedelta(days=30 * k + s)
            ratio = float(rng.uniform(0.2, 1.2))
            turbidity = 300 * ratio**2 * float(np.exp(rng.normal(0, 0.1)))
            samples.append(Sample(station, day, "turbidity", turbidity, False))
            scenes.append(scene(station, day, ratio))
    ci = route_a.ColombianInputs([], samples, {"300m": scenes, "core": scenes}, {}, stream_of)
    tables = route_a.analyse(CFG, ci)
    counts = {r["variant"]: r for r in tables["route_a_counts"] if r["target"] == "turbidity"}
    assert counts["primary"]["training_streams"] == 2 and counts["primary"]["test_stations"] == 5
    test = next(r for r in tables["route_a_scores"] if r["target"] == "turbidity"
                and r["variant"] == "primary" and r["candidate"] == "A1"
                and r["evaluation"] == "test (Magdalena)")  # fmt: skip
    assert test["n"] == 30 and test["mdsa"] < 15 and test["level"] == "validated"
    assert route_a.summary(tables)["turbidity"]["level"] == "validated"
    (card,) = tables["_cards"]
    assert card["modelId"] == "A1:turbidity:300m" and card["levels"][0]["level"] == "validated"
    assert card["trainingPairs"]["colombia"] == 48 + 30
    tss = [r for r in tables["route_a_scores"] if r["target"] == "tss"]
    assert tss and all(r.get("status") == "insufficient_data" for r in tss)


def test_confirmed_adjacency_makes_the_core_window_primary() -> None:
    day = date(2020, 1, 10)
    ci = route_a.ColombianInputs(
        [], [Sample("s", day, "turbidity", 100.0, False)],
        {"300m": [scene("s", day, 0.5)], "core": []}, {}, {"s": "CAUCA"},
    )  # fmt: skip
    for confirmed, window, pairs in ((False, "300m", 1), (True, "core", 0)):
        counts = route_a.analyse(CFG, ci, adjacency_confirmed=confirmed)["route_a_counts"]
        primary = next(
            r for r in counts if r["target"] == "turbidity" and r["variant"] == "primary"
        )
        assert primary["window"] == window and primary["training_pairs"] == pairs


def test_the_source_check_excludes_a_shifted_source() -> None:
    days = [date(2020, 1, 1) + timedelta(days=5 * k) for k in range(8)]
    es = [scene("s", d, 0.4 + 0.05 * k) for k, d in enumerate(days)]
    same = [SceneRow(s.station, "planetary-computer", s.key, s.day, s.family, s.stats, s.bands,
                     s.features) for s in es]  # fmt: skip
    ci = route_a.ColombianInputs([], [], {"300m": es, "core": es}, {}, {"s": "CAUCA"}, same)
    check = route_a.source_check(CFG, ci)
    assert check["scenes"] == 8 and check["median_difference"] == 0 and not check["excluded"]
    shifted = [scene("s", d, 0.4 + 0.05 * k + 0.3) for k, d in enumerate(days)]
    ci.check = [SceneRow(s.station, "planetary-computer", s.key, s.day, s.family, s.stats,
                         s.bands, s.features) for s in shifted]  # fmt: skip
    assert route_a.source_check(CFG, ci)["excluded"] is True
