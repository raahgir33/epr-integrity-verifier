"use client";

import { useState } from "react";
import { EvidenceList } from "@/components/EvidenceLink";
import { Button } from "@/components/ui/Button";
import type { MemoResponse } from "@/lib/api";
import { isClarificationMemo, renderMemoAsPlainText } from "@/lib/memo";

export function ClarificationMemoLetter({
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
  const memo = active.memo;
  if (!isClarificationMemo(active.doc_type, memo)) return null;

  /** Amendment C (T13.5 plan): the Hindi memo is fetched only once the
   * viewer actually clicks HI, not eagerly with the rest of the page —
   * and lang only ever flips to "hi" once that fetch has actually
   * succeeded, so a failed fetch leaves the EN letter showing rather
   * than a toggle stuck on a language with no content. */
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
        renderMemoAsPlainText(active.doc_type, memo, active.sender_line),
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
                className={`px-2 py-2.5 font-medium transition-colors duration-150 ${lang === "en" ? "bg-primary text-primary-foreground" : "bg-surface text-ink"}`}
              >
                EN
              </button>
              <button
                type="button"
                onClick={() => handleSelectLang("hi")}
                disabled={loadingHi}
                className={`px-2 py-2.5 font-medium transition-colors duration-150 disabled:opacity-60 ${lang === "hi" ? "bg-primary text-primary-foreground" : "bg-surface text-ink"}`}
              >
                {loadingHi ? "…" : "HI"}
              </button>
            </div>
          ) : null}
          <Button variant="ghost" size="xs" onClick={handleCopy}>
            {copied ? "Copied!" : "Copy"}
          </Button>
          <Button variant="ghost" size="xs" onClick={() => window.print()}>
            Print / Save as PDF
          </Button>
        </div>
      </div>
      {hiError ? (
        <p className="mt-2 text-xs text-risk-high print:hidden">
          Could not load the Hindi version — showing English.
        </p>
      ) : null}

      <p className="mt-4 text-sm text-ink-muted">{active.sender_line}</p>
      <p className="mt-3 font-display text-base font-semibold text-ink">{memo.subject}</p>
      <p className="mt-3 text-sm text-ink">{memo.salutation}</p>
      <p className="mt-3 text-sm text-ink">{memo.opening_paragraph}</p>

      <ol className="mt-4 space-y-4">
        {memo.items.map((item, i) => (
          <li key={i} className="border-t border-border pt-3 first:border-0 first:pt-0">
            <p className="text-sm font-medium text-ink">
              {i + 1}. {item.heading}
            </p>
            <p className="mt-1 text-sm text-ink">{item.what_we_observed}</p>
            <p className="mt-1 text-sm text-ink">
              <span className="font-medium text-ink-muted">What we request: </span>
              {item.what_we_request}
            </p>
            {item.evidence_ids.length > 0 ? (
              <div className="mt-2 text-xs">
                <span className="mr-1.5 font-medium text-ink-muted">Evidence:</span>
                <EvidenceList evidenceIds={item.evidence_ids} knownDocIds={knownDocIds} />
              </div>
            ) : null}
          </li>
        ))}
      </ol>

      <p className="mt-4 text-sm text-ink">
        We request a response within {memo.response_deadline_days} days of this letter.
      </p>
      <p className="mt-3 text-sm text-ink">{memo.closing_paragraph}</p>
    </div>
  );
}
