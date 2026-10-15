"""Code-level sanity guard for model-authored free text (T17).

Same discipline as app/agents/memo.py's number guard: the model's prose
is never trusted raw where a viewer will read it. This one catches
**degenerate repetition** — a generation that falls into a loop and
emits the same fragment hundreds of times.

Found live, 2026-10-15, on PWP-03's first run with the demo documents
restored. The Hypothesis agent tried to quote the weighbridge slip's
handwritten Devanagari remark in its own explanation, mis-transliterated
it, and then repeated the mis-transliteration ~170 times: a 3,012-character
explanation whose first 80 and last 90 characters were correct English and
whose middle was a loop. Extraction was clean (`remarks` came back as the
correct 14-character "माल नहीं उतारा"), and the Critic quoted it correctly
in its own verdict, so this is purely a generation pathology on one call.

The agent prompts and app/agents/orchestrator.py are frozen, so neither
the generation nor the retry policy can be changed. Guarding the text is
the available fix, and it is the right layer anyway: the raw trail stays
faithful in `agent_runs` (what the model actually said, for the record)
while every read path presents something a person can read.

Deliberately does NOT rewrite the model's quote. A mis-transliterated
remark stays mis-transliterated — correcting it would be the code putting
words in the model's mouth. Collapsing a loop to one occurrence is a
mechanical fix with no interpretation in it.
"""

# A repeated unit must be at least this long to count, so ordinary
# emphasis ("very very very") is never collapsed — its unit is 5
# characters including the space. The live failure's unit was 16.
_MIN_UNIT_CHARS = 6

# Three consecutive copies is already not prose.
_MIN_REPEATS = 3

# How long a unit to look for. The live failure's was 16; a loop over a
# whole clause could be longer, but beyond this the scan stops paying
# for itself.
_MAX_UNIT_CHARS = 120

# Backstop for a runaway that is long without being periodic. The
# longest legitimate explanation observed in this dataset is 273
# characters (PWP-03's Critic-raised electricity finding), so this has
# wide headroom and should never fire on real text.
_MAX_CHARS = 800

_ELLIPSIS = "…"


def _collapse_repeated_runs(text: str) -> str:
    """Collapses each maximal run of a consecutively repeated unit to a
    single occurrence.

    Scans unit lengths ascending so the *smallest* period that explains a
    run wins — "ababab" collapses to "ab", not "abab"."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        collapsed = False
        max_unit = min(_MAX_UNIT_CHARS, (n - i) // _MIN_REPEATS)
        for unit_len in range(_MIN_UNIT_CHARS, max_unit + 1):
            unit = text[i : i + unit_len]
            repeats = 1
            while text[i + repeats * unit_len : i + (repeats + 1) * unit_len] == unit:
                repeats += 1
            if repeats >= _MIN_REPEATS:
                out.append(unit)
                i += repeats * unit_len
                collapsed = True
                break
        if not collapsed:
            out.append(text[i])
            i += 1
    return "".join(out)


def _truncate_on_word_boundary(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    # Only back off to a space if one sits reasonably near the limit;
    # otherwise (a single enormous token) cut where the limit falls.
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip() + _ELLIPSIS


def clean_model_text(text: str | None) -> str | None:
    """Collapse degenerate repetition, then cap the length. None and the
    empty string pass straight through, so callers can hand over an
    optional field without checking it first.

    Idempotent: cleaning already-clean text returns it unchanged, which
    matters because the read path cleans the same stored trail on every
    cache rebuild."""
    if not text:
        return text
    return _truncate_on_word_boundary(_collapse_repeated_runs(text), _MAX_CHARS)
