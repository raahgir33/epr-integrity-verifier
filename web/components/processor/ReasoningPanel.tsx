"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft } from "lucide-react";
import { ReasoningLog } from "@/components/reasoning/ReasoningLog";
import { AILoadingSpinner } from "@/components/ui/AILoadingSpinner";
import { ShimmerText } from "@/components/ui/ShimmerText";
import type { ReasoningStepOut } from "@/lib/api";

const STORAGE_KEY = "epr:reasoningPanelCollapsed";

/** Docked reasoning panel (T13.5b plan, Part 4) — only rendered at lg and
 * above (see ProcessorTabs' useIsBreakpointUp(1024) check — moved from
 * xl in T13.5c plan, Batch 0.9, per the developer's note); below lg,
 * ReasoningLog is rendered directly as the "Agent Reasoning" tab instead,
 * with no dock/collapse chrome. Collapse state persists in localStorage
 * so a repeat visitor's choice sticks; top offset matches StickyHeader's
 * own lg:top-16, stacking directly below it rather than overlapping.
 *
 * `currentStageLabel` (Kokonut addendum's "AI Loading" equivalent) — set
 * only while a live run is active and hasn't produced its first reasoning
 * step yet (still reading documents / running checks); shows the real
 * stage name, never invented progress. */
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

  return (
    <aside className="hidden lg:block lg:sticky lg:top-16 lg:self-start">
      <div className="card flex max-h-[calc(100vh-5rem)] flex-col p-0">
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border px-4 py-3">
          <p className="font-display text-sm font-semibold text-ink">Reasoning</p>
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-expanded={!collapsed}
            aria-label={collapsed ? "Expand reasoning panel" : "Collapse reasoning panel"}
            className="flex h-10 w-10 items-center justify-center rounded-md text-ink-muted hover:bg-surface-sunk hover:text-ink"
          >
            <ChevronLeft
              aria-hidden
              size={16}
              className={`transition-transform duration-200 ${collapsed ? "rotate-180" : ""}`}
            />
          </button>
        </div>
        {/* hydrated gate avoids a one-frame flash of the wrong collapsed
            state on a repeat visitor (localStorage is unreadable during
            SSR) — the panel renders expanded-but-empty-looking for a
            moment rather than ever showing the stored "collapsed" state
            flipping open right after mount. */}
        {hydrated && collapsed ? null : (
          <div className="relative min-h-0 flex-1">
            <div ref={scrollRef} onScroll={handleScroll} className="h-full overflow-y-auto px-4 py-3">
              {isLive && steps.length === 0 && currentStageLabel ? (
                <div className="flex items-center gap-2 text-sm">
                  <AILoadingSpinner className="h-5 w-5 shrink-0" />
                  <ShimmerText className="font-medium text-ink">{currentStageLabel}</ShimmerText>
                </div>
              ) : (
                <ReasoningLog steps={steps} knownDocIds={knownDocIds} isLive={isLive} />
              )}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
