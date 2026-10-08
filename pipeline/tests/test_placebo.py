import random
from datetime import date, timedelta
from pathlib import Path

from climate_pipeline.validation.config import load_validation_config
from climate_pipeline.validation.placebo import run_placebo, s1, shuffle_within_season
from climate_pipeline.validation.variants import SceneRecord, evaluate

CONFIG = load_validation_config(Path(__file__).parents[1] / "urra-validation.yaml")
RAINY = {4, 5, 6, 7, 8, 9}


def records() -> list[SceneRecord]:
    rng = random.Random(7)
    out = []
    for k in range(80):
        day = date(2019, 1, 3) + timedelta(days=30 * k)
        value = rng.gauss(0.0, 0.01) + (0.2 if k in (10, 33, 47, 61) else 0.0)
        values = {"upstream": 0.0, "downstream": value, "delta": value}
        usable = k != 5
        out.append(
            SceneRecord(
                f"s{k}",
                day,
                {0.05: values, 0.03: values},
                {0.05: usable, 0.03: usable},
                rng.random() * 0.6,
            )
        )
    return out


def test_shuffles_keep_dates_and_seasons_and_leave_excluded_scenes_in_place() -> None:
    original = records()
    movable = [r.usable[0.05] for r in original]
    shuffled = shuffle_within_season(original, movable, RAINY, random.Random(1))
    assert [r.day for r in shuffled] == [r.day for r in original]
    assert shuffled[5] == original[5]
    moved = {id(r.values) for r in shuffled}
    assert moved == {id(r.values) for r in original}
    for new in shuffled:
        source = next(o for o in original if o.values is new.values)
        assert (source.day.month in RAINY) == (new.day.month in RAINY)


def test_d0_anomalies_do_not_change_under_within_season_shuffles() -> None:
    original = records()
    movable = [r.usable[0.05] for r in original]
    d0 = CONFIG.variant("D0")
    before = sorted(
        round(r.values[0.05]["downstream"], 9)
        for r, s in zip(original, evaluate(original, d0, RAINY, 0.01), strict=True)
        if s.anomalous
    )
    rng = random.Random(2)
    for _ in range(5):
        shuffled = shuffle_within_season(original, movable, RAINY, rng)
        scenes = evaluate(shuffled, d0, RAINY, 0.01)
        after = sorted(
            round(r.values[0.05]["downstream"], 9)
            for r, s in zip(shuffled, scenes, strict=True)
            if s.anomalous
        )
        assert after == before
    dry = [False] * len(original)
    assert s1(original, d0, RAINY, 0.01, dry) == len(before)


def test_the_placebo_is_deterministic_and_its_p_values_are_bounded() -> None:
    wet = [k % 9 == 0 for k in range(80)]
    first = run_placebo(records(), CONFIG.variants, RAINY, 0.01, wet, CONFIG.criteria, 20, 11)
    second = run_placebo(records(), CONFIG.variants, RAINY, 0.01, wet, CONFIG.criteria, 20, 11)
    assert first == second
    assert len(first.s1) == 20 and 1 / 21 <= first.p_s1 <= 1 and 1 / 21 <= first.p_s2 <= 1
    other = run_placebo(records(), CONFIG.variants, RAINY, 0.01, wet, CONFIG.criteria, 20, 12)
    assert other.s2 != first.s2 or other.s1 != first.s1
