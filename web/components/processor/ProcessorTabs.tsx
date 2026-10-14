"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import type {
  CheckResultOut,
  DocumentFactsResponse,
  DocumentListItem,
  FindingOut,
  MemoResponse,
  MonthlyFlowRow,
  ReasoningStepOut,
  SiteResponse,
  StageAssessment,
} from "@/lib/api";
import { DocumentPanelProvider } from "@/lib/document-panel-context";
import { isDisplayedFinding } from "@/lib/findings";
import { useIsBreakpointUp } from "@/lib/useIsBreakpointUp";
import { Tabs } from "@/components/ui/Tabs";
import { SidePanel } from "@/components/ui/SidePanel";
import { StatTile } from "@/components/ui/StatTile";
import { CheckCard } from "@/components/processor/CheckCard";
import { ReasoningPanel } from "@/components/processor/ReasoningPanel";
import { DocumentsTable } from "@/components/DocumentsTable";
import { EmptyState } from "@/components/EmptyState";
import { FindingCard } from "@/components/FindingCard";
import { ClarificationMemoLetter } from "@/components/memo/ClarificationMemoLetter";
import { VerificationStatementLetter } from "@/components/memo/VerificationStatementLetter";
import { MonthlyFlowChart } from "@/components/MonthlyFlowChart";
import { ReasoningTimeline } from "@/components/reasoning/ReasoningTimeline";
import { SitePanel } from "@/components/SitePanel";
import { StageComparison } from "@/components/StageComparison";

// Moved from the retired KeyFactsRail (T13.5b plan, Part 4) — same
// classification buckets, now shown as two small tiles in the Overview
// tab instead of a standalone right-hand rail.
const CONFIRMED_CLASSIFICATIONS = new Set(["deductible", "concurs_with_check"]);
const REVIEW_CLASSIFICATIONS = new Set(["systemic", "no_own_evidence", "review_flag"]);

const TAB_KEYS = ["overview", "checks", "reasoning", "documents", "site", "memo"] as const;
type TabKey = (typeof TAB_KEYS)[number];

/** Amendment C (T13.5 plan): unknown or missing ?tab= values fall back to
 * Overview, rather than rendering nothing or throwing. */
function validateTab(raw: string | null): TabKey {
  return (TAB_KEYS as readonly string[]).includes(raw ?? "") ? (raw as TabKey) : "overview";
}

function mimeTypeForDocType(docType: string): string {
  // Mirrors api/app/ingest/extract.py's MIME_TYPE_BY_DOC_TYPE — the only
  // image document type is the weighbridge slip photo, everything else
  // is a rendered PDF.
  return docType === "weighbridge_slip" ? "image/png" : "application/pdf";
}

