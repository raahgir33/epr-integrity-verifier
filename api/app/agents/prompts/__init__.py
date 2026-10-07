"""Static agent-loop instruction text (docs/ARCHITECTURE.md §4), one file
per orchestrator step. Reviewed in full before any real Gemini call — see
docs/PROGRESS.md's T10 entry. Each is pure instruction text: general audit
principles plus the sourced domain facts already cited in
docs/DATA_SPEC.md, never the internal F1-F8/H1-H4 taxonomy and never a
processor or shipment ID. Dynamic context (the context pack, dossier
digest, objections) is appended by orchestrator.py as separate content
after this text, not interpolated into it.

red_flags.txt is a single shared fragment appended to both the Hypothesis
and Critic (tool-loop) prompts below — one place to edit the red-flag
list, not two independently-maintained copies.
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


_RED_FLAGS = _read("red_flags.txt")

HYPOTHESIS_PROMPT = _read("hypothesis.txt") + "\n" + _RED_FLAGS
CRITIC_TOOLS_PROMPT = _read("critic_tools.txt") + "\n" + _RED_FLAGS
CRITIC_FINAL_PROMPT = _read("critic_final.txt")
REVISION_PROMPT = _read("revision.txt")
