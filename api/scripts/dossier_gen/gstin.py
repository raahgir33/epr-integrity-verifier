"""Synthetic GSTIN generator.

Produces 15-character, GSTIN-shaped strings (correct structure: state code,
PAN-like body, entity code, default 'Z', check digit) with a deliberately
WRONG check digit, so none can ever collide with a real registered GSTIN —
all project data must be clearly unable to match real taxpayers.
"""

import random

_CODEPOINTS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_MOD = 36
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_DIGITS = "0123456789"

# Real Indian state GSTIN codes — public information, used only so the
# fictional prefix looks plausible.
STATE_CODES = ["27", "24", "29", "33", "36", "08", "06", "23", "21", "19"]


def _real_check_digit(prefix: str) -> str:
    """The actual public GSTIN mod-36 check-digit algorithm.

    Used only to know which character to avoid — generate_invalid_gstin
    never emits this one.
    """
    factor = 2
    checksum = 0
    for char in reversed(prefix):
        code_point = _CODEPOINTS.index(char)
        digit = factor * code_point
        digit = (digit // _MOD) + (digit % _MOD)
        checksum += digit
        factor = 1 if factor == 2 else 2
    return _CODEPOINTS[(_MOD - (checksum % _MOD)) % _MOD]


def generate_invalid_gstin(rng: random.Random) -> str:
    """A GSTIN-shaped string with a deliberately incorrect check digit."""
    state_code = rng.choice(STATE_CODES)
    pan_letters = "".join(rng.choice(_LETTERS) for _ in range(5))
    pan_digits = "".join(rng.choice(_DIGITS) for _ in range(4))
    pan_check_letter = rng.choice(_LETTERS)
    entity_code = rng.choice("123456789")
    prefix = f"{state_code}{pan_letters}{pan_digits}{pan_check_letter}{entity_code}Z"

    real_digit = _real_check_digit(prefix)
    wrong_digit = _CODEPOINTS[(_CODEPOINTS.index(real_digit) + 1) % _MOD]
    return prefix + wrong_digit