export function ProcessorTabs({
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
  /** T13.5b plan, Part 4 — the active live-verification run, if any
   * (T16b: the live-run mirroring this once supported is gone with the
   * processor page's run control; the steps are the page-load snapshot.)
   * While present, the reasoning tab/docked panel mirror its steps live
   * instead of the page-load-time reasoningSteps snapshot. */
}) {
  const searchParams = useSearchParams();
  const urlTab = validateTab(searchParams.get("tab"));
  const [tab, setTab] = useState<TabKey>(urlTab);
  const [syncedUrlTab, setSyncedUrlTab] = useState<TabKey>(urlTab);
  const [openDocId, setOpenDocId] = useState<string | null>(null);

  // Adjusts state during render (react.dev's documented pattern for this
  // exact case), not in an effect — reacts to real Next navigations (an
  // evidence link to ?tab=site, the sticky header's "View memo" link,
  // browser back/forward) without an extra post-commit render. Never
  // fires for this component's own tab clicks below, since those use
  // window.history.replaceState directly rather than the Next router,
  // so urlTab never changes in response to them.
  if (urlTab !== syncedUrlTab) {
    setSyncedUrlTab(urlTab);
    setTab(urlTab);
  }

  /** Amendment C: client-side only, no Next navigation and so no RSC
   * refetch — history.replaceState keeps the URL shareable without
   * going through next/navigation's router (which would re-run this
   * page's server component for every tab click). */
  function handleTabChange(next: string) {
    const validated = validateTab(next);
    setTab(validated);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", validated);
    window.history.replaceState(null, "", url);
  }

  const displayedFindings = findings.filter(isDisplayedFinding);
  const openDocument = documents.find((d) => d.doc_id === openDocId) ?? null;
  const openFacts = openDocId ? factsByDocId[openDocId] : undefined;

  // T13.5b plan, Part 4 (breakpoint moved xl->lg in T13.5c plan, Batch
  // 0.9, per the developer's note): at lg and above, the reasoning log
  // docks on the right instead of living in a tab — isLgUp defaults
  // false (both on the server and on first client render), so there's no
  // hydration mismatch; a wide-viewport visitor sees the layout settle
  // right after mount.
  const isLgUp = useIsBreakpointUp(1024);
  const confirmedCount = findings.filter((f) => CONFIRMED_CLASSIFICATIONS.has(f.classification)).length;
  const reviewCount = findings.filter((f) => REVIEW_CLASSIFICATIONS.has(f.classification)).length;

  // While a live run is active, the reasoning tab/docked panel mirror its
  // steps instead of the static page-load snapshot — once it settles
  // (done/failed), its own final steps keep showing (frozen, isLive
  // false) rather than silently reverting to the now-stale pre-run
  // snapshot still sitting in `reasoningSteps`.

  const items = [
    {
      value: "overview" as const,
      label: "Overview",
      content: (
        <div className="space-y-6">
          <StageComparison checksOnly={checksOnly} full={full} agentStatus={agentStatus} />
          <div className="grid grid-cols-2 gap-3 sm:w-fit sm:grid-cols-2">
            <StatTile label="Confirmed findings" value={String(confirmedCount)} />
            <StatTile label="Review flags" value={String(reviewCount)} />
          </div>
          <div>
            <h2 className="font-display text-base font-semibold text-ink">Findings</h2>
            <div className="mt-3">
              {displayedFindings.length > 0 ? (
                <ul className="space-y-3">
                  {displayedFindings.map((finding, i) => (
                    <FindingCard key={i} finding={finding} knownDocIds={knownDocIds} />
                  ))}
                </ul>
              ) : (
                <EmptyState
                  title="Fully verified, no outstanding findings"
                  message="The agent loop raised no findings for this processor. Its certified tonnes are fully accounted for."
                />
              )}
            </div>
          </div>
        </div>
      ),
    },
    {
      value: "checks" as const,
      label: "Rule-Based Checks",
      content: (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {checkResults.map((check) => (
            <CheckCard key={check.check_id} check={check} knownDocIds={knownDocIds} />
          ))}
        </div>
      ),
    },
    // Below lg only — at lg and up the reasoning log docks on the right
    // instead (ReasoningPanel, rendered alongside Tabs further down).
    ...(isLgUp
      ? []
      : [
          {
            value: "reasoning" as const,
            label: "Agent reasoning",
            content: (
              <ReasoningTimeline
                steps={reasoningSteps}
                knownDocIds={knownDocIds}
              />
            ),
          },
        ]),
    {
      value: "documents" as const,
      label: "Documents",
      content: <DocumentsTable documents={documents} facts={factsByDocId} />,
    },
    {
      value: "site" as const,
      label: "Site evidence",
      content: <SitePanel site={site} processorId={processorId} />,
    },
    {
      value: "memo" as const,
      label: "Memo",
      content: memoEn === null ? (
        <EmptyState
          title="No draft available yet"
          message="The memo-drafting stage has not run for this processor yet."
        />
      ) : memoEn.doc_type === "clarification_memo" ? (
        <ClarificationMemoLetter processorId={processorId} memoEn={memoEn} knownDocIds={knownDocIds} />
      ) : (
        <VerificationStatementLetter processorId={processorId} memoEn={memoEn} knownDocIds={knownDocIds} />
      ),
    },
  ];

  // If the viewport crosses into lg while a narrower view had "reasoning"
  // open, that tab no longer exists in `items` above — fall back to
  // Overview rather than passing Tabs a value with no matching item.
  const effectiveTab = isLgUp && tab === "reasoning" ? "overview" : tab;

  return (
    <DocumentPanelProvider value={setOpenDocId}>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_minmax(420px,35%)] lg:items-start lg:gap-8">
        <div className="flex flex-col gap-6">
          <MonthlyFlowChart rows={monthlyFlow} />
          <ReasoningPanel
            steps={reasoningSteps}
            knownDocIds={knownDocIds}
          />
        </div>
        <div className="flex flex-col gap-6">
          <Tabs items={items} value={effectiveTab} onValueChange={handleTabChange} />
        </div>
      </div>

      <SidePanel
        open={openDocument !== null}
        onOpenChange={(open) => {
          if (!open) setOpenDocId(null);
        }}
        title={openDocument ? `${openDocument.doc_type} · ${openDocument.doc_id}` : "Document"}
      >
        {openDocument ? (
          <div className="space-y-4">
            {mimeTypeForDocType(openDocument.doc_type) === "image/png" ? (
              // eslint-disable-next-line @next/next/no-img-element -- proxied Cloud Run file stream, not a build-time asset
              <img
                src={`/files/${encodeURIComponent(openDocument.doc_id)}`}
                alt={`${openDocument.doc_type} image`}
                className="w-full rounded border border-border"
              />
            ) : (
              <iframe
                src={`/files/${encodeURIComponent(openDocument.doc_id)}`}
                title={`${openDocument.doc_type} preview`}
                className="h-[60vh] w-full rounded border border-border"
              />
            )}
            <a
              href={`/files/${encodeURIComponent(openDocument.doc_id)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-medium text-ink underline decoration-dotted hover:text-primary"
            >
              Open in a new tab
            </a>

            {openFacts && openFacts.fields.length > 0 ? (
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">Extracted fields</p>
                <dl className="mt-2 space-y-1.5 text-sm">
                  {openFacts.fields.map((field) => (
                    <div key={field.field_name} className="flex justify-between gap-3">
                      <dt className="shrink-0 text-ink-muted">{field.field_name}</dt>
                      <dd lang={openDocument.lang} className="text-right text-ink">
                        {field.printed_value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            ) : (
              <p className="text-sm text-ink-muted">No extracted fields for this document.</p>
            )}
          </div>
        ) : null}
      </SidePanel>
    </DocumentPanelProvider>
  );
}
