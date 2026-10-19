"""Extreme days of a demo reach's gauge record (rule v1, section 5): the thresholds, the counts and
ranks per year, what the satellite saw and the lock box's pairs, from synthetic values and from the
committed files (they reproduce the counts disclosed in docs/water-quality/prospective.md)."""

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from climate_pipeline.reach import climate, extremes
from climate_pipeline.reach.climate import Daily

REPO = Path(__file__).parents[2]


def test_the_quantile_interpolates_between_order_statistics() -> None:
    assert extremes.quantile([4.0, 1.0, 3.0, 2.0], 0.1) == pytest.approx(1.3)
    assert extremes.quantile([4.0, 1.0, 3.0, 2.0], 0.9) == pytest.approx(3.7)
    assert extremes.quantile([5.0], 0.9) == 5.0


def test_thresholds_use_approved_days_of_the_reference_periods_only() -> None:
    flow = [Daily(date(2020, 1, 1) + timedelta(days=k), float(k), False) for k in range(11)]
    flow.append(Daily(date(2026, 1, 1), 1000.0, False))  # after 2025: not a reference day
    flow.append(Daily(date(2020, 3, 1), -50.0, True))  # provisional: not a reference day
    summer = [Daily(date(2010, 7, 1) + timedelta(days=k), 20.0 + k, False) for k in range(11)]
    warm = [Daily(date(2001, 7, 1), 99.0, False),  # before 2002
            Daily(date(2010, 1, 15), 99.0, False),  # not June-September
            *summer]  # fmt: skip
    t = extremes.thresholds({climate.DISCHARGE: flow, climate.TEMPERATURE: warm})
    assert t.low == pytest.approx(1.0) and t.high == pytest.approx(9.0) and t.flow_days == 11
    assert t.warm == pytest.approx(29.0) and t.warm_days == 11
    assert extremes.thresholds({climate.DISCHARGE: flow}).warm is None


def test_a_day_published_twice_counts_once() -> None:
    day = date(2007, 7, 1)
    merged = extremes.one_per_day(
        {climate.TEMPERATURE: [Daily(day, 25.0, False), Daily(day, 26.0, True)]}
    )
    assert merged[climate.TEMPERATURE] == [Daily(day, 25.5, True)]


def year_of(year: int, value: float) -> list[Daily]:
    first = date(year, 1, 1)
    return [Daily(first + timedelta(days=k), value, False)
            for k in range((date(year, 12, 31) - first).days + 1)]  # fmt: skip


def test_counts_rank_the_complete_years_most_first_and_never_the_year_to_date() -> None:
    # 2018-2020 complete; 2021 is the year to date. 130 of the 1,126 days are at 1.0, so the 10th
    # percentile is 1.0: 2018 has 70 low days, 2019 has 30, 2020 none, 2021 (to date) 30.
    flow = (
        year_of(2018, 100.0) + year_of(2019, 100.0) + year_of(2020, 100.0) + year_of(2021, 1.0)[:30]
    )
    flow = [Daily(d.day, 1.0, False) if (d.day.year == 2018 and d.day.timetuple().tm_yday <= 70)
            or (d.day.year == 2019 and d.day.timetuple().tm_yday <= 30) else d
            for d in flow]  # fmt: skip
    snapshot = {climate.DISCHARGE: flow}
    doc = climate.summarise(snapshot, {"id": "USGS-1", "name": "A gauge"})
    seen = {date(2019, 1, 2), date(2019, 6, 1)}
    block = extremes.summarise(
        snapshot, doc, seen, ("2019-01-01", "2019-12-31"), [date(2019, 1, 3)]
    )
    years = {r["year"]: r for r in block["years"]}
    assert [years[y]["low"] for y in (2018, 2019, 2020, 2021)] == [70, 30, 0, 30]
    assert [years[y]["lowRank"] for y in (2018, 2019, 2020, 2021)] == [1, 2, 3, None]
    assert years[2019]["lowSeen"] == 1 and years[2019]["passes"] == 2  # 2 Jan: low and seen
    assert years[2018]["lowSeen"] is None and years[2018]["seenFrom"] is None  # before the v5 years
    assert block["lockbox"] == {"first": "2019-01-01", "last": "2019-12-31", "pairs": 1, "low": 1,
                                "high": 0, "warm": None, "minimum": 20}  # fmt: skip
    assert block["satelliteEra"]["warm"] is None


@pytest.mark.parametrize(
    ("site", "thresholds", "lockbox", "era"),
    [
        ("mississippi-belle-chasse", (6654.5, 27807.1, None), (57, 13, 0, None),
         {"low": (306, 49), "high": (369, 37), "normal": (1655, 198)}),
        ("platte-louisville", (62.6, 379.4, 28.9), (54, 1, 4, 4),
         {"low": (100, 11), "high": (351, 34), "normal": (2030, 160), "warm": (95, 18)}),
    ],
)  # fmt: skip
def test_the_committed_files_reproduce_the_disclosed_counts(
    site: str, thresholds: tuple[Any, ...], lockbox: tuple[Any, ...], era: dict[str, Any]
) -> None:
    folder = REPO / "docs/water-quality/reach" / site
    committed = json.loads((folder / "examples/climate.json").read_text(encoding="utf-8"))
    rest = {k: v for k, v in committed.items() if k != "extremes"}
    snapshot = climate.read_snapshot(climate.snapshot_path(REPO, site))
    block = extremes.document(REPO, site, committed["station"]["id"], snapshot, rest)
    assert block == committed["extremes"]  # the committed block is what the code writes
    t = block["thresholds"]
    assert (t["low"], t["high"], t["warm"]) == thresholds
    lock = block["lockbox"]
    assert (lock["pairs"], lock["low"], lock["high"], lock["warm"]) == lockbox
    for kind, (days, seen) in era.items():
        assert (block["satelliteEra"][kind]["days"], block["satelliteEra"][kind]["seen"]) == (
            days,
            seen,
        )
