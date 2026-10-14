"use client";

import { useEffect, useRef } from "react";
import { useScrollFade } from "@/lib/useScrollFade";
import { Check, ChevronDown, OctagonAlert } from "lucide-react";
import type { RunRow } from "@/lib/runRows";
import { AILoadingSpinner } from "@/components/ui/AILoadingSpinner";

/** One pill-shaped task row in the live-run panel (T16b).
 *
 * Anatomy, left to right: status icon, stage title (truncated), a short
 * muted detail, a status tag once terminal, and a chevron. The whole
 * header is the toggle, so the chevron needs no hit area of its own —
 * which also avoids two overlapping targets in a 44px row.
 *
 * **Every state's icon occupies the same 24px box**, deliberately: the
 * spinner is sized to match the completed tick so a row does not shift
 * sideways the instant its stage finishes. That is the one thing a viewer
 * is looking straight at when it happens, which is also why the running
 * spinner could not simply be enlarged on its own — every state grew
 * together instead, which is the only way to make it bigger and keep the
 * row still.
 *
 * Icon colours are picked for contrast in both themes rather than by
 * name. The tick is `text-primary-foreground`, which is white in light
 * and navy in dark — a white tick on dark's lighter `--color-risk-low`
 * (#4ade80) measures 1.7:1 and would be nearly invisible, where navy on
 * it measures 9.4:1. Colour is never the only signal: each state also has
 * a distinct icon shape, and the terminal states carry a text tag.
 *
 * **The body expands with CSS grid, not a measured height.** ReasoningLog
 * had to be corrected to this exact technique: animating height 0 ->
 * "auto" measures the content in JS first, and inside a scrolling panel
 * that measurement races the sibling rows' own reflow, so content visibly
 * spilled past the card's edge. `grid-template-rows: 0fr -> 1fr` needs no
 * measurement, so there is nothing to race. */

// The /5 tint, not /10, and the same pairing RiskBadge already uses: at
// /10 the light-theme Completed tag measured 4.37:1, under AA's 4.5:1
// floor for text this size. /5 leaves a lighter background and clears it.
// Measured on the painted pixel, not assumed.
const TAG_STYLE: Record<NonNullable<RunRow["tag"]>, string> = {
  Completed: "bg-risk-low/5 text-risk-low",
  Failed: "bg-risk-high/5 text-risk-high",
};

function StatusIcon({ row }: { row: RunRow }) {
  if (row.state === "done") {
    return (
      <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-risk-low text-primary-foreground">
        <Check aria-hidden size={15} strokeWidth={3} />
      </span>
    );
  }
  if (row.state === "failed") {
    return <OctagonAlert aria-hidden size={24} className="size-6 shrink-0 text-risk-high" />;
  }
  if (row.state === "in_progress") {
    return <AILoadingSpinner className="size-6 shrink-0" />;
  }
  return (
    <span className="flex size-6 shrink-0 items-center justify-center rounded-full border border-border text-xs font-medium tabular-nums text-ink-muted">
      {row.index}
    </span>
  );
}

export function RunTaskRow({
  row,
  open,
  onToggle,
}: {
  row: RunRow;
  open: boolean;
  onToggle: () => void;
}) {
  const { ref: scrollRef, fade, onScroll: measureFade } = useScrollFade(`${row.lines.length}:${open}`);
  const atBottomRef = useRef(true);
  const lineCountRef = useRef(row.lines.length);
  const headerId = `run-row-${row.id}-header`;
  const bodyId = `run-row-${row.id}-body`;

  // Follow an arriving line only when the viewer is already at the
  // bottom. Scrolling up inside a row to read an earlier step must not be
  // undone 2.5s later by the next poll — the same rule the processor
  // page's reasoning panel follows, measured from the other end.
  useEffect(() => {
    const grew = row.lines.length > lineCountRef.current;
    lineCountRef.current = row.lines.length;
    const element = scrollRef.current;
    if (!grew || !open || !element || !atBottomRef.current) return;
    element.scrollTop = element.scrollHeight;
  }, [row.lines.length, open, scrollRef]);

  function handleScroll() {
    const element = scrollRef.current;
    if (element) {
      atBottomRef.current = element.scrollHeight - element.scrollTop - element.clientHeight <= 8;
    }
    measureFade();
  }

  return (
    <li
      className={`bg-surface shadow-resting transition-[border-radius] duration-200 ease-out motion-reduce:transition-none ${
        open ? "rounded-2xl" : "rounded-full"
      }`}
    >
      <button
        type="button"
        id={headerId}
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={bodyId}
        className="flex min-h-11 w-full items-center gap-3 rounded-full px-3 py-2 text-left outline-none focus-visible:outline-solid focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
      >
        <StatusIcon row={row} />

        <span
          className={`min-w-0 flex-1 truncate text-sm font-medium ${
            row.state === "waiting" ? "text-ink-muted" : "text-ink"
          }`}
        >
          {row.title}
        </span>

        {row.detail ? (
          <span className="shrink-0 text-xs tabular-nums text-ink-muted">{row.detail}</span>
        ) : null}

        {row.tag ? (
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${TAG_STYLE[row.tag]}`}
          >
            {row.tag}
          </span>
        ) : null}

        <ChevronDown
          aria-hidden
          size={16}
          className={`shrink-0 text-ink-muted transition-transform duration-200 motion-reduce:transition-none ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      <div
        id={bodyId}
        role="region"
        aria-labelledby={headerId}
        className={`grid transition-[grid-template-rows] duration-200 ease-out motion-reduce:transition-none ${
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
        }`}
      >
        <div className="min-h-0 overflow-hidden">
          {/* Capped and scrolled per row, so one long reasoning trail
              cannot push the panel past the card's height. */}
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            className={`scrollbar-subtle max-h-28 overflow-y-auto overscroll-contain px-3 pb-3 pl-10 ${
              fade ? "fade-bottom" : ""
            }`}
          >
            <ul className="space-y-1.5 border-l border-border pl-3">
              {row.lines.map((line, i) => (
                <li
                  key={`${line.label}-${i}`}
                  className="flex items-baseline justify-between gap-3 text-xs"
                >
                  <span className="min-w-0 text-ink-muted">{line.label}</span>
                  {line.value ? (
                    <span
                      className={`shrink-0 tabular-nums text-ink-muted ${line.mono ? "font-mono" : ""}`}
                    >
                      {line.value}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </li>
  );
}
