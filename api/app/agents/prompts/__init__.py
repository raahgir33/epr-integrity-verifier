"""Static agent-loop instruction text (docs/ARCHITECTURE.md §4), one file
per orchestrator step. Reviewed in full before any real Gemini call — see
docs/PROGRESS.md's T10 entry. Each is pure instruction text: general audit
principles plus the sourced domain facts already cited in
docs/DATA_SPEC.md, never the internal F1-F8/H1-H4 taxonomy and never a
processor or shipment ID. Dynamic context (the context pack, dossier
digest, objections) is appended by orchestrator.py as separate content
after this text, not interpolated into it.
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent

HYPOTHESIS_PROMPT = (_PROMPTS_DIR / "hypothesis.txt").read_text(encoding="utf-8")
CRITIC_TOOLS_PROMPT = (_PROMPTS_DIR / "critic_tools.txt").read_text(encoding="utf-8")
CRITIC_FINAL_PROMPT = (_PROMPTS_DIR / "critic_final.txt").read_text(encoding="utf-8")
REVISION_PROMPT = (_PROMPTS_DIR / "revision.txt").read_text(encoding="utf-8")
