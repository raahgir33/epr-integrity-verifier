// Shapes of ReasoningStepOut.output per step_type, from
// api/app/models/agent.py and api/app/store/cache.py's _compute_reasoning_
// steps/score-step construction — the OpenAPI schema types `output` as a
// loose object (it varies by step_type), so these are hand-written to match
// the real backend shapes, not generated.

export type HypothesisConclusion = {
  certificate_batch: string;
  status: "supported" | "partly_supported" | "unsupported";
  evidence_ids: string[];
  explanation: string;
};

export type ProposedFinding = {
  finding_type: string;
  effect: "raises_concern" | "resolves_concern";
  cited_shipment_ids: string[];
  evidence_ids: string[];
  explanation: string;
};

export type HypothesisOutput = {
  conclusions: HypothesisConclusion[];
  findings: ProposedFinding[];
};

export type CriticVerdict = {
  hypothesis_finding_index: number;
  verdict: "upheld" | "disputed";
  reason: string;
};

export type CriticFinalOutput = {
  verdicts: CriticVerdict[];
  objections: ProposedFinding[];
};

export type RevisionDecision = {
  objection_index: number;
  accepted: boolean;
  explanation: string;
};

export type HypothesisFindingResponse = {
  hypothesis_finding_index: number;
  decision: "maintain" | "withdraw";
  explanation: string;
};

export type RevisionOutput =
  | { note: string }
  | { revisions: RevisionDecision[]; hypothesis_finding_responses: HypothesisFindingResponse[] };

export type DeductedShipment = { shipment_id: string; weighbridge_net_t: number | null };

export type ScoreOutput = {
  checks_only_verifiable_t: number | null;
  full_verifiable_t: number | null;
  deducted_shipments: DeductedShipment[];
  risk_band_before: string | null;
  risk_band_after: string | null;
};
