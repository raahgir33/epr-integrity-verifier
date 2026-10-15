"use client";

import { useState } from "react";
import { Accordion, type AccordionItemData } from "@/components/ui/Accordion";
import type { DocumentFactsResponse, DocumentListItem } from "@/lib/api";
import { useDocumentPanel } from "@/lib/document-panel-context";
import { docTypeName } from "@/lib/labels";

const EXTRACTION_LABEL: Record<string, string> = {
  ok: "Extracted",
  failed: "Extraction failed",
  // "Not extracted" in red read as something having gone wrong with the
  // document. Nothing has: these are the *-DEMO-* files staged for the
  // live verification run, which serve their PDF normally and simply have
  // not been through extraction yet. The wording says that plainly.
  not_extracted: "Not yet read",
};

/** T13.5b plan, Part 5: a document is "flagged" when its own extraction
 * actually failed. If "flagged" was meant to mean something broader (e.g.
 * cited by an unresolved finding), this is the one spot to change.
 *
 * Deliberately NOT `!== "ok"`: that also caught "not_extracted", which is
 * the absence of an extraction attempt, not a failed one — the staged
 * demo-batch documents sit in that state permanently until a live run
 * reads them. Counting them as flagged painted a red "N flagged" badge on
 * a clean processor and forced that group open. A real extraction failure
 * still flags, still shows red: the project's rule is to fail visibly,
 * and this change does not hide one. */
function isFlagged(document: DocumentListItem): boolean {
  return document.extraction_status === "failed";
}

function DocumentRow({
  document,
  facts,
}: {
  document: DocumentListItem;
  facts: DocumentFactsResponse | undefined;
}) {
  const openDocument = useDocumentPanel();
  const [open, setOpen] = useState(false);
  const hasFields = facts && facts.fields.length > 0;

  return (
    <li className="border-b border-border py-3 last:border-0">
      {/* T16c F18: a grid at sm and up, so lang/status/actions line up
          down the list instead of being pushed around by each doc_id's
          own width (one longer id used to wrap its whole row). Still a
          plain wrapping flex below sm. */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm sm:grid sm:grid-cols-[minmax(0,1fr)_3rem_8rem_auto_auto] sm:items-center sm:gap-x-4">
        <span className="font-mono text-xs text-ink-muted">{document.doc_id}</span>
        <span className="text-xs uppercase tracking-wide text-ink-muted">{document.lang}</span>
        <span className={isFlagged(document) ? "text-xs font-medium text-risk-high" : "text-xs text-ink-muted"}>
          {EXTRACTION_LABEL[document.extraction_status] ?? document.extraction_status}
        </span>
        <a
          href={`/files/${encodeURIComponent(document.doc_id)}`}
          target="_blank"
          rel="noopener noreferrer"
          className="relative text-xs font-medium text-ink underline decoration-dotted outline-none after:absolute after:-inset-x-1.5 after:-inset-y-px after:content-[''] hover:text-primary focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary"
        >
          View file
        </a>
        {openDocument ? (
          <button
            type="button"
            onClick={() => openDocument(document.doc_id)}
            className="relative text-xs font-medium text-ink underline decoration-dotted outline-none after:absolute after:-inset-x-1.5 after:-inset-y-px after:content-[''] hover:text-primary focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary"
          >
            Open details
          </button>
        ) : hasFields ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="relative text-xs font-medium text-ink underline decoration-dotted outline-none after:absolute after:-inset-x-1.5 after:-inset-y-px after:content-[''] hover:text-primary focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary"
          >
            {open ? "Hide extracted fields" : "Show extracted fields"}
          </button>
        ) : null}
      </div>
      {!openDocument && open && facts ? (
        <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 rounded bg-surface-sunk p-3 text-xs sm:grid-cols-2">
          {facts.fields.map((field) => (
            <div key={field.field_name} className="flex gap-2">
              <dt className="shrink-0 font-medium text-ink-muted">{field.field_name}:</dt>
              <dd lang={document.lang} className="text-ink">
                {field.printed_value}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </li>
  );
}

/** Grouped by doc_type (T13.5b plan, Part 5) — each group shows the type,
 * a count and a flagged-count badge; groups containing a flagged document
 * start open. T16c F8: the heading renders docTypeName(doc_type), not the
 * raw API enum — "weighbridge_slip"/"cto" were reaching the screen as-is.
 * Grouping and sort order still key on the raw doc_type. */
export function DocumentsTable({
  documents,
  facts,
}: {
  documents: DocumentListItem[];
  facts: Record<string, DocumentFactsResponse>;
}) {
  const byType = new Map<string, DocumentListItem[]>();
  for (const document of documents) {
    const group = byType.get(document.doc_type);
    if (group) group.push(document);
    else byType.set(document.doc_type, [document]);
  }

  const groups = [...byType.entries()].sort(([a], [b]) => a.localeCompare(b));
  const defaultOpen = groups.filter(([, docs]) => docs.some(isFlagged)).map(([type]) => type);

  const items: AccordionItemData[] = groups.map(([type, docs]) => {
    const flaggedCount = docs.filter(isFlagged).length;
    return {
      id: type,
      trigger: (
        <span className="flex items-center gap-2">
          <span className="text-ink">{docTypeName(type)}</span>
          {/* T16c F17: a border, because bg-surface-sunk is now the same
              value as --color-page — on the tab background the pill was
              invisible and the count read as a bare number. */}
          <span className="rounded-full border border-border bg-surface-sunk px-2 py-0.5 text-xs font-medium text-ink-muted">
            {docs.length}
          </span>
          {flaggedCount > 0 ? (
            <span className="rounded-full bg-risk-high/10 px-2 py-0.5 text-xs font-medium text-risk-high">
              {flaggedCount} flagged
            </span>
          ) : null}
        </span>
      ),
      content: (
        <ul>
          {docs.map((document) => (
            <DocumentRow key={document.doc_id} document={document} facts={facts[document.doc_id]} />
          ))}
        </ul>
      ),
    };
  });

  return <Accordion type="multiple" items={items} defaultValue={defaultOpen} />;
}
