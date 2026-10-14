import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { ProcessorTabs } from "@/components/processor/ProcessorTabs";
import { StickyHeader } from "@/components/processor/StickyHeader";
import {
  ApiError,
  getDocumentFacts,
  getProcessor,
  getProcessorDocuments,
  getProcessorMemo,
  getProcessorReasoning,
  getProcessorSite,
  type DocumentFactsResponse,
} from "@/lib/api";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  return {
    title: `Processor ${id}`,
    description: `Verification evidence, checks and findings for processor ${id}.`,
  };
}

export default async function ProcessorDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let processor, documents, reasoning, site, memoEn;
  try {
    [processor, documents, reasoning, site, memoEn] = await Promise.all([
      getProcessor(id),
      getProcessorDocuments(id),
      getProcessorReasoning(id),
      getProcessorSite(id),
      getProcessorMemo(id, "en"),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error; // anything else (API unreachable, 5xx) surfaces via app/error.tsx
  }
  // Amendment C (T13.5 plan): the Hindi memo is no longer fetched here —
  // ClarificationMemoLetter/VerificationStatementLetter fetch it lazily,
  // client-side, only once the viewer clicks the HI toggle.

  const facts = await Promise.all(
    documents.documents.map((d) => getDocumentFacts(d.doc_id).catch(() => null)),
  );
  const factsByDocId: Record<string, DocumentFactsResponse> = {};
  documents.documents.forEach((d, i) => {
    const f = facts[i];
    if (f) factsByDocId[d.doc_id] = f;
  });

  const knownDocIds = new Set(documents.documents.map((d) => d.doc_id));
  // Amendment A (T13.5 plan): certified_t always reads checks_only (the
  // figure is identical across stages); the "headline" stage for
  // verifiable_t/unverifiable_t/risk_band always prefers full, falling
  // back to checks_only — the same (full ?? checks_only) pattern
  // ProcessorsTable and StageComparison use, so the sticky header, the
  // rail and the Overview tab never disagree with each other.
  const stage = processor.full ?? processor.checks_only;

  return (
    <div className="space-y-6">
      <Link
        href="/"
        className="inline-flex items-center gap-1 text-sm text-ink-muted outline-none hover:text-ink focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        <ArrowLeft aria-hidden size={14} />
        Overview
      </Link>

      <StickyHeader
        profile={processor.profile}
        certifiedT={processor.checks_only.certified_t}
        stage={stage}
      />

      <ProcessorTabs
        processorId={id}
        checksOnly={processor.checks_only}
        full={processor.full}
        agentStatus={processor.agent_status}
        monthlyFlow={processor.monthly_flow}
        findings={processor.findings}
        checkResults={processor.check_results}
        reasoningSteps={reasoning.steps}
        documents={documents.documents}
        factsByDocId={factsByDocId}
        site={site}
        memoEn={memoEn}
        knownDocIds={knownDocIds}
      />
    </div>
  );
}
