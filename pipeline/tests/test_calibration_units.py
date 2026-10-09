import math
from datetime import date, timedelta
from pathlib import Path

import httpx
import numpy as np
import pytest

from climate_pipeline.calibration import climate, models, stations
from climate_pipeline.calibration.config import load_calibration_config
from climate_pipeline.calibration.matchups import (
    Sample,
    SceneRow,
    candidate_values,
    match,
    parse_value,
    reduce_replicates,
    split,
)

CFG = load_calibration_config(Path(__file__).parents[1] / "calibration.yaml")


# ----------------------------------------------------------------------------------------------
# Stations
# ----------------------------------------------------------------------------------------------


def test_names_codes_and_coordinates() -> None:
    assert stations.normalize("  Río Magdalena ") == "RIO MAGDALENA"
    assert stations.normalize("MAGDALENA") == "MAGDALENA"
    assert stations.normalize("MAGDALENA BZO.DE LOBA") != "MAGDALENA"
    assert stations.point_code("MAGDALENA_SAN_PUERTO WILCHES_PTO.WILCHES [23187010]") == "23187010"
    assert stations.point_code("NO CODE") is None
    assert stations.station_id("0023187010") == stations.station_id("23187010") == "23187010"
    assert stations.number("7,344") == pytest.approx(7.344) and math.isnan(stations.number("x"))
    # datos.gov.co's catalogue copy has latitude and longitude swapped: it is detected.
    assert stations.fix_lonlat(6.5006, -72.7392) == (-72.7392, 6.5006, True)
    assert stations.fix_lonlat(-73.9, 7.3) == (-73.9, 7.3, False)


def test_candidates_union_points_and_catalogue_stations() -> None:
    points = [
        {"nombre_del_punto_de_monitoreo": "X [23187010]", "corriente": "MAGDALENA",
         "latitud": "7,34", "longitud": "-73,90", "propiedad_observada": "TURBIDEZ",
         "n": "7", "first": "2021-07-28T00:00:00", "last": "2023-06-17T00:00:00"},
        {"nombre_del_punto_de_monitoreo": "X [23187010]", "corriente": "MAGDALENA",
         "latitud": "7,34", "longitud": "-73,90",
         "propiedad_observada": "SOLIDOS SUSPENDIDOS TOTALES", "n": "6",
         "first": "2021-07-28T00:00:00", "last": "2023-06-17T00:00:00"},
    ]  # fmt: skip
    catalog = [
        {"Codigo": "0023187010", "Nombre": "PUERTO WILCHES", "Longitud": "-73.905",
         "Latitud": "7.344", "Corriente": "Magdalena"},
        {"Codigo": "0021237010", "Nombre": "NARINO", "Longitud": "-74.838", "Latitud": "4.387",
         "Corriente": "MAGDALENA"},
        {"Codigo": "0099999999", "Nombre": "OTHER", "Longitud": "-74", "Latitud": "4",
         "Corriente": "CAUCA"},
    ]  # fmt: skip
    files = {"CM_D": {"0021237010": 100, "0099999999": 5}, "Q_MEDIA_D": {"0023187010": 9}}
    out = stations.candidates(points, catalog, files, "MAGDALENA",
                              ["TURBIDEZ", "SOLIDOS SUSPENDIDOS TOTALES"])  # fmt: skip
    assert [c.station_id for c in out] == ["21237010", "23187010"]
    pw = out[1]
    assert pw.coordinates_from == "catalog" and pw.lon == pytest.approx(-73.905)
    assert pw.sample_counts == {"TURBIDEZ": 7, "SOLIDOS SUSPENDIDOS TOTALES": 6}
    assert pw.files == {"Q_MEDIA_D": 9} and pw.code == "0023187010"
    assert out[0].files == {"CM_D": 100} and out[0].quality_point == ""


def test_bucket_listing_follows_continuation_tokens() -> None:
    pages = {
        None: b"<ListBucketResult xmlns='http://s3.amazonaws.com/doc/2006-03-01/'>"
        b"<IsTruncated>true</IsTruncated><NextContinuationToken>T</NextContinuationToken>"
        b"<Contents><Key>p/CM_D/0021237010-CM_D.csv</Key><Size>10</Size></Contents>"
        b"</ListBucketResult>",
        "T": b"<ListBucketResult xmlns='http://s3.amazonaws.com/doc/2006-03-01/'>"
        b"<IsTruncated>false</IsTruncated>"
        b"<Contents><Key>p/CM_D/0021097070-CM_D.csv</Key><Size>20</Size></Contents>"
        b"</ListBucketResult>",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=pages[request.url.params.get("continuation-token")])

    listing = stations.bucket_listing(
        httpx.Client(transport=httpx.MockTransport(handler)), "https://b.test", "p/"
    )
    assert stations.label_files(listing, "CM_D") == {"0021237010": 10, "0021097070": 20}
    assert stations.read_catalog("Codigo,Nombre\n1,Nariño\n".encode("latin-1"))[0]["Nombre"] == (
        "Nariño"
    )


