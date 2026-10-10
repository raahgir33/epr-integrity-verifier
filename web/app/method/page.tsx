import { RuleBasedChecksAccordion } from "@/components/method/RuleBasedChecksAccordion";
import { Heading } from "@/components/ui/Heading";
import { SectionTitle } from "@/components/ui/SectionTitle";

export default function MethodPage() {
  return (
    // Developer review note, 2026-10-10: the FullBleed/.band wrapper this
    // page used is gone — --color-page is now the same light-blue tint
    // .band used to apply, so the root layout's own background already
    // gives every page (including this one) that continuous colour with
    // no extra markup here.
    <div className="space-y-8">
      <div className="text-center">
        <Heading>Method</Heading>
        <p className="mx-auto mt-1 text-pretty text-sm text-ink-muted">
          How the agent loop reasons, the real limits placed on its output, what each deterministic
          check does, how verifiable tonnes are computed, and what this system does not (yet) prove.
        </p>
      </div>

        <section className="card p-5 text-center">
          <SectionTitle className="text-method-heading">Agent reasoning</SectionTitle>
          <div className="mt-2 space-y-2 text-pretty text-method-body text-ink-muted">
            <p>
              Deterministic checks catch what arithmetic and document fields can prove. The agent loop
              exists for what they can&apos;t: reading meaning in free text, connecting evidence across a
              whole dossier, and challenging a first conclusion before it&apos;s trusted. Both agents run on
              Gemini 3.5 Flash on Vertex AI with model-default thinking (no thinking config is sent), and
              each call has its own timeout and retry policy.
            </p>
            <p>
              A <strong className="text-ink">Hypothesis</strong> agent reads a compact digest of the
              processor&apos;s dossier (profile, consent terms, monthly material flow, every check result
              with its evidence, the site result, and every distinct inbound item description) and judges
              each certificate batch (calendar month) as supported, partly supported or unsupported, with
              its own proposed findings.
            </p>
            <p>
              A <strong className="text-ink">Critic</strong> agent then runs a tool-calling loop
              (inspecting check results, shipments, document facts, the site assessment, and reading a
              document&apos;s own bytes directly) to challenge or confirm the Hypothesis, then issues a
              verdict on every one of the Hypothesis&apos;s own findings and raises any new objections of
              its own.
            </p>
            <p>
              The Hypothesis then gets one revision round: it can accept or reject each Critic objection,
              and maintain or withdraw each of its own disputed findings.
            </p>
            <p>
              <strong className="text-ink">Two agents must agree before a finding is deducted.</strong>{" "}
              A finding neither agent disputes becomes a deduction. One they disagree on, or that the other
              agent never addressed, becomes a visible review flag instead. It&apos;s never a silent
              deduction, and never silently dropped.
            </p>
          </div>
        </section>

        <section className="card p-5 text-center">
          <SectionTitle className="text-method-heading">Guardrails</SectionTitle>
          <p className="mt-2 text-pretty text-method-body text-ink-muted">
            Real limits placed on AI output, enforced in code, never left to the prompt alone.
          </p>
          <div className="mt-4 space-y-4">
            <div>
              <p className="font-semibold text-method-body text-ink">Evidence and shipment IDs are validated</p>
              <p className="text-pretty text-method-body text-ink-muted">
                Every shipment and evidence ID a finding cites is checked against the processor&apos;s own
                verified documents and shipments, never taken on trust from the model.
              </p>
            </div>
            <div>
              <p className="font-semibold text-method-body text-ink">A finding counts only when both agents agree</p>
              <p className="text-pretty text-method-body text-ink-muted">
                The Hypothesis and Critic must independently concur before a finding is deducted.
              </p>
            </div>
            <div>
              <p className="font-semibold text-method-body text-ink">Processor-level evidence makes a finding review-only</p>
              <p className="text-pretty text-method-body text-ink-muted">
                A finding backed only by processor-level evidence, not evidence tied to the specific
                shipments it cites, is kept but not deducted.
              </p>
            </div>
            <div>
              <p className="font-semibold text-method-body text-ink">Findings citing most shipments become review flags</p>
              <p className="text-pretty text-method-body text-ink-muted">
                A finding touching more than half a processor&apos;s verified shipments is too broad to act
                on automatically, so it&apos;s flagged for review instead of deducted.
              </p>
            </div>
            <div>
              <p className="font-semibold text-method-body text-ink">No extra deduction for restating a failed check</p>
              <p className="text-pretty text-method-body text-ink-muted">
                A finding that only restates what a deterministic check already caught earns no second
                deduction and no second risk-band bump.
              </p>
            </div>
            <div>
              <p className="font-semibold text-method-body text-ink">Hard checks are final</p>
              <p className="text-pretty text-method-body text-ink-muted">
                No agent finding can overrule a failed hard check.
              </p>
            </div>
            <div>
              <p className="font-semibold text-method-body text-ink">Drafted documents are guarded, with a template fallback</p>
              <p className="text-pretty text-method-body text-ink-muted">
                Before a clarification memo or verification statement goes out, every number in it is
                checked against figures the system already computed, every evidence ID against the
                processor&apos;s own verified documents, and its wording against a short list of disallowed
                words. A failure triggers one corrective rewrite. If that still fails, a plain pre-written
                template is used instead, never a partially-edited model draft.
              </p>
            </div>
            <div>
              <p className="font-semibold text-method-body text-ink">The model never does arithmetic that matters</p>
              <p className="text-pretty text-method-body text-ink-muted">
                Every tonnage figure and the risk band are computed deterministically from the agents&apos;
                structured findings. The model only writes the plain-language narrative from numbers that
                are already computed.
              </p>
            </div>
          </div>
        </section>

        <section className="card p-5 text-center">
          <SectionTitle className="text-method-heading">Rule-Based Checks</SectionTitle>
          <p className="mt-2 text-pretty text-method-body text-ink-muted">
            Every threshold below lives in <code>app/checks/params.py</code>, each labelled as either
            rule-derived (cited to a regulation or document convention) or an explicit assumption. A
            failed <strong>hard</strong> check can never be overruled by an agent. A <strong>soft</strong>{" "}
            check can raise the risk band by at most one step.
          </p>
          <div className="mt-4">
            <RuleBasedChecksAccordion />
          </div>
        </section>

        <section className="card p-5 text-center">
          <SectionTitle className="text-method-heading">Verifiable tonnes and risk band</SectionTitle>
          <div className="mt-4 space-y-4">
            <div>
              <p className="font-semibold text-method-body text-ink">Verified inbound tonnes</p>
              <p className="text-pretty text-method-body text-ink-muted">
                Weighbridge-net tonnes of shipments that pass C3, C4 and C5, minus shipments an agreed
                agent finding deducts.
              </p>
            </div>
            <div>
              <p className="font-semibold text-method-body text-ink">Capacity limit</p>
              <p className="text-pretty text-method-body text-ink-muted">
                Consented capacity × months elapsed ÷ 12, zero for any month outside the consent&apos;s
                validity window (C6).
              </p>
            </div>
            <div>
              <p className="font-semibold text-method-body text-ink">Verifiable tonnes</p>
              <p className="text-pretty text-method-body text-ink-muted">
                The minimum of eligible certified tonnes (certified tonnes excluding any out-of-consent
                category), verified inbound tonnes, and the capacity limit.
              </p>
            </div>
            <div>
              <p className="font-semibold text-method-body text-ink">Unverifiable tonnes</p>
              <p className="text-pretty text-method-body text-ink-muted">
                Certified tonnes minus verifiable tonnes.
              </p>
            </div>
            <div>
              <p className="font-semibold text-method-body text-ink">Risk band</p>
              <p className="text-pretty text-method-body text-ink-muted">
                Low under 5% unverifiable, Medium 5–25%, High over 25%. Each failed soft check (C2b, C7,
                C8), or any non-empty review-flag, systemic-finding or no-own-evidence finding list,
                raises the band by one step. That&apos;s never more than one step in total, however many of
                these signals fire together.
              </p>
            </div>
          </div>
        </section>

        <section className="card p-5 text-center">
          <SectionTitle className="text-method-heading">Evaluation protocol</SectionTitle>
          <div className="mt-2 space-y-2 text-pretty text-method-body text-ink-muted">
            <p>
              A held-out test set, generated the same way as the development set but with a different seed,
              is never used while building or tuning the system. Before it is generated, every check
              threshold and every agent prompt is frozen (tagged <code>eval-freeze</code>) so nothing is
              tuned against it afterwards.
            </p>
            <p>
              The full pipeline (extraction, normalisation, checks, agents) runs once on the held-out set.
              Reported metrics: extraction field accuracy against the seeded ground truth, detection
              precision and recall against the seeded issue types, and the measured gain of the full system
              (checks plus agents) over deterministic checks alone. The{" "}
              <a href="/evaluation" className="underline decoration-dotted hover:text-primary">
                Evaluation
              </a>{" "}
              page reports these once the held-out run has completed. Development-set numbers, where shown
              anywhere, are always labelled as such.
            </p>
          </div>
        </section>

        <section className="card p-5 text-center">
          <SectionTitle className="text-method-heading">Limitations</SectionTitle>
          <div className="mt-2 space-y-2 text-pretty text-method-body text-ink-muted">
            <p>
              Every processor, document, brand and certificate shown here is synthetic and fictional. No
              real company, recycler or brand is represented or implicated.
            </p>
            <p>
              C3 (transport plausibility) is exercised only by hand-built test fixtures. No scenario in the
              seeded demonstration dataset trips it, so its behaviour on real documents is unproven here.
            </p>
            <p>
              Site coordinates are illustrative, rounded to two decimal places, with no street address
              shown. They should not be read as real locations.
            </p>
            <p>
              Open Buildings is a single snapshot from imagery processed in 2023. It does not reflect any
              construction or demolition since.
            </p>
          </div>
        </section>

        <section className="card p-5 text-center">
          <SectionTitle className="text-method-heading">Data sources and attribution</SectionTitle>
          <p className="mt-2 text-method-body text-ink-muted">Contains modified Copernicus Sentinel data (2023).</p>
          <p className="text-method-body text-ink-muted">Open Buildings v3, Google Research (CC BY 4.0).</p>
          <p className="text-method-body text-ink-muted">Hero imagery generated with Google Flow.</p>
        </section>
      </div>
  );
}
