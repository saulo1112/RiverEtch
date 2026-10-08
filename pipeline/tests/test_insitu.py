import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from climate_pipeline.validation import insitu
from climate_pipeline.validation.config import InsituConfig, load_validation_config

ROOT = Path(__file__).parents[1]
CONFIG = load_validation_config(ROOT / "magdalena-validation.yaml").insitu
assert CONFIG is not None
RULE: InsituConfig = CONFIG.model_copy(update={"min_pairs": 5, "bootstrap": 300})


def test_spearman_uses_average_ranks() -> None:
    assert insitu.spearman([1, 2, 3, 4], [1, 3, 2, 4]) == pytest.approx(0.8)
    assert insitu.spearman([1, 1, 2], [1, 2, 3]) == pytest.approx(math.sqrt(3) / 2)
    assert math.isnan(insitu.spearman([1, 2], [1, 2]))
    assert math.isnan(insitu.spearman([1, 1, 1], [1, 2, 3]))


def test_the_bootstrap_is_reproducible_and_brackets_rho() -> None:
    x = [float(k) for k in range(20)]
    y = [k + (3 if k % 4 == 0 else -2) * 1.5 for k in x]
    a = insitu.bootstrap_interval(x, y, 500, 1)
    assert a == insitu.bootstrap_interval(x, y, 500, 1)
    assert a[0] < insitu.spearman(x, y) <= a[1]


@pytest.mark.parametrize(
    ("n", "rho", "low", "high", "expected"),
    [
        (4, 0.9, 0.5, 1.0, "not enough data"),
        (12, math.nan, math.nan, math.nan, "not enough data"),
        (12, 0.6, 0.1, 0.9, "tracks"),
        (12, 0.6, -0.1, 0.9, "inconclusive"),
        (12, 0.1, -0.4, 0.39, "does not track"),
        (12, 0.3, -0.2, 0.7, "inconclusive"),
    ],
)
def test_the_reading_rule(n: int, rho: float, low: float, high: float, expected: str) -> None:
    assert insitu.reading(n, rho, low, high, RULE.model_copy(update={"min_pairs": 10})) == expected


def scene(day: date, up: float, down: float, red: float = 0.05) -> insitu.SceneValue:
    when = datetime(day.year, day.month, day.day, 15, 30, tzinfo=UTC)
    return insitu.SceneValue(f"S2_{day:%Y%m%d}", when, up, down, red, red)


def test_the_reach_value_is_the_mean_of_the_measured_sub_reaches() -> None:
    assert scene(date(2022, 1, 1), 0.1, 0.3).ndti_reach == pytest.approx(0.2)
    assert scene(date(2022, 1, 1), math.nan, 0.3).ndti_reach == pytest.approx(0.3)
    assert math.isnan(scene(date(2022, 1, 1), math.nan, math.nan).ndti_reach)


def test_samples_match_the_nearest_scene_within_the_window() -> None:
    scenes = [scene(date(2022, 1, d), 0.0, 0.0) for d in (1, 5, 9)]
    samples = [
        insitu.Sample("s", date(2022, 1, 3), "TURBIDEZ", 10.0, "NTU", False),  # tie: earlier scene
        insitu.Sample("s", date(2022, 1, 6), "TURBIDEZ", 10.0, "NTU", False),
        insitu.Sample("s", date(2022, 1, 20), "TURBIDEZ", 10.0, "NTU", False),  # too far
    ]
    pairs = insitu.match_samples(samples, scenes, 2)
    assert [(p[1].key, p[2]) for p in pairs] == [("S2_20220101", 2), ("S2_20220105", 1)]


def test_the_level_is_the_mean_inside_the_window_with_enough_observations() -> None:
    t0 = datetime(2024, 11, 1, 15, 0, tzinfo=UTC)
    series = [(t0 + timedelta(hours=h), float(h)) for h in range(-20, 21, 4)]
    assert insitu.level_at(series, t0, 12, 3) == pytest.approx(0.0)
    assert math.isnan(insitu.level_at(series, t0, 2, 3))
    assert insitu.percentile_rank([1.0, 2.0, 3.0, math.nan], 2.0) == pytest.approx(2 / 3)
    assert math.isnan(insitu.percentile_rank([], 1.0))