def test_main_channel_snap_width_and_window() -> None:
    mask = np.zeros((60, 60), dtype=bool)
    mask[20:30, :] = True  # a channel 10 px wide
    mask[50:52, 50:52] = True  # a pond
    main = stations.largest_component(mask)
    assert main.sum() == 600 and not main[50, 50]
    # Pixel centres: the channel's middle rows sit 5 px from the first land row.
    assert stations.width_m(main, (20, 30), 15, 20.0) == pytest.approx(2 * 5 * 20)
    window = stations.window_mask(main, (25, 30), 5, 2)
    assert window.any() and not window[20, 30] and not window[29, 30]
    assert stations.disk((5, 5), (2, 2), 1).sum() == 5


# ----------------------------------------------------------------------------------------------
# Matchups
# ----------------------------------------------------------------------------------------------


def scene(station: str, day: date, valid: float = 50.0, **bands: float) -> SceneRow:
    b = {"B02": 0.04, "B03": 0.06, "B04": 0.08, "B05": 0.07, "B8A": 0.03, **bands}
    return SceneRow(station, "sentinel-2-l2a", f"s2_{day}", day, "05.xx",
                    {"valid_px": valid, "contamination": 0.0, "b11_ok": 1.0, "glint_share": 0.0},
                    b, candidate_values(b, None))  # fmt: skip


def test_values_replicates_and_matching_rules() -> None:
    assert parse_value("<10") == (10.0, True) and parse_value("35,5") == (35.5, False)
    d = date(2022, 3, 2)
    reduced = reduce_replicates([
        Sample("s", d, "tss", 10.0, False), Sample("s", d, "tss", 30.0, True),
        Sample("s", d, "turbidity", 5.0, False),
    ])  # fmt: skip
    tss = next(s for s in reduced if s.target == "tss")
    assert tss.value == 20.0 and tss.censored and tss.replicates == 2
    scenes = [scene("s", d - timedelta(days=1)), scene("s", d + timedelta(days=1)),
              scene("s", d, valid=5.0), scene("other", d)]  # fmt: skip
    pairs = match([Sample("s", d, "tss", 20.0, False)], scenes, 1, CFG.window)
    # The same-day scene has too few valid pixels; the tie goes to the earlier scene.
    assert len(pairs) == 1 and pairs[0].scene_day == d - timedelta(days=1)
    assert pairs[0].gap_days == 1
    assert match([Sample("s", d, "tss", 20.0, False)], scenes, 0, CFG.window) == []


def test_holdout_is_the_most_recent_share_with_ties_in_training() -> None:
    d = date(2022, 1, 1)
    pairs = match(
        [Sample("s", d + timedelta(days=k), "tss", 1.0 + k, False) for k in range(10)],
        [scene("s", d + timedelta(days=k)) for k in range(10)], 0, CFG.window,
    )  # fmt: skip
    cut, train, holdout = split(pairs, 0.3)
    assert cut == d + timedelta(days=6) and len(train) == 7 and len(holdout) == 3
    assert split([], 0.3) == (None, [], [])


def test_candidates_from_band_medians() -> None:
    values = candidate_values({"B02": 0.04, "B03": 0.06, "B04": 0.08, "B05": 0.1, "B8A": 0.02},
                              ((366.14, 0.19563), (3250.32, 0.21151)))  # fmt: skip
    assert values["NDTI"] == pytest.approx((0.08 - 0.06) / 0.14)
    assert values["B04/B02"] == pytest.approx(2.0) and values["B8A/B04"] == pytest.approx(0.25)
    # Red reflectance 0.08 is above the switch's upper limit: the NIR (B8A) model applies.
    assert values["D15switch"] == pytest.approx(models.nechad(0.02, 3250.32, 0.21151))
    assert math.isnan(candidate_values({}, None)["D15switch"])


# ----------------------------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------------------------


def power_law(n: int, noise: float, seed: int) -> tuple[list[dict[str, float]], list[float]]:
    rng = np.random.default_rng(seed)
    x = np.exp(rng.uniform(np.log(0.02), np.log(0.2), size=n))
    y = 5000 * x**1.5 * np.exp(rng.normal(scale=noise, size=n))
    return [{"B04": float(v), "B8A/B04": float(v) * 2} for v in x], y.tolist()


