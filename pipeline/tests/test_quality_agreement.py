"""A recomputed output agrees with the committed one to its last printed digit, and no further."""

from climate_pipeline.quality import agreement


def test_identical_outputs_agree() -> None:
    text = '{\n  "a": -1.1986377044,\n  "n": 20\n}\n'
    assert agreement.disagreements(text, text) == []


def test_one_unit_in_the_last_printed_digit_agrees() -> None:
    committed = '{"a": -1.1986377044, "b": 1.3867997767, "q": 0.401126}'
    recomputed = '{"a": -1.1986377045, "b": 1.3867997766, "q": 0.401127}'
    assert agreement.disagreements(committed, recomputed) == []
    # A trailing zero is not printed: 0.1 rounded to three decimals may come out as 0.101.
    assert agreement.disagreements("mdsa,0.1\n", "mdsa,0.101\n") == []


def test_two_units_or_a_coarse_digit_do_not_agree() -> None:
    assert agreement.disagreements('{"a": 1.0000000001}', '{"a": 1.0000000003}') != []
    # One unit in a digit coarser than the third decimal is a real change.
    assert agreement.disagreements("mdsa,65.5\n", "mdsa,65.6\n") != []
    assert agreement.disagreements("q,0.1\n", "q,0.2\n") != []


def test_integers_and_text_must_match_exactly() -> None:
    assert agreement.disagreements('{"n": 20}', '{"n": 21}') == ["20 recomputed 21 (an integer)"]
    assert agreement.disagreements('{"candidate": "H3"}', '{"candidate": "H2"}') != []
    assert agreement.disagreements('{"level": "estimated"}', '{"level": "none"}') != []
    assert agreement.disagreements("a,1.5\n", "a,1.5\nb,2.5\n") != []


def test_digits_inside_names_and_hashes_are_text() -> None:
    committed = '{"log_B8A/B04": 0.79988, "sha": "6f6b654cd61b6e6e"}'
    assert agreement.disagreements(committed, committed.replace("B04", "B05")) != []
    assert agreement.disagreements(committed, committed.replace("6f6b654", "6f6b655")) != []


def test_exponents_count_their_last_digit() -> None:
    assert agreement.disagreements("x,1.2345e-07\n", "x,1.2346e-07\n") == []
    assert agreement.disagreements("x,1.2345e-07\n", "x,1.2347e-07\n") != []
