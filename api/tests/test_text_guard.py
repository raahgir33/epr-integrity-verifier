"""T17: the degenerate-repetition guard on model-authored free text.

The headline case is real, reconstructed from its parts rather than
carried as a blob: on PWP-03's 2026-10-15 live run the Hypothesis agent
produced a 3,012-character explanation made of correct English wrapped
around 175 copies of one mis-transliterated fragment. Captured from GET
/processors/PWP-03 before the guard existed, and asserted below to
rebuild to exactly that length, so the reconstruction cannot drift from
what actually happened.
"""

from app.agents.text_guard import _MAX_CHARS, clean_model_text
from app.store import cache

_PREFIX = (
    "The weighbridge slip for shipment PWP-03-DEMO-SHP-001 contains a Hindi remark 'ठरे नहीं उतलररर "
)
# The looped fragment. Note the first copy, in the prefix above, begins
# "ठरे" where every later one begins "डरे" — the generation corrupted the
# glyph differently on its first pass, then settled into the loop.
_LOOP_UNIT = "डरे नहीं उतलररर "
_SUFFIX = (
    "' which translates to 'material not unloaded', indicating that the "
    "physical material was not received at the facility."
)
# 174 full copies, then one more without its trailing space before the
# closing quote.
REAL_GARBLED = _PREFIX + _LOOP_UNIT * 174 + _LOOP_UNIT.rstrip() + _SUFFIX

# What the model was trying to quote, as extraction actually read it.
CORRECT_REMARK = "माल नहीं उतारा"


def test_the_real_failure_collapses_to_a_readable_sentence():
    assert len(REAL_GARBLED) == 3012

    cleaned = clean_model_text(REAL_GARBLED)

    assert len(cleaned) < 300
    # The English on both sides of the loop survives intact — that is
    # where the finding's actual meaning lives.
    assert cleaned.startswith(
        "The weighbridge slip for shipment PWP-03-DEMO-SHP-001 contains a Hindi remark"
    )
    assert cleaned.endswith(
        "which translates to 'material not unloaded', indicating that the physical "
        "material was not received at the facility."
    )
    # Collapsed, not truncated: no ellipsis, because the repetition guard
    # got it under the cap on its own.
    assert "…" not in cleaned


def test_the_real_failures_repetition_is_gone():
    cleaned = clean_model_text(REAL_GARBLED)
    unit = "डरे नहीं उतलररर "
    assert REAL_GARBLED.count(unit) > 100
    assert cleaned.count(unit) <= 1


def test_the_guard_does_not_invent_a_correction():
    """Deliberate: the model mis-transliterated the remark, and the guard
    collapses the loop without fixing the glyphs. Correcting them would be
    the code putting words in the model's mouth — the Critic's own verdict
    carries the right text, and the UI shows it on the same card."""
    cleaned = clean_model_text(REAL_GARBLED)
    assert CORRECT_REMARK not in cleaned
    assert "उतलररर" in cleaned


def test_clean_text_is_untouched():
    # The Critic's real verdict from the same run.
    verdict = (
        "The weighbridge slip PWP-03-DEMO-WEIGHBRIDGE_SLIP-001 contains the remark "
        f"'{CORRECT_REMARK}' which translates to 'material not unloaded', confirming "
        "that the shipment was not received or unloaded at the facility."
    )
    assert clean_model_text(verdict) == verdict

    # And the other real finding from that run, the longest legitimate
    # explanation in the dataset.
    electricity = (
        "The electricity bill for March 2026 (PWP-03-ELECTRICITY_BILL-060) shows 0.00 kWh "
        "of units consumed, which means no processing activity (such as shipment "
        "PWP-03-DEMO-SHP-001) could have occurred at the facility during this period."
    )
    assert clean_model_text(electricity) == electricity


def test_ordinary_emphasis_is_not_collapsed():
    """The minimum unit length is 6 characters precisely so repeated
    short words survive — "very " is 5."""
    assert clean_model_text("This is very very very implausible.") == (
        "This is very very very implausible."
    )


def test_two_repeats_are_not_a_loop():
    text = "The remark appears twice: ABCDEFGH ABCDEFGH and then stops."
    assert clean_model_text(text) == text


def test_the_smallest_period_wins():
    assert clean_model_text("xy" * 60) == "xyxyxy"


def test_a_long_non_repeating_runaway_is_capped_on_a_word_boundary():
    text = " ".join(f"word{i}" for i in range(400))
    cleaned = clean_model_text(text)
    assert len(cleaned) <= _MAX_CHARS + 1  # +1 for the ellipsis
    assert cleaned.endswith("…")
    assert "  " not in cleaned


def test_the_guard_is_idempotent():
    """The read path cleans the same stored trail on every cache rebuild,
    so cleaning twice must not keep eroding the text."""
    once = clean_model_text(REAL_GARBLED)
    assert clean_model_text(once) == once


def test_empty_and_none_pass_through():
    assert clean_model_text(None) is None
    assert clean_model_text("") == ""


def test_the_tree_walker_cleans_nested_model_output():
    """app/store/cache.py applies the guard to a parsed model response at
    any depth — the hypothesis step's output is nested objects, not a
    bare string."""
    payload = {
        "findings": [
            {"explanation": REAL_GARBLED, "cited_shipment_ids": ["PWP-03-DEMO-SHP-001"]},
            {"explanation": "A short, clean finding.", "effect": "raises_concern"},
        ],
        "count": 2,
        "ok": True,
    }

    cleaned = cache._clean_model_text_tree(payload)

    assert len(cleaned["findings"][0]["explanation"]) < 300
    assert cleaned["findings"][1]["explanation"] == "A short, clean finding."
    # Non-string leaves survive unchanged, including inside lists.
    assert cleaned["count"] == 2
    assert cleaned["ok"] is True
    assert cleaned["findings"][0]["cited_shipment_ids"] == ["PWP-03-DEMO-SHP-001"]
