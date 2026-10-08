"use client";

import { useState } from "react";
import { EvidenceList } from "@/components/EvidenceLink";
import type { MemoResponse } from "@/lib/api";
import { isClarificationMemo, renderMemoAsPlainText } from "@/lib/memo";

export function VerificationStatementLetter({
  memoEn,
  memoHi,
  knownDocIds,
}: {
  memoEn: MemoResponse;
  memoHi: MemoResponse | null;
  knownDocIds: ReadonlySet<string>;
}) {
  const [lang, setLang] = useState<"en" | "hi">("en");
  const [copied, setCopied] = useState(false);
  const active = lang === "hi" && memoHi ? memoHi : memoEn;
  const statement = active.memo;
  if (isClarificationMemo(active.doc_type, statement)) return null;

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(
        renderMemoAsPlainText(active.doc_type, statement, active.sender_line),
      );
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access denied by the browser — nothing to recover from;
      // the Copy button simply stays inert.
    }
  }

  return (
    <div
      className="memo-print-area rounded-lg border border-slate-200 bg-white p-4"
      lang={lang === "hi" ? "hi" : undefined}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs print:hidden">
        <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-700">
          {active.drafted_by}
        </span>
        <div className="flex items-center gap-2">
          {memoHi ? (
            <div className="flex overflow-hidden rounded border border-slate-300">
              <button
                type="button"
                onClick={() => setLang("en")}
                className={`px-2 py-1 font-medium ${lang === "en" ? "bg-slate-900 text-white" : "bg-white text-slate-700"}`}
              >
                EN
              </button>
              <button
                type="button"
                onClick={() => setLang("hi")}
                className={`px-2 py-1 font-medium ${lang === "hi" ? "bg-slate-900 text-white" : "bg-white text-slate-700"}`}
              >
                HI
              </button>
            </div>
          ) : null}
          <button
            type="button"
            onClick={handleCopy}
            className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
          <button
            type="button"
            onClick={() => window.print()}
            className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50"
          >
            Print / Save as PDF
          </button>
        </div>
      </div>

      <p className="mt-4 text-sm text-slate-500">{active.sender_line}</p>
      <p className="mt-3 font-display text-base font-semibold text-slate-900">
        {statement.subject}
      </p>
      <p className="mt-3 text-sm text-slate-700">{statement.salutation}</p>
      <p className="mt-3 text-sm text-slate-700">{statement.part_a_paragraph}</p>

      {statement.observations.length > 0 ? (
        <ol className="mt-4 space-y-3">
          {statement.observations.map((obs, i) => (
            <li key={i} className="border-t border-slate-100 pt-3 first:border-0 first:pt-0">
              <p className="text-sm text-slate-700">{obs.recommendation}</p>
              {obs.evidence_ids.length > 0 ? (
                <div className="mt-2 text-xs">
                  <span className="mr-1.5 font-medium text-slate-500">Evidence:</span>
                  <EvidenceList evidenceIds={obs.evidence_ids} knownDocIds={knownDocIds} />
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-4 text-sm text-slate-500">{statement.no_items_note}</p>
      )}

      <p className="mt-4 text-sm text-slate-700">{statement.closing_paragraph}</p>
    </div>
  );
}
