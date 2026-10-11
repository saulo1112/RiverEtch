import math
from datetime import date, timedelta
from pathlib import Path

from climate_pipeline.calibration.config import load_calibration_config
from climate_pipeline.calibration.matchups import Sample, SceneRow, candidate_values
from climate_pipeline.calibration.run import Inputs
from climate_pipeline.quality import route_b
from climate_pipeline.quality.config import load_quality_config

PIPELINE = Path(__file__).parents[1]
NECHAD = {("TUR", "B4"): (228.1, 0.1641), ("TUR", "B8A"): (3078.9, 0.2112),
          ("SPM", "B4"): (355.85, 0.1728)}  # fmt: skip
STATS = {"valid_px": 50.0, "contamination": 0.0, "b11_ok": 1.0, "glint_share": 0.0,
         "bands_read": 1.0}  # fmt: skip


def scene(station: str, day: date, red: float, nir: float, b11: float) -> SceneRow:
    bands = {"B02": 0.03, "B03": 0.05, "B04": red, "B05": red, "B06": nir, "B07": nir,
             "B08": nir, "B8A": nir, "B11": b11, "B12": b11 / 2}  # fmt: skip
    return SceneRow(station, "x", f"sentinel-2a_{day}_R025", day, "05.xx", STATS, bands,
                    candidate_values(bands, None))  # fmt: skip


def synthetic() -> route_b.RouteBInputs:
    """Ten stations, two samples each; NIR/red tracks turbidity under L2A and RAdCor.

    Under DSF the narrow stations' NIR is lifted (a bank signal), which breaks the ranks.
    """
    samples: list[Sample] = []
    scenes: dict[str, list[SceneRow]] = {"l2a-300m": [], "dsf-300m": [], "radcor-300m": []}
    widths: dict[str, float] = {}
    for s in range(10):
        station = f"s{s}"
        widths[station] = 160.0 if s < 4 else 400.0
        for k in range(2):
            day = date(2020, 1, 1) + timedelta(days=40 * (2 * s + k))
            turbidity = 20.0 * (1.35 ** (2 * s + k))
            red = 0.03 + 0.01 * math.log(turbidity)
            nir = red * min(1.2, 0.1 + 0.15 * math.log(turbidity))
            samples.append(Sample(station, day, "turbidity", turbidity, False))
            samples.append(Sample(station, day, "tss", 1.4 * turbidity, False))
            narrow = s < 4
            scenes["l2a-300m"].append(scene(station, day, red, nir, 0.01))
            scenes["dsf-300m"].append(scene(station, day, red, nir + (0.08 if narrow else 0),
                                            0.04 if narrow else 0.01))  # fmt: skip
            scenes["radcor-300m"].append(scene(station, day, red, nir, 0.012 if narrow else 0.01))
    inputs = Inputs(stations=[], samples=samples, scenes=scenes, extents=[], series={}, rain={},
                    chirps={}, oni=[], nechad=NECHAD, dogliotti_limits=(0.05, 0.07),
                    items={})  # fmt: skip
    d15 = load_calibration_config(PIPELINE / "calibration.yaml")
    mdn = {("dsf", p.station, f"sentinel-2a_{p.day}_R025"): p.value for p in samples
           if p.target == "tss"}  # fmt: skip
    return route_b.RouteBInputs(d15, inputs, mdn, widths)


def test_parse_mdn_keeps_finite_values() -> None:
    text = (
        "correction,station,key,local_date,valid_px,tss_mg_l\n"
        "dsf,a,k1,2020-01-01,30,12.5\n"
        "dsf,a,k2,2020-01-02,30,\n"
        "radcor,b,k3,d,1,nan\n"
    )
    assert route_b.parse_mdn(text) == {("dsf", "a", "k1"): 12.5}
    assert route_b.parse_mdn("") == {}


def test_bin_labels_name_open_ends() -> None:
    edges = (30.0, 100.0, 300.0, 1000.0)
    assert [route_b.bin_label(edges, k) for k in range(5)] == [
        "<30", "30-100", "100-300", "300-1000", ">=1000"]  # fmt: skip


def test_score_ignores_missing_estimates() -> None:
    row = route_b.score([10.0, math.nan, 0.0, 40.0], [10.0, 20.0, 30.0, 20.0], list("abcd"), 1,
                        200, 0.95)  # fmt: skip
    assert row["n"] == 2 and round(row["mdsa"], 6) == round(100 * (math.sqrt(2) - 1), 6)


def test_route_b_tables_compare_corrections_on_the_same_pairs() -> None:
    cfg = load_quality_config(PIPELINE / "water-quality.yaml")
    rb = synthetic()
    tables = route_b.analyse(cfg, rb)
    scores = tables["route_b_scores"]
    turbidity = [r for r in scores if r["target"] == "turbidity"]
    assert {r["correction"] for r in turbidity} == {"l2a", "dsf", "radcor"}
    assert len({r["n"] for r in turbidity if r["model"] == "B2 Nechad 2009"}) == 1
    mdn = [r for r in scores if r["model"] == "B3 MDN"]
    assert [r["correction"] for r in mdn] == ["dsf"] and mdn[0]["mdsa"] == 0
    rule = tables["route_b_adjacency"][-1]
    rows = {r["correction"]: r for r in tables["route_b_adjacency"][:-1]}
    assert rows["radcor"]["rho"] > 0.9 and rows["dsf"]["rho"] < rows["radcor"]["rho"]
    assert rows["radcor"]["median_b11_narrow"] < rows["dsf"]["median_b11_narrow"]
    assert rule["correction"] == "rule" and rule["confirmed"] is True
    assert route_b.summary(tables)["adjacency_confirmed"] is True


def test_adjacency_is_not_confirmed_when_b11_does_not_drop() -> None:
    cfg = load_quality_config(PIPELINE / "water-quality.yaml")
    rb = synthetic()
    rb.inputs.scenes["radcor-300m"] = [
        scene(s.station, s.day, s.bands["B04"], s.bands["B8A"], 0.05)
        for s in rb.inputs.scenes["radcor-300m"]
    ]
    assert route_b.adjacency(cfg, rb)[-1]["confirmed"] is False
