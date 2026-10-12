import math
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from test_quality_route_a import CFG, pair, scene

from climate_pipeline.calibration.matchups import Pair, Sample
from climate_pipeline.quality import posthoc, route_a


def test_the_held_out_station_never_trains_or_selects() -> None:
    pool = [pair(f"s{k % 4}", 10.0 + k) for k in range(16)]
    seen: list[set[str]] = []

    def spy(train: Sequence[Pair], test: Sequence[Pair]) -> list[float]:
        seen.append({p.station for p in train} & {p.station for p in test})
        return [1.0] * len(test)

    result = posthoc.nested(CFG, pool, {"P1": spy})
    assert seen and all(not overlap for overlap in seen)
    assert set(result.chosen) == {"s0", "s1", "s2", "s3"}


def test_the_simpler_candidate_wins_within_five_points() -> None:
    assert posthoc.choose({"P1": 54.0, "P3": 50.0}, 5.0) == "P1"
    assert posthoc.choose({"P1": 56.0, "P3": 50.0}, 5.0) == "P3"
    assert posthoc.choose({"P1": math.nan}, 5.0) == "P1"


def test_december_opens_the_next_hydrological_year() -> None:
    assert posthoc.hydrological_year(pair("s", 1.0, day=date(2020, 12, 5))) == "2021"
    assert posthoc.hydrological_year(pair("s", 1.0, day=date(2021, 11, 30))) == "2021"


def test_a_clean_magdalena_relation_reaches_estimated_post_hoc() -> None:
    samples, scenes, stream_of = [], [], {}
    rng = np.random.default_rng(5)
    for s in range(6):
        station = f"magdalena{s}"
        stream_of[station] = "MAGDALENA"
        for k in range(8):
            day = date(2019, 1, 1) + timedelta(days=37 * k + s)
            ratio = float(rng.uniform(0.2, 1.2))
            value = 300 * ratio**2 * float(np.exp(rng.normal(0, 0.08)))
            samples.append(Sample(station, day, "turbidity", value, False))
            scenes.append(scene(station, day, ratio))
    ci = route_a.ColombianInputs([], samples, {"300m": scenes, "core": scenes}, {}, stream_of)
    tables = posthoc.analyse(CFG, ci, False, None, Path())
    main = next(r for r in tables["posthoc_scores"] if r["target"] == "turbidity"
                and r["variant"] == "main" and r["evaluation"] == "nested LOSO")  # fmt: skip
    assert main["n"] == 48 and main["mdsa"] < 15 and main["level"] == "estimated"
    (card,) = tables["_posthoc_cards"]
    assert card["basis"] == posthoc.BASIS and card["modelId"].endswith(":posthoc")
    assert card["candidate"] == "P1" and card["levels"][0]["level"] == "estimated"
    assert posthoc.summary(tables)["turbidity"]["level"] == "estimated (post hoc)"
    tss = [r for r in tables["posthoc_scores"] if r["target"] == "tss"]
    assert tss and all(r.get("status") == "insufficient_data" for r in tss)