def test_ols_recovers_a_power_law_and_loo_is_honest() -> None:
    rows, values = power_law(40, 0.05, 1)
    fit = models.fit_model("m", "tss", rows, values, ["B04"])
    assert fit.transforms == ("log",) and fit.coefficients[1] == pytest.approx(1.5, abs=0.05)
    assert len(fit.loo_predictions) == 40
    assert fit.predict({"B04": 0.1}) == pytest.approx(5000 * 0.1**1.5, rel=0.05)
    assert math.isnan(fit.predict({"B04": -1.0}))
    card = fit.card("mg/L", {"loo_mdsa": 5.0})
    assert card["parametersHash"] == fit.card("mg/L", {"loo_mdsa": 9.0})["parametersHash"]


def test_calibration_passes_on_a_clean_relation_and_fails_on_noise() -> None:
    rows, values = power_law(40, 0.1, 2)
    good = models.calibrate("tss", rows[:30], values[:30], rows[30:], values[30:],
                            ["B04", "B8A/B04"], CFG.stage3)  # fmt: skip
    assert good.status == "passed" and good.chosen is not None
    assert good.metrics["holdout_mdsa"] < 50
    noisy_rows, noisy = power_law(40, 2.0, 3)
    rng = np.random.default_rng(4)
    shuffled = rng.permutation(noisy).tolist()
    bad = models.calibrate("tss", noisy_rows[:30], shuffled[:30], noisy_rows[30:], shuffled[30:],
                           ["B04"], CFG.stage3)  # fmt: skip
    assert bad.status == "failed" and bad.reasons
    few = models.calibrate("tss", rows[:30], values[:30], rows[30:33], values[30:33], ["B04"],
                           CFG.stage3)  # fmt: skip
    assert few.status == "insufficient_data"


def test_abstention_rules() -> None:
    rows, values = power_law(30, 0.05, 5)
    fit = models.fit_model("m", "tss", rows, values, ["B04"])
    ok = {"glint_share": 0.1, "contamination": 0.0, "valid_px": 50, "b11_ok": 1}
    low, high = fit.feature_range["B04"]
    inside = {"B04": (low + high) / 2}
    assert models.abstain_reason(fit, inside, ok, CFG.window) is None
    assert "outside" in str(models.abstain_reason(fit, {"B04": high * 2}, ok, CFG.window))
    assert "glint" in str(models.abstain_reason(fit, inside, {**ok, "glint_share": 0.6},
                                                CFG.window))  # fmt: skip
    assert "B11" in str(models.abstain_reason(fit, inside, {**ok, "b11_ok": 0}, CFG.window))
    assert models.uncertainty_band(100.0, 50.0) == pytest.approx((100 / 1.5, 150.0))


def test_published_models() -> None:
    assert models.nechad(0.05, 366.14, 0.19563) == pytest.approx(
        366.14 * 0.05 / (1 - 0.05 / 0.19563)
    )
    assert math.isnan(models.nechad(0.3, 366.14, 0.19563))
    red, nir = (228.1, 0.1641), (3078.9, 0.2112)
    assert models.dogliotti_switch(0.04, 0.01, red, nir) == pytest.approx(models.nechad(0.04, *red))
    assert models.dogliotti_switch(0.08, 0.02, red, nir) == pytest.approx(models.nechad(0.02, *nir))
    mid = models.dogliotti_switch(0.06, 0.02, red, nir)
    assert min(models.nechad(0.06, *red), models.nechad(0.02, *nir)) <= mid
    assert mid <= max(models.nechad(0.06, *red), models.nechad(0.02, *nir))


# ----------------------------------------------------------------------------------------------
# Climate
# ----------------------------------------------------------------------------------------------


def rainy_world(seed: int, driven: bool) -> tuple[list[tuple[date, float]], dict[date, float]]:
    rng = np.random.default_rng(seed)
    start = date(2018, 12, 1)
    rain = {start + timedelta(days=k): float(rng.gamma(0.6, 8.0)) for k in range(2700)}
    obs = []
    for k in range(40, 2700, 12):
        d = start + timedelta(days=k)
        season = 0.02 * math.sin(2 * math.pi * d.timetuple().tm_yday / 365.25)
        effect = 0.03 * math.log1p(sum(rain[d - timedelta(days=j)] for j in range(7))) if driven \
            else 0.0  # fmt: skip
        obs.append((d, season + effect + float(rng.normal(scale=0.004))))
    return obs, rain


def test_hydrological_years_and_rain_windows() -> None:
    assert climate.hydrological_year(date(2018, 12, 5), 12) == 2019
    assert climate.hydrological_year(date(2019, 11, 30), 12) == 2019
    daily = {date(2020, 1, k): 1.0 for k in range(1, 11)}
    assert climate.rain_sums(daily, date(2020, 1, 10), [1, 3]) == pytest.approx(
        [math.log1p(1), math.log1p(3)]
    )
    assert math.isnan(climate.rain_sums(daily, date(2020, 1, 2), [3])[0])


