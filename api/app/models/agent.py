"""Hypothesis / Critic / revision models for the agent loop
(app/agents/). Pure data, no I/O. See docs/ARCHITECTURE.md §4.
"""

from typing import Literal

from pydantic import BaseModel

HypothesisStatus = Literal["supported", "partly_supported", "unsupported"]

# docs/PROGRESS.md's objection-direction rule — required, no default: the
# Critic must say which kind of objection this is, not have it assumed.
# "raises_concern" identifies a problem (a candidate finding, subject to
# scoring/deduction); "resolves_concern" corrects an earlier Hypothesis
# conclusion that reads as over-harsh given the evidence — it stays in the
# reasoning trail (app/agents/orchestrator.py logs the Critic's full raw
# response before any filtering) but never counts as a finding.
ObjectionEffect = Literal["raises_concern", "resolves_concern"]


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
    effect: ObjectionEffect
    cited_shipment_ids: list[str] = []
    evidence_ids: list[str] = []
    explanation: str


class HypothesisRevision(BaseModel):
    """The Hypothesis's accept/reject decision on ONE of the Critic's own
    newly-raised findings. objection_index is the 0-indexed position in
    that (filtered) Objection list — orchestrator.py validates it's in
    range before use, same discipline as every other model-supplied
    ID in this module."""

    objection_index: int
    accepted: bool
    explanation: str


class CriticVerdict(BaseModel):
    """The Critic's verdict on ONE of the Hypothesis's own proposed
    findings (docs/PROGRESS.md's Hypothesis-findings restructure).
    hypothesis_finding_index is the 0-indexed position in the (filtered,
    reindexed) list of Hypothesis findings shown to the Critic —
    orchestrator.py validates it's in range before use."""

    hypothesis_finding_index: int
    verdict: Literal["upheld", "disputed"]
    reason: str


class HypothesisFindingResponse(BaseModel):
    """The Hypothesis's maintain/withdraw decision on ONE of its own
    findings that the Critic disputed (or never gave a verdict on —
    orchestrator.py treats that the same as disputed, since the Critic
    not addressing a Hypothesis finding is not evidence of agreement).
    hypothesis_finding_index matches CriticVerdict's own indexing."""

    hypothesis_finding_index: int
    decision: Literal["maintain", "withdraw"]
    explanation: str


class ConclusionsResponse(BaseModel):
    """Top-level wrapper for the Hypothesis agent's generate_structured
    call — Gemini structured output needs a single object at the top
    level, not a bare list. findings is the Hypothesis's own proposed
    findings (docs/PROGRESS.md), same shape as a Critic Objection — the
    Critic gives each one a verdict (CriticVerdict) rather than only
    ever objecting to batch-level conclusions."""

    conclusions: list[HypothesisConclusion] = []
    findings: list[Objection] = []


class ObjectionsResponse(BaseModel):
    """Top-level wrapper for the Critic's phase-2 (no-tools) call.
    verdicts covers the Hypothesis's own findings (upheld/disputed);
    objections is the Critic's own newly-raised findings, same as
    before this restructure."""

    verdicts: list[CriticVerdict] = []
    objections: list[Objection] = []


class RevisionsResponse(BaseModel):
    """Top-level wrapper for the Hypothesis revision call. revisions
    covers the Critic's own newly-raised findings (accept/reject), same
    as before this restructure; hypothesis_finding_responses covers the
    Hypothesis's own disputed (or unaddressed) findings (maintain/
    withdraw)."""

    revisions: list[HypothesisRevision] = []
    hypothesis_finding_responses: list[HypothesisFindingResponse] = []


class NarrativeSummary(BaseModel):
    """app/agents/scorer.py's plain-language summary of an assessment's
    computed numbers. The model writes prose only — every number in it is
    verified against the actual computed figures before use (the
    narrative guard); this schema has no numeric fields for the model to
    fill in itself."""

    summary: str
