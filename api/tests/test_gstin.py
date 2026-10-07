import random

from scripts.dossier_gen.gstin import _real_check_digit, generate_invalid_gstin


def test_generated_gstin_has_correct_shape_and_wrong_checksum():
    rng = random.Random(0)
    for _ in range(50):
        gstin = generate_invalid_gstin(rng, state_code="27")
        assert len(gstin) == 15
        assert gstin[:2] == "27"
        real_digit = _real_check_digit(gstin[:14])
        assert gstin[14] != real_digit


def test_generate_invalid_gstin_uses_the_given_state_code():
    rng = random.Random(0)
    assert generate_invalid_gstin(rng, state_code="33")[:2] == "33"


def test_generate_invalid_gstin_is_deterministic_for_a_given_rng_state():
    assert generate_invalid_gstin(random.Random(42), state_code="27") == generate_invalid_gstin(
        random.Random(42), state_code="27"
    )
