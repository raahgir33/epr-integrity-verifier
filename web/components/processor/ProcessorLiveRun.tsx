"use client";

import { useState } from "react";
import { RunLiveVerification } from "@/components/demo/RunLiveVerification";
import { ProcessorTabs } from "@/components/processor/ProcessorTabs";
import type {
  CheckResultOut,
  DemoBatchOut,
  DocumentFactsResponse,
  DocumentListItem,
  FindingOut,
  MemoResponse,
  MonthlyFlowRow,
  ReasoningStepOut,
  RunStatusOut,
  SiteResponse,
  StageAssessment,
} from "@/lib/api";

/** Owns the one piece of state RunLiveVerification and ProcessorTabs need
 * to share (T13.5b plan, Part 4): the active live run, if any, so the
 * docked reasoning panel/tab can mirror it live instead of only ever
 * showing the page-load-time snapshot. processors/[id]/page.tsx is a
 * Server Component and can't hold this itself, hence this thin client
 * wrapper around both siblings. */
export function ProcessorLiveRun({
  batches,
  processorId,
  checksOnly,
  full,
  agentStatus,
  monthlyFlow,
  findings,
  checkResults,
  reasoningSteps,
  documents,
  factsByDocId,
  site,
  memoEn,
  knownDocIds,
}: {
  batches: DemoBatchOut[];
  processorId: string;
  checksOnly: StageAssessment;
  full: StageAssessment | null;
  agentStatus: string | null;
  monthlyFlow: MonthlyFlowRow[];
  findings: FindingOut[];
  checkResults: CheckResultOut[];
  reasoningSteps: ReasoningStepOut[];
  documents: DocumentListItem[];
  factsByDocId: Record<string, DocumentFactsResponse>;
  site: SiteResponse;
  memoEn: MemoResponse | null;
  knownDocIds: ReadonlySet<string>;
}) {
  const [liveRun, setLiveRun] = useState<RunStatusOut | null>(null);

  return (
    <>
      {/* {batches.length > 0 ? (
        <div id="live-verification" className="scroll-mt-20">
          <RunLiveVerification batches={batches} onRunUpdate={setLiveRun} />
        </div>
      ) : null} */}

      <ProcessorTabs
        processorId={processorId}
        checksOnly={checksOnly}
        full={full}
        agentStatus={agentStatus}
        monthlyFlow={monthlyFlow}
        findings={findings}
        checkResults={checkResults}
        reasoningSteps={reasoningSteps}
        documents={documents}
        factsByDocId={factsByDocId}
        site={site}
        memoEn={memoEn}
        knownDocIds={knownDocIds}
        liveRun={liveRun}
      />
    </>
  );
}
