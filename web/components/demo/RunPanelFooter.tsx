"use client";

import Link from "next/link";
import type { MouseEvent } from "react";
import { ArrowRight, RotateCcw } from "lucide-react";
import { alertTone } from "@/components/demo/alertTone";
import type { RunStatusOut } from "@/lib/api";

/** Closing state for a settled run (T16b), pinned at the bottom of the
 * task panel so it never scrolls out of view.
 *
 * On a run that finished this carries the alert outcome — the line that
 * used to render inside the card via RunProgress — plus the way through
 * to the processor it just verified. On a run that failed it carries the
 * backend's error and a way to start over.
 *
 * The processor link stays a real `Link` with an href rather than a
 * button, so middle-click, cmd-click and "open in new tab" all behave.
 * Only an unmodified left click is intercepted, to let the panel slide
 * away before the route changes. */
export function RunPanelFooter({
  run,
  onViewProcessor,
  onTryAgain,
}: {
  run: RunStatusOut;
  onViewProcessor: (processorId: string) => void;
  onTryAgain: () => void;
}) {
  if (run.status !== "done" && run.status !== "failed") return null;

  const href = `/processors/${encodeURIComponent(run.processor_id)}`;

  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    onViewProcessor(run.processor_id);
  }

  return (
    <div className="mt-2 shrink-0 border-t border-border px-3 pb-1 pt-3">
      {run.status === "done" ? (
        <>
          <p className="flex items-start gap-2 text-xs text-ink">
            {run.alert ? (
              (() => {
                const tone = alertTone(run.alert);
                return <tone.Icon aria-hidden size={14} className={`mt-px shrink-0 ${tone.accent}`} />;
              })()
            ) : null}
            <span className="text-pretty">
              {run.alert?.message ?? "No alert — risk band unchanged, no new finding."}
            </span>
          </p>
          <Link
            href={href}
            onClick={handleClick}
            className="mt-2 inline-flex min-h-9 items-center gap-1.5 text-sm font-medium text-ink underline decoration-2 underline-offset-4 outline-none transition-opacity duration-150 hover:opacity-80 focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            View verified processor
            <ArrowRight aria-hidden size={14} />
          </Link>
        </>
      ) : (
        <>
          <p className="text-pretty text-xs text-risk-high">
            {run.error_message ?? "The run failed before it finished."}
          </p>
          <button
            type="button"
            onClick={onTryAgain}
            className="mt-2 inline-flex min-h-9 items-center gap-1.5 text-sm font-medium text-ink underline decoration-2 underline-offset-4 outline-none transition-opacity duration-150 hover:opacity-80 focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <RotateCcw aria-hidden size={14} />
            Try again
          </button>
        </>
      )}
    </div>
  );
}
