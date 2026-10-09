import copy
import math
import random
from datetime import date, timedelta
from pathlib import Path

import pytest

from climate_pipeline.validation.config import DemoEventConfig, Window, load_validation_config
from climate_pipeline.validation.injection import (
    Injection,
    choose_demo,
    detection_rows,
    eligible,
    glint_class,
    inject,
    robust_sigma,
    run_injections,
    threshold,
)
from climate_pipeline.validation.variants import SceneRecord, evaluate

ROOT = Path(__file__).parents[1]
CONFIG = load_validation_config(ROOT / "magdalena-validation.yaml")
D0 = CONFIG.variant("D0")
LIMIT = D0.swir16_max
RAINY = {4, 5, 6, 8, 10, 11}
FLOOR = 0.01
assert CONFIG.injection is not None and CONFIG.demo_event is not None
INJECTION = CONFIG.injection
DEMO = CONFIG.demo_event


def series(n: int = 120, seed: int = 7, start: date = date(2021, 1, 3)) -> list[SceneRecord]:
    """A quiet reach: small noise around a seasonal level, a few unusable scenes."""
    rng = random.Random(seed)
    out = []
    for k in range(n):
        day = start + timedelta(days=12 * k)
        level = 0.05 if day.month in RAINY else 0.0
        up = level + rng.gauss(0, 0.01)
        down = level + 0.005 + rng.gauss(0, 0.01)
        values = {"upstream": up, "downstream": down, "delta": down - up}
        out.append(
            SceneRecord(
                key=f"S2_{day:%Y%m%d}",
                day=day,
                values={0.05: dict(values), 0.03: dict(values)},
                usable={0.05: k % 10 != 9, 0.03: k % 10 != 9},
                glint_share=(k % 5) / 10,
            )
        )
    return out


def test_robust_sigma_and_glint_classes() -> None:
    assert robust_sigma([1.0, 2.0, 3.0, math.nan], 0.01) == pytest.approx(1.4826)
    assert robust_sigma([], 0.01) == 0.01 and robust_sigma([1.0, 1.0], 0.01) == 0.01
    assert [glint_class(s, (0.1, 0.3)) for s in (0.0, 0.1, 0.2, 0.31, math.nan)] == [
        "low", "low", "mid", "high", "unknown"
    ]  # fmt: skip


def test_inject_changes_a_copy_and_moves_the_difference_signal() -> None:
    record = series()[0]
    before = copy.deepcopy(record)
    changed = inject(record, LIMIT, 0.1)
    assert record == before
    assert changed.values[LIMIT]["downstream"] == pytest.approx(
        before.values[LIMIT]["downstream"] + 0.1
    )
    assert changed.values[LIMIT]["delta"] == pytest.approx(before.values[LIMIT]["delta"] + 0.1)
    assert changed.values[LIMIT]["upstream"] == before.values[LIMIT]["upstream"]
    assert changed.values[0.03] == before.values[0.03]


def test_every_eligible_scene_gets_every_step_and_the_real_series_is_untouched() -> None:
    records = series()
    before = copy.deepcopy(records)
    injections, sigma = run_injections(records, D0, RAINY, FLOOR, INJECTION)
    assert records == before
    targets = eligible(records, evaluate(records, D0, RAINY, FLOOR), LIMIT)
    steps = 1 + len(INJECTION.raw_ndti) + len(INJECTION.sigma_multiples)
    assert len(injections) == len(targets) * steps and len(targets) == 108
    assert 0.005 < sigma < 0.05
    # The zero step is the uninjected copy: its detections are the real D0 flags downstream/delta.
    d0 = evaluate(records, D0, RAINY, FLOOR)
    zero = {i.key: i.detected for i in injections if i.scale == "ndti" and i.size == 0.0}
    expected = {records[k].key: bool({"downstream", "delta"} & set(d0[k].signals)) for k in targets}
    assert zero == expected
    big = [i for i in injections if i.scale == "sigma" and i.size == 10]
    assert all(i.detected for i in big)
    assert {i.season for i in injections} == {"rainy", "dry"}


