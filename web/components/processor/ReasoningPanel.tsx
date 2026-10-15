"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft } from "lucide-react";
import { ReasoningLog, type ReasoningLogHandle } from "@/components/reasoning/ReasoningLog";
import { AILoadingSpinner } from "@/components/ui/AILoadingSpinner";
import { ShimmerText } from "@/components/ui/ShimmerText";
import type { ReasoningStepOut } from "@/lib/api";

const STORAGE_KEY = "epr:reasoningPanelCollapsed";

/** Docked reasoning panel (T13.5b plan, Part 4) — only rendered at lg and
 * above (see ProcessorTabs' useIsBreakpointUp(1024) check — moved from
 * xl in T13.5c plan, Batch 0.9, per the developer's note); below lg,
 * ReasoningLog is rendered directly as the "Agent Reasoning" tab instead,
 * with no dock/collapse chrome. Collapse state persists in localStorage
 * so a repeat visitor's choice sticks; lg:top-16 clears the fixed Nav's
 * own ~64px height, so the panel pins directly below it. (The processor
 * header above is deliberately not sticky, so there is nothing else to
 * stack under.)

 * Collapsed state: the card drops its fixed height so collapsing actually
 * reclaims the space instead of leaving a full-height empty box, and the
 * aside no longer sets `self-start` — inside this column flex container
 * that resolved to `align-self: flex-start`, whose cross axis is
 * horizontal, so the aside shrink-wrapped to its content and the collapsed
 * card rendered 335px wide against the chart's 842px. Stickiness comes
 * from `lg:sticky lg:top-16`, never from `self-start`.
 *
 * `currentStageLabel` (Kokonut addendum's "AI Loading" equivalent) — set
 * only while a live run is active and hasn't produced its first reasoning
 * step yet (still reading documents / running checks); shows the real
 * stage name, never invented progress.
 *
 * Round 7 fix (developer-reported, 2026-10-10): the card used
 * `max-height` with no `overflow` set (default `visible`), not a real
 * `height`. A column flex container sized only by `max-height` has no
 * definite main size to hand its `flex-1` body for free-space
 * distribution, so the body never actually got bounded — it grew to fit
 * all its content, and the card's own box (clipped only by `max-height`,
 * `overflow: visible`) let that excess spill straight past its bottom
 * edge onto the rest of the page once more than a step or two was open.
 * Fixed by giving the card a real, fixed `height` (not `max-height`) so
 * flex-grow has a concrete space to fill, plus `overflow-hidden` on the
 * card itself as a second line of defense. Reproduced and pinned down by
 * e2e/reasoning-panel-overflow.spec.ts. */
export function ReasoningPanel({
  steps,
  knownDocIds,
  isLive = false,
  currentStageLabel,
}: {
  steps: ReasoningStepOut[];
  knownDocIds: ReadonlySet<string>;
  isLive?: boolean;
  currentStageLabel?: string;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const logRef = useRef<ReasoningLogHandle>(null);
  const userScrolledAwayRef = useRef(false);
  const stepCountRef = useRef(steps.length);

  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(STORAGE_KEY);
    } catch {
      // Private browsing / storage disabled — fall back to expanded.
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCollapsed(stored === "true");
    setHydrated(true);
  }, []);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(STORAGE_KEY, String(next));
      } catch {
        // Nothing to recover from — the choice just won't persist.
      }
      return next;
    });
  }

  // Keep the panel scrolled to the top on a new live entry unless the
  // viewer has deliberately scrolled away from it.
  useEffect(() => {
    const grew = steps.length > stepCountRef.current;
    stepCountRef.current = steps.length;
    if (isLive && grew && scrollRef.current && !userScrolledAwayRef.current) {
      scrollRef.current.scrollTo({ top: 0 });
    }
  }, [steps.length, isLive]);

  function handleScroll() {
    if (scrollRef.current) {
      userScrolledAwayRef.current = scrollRef.current.scrollTop > 8;
    }
  }

  const showExpandControls = steps.length > 0 && !(isLive && steps.length === 0);
  // localStorage is unreadable during SSR, so `collapsed` is only
  // meaningful once hydrated — both the card's height and its body read
  // this single flag, never `collapsed` on its own.
  const isCollapsed = hydrated && collapsed;

  return (
    <aside className="hidden lg:block lg:sticky lg:top-16">
      <div
        className={`card flex flex-col overflow-hidden p-0 ${
          isCollapsed ? "" : "h-[calc(100dvh-5rem)]"
        }`}
      >
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
          <p className="font-display text-sm font-semibold text-ink">Reasoning</p>
          <div className="flex items-center gap-3">
            {showExpandControls ? (
              <div className="flex items-center gap-2 text-xs font-medium text-ink-muted">
                <button
                  type="button"
                  onClick={() => logRef.current?.expandAll()}
                  className="relative outline-none after:absolute after:-inset-1.5 after:content-[''] hover:text-ink focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary"
                >
                  Expand all
                </button>
                <span aria-hidden>·</span>
                <button
                  type="button"
                  onClick={() => logRef.current?.collapseAll()}
                  className="relative outline-none after:absolute after:-inset-1.5 after:content-[''] hover:text-ink focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary"
                >
                  Collapse all
                </button>
              </div>
            ) : null}
            <button
              type="button"
              onClick={toggleCollapsed}
              aria-expanded={!collapsed}
              aria-label={collapsed ? "Expand reasoning panel" : "Collapse reasoning panel"}
              className="flex h-10 w-10 items-center justify-center rounded-md text-ink-muted outline-none transition-[color,background-color,scale] duration-150 hover:bg-surface-sunk hover:text-ink focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary motion-safe:active:scale-[0.96]"
            >
              <ChevronLeft
                aria-hidden
                size={16}
                className={`transition-transform duration-200 ${collapsed ? "rotate-180" : ""}`}
              />
            </button>
          </div>
        </div>
        {/* hydrated gate avoids a one-frame flash of the wrong collapsed
            state on a repeat visitor (localStorage is unreadable during
            SSR) — the panel renders expanded-but-empty-looking for a
            moment rather than ever showing the stored "collapsed" state
            flipping open right after mount. */}
        {isCollapsed ? null : (
          <div className="relative min-h-0 flex-1">
            <div
              ref={scrollRef}
              onScroll={handleScroll}
              className="h-full overflow-y-auto overscroll-contain px-4 py-3"
            >
              {isLive && steps.length === 0 && currentStageLabel ? (
                <div className="flex items-center gap-2 text-sm">
                  <AILoadingSpinner className="h-5 w-5 shrink-0" />
                  <ShimmerText className="font-medium text-ink">{currentStageLabel}</ShimmerText>
                </div>
              ) : (
                <ReasoningLog ref={logRef} steps={steps} knownDocIds={knownDocIds} isLive={isLive} />
              )}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