def test_5a_passes_when_rain_drives_the_signal_and_labels_follow_the_rule() -> None:
    obs, rain = rainy_world(1, driven=True)
    model = climate.fit_signal("delta", obs, rain, CFG.climate)
    assert model.status == "passed" and model.skill > 0.5
    noise_obs, noise_rain = rainy_world(2, driven=False)
    weak = climate.fit_signal("delta", noise_obs, noise_rain, CFG.climate)
    assert weak.status == "weak"
    day, value = obs[30]
    models_ = {"delta": model, "upstream": weak}
    ctx = climate.label([("delta", 4.0)], models_, day, {"delta": value}, 3.0)
    assert ctx["status"] == "passed" and ctx["label"] in ("explained_by_climate", "unexplained")
    far = climate.label([("delta", 4.0)], models_, day, {"delta": value + 1.0}, 3.0)
    assert far["label"] == "unexplained"
    assert climate.label([("upstream", 5.0)], models_, day, {}, 3.0)["label"] == "not_evaluated"
    assert climate.label([], {"delta": weak}, day, {}, 3.0)["label"] == "not_evaluated"
    assert climate.label([], models_, day, {}, 3.0)["label"] == "normal"


def test_oni_episodes_need_five_consecutive_seasons() -> None:
    text = "SEAS  YR   TOTAL   ANOM\n" + "\n".join(
        f"{s}  2020  27.0  {v}"
        for s, v in zip(climate.SEASON_CENTER, [0.6, 0.7, 0.8, 0.9, 1.0, 0.2, -0.6, -0.7, -0.8,
                                                -0.9, 0.0, 0.0], strict=True)
    )  # fmt: skip
    oni = climate.parse_oni(text)
    assert len(oni) == 12 and oni[0] == (2020, 1, 0.6)
    phases = climate.enso_months(oni, CFG.climate.enso)
    assert [phases[(2020, m)] for m in range(1, 6)] == ["el_nino"] * 5
    assert phases[(2020, 7)] == "neutral"  # four La Niña seasons are not enough
    assert climate.year_phases(phases, 12)[2020] == "neutral"


def test_enso_test_and_extent_flow() -> None:
    days = [date(2018, 12, 1) + timedelta(days=15 * k) for k in range(200)]
    phases = {(y, m): ("la_nina" if y in (2021, 2022) else "el_nino" if y == 2024 else "neutral")
              for y in range(2018, 2027) for m in range(1, 13)}  # fmt: skip
    values = [(d, 5.0 + (2.0 if d.year in (2021, 2022) else -2.0 if d.year == 2024 else 0.0))
              for d in days]  # fmt: skip
    res = climate.enso_test(values, phases, CFG.climate, 1, "greater")
    assert float(str(res["diff_la_nina_minus_el_nino"])) > 0
    episodes = res["episodes"]
    assert isinstance(episodes, list) and {e["outcome"] for e in episodes} == {"hit"}
    series = {d: 100.0 + 10 * k for k, d in enumerate(days)}
    extents = [(d, 1.0 + 0.1 * k) for k, d in enumerate(days)]
    flow = climate.extent_flow(extents, series, CFG.climate.width, 1)
    assert flow["n"] == 200 and float(flow["rho"]) == pytest.approx(1.0)


def test_mndwi_fallback_only_when_scl_fails_and_keeps_the_scl_outcome() -> None:
    from climate_pipeline.calibration import extract
    from climate_pipeline.screening.rio import Grid

    grid = Grid(32618, 20.0, 0.0, 0.0, 60, 60)
    narrow = np.zeros((60, 60), dtype=bool)
    narrow[28:31, :] = True  # 60 m: SCL saw a fragment of a turbid river
    wide = np.zeros((60, 60), dtype=bool)
    wide[20:40, :] = True  # 400 m under MNDWI
    st = CFG.stations
    scl = extract.evaluate_channel("s", grid, narrow, (29, 30), "scl", st)
    assert not scl.selected and "wide" in scl.reason
    calls: list[str] = []

    def mndwi() -> extract.StationGeometry:
        calls.append("mndwi")
        return extract.evaluate_channel("s", grid, wide, (29, 30), "mndwi", st)

    final = extract.with_fallback(scl, mndwi)
    assert final.selected and final.mask_source == "mndwi" and calls == ["mndwi"]
    assert not final.scl_selected and final.scl_reason == scl.reason
    assert final.scl_width_m == pytest.approx(scl.width_m)
    good = extract.evaluate_channel("s", grid, wide, (29, 30), "scl", st)
    kept = extract.with_fallback(good, mndwi)
    assert kept.mask_source == "scl" and kept.scl_selected and calls == ["mndwi"]
    far = extract.evaluate_channel("s", grid, wide, (0, 0), "scl", st)
    assert far.reason.startswith("no main channel") or far.selected
    empty = extract.evaluate_channel("s", grid, np.zeros((60, 60), dtype=bool), (1, 1), "scl", st)
    assert empty.reason == "no water"
