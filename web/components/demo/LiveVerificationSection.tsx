"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
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
 * Landing page only — and, since T16b removed the processor page's own
 * live-run control, the only place a run is started at all.
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
 * **The grid maths.** The card began as exactly half the content column.
 * T16b later narrowed it by 25% at the developer's request and centred the
 * pair: the grid itself is `87.5%` of the column (so the two tracks plus
 * the gap stay centred, `mx-auto`), and the card track is `42.857%` of
 * that — 0.875 x 0.42857 = 0.375 of the column, which is exactly 0.75 x the
 * original half. The panel takes the remainder.
 *
 * The track is declared as a literal percentage rather than using
 * `grid-cols-2`, whose two equal tracks would each come out a gap
 * narrower.
 *
 * At rest the card is centred in the full content column, not in the
 * grid: the grid starts `0.0625W` in, the card track is `0.375W`, and a
 * centred card needs its left edge at `(W - 0.375W) / 2 = 0.3125W`. That
 * is a shift of `0.25W`, which is two-thirds of the card's own width —
 * hence `translate-x-[66.667%]`. (It was `translate-x-1/2` while the
 * track was half the column; narrowing the card changed the offset, and
 * leaving it at half left the card visibly off-centre.) */
export function LiveVerificationSection({ batches }: { batches: DemoBatchOut[] }) {
  const [runId, setRunId] = useState<string | null>(null);
  const [batchId, setBatchId] = useState<string | null>(null);
  // Bumped on reset to remount the card, which is what clears the picker
  // and any cooldown / daily-cap message from the previous attempt.
  const [formKey, setFormKey] = useState(0);
  // Held until the panel has finished sliding away, so the route changes
  // after the animation rather than cutting it off.
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  const router = useRouter();
  const cardRef = useRef<HTMLDivElement>(null);
  const cardHeight = useElementHeight(cardRef);
  const reducedMotion = usePrefersReducedMotion();
  const { run, error } = useRunPolling(runId);

  const open = runId !== null;
  const settled = run?.status === "done" || run?.status === "failed";
  // The batch supplies the reading_documents row's detail. It comes from
  // the picker rather than the run, because GET /runs/{id} does not echo
  // the batch's tonnage or period -- only its id.
  const batch = batches.find((b) => b.batch_id === batchId) ?? null;

  const handleRunStart = useCallback((id: string, startedBatchId: string) => {
    setRunId(id);
    setBatchId(startedBatchId);
  }, []);

  // Both closing actions do the same thing to the layout — drop the run,
  // which slides the panel out and the card back to centre, and remount
  // the card empty. They differ only in where they leave the viewer.
  const reset = useCallback(() => {
    setRunId(null);
    setBatchId(null);
    setFormKey((previous) => previous + 1);
  }, []);

  const handleViewProcessor = useCallback(
    (processorId: string) => {
      setPendingHref(`/processors/${encodeURIComponent(processorId)}`);
      reset();
    },
    [reset],
  );

  if (batches.length === 0) return null;

  return (
    <div className="mx-auto grid grid-cols-1 gap-6 lg:w-[87.5%] lg:grid-cols-[42.857%_1fr]">
      <div
        ref={cardRef}
        className={`transition-transform duration-400 ease-out motion-reduce:transition-none ${
          open ? "lg:translate-x-0" : "lg:translate-x-[66.667%]"
        }`}
      >
        <RunLiveVerification
          key={formKey}
          batches={batches}
          fill
          isRunning={open}
          busyLabel={settled ? (run?.status === "done" ? "Verification complete" : "Verification failed") : undefined}
          onRunStart={handleRunStart}
        />
      </div>

      <AnimatePresence
        initial={false}
        onExitComplete={() => {
          if (!pendingHref) return;
          router.push(pendingHref);
          setPendingHref(null);
        }}
      >
        {open ? (
          <motion.div
            key="run-panel"
            initial={reducedMotion ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            // The exit carries its own 0.4s to match the card's own CSS
            // slide back to centre. Navigation waits on onExitComplete, so
            // a shorter exit would change the route while the card was
            // still moving.
            exit={{
              opacity: 0,
              ...(reducedMotion ? {} : { y: 8 }),
              transition: { duration: reducedMotion ? 0 : 0.4, ease: "easeOut" },
            }}
            transition={{ duration: reducedMotion ? 0 : 0.3, ease: "easeOut" }}
            // A definite height at every breakpoint, handed over as a CSS
            // variable. It was max-height below lg, which let the panel
            // resize as rows auto-expanded — so the page grew once when the
            // panel opened and then kept moving for the rest of the run.
            // Fixed to the card's height, it grows exactly once.
            style={cardHeight ? ({ "--card-h": `${cardHeight}px` } as React.CSSProperties) : undefined}
            className={cardHeight ? "h-[var(--card-h)]" : undefined}
          >
            <RunTaskPanel
              run={run}
              batch={batch}
              error={error}
              onViewProcessor={handleViewProcessor}
              onTryAgain={reset}
            />
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