def test_saturation_reads_the_upper_half_of_red_reflectance() -> None:
    days = [date(2022, 1, 1) + timedelta(days=k) for k in range(40)]
    linear = [scene(d, 0.01 * k, 0.01 * k, red=0.02 + 0.002 * k) for k, d in enumerate(days)]
    capped = [min(0.01 * k, 0.2) + (0.001 if k % 2 else 0.0) for k in range(len(days))]
    flat = [
        scene(d, v, v, red=0.02 + 0.002 * k)
        for k, (d, v) in enumerate(zip(days, capped, strict=True))
    ]
    assert {r["reading"] for r in insitu.saturation_rows(linear, RULE)} == {
        "responds across the range"
    }
    assert {r["reading"] for r in insitu.saturation_rows(flat, RULE)} == {
        "flattens at high red reflectance"
    }
    assert insitu.saturation_rows(linear[:6], RULE)[0]["reading"] == "not enough data"


def socrata(rows: list[dict[str, str]], seen: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=rows)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_quality_samples_parse_commas_and_censored_values_and_are_cached(tmp_path: Path) -> None:
    rows = [
        {"nombre_del_punto_de_monitoreo": "X [23187010]", "fecha": "2022-03-02T00:00:00.000",
         "propiedad_observada": "TURBIDEZ", "resultado": "35,5", "unidad_del_resultado": "NTU"},
        {"nombre_del_punto_de_monitoreo": "X [23187010]", "fecha": "2022-09-02T00:00:00.000",
         "propiedad_observada": "SOLIDOS SUSPENDIDOS TOTALES", "resultado": "<10",
         "unidad_del_resultado": "mg/L"},
        {"nombre_del_punto_de_monitoreo": "X [23187010]", "fecha": "2022-10-02T00:00:00.000",
         "propiedad_observada": "TURBIDEZ", "resultado": "n.d.", "unidad_del_resultado": "NTU"},
    ]  # fmt: skip
    seen: list[httpx.Request] = []
    station = CONFIG.quality_stations[0]
    samples, digest = insitu.quality_samples(socrata(rows, seen), CONFIG, station, tmp_path)
    assert [(s.day, s.variable, s.value, s.censored) for s in samples] == [
        (date(2022, 3, 2), "TURBIDEZ", 35.5, False),
        (date(2022, 9, 2), "SOLIDOS SUSPENDIDOS TOTALES", 10.0, True),
    ]
    assert "23187010" in seen[0].url.params["$where"]
    assert len(digest) == 64
    again, digest2 = insitu.quality_samples(socrata([], seen), CONFIG, station, tmp_path)
    assert again == samples and digest2 == digest and len(seen) == 1


def test_levels_are_read_as_local_time(tmp_path: Path) -> None:
    rows = [
        {"fechaobservacion": f"2024-11-01T{h}:00:00.000", "valorobservado": v, "unidadmedida": "mt"}
        for h, v in (("10", "5.2"), ("11", ""))
    ]
    seen: list[httpx.Request] = []
    station = CONFIG.level_stations[0]
    series, unit, _ = insitu.level_series(
        socrata(rows, seen), CONFIG, station, date(2024, 11, 1), date(2024, 11, 2), tmp_path
    )
    assert unit == "mt" and len(series) == 1
    assert series[0][0].astimezone(UTC) == datetime(2024, 11, 1, 15, 0, tzinfo=UTC)
    assert "0023187010" in seen[0].url.params["$where"]


def test_compare_drops_missing_pairs() -> None:
    x = [0.1, 0.2, math.nan, 0.4, 0.5, 0.6, 0.7]
    y = [1.0, 2.0, 3.0, math.nan, 5.0, 6.0, 7.0]
    row = insitu.compare("test", x, y, RULE)
    assert row["pairs"] == 5 and row["spearman"] == 1.0 and row["reading"] == "tracks"
