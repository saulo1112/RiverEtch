from datetime import date
from pathlib import Path

import pytest

from climate_pipeline.screening.config import EventConfig
from climate_pipeline.screening.events import (
    EVENT_COLUMNS,
    CatalogEvent,
    chance_rate,
    evaluate,
    event_window,
    is_scored,
    load_events,
)

CFG = EventConfig(
    window_before_days=2,
    window_after_days=10,
    scored_precisions=("day", "week"),
    chance_shifts=400,
    seed=7,
)


def event(start: date, end: date | None = None, precision: str = "day") -> CatalogEvent:
    return CatalogEvent(
        event_id="e1",
        site_id="cauca-test",
        date_start=start,
        date_end=end or start,
        date_precision=precision,
        river="Cauca",
        event_type="flow_increase",
        description="Discharge increased",
        source_url="https://example.test",
        source_type="news",
        confidence="medium",
        verification="search summary only",
        notes="",
    )


def test_load_events_expands_month_precision(tmp_path: Path) -> None:
    path = tmp_path / "events.csv"
    path.write_text(
        ",".join(EVENT_COLUMNS)
        + "\n"
        + "e1,s,2023-02-05,2023-02-05,day,Cauca,flow_increase,d,https://x,news,high,v,\n"
        + "e2,s,2024-03,,month,Cauca,flood,d,https://y,news,low,v,n\n",
        encoding="utf-8",
    )
    first, second = load_events(path)
    assert (first.date_start, first.date_end) == (date(2023, 2, 5), date(2023, 2, 5))
    assert (second.date_start, second.date_end) == (date(2024, 3, 1), date(2024, 3, 31))


def test_load_events_rejects_unexpected_columns(tmp_path: Path) -> None:
    path = tmp_path / "events.csv"
    path.write_text("id,date\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_events(path)


def test_window_and_scoring_rules() -> None:
    e = event(date(2023, 6, 10))
    assert event_window(e, CFG) == (date(2023, 6, 8), date(2023, 6, 20))
    period = (date(2022, 1, 1), date(2025, 12, 31))
    assert is_scored(e, CFG, *period)
    assert not is_scored(event(date(2023, 6, 1), precision="month"), CFG, *period)
    assert not is_scored(event(date(2019, 2, 5)), CFG, *period)


def test_hit_miss_and_unobservable() -> None:
    e = event(date(2023, 6, 10))
    scores = {
        date(2023, 6, 1): {"delta": 9.0},  # outside the window
        date(2023, 6, 12): {"delta": float("nan"), "downstream": -3.4},
    }
    hit = evaluate(e, CFG, scores, threshold=3.0)
    assert (hit.status, hit.max_abs_z, hit.signal) == ("hit", 3.4, "downstream")
    miss = evaluate(e, CFG, {date(2023, 6, 12): {"delta": 1.0}}, threshold=3.0)
    assert miss.status == "miss"
    gone = evaluate(e, CFG, {date(2023, 7, 30): {"delta": 5.0}}, threshold=3.0)
    assert gone.status == "unobservable" and gone.max_abs_z is None


def test_chance_rate_is_reproducible_and_avoids_event_windows() -> None:
    scores = {date(2023, 1, 1 + i): {"delta": 4.0 if i % 10 == 0 else 0.5} for i in range(0, 28, 3)}
    rate, n = chance_rate(13, scores, 3.0, date(2023, 1, 1), date(2023, 3, 31), [], 300, 1)
    rate2, n2 = chance_rate(13, scores, 3.0, date(2023, 1, 1), date(2023, 3, 31), [], 300, 1)
    assert (rate, n) == (rate2, n2)
    assert 0 < rate < 1 and n > 0
    blocked, m = chance_rate(
        13,
        scores,
        3.0,
        date(2023, 1, 1),
        date(2023, 3, 31),
        [(date(2022, 12, 1), date(2023, 4, 30))],
        50,
        1,
    )
    assert m == 0 and blocked != blocked


def test_usable_scenes_without_a_baseline_are_not_a_miss() -> None:
    e = event(date(2023, 6, 10))
    outcome = evaluate(e, CFG, {date(2023, 6, 12): {}}, threshold=3.0)
    assert outcome.status == "insufficient-baseline"


def test_chance_windows_can_end_on_the_last_day() -> None:
    last = date(2023, 1, 31)
    scores = {last: {"delta": 5.0}}
    rate, n = chance_rate(31, scores, 3.0, date(2023, 1, 1), last, [], 50, 3)
    assert (rate, n) == (1.0, 50)
