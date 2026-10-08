import Link from "next/link";
import { notFound } from "next/navigation";
import { CheckResultRow } from "@/components/CheckResultRow";
import { DocumentsTable } from "@/components/DocumentsTable";
import { EmptyState } from "@/components/EmptyState";
import { FindingCard } from "@/components/FindingCard";
import { MonthlyFlowChart } from "@/components/MonthlyFlowChart";
import { ReasoningTimeline } from "@/components/reasoning/ReasoningTimeline";
import { RiskBadge } from "@/components/RiskBadge";
import { SitePanel } from "@/components/SitePanel";
import { StageComparison } from "@/components/StageComparison";
import {
  ApiError,
  getDocumentFacts,
  getProcessor,
  getProcessorDocuments,
  getProcessorReasoning,
  getProcessorSite,
  type DocumentFactsResponse,
} from "@/lib/api";
import { isDisplayedFinding } from "@/lib/findings";

export default async function ProcessorDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let processor, documents, reasoning, site;
  try {
    [processor, documents, reasoning, site] = await Promise.all([
      getProcessor(id),
      getProcessorDocuments(id),
      getProcessorReasoning(id),
      getProcessorSite(id),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error; // anything else (API unreachable, 5xx) surfaces via app/error.tsx
  }

  const facts = await Promise.all(
    documents.documents.map((d) => getDocumentFacts(d.doc_id).catch(() => null)),
  );
  const factsByDocId: Record<string, DocumentFactsResponse> = {};
  documents.documents.forEach((d, i) => {
    const f = facts[i];
    if (f) factsByDocId[d.doc_id] = f;
  });

  const knownDocIds = new Set(documents.documents.map((d) => d.doc_id));
  const displayedFindings = processor.findings.filter(isDisplayedFinding);
  const stage = processor.full ?? processor.checks_only;

  return (
    <div className="space-y-10">
      <div>
        <Link href="/" className="text-sm text-slate-500 hover:text-slate-900">
          ← Overview
        </Link>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
          <h1 className="font-display text-2xl font-semibold text-slate-900">
            {processor.profile.processor_id} — {processor.profile.name}
          </h1>
          <RiskBadge band={stage.risk_band} />
        </div>
        <p className="text-sm text-slate-500">{processor.profile.type}</p>
      </div>

      <section>
        <h2 className="font-display text-lg font-semibold text-slate-900">1. Summary</h2>
        <div className="mt-3">
          <StageComparison
            checksOnly={processor.checks_only}
            full={processor.full}
            agentStatus={processor.agent_status}
          />
        </div>
      </section>

      <section>
        <h2 className="font-display text-lg font-semibold text-slate-900">2. Monthly material flow</h2>
        <div className="mt-3">
          <MonthlyFlowChart rows={processor.monthly_flow} />
        </div>
      </section>

      <section>
        <h2 className="font-display text-lg font-semibold text-slate-900">3. Findings</h2>
        <div className="mt-3">
          {displayedFindings.length > 0 ? (
            <ul className="space-y-3">
              {displayedFindings.map((finding, i) => (
                <FindingCard key={i} finding={finding} knownDocIds={knownDocIds} />
              ))}
            </ul>
          ) : (
            <EmptyState
              title="No agent findings"
              message="The agent loop has not raised any findings for this processor."
            />
          )}
        </div>
      </section>

      <section>
        <h2 className="font-display text-lg font-semibold text-slate-900">4. Reasoning trail</h2>
        <div className="mt-3">
          <ReasoningTimeline steps={reasoning.steps} knownDocIds={knownDocIds} />
        </div>
      </section>

      <section>
        <h2 className="font-display text-lg font-semibold text-slate-900">5. Checks</h2>
        <ul className="mt-3">
          {processor.check_results.map((check) => (
            <CheckResultRow key={check.check_id} check={check} knownDocIds={knownDocIds} />
          ))}
        </ul>
      </section>

      <section>
        <h2 className="font-display text-lg font-semibold text-slate-900">6. Site</h2>
        <div className="mt-3">
          <SitePanel site={site} processorId={id} />
        </div>
      </section>

      <section>
        <h2 className="font-display text-lg font-semibold text-slate-900">7. Documents</h2>
        <div className="mt-3">
          <DocumentsTable documents={documents.documents} facts={factsByDocId} />
        </div>
      </section>
    </div>
  );
}
