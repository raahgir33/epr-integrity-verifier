"""Hypothesis / Critic / revision models for the agent loop
(app/agents/). Pure data, no I/O. See docs/ARCHITECTURE.md §4.
"""

from typing import Literal

from pydantic import BaseModel

HypothesisStatus = Literal["supported", "partly_supported", "unsupported"]


class HypothesisConclusion(BaseModel):
    certificate_batch: str  # period_month, e.g. "2026-01"
    status: HypothesisStatus
    evidence_ids: list[str] = []
    explanation: str


class Objection(BaseModel):
    """A Critic finding. finding_type is a free descriptive label the
    model writes — never an internal F1-F8/H1-H4 code (prompts never
    mention that taxonomy; see app/agents/prompts/). Scoring against
    ground truth (scripts/probe_agent_thinking.py) works from
    cited_shipment_ids, never by matching this string."""

    finding_type: str
    cited_shipment_ids: list[str] = []
    evidence_ids: list[str] = []
    explanation: str


class HypothesisRevision(BaseModel):
    """One per Objection the Critic raised. objection_index is the
    0-indexed position in that Objection list — orchestrator.py validates
    it's in range before use, same discipline as every other model-supplied
    ID in this module."""

    objection_index: int
    accepted: bool
    explanation: str


class ConclusionsResponse(BaseModel):
    """Top-level wrapper for the Hypothesis agent's generate_structured
    call — Gemini structured output needs a single object at the top
    level, not a bare list."""

    conclusions: list[HypothesisConclusion] = []


class ObjectionsResponse(BaseModel):
    """Top-level wrapper for the Critic's phase-2 (no-tools) call."""

    objections: list[Objection] = []


class RevisionsResponse(BaseModel):
    """Top-level wrapper for the Hypothesis revision call."""

    revisions: list[HypothesisRevision] = []


class NarrativeSummary(BaseModel):
    """app/agents/scorer.py's plain-language summary of an assessment's
    computed numbers. The model writes prose only — every number in it is
    verified against the actual computed figures before use (the
    narrative guard); this schema has no numeric fields for the model to
    fill in itself."""

    summary: str
