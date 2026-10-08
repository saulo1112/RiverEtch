import math
import random
from datetime import date, timedelta
from pathlib import Path

import pytest

from climate_pipeline.screening.config import load_screening_config
from climate_pipeline.screening.stage2 import robust_z
from climate_pipeline.validation.config import Variant, load_validation_config
from climate_pipeline.validation.run import check_d0, glint_limits
from climate_pipeline.validation.variants import (
    SceneRecord,
    criterion_a,
    episodes,
    evaluate,
    persistence,
    share,
    zscores,
)

ROOT = Path(__file__).parents[1]
SCREENING = load_screening_config(ROOT / "screening.yaml")
CONFIG = load_validation_config(ROOT / "urra-validation.yaml")
RAINY = {4, 5, 6, 7, 8, 9}


def variant(**changes: object) -> Variant:
    return CONFIG.variant("D0").model_copy(update=changes)


def days_every(start: date, step: int, n: int) -> list[date]:
    return [start + timedelta(days=step * k) for k in range(n)]


def test_the_config_holds_ten_variants_and_d0_is_the_screening_rule() -> None:
    assert [v.id for v in CONFIG.variants] == [
        "D0",
        "B1",
        "B2",
        "B3",
        "B4",
        "B5",
        "Z2.5",
        "Z3.5",
        "G1",
        "G2",
    ]
    assert {v.id for v in CONFIG.variants if v.distinct} == {"B2", "B3", "Z3.5", "G1", "G2"}
    check_d0(CONFIG, SCREENING)
    assert glint_limits(CONFIG) == (0.05, 0.03)
    changed = CONFIG.model_copy(update={"variants": (variant(anomaly_z=2.9), *CONFIG.variants[1:])})
    with pytest.raises(ValueError, match="screening rule"):
        check_d0(changed, SCREENING)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_d0_equals_the_screening_robust_z(seed: int) -> None:
    rng = random.Random(seed)
    days = sorted(date(2019, 1, 1) + timedelta(days=rng.randrange(2500)) for _ in range(60))
    values = [rng.gauss(0, 0.05) if rng.random() > 0.1 else math.nan for _ in days]
    mine = zscores(values, days, RAINY, CONFIG.variant("D0"), SCREENING.stage2.mad_floor)
    theirs, groups = robust_z(values, days, RAINY, [], SCREENING)
    assert mine.group == groups
    assert all(
        (math.isnan(a) and math.isnan(b)) or a == pytest.approx(b, abs=1e-12)
        for a, b in zip(mine.z, theirs, strict=True)
    )


def test_season_only_never_falls_back_to_all() -> None:
    days = days_every(date(2020, 1, 5), 30, 24)  # two years, 10 dry and 14 rainy... per year
    values = [0.0] * len(days)
    rainy_one = {1}  # only January is "rainy": each January has a group of 1 other value
    d0 = zscores(values, days, rainy_one, CONFIG.variant("D0"), 0.01)
    b1 = zscores(values, days, rainy_one, CONFIG.variant("B1"), 0.01)
    january = [k for k, d in enumerate(days) if d.month == 1]
    assert all(d0.group[k] == "all" for k in january)
    assert all(b1.group[k] == "insufficient" and math.isnan(b1.z[k]) for k in january)


def test_month_window_wraps_around_the_year_end() -> None:
    days = [date(y, m, 15) for y in range(2019, 2024) for m in (1, 2, 6, 11, 12)]
    values = [1.0 if d.month == 6 else 0.0 for d in days]
    b2 = zscores(values, days, RAINY, CONFIG.variant("B2"), 0.01)
    december = days.index(date(2021, 12, 15))
    # November, December and January of other years: 3 * 5 - 1 = 14 others, no June.
    assert b2.group[december] == "month" and b2.size[december] == 14
    assert b2.z[december] == 0.0
    june = days.index(date(2021, 6, 15))
    assert b2.group[june] == "insufficient"  # only 4 other Junes (May and July have none)


