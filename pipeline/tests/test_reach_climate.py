"""A reach's gauge record, year by year (``reach climate``): complete years, ranks and the to-date
year, from synthetic daily values."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from climate_pipeline.reach import climate
from climate_pipeline.reach.climate import Daily
from climate_pipeline.reach.run import ReachError


def year_of(year: int, value: float, skip: int = 0, provisional: bool = False) -> list[Daily]:
    first = date(year, 1, 1)
    days = (date(year, 12, 31) - first).days + 1
    return [Daily(first + timedelta(days=k), value, provisional) for k in range(skip, days)]


def test_peak_low_and_ranks_over_complete_years_only() -> None:
    values = year_of(2019, 1000.0) + year_of(2020, 500.0) + year_of(2021, 800.0, skip=60)
    values += year_of(2022, 300.0)[:100]  # the last value's year: to date
    flood = date(2019, 3, 16)
    dry = [date(2020, 9, 1) + timedelta(days=k) for k in range(7)]
    values = [Daily(d.day, 100_000.0 if d.day == flood else 50.0 if d.day in dry else d.value,
                    d.provisional) for d in values]  # fmt: skip
    rows = {r["year"]: r for r in climate.discharge_years(values, date(2022, 4, 10))}
    assert rows[2019]["peak"] == round(100_000 * climate.FT3_TO_M3, 1)
    assert rows[2019]["peakDay"] == "2019-03-16" and rows[2019]["peakRank"] == 1
    assert rows[2020]["low7"] == round(50 * climate.FT3_TO_M3, 1)
    assert rows[2020]["low7Day"] == "2020-09-07" and rows[2020]["low7Rank"] == 1
    # 2021 lacks 60 days (84 % of the year): shown, not ranked. 2022 is the to-date year.
    assert not rows[2021]["complete"] and rows[2021]["peakRank"] is None
    assert rows[2022]["toDate"] and rows[2022]["peakRank"] is None
    assert rows[2019]["low7Rank"] == 2


def test_the_7_day_low_needs_seven_measured_days_inside_the_year() -> None:
    values = year_of(2019, 100.0)
    gap = date(2019, 6, 4)
    values = [Daily(d.day, 1.0 if date(2019, 6, 1) <= d.day < date(2019, 6, 7) else d.value, False)
              for d in values if d.day != gap]  # fmt: skip
    # The six low days are broken by a gap: no 7-day window holds them all.
    row = climate.discharge_years(values, date(2020, 1, 1))[0]
    assert row["low7"] > 1.0 * climate.FT3_TO_M3 * 2
    # A year-end window does not borrow January's days.
    late = year_of(2019, 100.0) + [Daily(date(2020, 1, k), 1.0, False) for k in range(1, 8)]
    assert climate.discharge_years(late, date(2020, 1, 7))[0]["low7"] == round(
        100 * climate.FT3_TO_M3, 1
    )


def test_ties_share_the_better_rank_and_provisional_years_are_labelled() -> None:
    values = year_of(2019, 700.0) + year_of(2020, 700.0, provisional=True) + year_of(2021, 100.0)
    rows = climate.discharge_years(values + year_of(2022, 1.0)[:5], date(2022, 1, 5))
    ranks = [(r["year"], r["peakRank"], r["provisional"]) for r in rows[:3]]
    assert ranks == [(2019, 1, False), (2020, 1, True), (2021, 3, False)]


def test_warmest_day_needs_a_covered_summer() -> None:
    summer = [Daily(date(2019, 6, 1) + timedelta(days=k), 20.0 + (k == 40), False)
              for k in range(122)]  # fmt: skip
    short = [Daily(date(2020, 6, 1) + timedelta(days=k), 35.0, False) for k in range(30)]
    rows = climate.temperature_years(summer + short, date(2021, 3, 1))
    assert rows[0]["warmest"] == 21.0 and rows[0]["warmestDay"] == "2019-07-11"
    assert rows[0]["warmestRank"] == 1
    assert not rows[1]["complete"] and rows[1]["warmestRank"] is None


def test_the_snapshot_round_trips_and_the_summary_is_deterministic(tmp_path: Path) -> None:
    rows = [{"day": d.day.isoformat(), "parameter": "00060", "value": d.value,
             "approval": "Approved" if d.day.year < 2020 else "Provisional"}
            for d in year_of(2019, 1000.0) + year_of(2020, 900.0)[:10]]  # fmt: skip
    rows.append({"day": "2019-07-01", "parameter": "00010", "value": 27.5, "approval": "Approved"})
    path = tmp_path / "daily.csv"
    climate.write_snapshot(path, rows)
    snapshot = climate.read_snapshot(path)
    assert snapshot["00060"][0] == Daily(date(2019, 1, 1), 1000.0, False)
    assert snapshot["00060"][-1].provisional
    station = {"id": "USGS-1", "name": "A gauge"}
    doc = climate.summarise(snapshot, station)
    assert doc == climate.summarise(climate.read_snapshot(path), station)
    assert doc["through"] == "2020-01-10" and doc["discharge"]["rankedYears"] == 1
    assert doc["temperature"]["years"][0]["warmest"] == 27.5
    with pytest.raises(ReachError):
        climate.summarise({}, station)
