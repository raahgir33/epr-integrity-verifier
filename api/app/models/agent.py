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


class MemoItem(BaseModel):
    """One item in a ClarificationMemo (app/agents/memo.py). evidence_ids
    is filtered to a code-supplied allow-list after the call (the
    evidence-ID subset guard) — an item left with none is dropped."""

    heading: str
    what_we_observed: str
    evidence_ids: list[str] = []
    what_we_request: str


class ClarificationMemo(BaseModel):
    """A neutral clarification-request letter drafted for a flagged
    processor (docs/ARCHITECTURE.md's generative-deliverable feature,
    app/agents/memo.py). The model fills every field here; every number
    it writes is checked against a code-supplied allow-list before use
    (the number guard) and every evidence_ids entry is checked against a
    code-supplied allow-list (the evidence-ID subset guard) — see
    app/agents/memo.py's docstring for the full guard sequence.
    sender_line/doc_type/lang/guard_status are NOT part of this schema —
    they're bookkeeping the API/pipeline attach outside the Gemini call."""

    subject: str
    salutation: str
    opening_paragraph: str
    items: list[MemoItem] = []
    response_deadline_days: int
    closing_paragraph: str


class ImprovementObservation(BaseModel):
    """One observation in a VerificationStatement's Part B (app/agents/
    memo.py). kind/measured/threshold/evidence_ids are set by code from
    measured data only; recommendation is the only model-written field,
    one sentence, no new fact or number beyond what's given."""

    kind: Literal["near_threshold", "documentation_gap", "consent_expiry", "soft_note"]
    measured: float | None = None
    threshold: float | None = None
    evidence_ids: list[str] = []
    recommendation: str


class VerificationStatement(BaseModel):
    """A verification statement & improvement roadmap for a clean
    processor (app/agents/memo.py) — the complement to ClarificationMemo;
    every processor resolves to exactly one of the two documents. Part A
    is part_a_paragraph (model-written, number-guarded, around code-
    computed figures passed in the prompt); Part B is observations
    (code-derived, model writes only each recommendation sentence) or
    no_items_note (set by code, never requested from Gemini, when
    observations is empty — nothing for the model to hallucinate into
    existence)."""

    subject: str
    salutation: str
    part_a_paragraph: str
    observations: list[ImprovementObservation] = []
    no_items_note: str | None = None
    closing_paragraph: str
