from pathlib import Path

import pytest

from climate_pipeline.validation.config import QuietnessConfig, load_validation_config
from climate_pipeline.validation.quietness import assess, share_rows, wilson
from climate_pipeline.validation.variants import VariantScene

ROOT = Path(__file__).parents[1]
CONFIG = load_validation_config(ROOT / "magdalena-validation.yaml")
RULE = QuietnessConfig(wilson_z=1.96, max_upper_bound=0.10, max_variant_share=0.10)


def scenes(anomalous: int, scored: int, insufficient: int = 0) -> list[VariantScene]:
    out = [
        VariantScene("scored", {"downstream": 4.0 if k < anomalous else 0.5}, {}, {},
                     ("downstream",) if k < anomalous else ())
        for k in range(scored)
    ]  # fmt: skip
    return out + [VariantScene("insufficient", {}, {}, {}, ()) for _ in range(insufficient)]


@pytest.mark.parametrize(
    ("k", "n", "low", "high"),
    [(0, 10, 0.0, 0.2775), (5, 10, 0.2366, 0.7634), (1, 112, 0.0016, 0.0489)],
)
def test_wilson_matches_published_values(k: int, n: int, low: float, high: float) -> None:
    a, b = wilson(k, n)
    assert a == pytest.approx(low, abs=1e-4) and b == pytest.approx(high, abs=1e-4)


def test_wilson_without_scenes_is_undefined() -> None:
    low, high = wilson(0, 0)
    assert low != low and high != high


def test_share_rows_report_every_variant_with_its_interval() -> None:
    evaluations = {v.id: scenes(1, 50, insufficient=3) for v in CONFIG.variants}
    rows = share_rows("reach", "frozen", evaluations, CONFIG.variants, 1.96)
    assert [r["variant"] for r in rows] == [v.id for v in CONFIG.variants]
    assert rows[0]["scored"] == 50 and rows[0]["anomalous"] == 1 and rows[0]["share"] == 0.02
    assert rows[0]["wilson_low"] < 0.02 < rows[0]["wilson_high"]


def test_a_reach_is_quiet_only_when_every_part_of_the_rule_holds() -> None:
    quiet = {v.id: scenes(1, 112) for v in CONFIG.variants}
    control = {v.id: scenes(3, 51) for v in CONFIG.variants}
    reading = assess(quiet, control, CONFIG.variants, RULE)
    assert reading.quiet and reading.reasons == ()
    assert reading.comparison == "not distinguishable from the control"

    one_noisy_variant = {**quiet, "B3": scenes(13, 112)}
    reading = assess(one_noisy_variant, control, CONFIG.variants, RULE)
    assert not reading.quiet and reading.worst_variant == "B3"
    assert "variant B3" in reading.reasons[0]

    small_sample = {v.id: scenes(1, 20) for v in CONFIG.variants}
    reading = assess(small_sample, control, CONFIG.variants, RULE)
    assert not reading.quiet and "upper bound" in reading.reasons[0]


def test_the_comparison_with_the_control_uses_the_intervals() -> None:
    target = {v.id: scenes(0, 300) for v in CONFIG.variants}
    noisy = {v.id: scenes(30, 100) for v in CONFIG.variants}
    assert assess(target, noisy, CONFIG.variants, RULE).comparison == "lower than the control"
    assert assess(noisy, target, CONFIG.variants, RULE).comparison == "higher than the control"
    assert assess(target, None, CONFIG.variants, RULE).comparison == "control unavailable"


def test_the_magdalena_settings_are_a_baseline_validation_and_urra_keeps_its_defaults() -> None:
    assert CONFIG.kind == "baseline" and CONFIG.sites.reference is None
    assert CONFIG.quietness is not None and CONFIG.injection is not None
    assert CONFIG.demo_event is not None and CONFIG.insitu is not None
    assert [v.id for v in CONFIG.variants] == [
        "D0", "B1", "B2", "B3", "B4", "B5", "Z2.5", "Z3.5", "G1", "G2"
    ]  # fmt: skip
    urra = load_validation_config(ROOT / "urra-validation.yaml")
    assert urra.kind == "signal" and urra.title == "Urrá validation"
    assert urra.variants == CONFIG.variants and urra.quietness is None
    assert "urrá" in urra.context.forbidden_names


def test_a_baseline_validation_needs_its_sections() -> None:
    data = CONFIG.model_dump()
    data["quietness"] = None
    with pytest.raises(ValueError, match="baseline"):
        type(CONFIG).model_validate(data)
