"use client";

import { useCallback, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { RunLiveVerification } from "@/components/demo/RunLiveVerification";
import { RunTaskPanel } from "@/components/demo/RunTaskPanel";
import type { DemoBatchOut } from "@/lib/api";
import { useElementHeight } from "@/lib/useElementHeight";
import { usePrefersReducedMotion } from "@/lib/usePrefersReducedMotion";
import { useRunPolling } from "@/lib/useRunPolling";

/** Landing-page shell for "Run Live Verification" (T16b).
 *
 * Before T16b the run's stage progress rendered *inside* the card, below
 * the button, so the card grew as the run advanced and pushed every
 * section below it down the page. Here the card instead slides left and a
 * task-row panel opens beside it, capped to the card's own height, so the
 * section is exactly as tall before, during and after a run.
 *
 * Landing page only. The processor page keeps rendering
 * RunLiveVerification directly (components/processor/ProcessorLiveRun.tsx),
 * which is why every prop this shell passes down is opt-in with a
 * backwards-compatible default rather than a change to the card itself.
 *
 * **Why the card's slide is CSS and not `motion`.** The translate must
 * apply only at `lg` and up, and a JS breakpoint hook
 * (lib/useIsBreakpointUp.ts) deliberately returns `false` on the server and
 * on the first client render to keep hydration stable — so a motion-driven
 * `x` would render the card hard against the left column for one frame and
 * then visibly jump to centre on every page load. A Tailwind
 * `lg:translate-x-*` class is server-rendered in the right place, costs no
 * frame, and (per the design skill) a CSS transition is interruptible
 * mid-flight, which a one-shot JS animation is not. `motion` still drives
 * the panel's enter/exit, where `AnimatePresence` earns its place: an exit
 * animation on unmount is the thing CSS genuinely cannot do.
 *
 * **The grid maths.** The card's at-rest geometry is unchanged from before
 * this component existed: measured at 1280/1440/1920 it is exactly half its
 * content column's width, centred. The grid therefore declares that width
 * literally — `lg:grid-cols-[50%_1fr]` — rather than `grid-cols-2`, whose
 * two equal tracks would each come out `(W - 24) / 2`, 12px narrower than
 * today. Column one is exactly `W / 2`; the panel takes the remainder,
 * `W / 2 - 24`, so it is one gap narrower than the card. That asymmetry is
 * deliberate (the developer's call): it keeps the grid inside the content
 * column, so during a run the card's left edge sits exactly on the content
 * column's left edge and the panel's right edge on its right edge, with
 * nothing bleeding past either. At rest the card translates by half its own
 * width — `translate-x-1/2`, i.e. `W / 4` — which is precisely the offset
 * that centres a half-width box in the column. */
export function LiveVerificationSection({ batches }: { batches: DemoBatchOut[] }) {
  const [runId, setRunId] = useState<string | null>(null);
  const [batchId, setBatchId] = useState<string | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const cardHeight = useElementHeight(cardRef);
  const reducedMotion = usePrefersReducedMotion();
  const { run, error } = useRunPolling(runId);

  const open = runId !== null;
  // The batch supplies the reading_documents row's detail. It comes from
  // the picker rather than the run, because GET /runs/{id} does not echo
  // the batch's tonnage or period -- only its id.
  const batch = batches.find((b) => b.batch_id === batchId) ?? null;

  const handleRunStart = useCallback((id: string, startedBatchId: string) => {
    setRunId(id);
    setBatchId(startedBatchId);
  }, []);

  if (batches.length === 0) return null;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[50%_1fr]">
      <div
        ref={cardRef}
        className={`transition-transform duration-400 ease-out motion-reduce:transition-none ${
          open ? "lg:translate-x-0" : "lg:translate-x-1/2"
        }`}
      >
        <RunLiveVerification batches={batches} fill isRunning={open} onRunStart={handleRunStart} />
      </div>

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="run-panel"
            initial={reducedMotion ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 8 }}
            transition={{ duration: reducedMotion ? 0 : 0.3, ease: "easeOut" }}
            // The cap is handed over as a CSS variable rather than a JS
            // breakpoint so the two behaviours stay pure CSS: below lg the
            // panel stacks under the card and may grow to its own content
            // up to the cap; at lg and up it takes exactly the card's
            // height, which is what keeps the section's height constant.
            style={cardHeight ? ({ "--card-h": `${cardHeight}px` } as React.CSSProperties) : undefined}
            className={cardHeight ? "max-h-[var(--card-h)] lg:h-[var(--card-h)]" : undefined}
          >
            <RunTaskPanel run={run} batch={batch} error={error} />
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
