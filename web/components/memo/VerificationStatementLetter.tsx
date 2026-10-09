"use client";

import { useState } from "react";
import { EvidenceList } from "@/components/EvidenceLink";
import type { MemoResponse } from "@/lib/api";
import { isClarificationMemo, renderMemoAsPlainText } from "@/lib/memo";

export function VerificationStatementLetter({
  processorId,
  memoEn,
  knownDocIds,
}: {
  processorId: string;
  memoEn: MemoResponse;
  knownDocIds: ReadonlySet<string>;
}) {
  const [lang, setLang] = useState<"en" | "hi">("en");
  const [memoHi, setMemoHi] = useState<MemoResponse | null>(null);
  const [loadingHi, setLoadingHi] = useState(false);
  const [hiError, setHiError] = useState(false);
  const [copied, setCopied] = useState(false);
  const active = lang === "hi" && memoHi ? memoHi : memoEn;
  const statement = active.memo;
  if (isClarificationMemo(active.doc_type, statement)) return null;

  /** Amendment C (T13.5 plan): lazy, success-gated Hindi fetch — see
   * ClarificationMemoLetter's identical handler for the full rationale. */
  async function handleSelectLang(next: "en" | "hi") {
    if (next === "en") {
      setLang("en");
      return;
    }
    if (memoHi) {
      setLang("hi");
      return;
    }
    setLoadingHi(true);
    setHiError(false);
    try {
      const response = await fetch(`/api/processors/${encodeURIComponent(processorId)}/memo?lang=hi`, {
        cache: "no-store",
      });
      if (!response.ok) throw new Error("fetch failed");
      setMemoHi((await response.json()) as MemoResponse);
      setLang("hi");
    } catch {
      setHiError(true);
    } finally {
      setLoadingHi(false);
    }
  }

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
    <div className="memo-print-area card p-4" lang={lang === "hi" ? "hi" : undefined}>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs print:hidden">
        <span className="rounded-full bg-surface-sunk px-2 py-0.5 font-medium text-ink">
          {active.drafted_by}
        </span>
        <div className="flex items-center gap-2">
          {memoEn.has_hindi ? (
            <div className="flex overflow-hidden rounded border border-border">
              <button
                type="button"
                onClick={() => handleSelectLang("en")}
                className={`px-2 py-1 font-medium transition-colors duration-150 ${lang === "en" ? "bg-primary text-primary-foreground" : "bg-surface text-ink"}`}
              >
                EN
              </button>
              <button
                type="button"
                onClick={() => handleSelectLang("hi")}
                disabled={loadingHi}
                className={`px-2 py-1 font-medium transition-colors duration-150 disabled:opacity-60 ${lang === "hi" ? "bg-primary text-primary-foreground" : "bg-surface text-ink"}`}
              >
                {loadingHi ? "…" : "HI"}
              </button>
            </div>
          ) : null}
          <button
            type="button"
            onClick={handleCopy}
            className="rounded border border-border px-2 py-1 font-medium text-ink hover:bg-surface-sunk"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
          <button
            type="button"
            onClick={() => window.print()}
            className="rounded border border-border px-2 py-1 font-medium text-ink hover:bg-surface-sunk"
          >
            Print / Save as PDF
          </button>
        </div>
      </div>
      {hiError ? (
        <p className="mt-2 text-xs text-risk-high print:hidden">
          Could not load the Hindi version — showing English.
        </p>
      ) : null}

      <p className="mt-4 text-sm text-ink-muted">{active.sender_line}</p>
      <p className="mt-3 font-display text-base font-semibold text-ink">{statement.subject}</p>
      <p className="mt-3 text-sm text-ink">{statement.salutation}</p>
      <p className="mt-3 text-sm text-ink">{statement.part_a_paragraph}</p>

      {statement.observations.length > 0 ? (
        <ol className="mt-4 space-y-3">
          {statement.observations.map((obs, i) => (
            <li key={i} className="border-t border-border pt-3 first:border-0 first:pt-0">
              <p className="text-sm text-ink">{obs.recommendation}</p>
              {obs.evidence_ids.length > 0 ? (
                <div className="mt-2 text-xs">
                  <span className="mr-1.5 font-medium text-ink-muted">Evidence:</span>
                  <EvidenceList evidenceIds={obs.evidence_ids} knownDocIds={knownDocIds} />
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-4 text-sm text-ink-muted">{statement.no_items_note}</p>
      )}

      <p className="mt-4 text-sm text-ink">{statement.closing_paragraph}</p>
    </div>
  );
}
