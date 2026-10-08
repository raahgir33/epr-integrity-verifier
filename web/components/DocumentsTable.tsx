"use client";

import { useState } from "react";
import type { DocumentFactsResponse, DocumentListItem } from "@/lib/api";

const EXTRACTION_LABEL: Record<string, string> = {
  ok: "Extracted",
  failed: "Extraction failed",
  not_extracted: "Not extracted",
};

function DocumentRow({
  document,
  facts,
}: {
  document: DocumentListItem;
  facts: DocumentFactsResponse | undefined;
}) {
  const [open, setOpen] = useState(false);
  const hasFields = facts && facts.fields.length > 0;

  return (
    <li className="border-b border-slate-100 py-3 last:border-0">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span className="font-medium text-slate-900">{document.doc_type}</span>
        <span className="text-xs uppercase tracking-wide text-slate-400">{document.lang}</span>
        <span className="text-xs text-slate-500">
          {EXTRACTION_LABEL[document.extraction_status] ?? document.extraction_status}
        </span>
        <a
          href={`/files/${encodeURIComponent(document.doc_id)}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs font-medium text-slate-700 underline decoration-dotted hover:text-slate-900"
        >
          View file
        </a>
        {hasFields ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="text-xs font-medium text-slate-700 underline decoration-dotted hover:text-slate-900"
          >
            {open ? "Hide extracted fields" : "Show extracted fields"}
          </button>
        ) : null}
      </div>
      {open && facts ? (
        <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 rounded bg-slate-50 p-3 text-xs sm:grid-cols-2">
          {facts.fields.map((field) => (
            <div key={field.field_name} className="flex gap-2">
              <dt className="shrink-0 font-medium text-slate-500">{field.field_name}:</dt>
              <dd lang={document.lang} className="text-slate-800">
                {field.printed_value}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </li>
  );
}

export function DocumentsTable({
  documents,
  facts,
}: {
  documents: DocumentListItem[];
  facts: Record<string, DocumentFactsResponse>;
}) {
  return (
    <ul>
      {documents.map((document) => (
        <DocumentRow key={document.doc_id} document={document} facts={facts[document.doc_id]} />
      ))}
    </ul>
  );
}