def test_day_window_needs_six_values_within_182_days() -> None:
    days = days_every(date(2020, 1, 1), 60, 12)
    values = [0.0] * 12
    b3 = zscores(values, days, RAINY, CONFIG.variant("B3"), 0.01)
    # 182 days hold 3 scenes on each side at a 60-day step: 6 others at most.
    assert b3.group[6] == "window" and b3.size[6] == 6
    assert b3.group[0] == "insufficient"


def test_group_minimums_of_b4_and_b5() -> None:
    days = days_every(date(2020, 1, 10), 20, 20)  # 20 scenes
    values = [0.0] * 20
    b4 = zscores(values, days, RAINY, CONFIG.variant("B4"), 0.01)
    b5 = zscores(values, days, RAINY, CONFIG.variant("B5"), 0.01)
    assert all(g in ("season", "all") for g in b4.group)
    assert all(g == "insufficient" for g in b5.group)  # 19 others < 20, seasons < 12


def record(day: date, value: float, usable: bool = True, glint: float = 0.0) -> SceneRecord:
    values = {"upstream": 0.0, "downstream": value, "delta": value}
    return SceneRecord(
        key=f"s_{day}",
        day=day,
        values={0.05: values, 0.03: values},
        usable={0.05: usable, 0.03: usable},
        glint_share=glint,
    )


def test_evaluate_reports_excluded_removed_and_anomalous_scenes() -> None:
    days = days_every(date(2021, 1, 3), 12, 40)
    records = [record(d, 0.5 if k == 20 else 0.001 * (k % 3)) for k, d in enumerate(days)]
    records[3] = record(days[3], 0.0, usable=False)
    records[5] = record(days[5], 0.0, glint=0.8)
    g2 = evaluate(records, CONFIG.variant("G2"), RAINY, 0.01)
    assert g2[3].status == "excluded" and g2[5].status == "removed"
    assert g2[20].anomalous and set(g2[20].signals) == {"downstream", "delta"}
    d0 = evaluate(records, CONFIG.variant("D0"), RAINY, 0.01)
    assert d0[5].status == "scored"
    assert share(d0) == (1, 39)


def test_persistence_counts_variants_and_eight_of_ten_is_the_line() -> None:
    eight = [[True]] * 8 + [[False]] * 2
    seven = [[True]] * 7 + [[False]] * 3
    assert persistence(eight) == [8] and persistence(seven) == [7]


def test_episodes_merge_scenes_at_most_30_days_apart() -> None:
    days = [
        date(2024, 1, 16),
        date(2024, 2, 10),
        date(2024, 2, 25),
        date(2023, 12, 2),
        date(2022, 12, 7),
        date(2025, 12, 16),
        date(2024, 2, 25),
    ]
    found = episodes(days, 30)
    assert [len(e) for e in found] == [1, 1, 3, 1]
    assert episodes([date(2024, 1, 1), date(2024, 1, 31)], 30) == [
        [date(2024, 1, 1), date(2024, 1, 31)]
    ]
    assert len(episodes([date(2024, 1, 1), date(2024, 2, 1)], 30)) == 2


def test_criterion_a_keeps_persistent_scenes_away_from_rain() -> None:
    days = days_every(date(2019, 1, 2), 10, 200)
    spikes = {40, 90, 140, 190}
    records = [record(d, 0.5 if k in spikes else 0.002 * (k % 5)) for k, d in enumerate(days)]
    wet = [k == 140 for k in range(len(days))]
    result = criterion_a(records, CONFIG.variants, RAINY, 0.01, wet, 8, 30)
    assert [result.counts[k] for k in sorted(spikes)] == [10, 10, 10, 10]
    assert result.candidates == [days[40], days[90], days[190]]
    assert len(result.episodes) == 3
    assert result.distinct_counts[40] == 5