def test_the_linear_shortcut_equals_scoring_every_copy() -> None:
    records = series(n=60)
    fast, sigma_fast = run_injections(records, D0, RAINY, FLOOR, INJECTION)
    slow, sigma_slow = run_injections(records, D0, RAINY, FLOOR, INJECTION, direct=True)
    assert sigma_fast == sigma_slow and len(fast) == len(slow)
    for a, b in zip(fast, slow, strict=True):
        assert (a.key, a.scale, a.size) == (b.key, b.scale, b.size)
        assert a.z_downstream == pytest.approx(b.z_downstream, abs=1e-9)
        assert a.z_delta == pytest.approx(b.z_delta, abs=1e-9)
        assert a.detected == b.detected


def test_detection_rows_and_threshold() -> None:
    injections, _ = run_injections(series(), D0, RAINY, FLOOR, INJECTION)
    rows = detection_rows(injections)
    overall = [r for r in rows if r["scale"] == "ndti" and r["stratum"] == "all"]
    assert [r["size"] for r in overall] == [0.0, *INJECTION.raw_ndti]
    rates = [float(str(r["detected"])) for r in overall]
    # |z| >= 3 counts both directions: a small positive step can cancel a real negative anomaly,
    # so the curve need not rise at the smallest steps; it does from the first percent of NDTI.
    assert rates[2:] == sorted(rates[2:]) and rates[-1] == 1.0
    assert {r["stratum"] for r in rows} == {"all", "season", "glint"}
    grid, interpolated = threshold(injections, "ndti", 0.8)
    assert grid is not None and interpolated is not None and interpolated <= grid


def made(size: float, detected: bool) -> Injection:
    return Injection(
        "k", date(2022, 1, 1), "dry", "low", "ndti", size, size, 0.0, 0.0, detected, False
    )


def test_threshold_interpolates_between_grid_steps() -> None:
    injections = [made(0.01, k < 1) for k in range(2)] + [made(0.02, True) for _ in range(2)]
    grid, interpolated = threshold(injections, "ndti", 0.8)
    assert grid == 0.02 and interpolated == pytest.approx(0.016)
    assert threshold(injections, "ndti", 0.5) == (0.01, 0.01)
    assert threshold([made(0.01, False)], "ndti", 0.8) == (None, None)
    assert threshold(injections, "sigma", 0.8) == (None, None)


def demo_rule(**changes: object) -> DemoEventConfig:
    window = Window(start=date(2022, 1, 1), end=date(2024, 12, 31))
    return DEMO.model_copy(update={"window": window, **changes})


def test_the_demo_event_follows_the_rule_and_is_reproducible() -> None:
    records = series()
    clear = {r.key for r in records}
    avoid = [(date(2022, 6, 1), date(2022, 6, 30))]
    a = choose_demo(records, D0, RAINY, FLOOR, clear, avoid, 0.016, demo_rule())
    b = choose_demo(records, D0, RAINY, FLOOR, clear, avoid, 0.016, demo_rule())
    assert a is not None and a == b
    assert a.step == pytest.approx(0.04)  # ceil(2.0 * 0.016 / 0.01) * 0.01
    assert date(2022, 1, 1) <= a.day <= date(2024, 12, 31)
    assert not (date(2022, 5, 2) <= a.day <= date(2022, 7, 30))
    record = next(r for r in records if r.key == a.key)
    assert record.usable[LIMIT] and record.glint_share <= DEMO.max_glint_share
    assert a.real_downstream == record.values[LIMIT]["downstream"]
    assert a.label.startswith("SYNTHETIC")
    other = choose_demo(records, D0, RAINY, FLOOR, clear, avoid, 0.016, demo_rule(seed=1))
    assert other is not None and other.eligible_scenes == a.eligible_scenes


def test_the_demo_date_keeps_away_from_ranges_and_may_find_nothing() -> None:
    records = series()
    clear = {r.key for r in records}
    contract = [(date(2023, 1, 1), date(2030, 1, 1))]
    kept = choose_demo(records, D0, RAINY, FLOOR, clear, contract, 0.016, demo_rule())
    assert kept is not None and kept.day < date(2022, 12, 2)
    everything = [(date(2000, 1, 1), date(2030, 1, 1))]
    assert choose_demo(records, D0, RAINY, FLOOR, clear, everything, 0.016, demo_rule()) is None
    assert choose_demo(records, D0, RAINY, FLOOR, set(), [], 0.016, demo_rule()) is None
    assert choose_demo(records, D0, RAINY, FLOOR, clear, [], None, demo_rule()) is None
