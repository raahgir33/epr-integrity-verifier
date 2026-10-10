"use client";

import { forwardRef, useImperativeHandle, useState } from "react";
import { ChevronDown } from "lucide-react";
import { AnimatedListItem } from "@/components/magicui/animated-list";
import { StepDetail } from "@/components/reasoning/StepDetail";
import type { ReasoningStepOut } from "@/lib/api";
import { stepActionLine, stepTag, type StepTag } from "@/lib/reasoning";
import { titleCase } from "@/lib/titleCase";
import { usePrefersReducedMotion } from "@/lib/usePrefersReducedMotion";

/** T13.5b plan, Part 4 — a log-style reasoning panel, newest entry on
 * top, replacing the old numbered timeline. Each entry: a colored dot on
 * a connecting vertical line, an agent tag, "Step N" (no timestamp field
 * exists on ReasoningStepOut today — see lib/reasoning.ts), a one-line
 * action, and an expand toggle whose detail panel animates open.
 *
 * Round 7 fix, part 1 (developer-reported, 2026-10-10): the detail panel
 * used to animate via motion/react's height: 0 -> "auto", which measures
 * the content's pixel height in JS before animating to it. With more
 * than one row expanded at once inside the docked panel's own
 * overflow-auto scroll box, that measurement raced against the sibling
 * row's own reflow and the panel's content visibly spilled past the
 * card's edge. Replaced with the CSS-only grid-template-rows: 0fr -> 1fr
 * technique (no JS measurement, nothing to race) — the row's box is
 * always exactly its current animated size, so there's nothing to
 * overflow.
 *
 * Round 7 fix, part 2: that wasn't the whole bug — see
 * ReasoningPanel.tsx's own doc comment for the real root cause (the
 * panel's card had no definite height for its flex-grow body to fill).
 * This file's own change here is unrelated plumbing for the same report:
 * each row's open/closed state moved from local useState into a Set kept
 * in this component, exposed via a forwardRef handle (expandAll/
 * collapseAll) so ReasoningPanel's new header buttons can drive every
 * row at once. */

const TAG_DOT: Record<StepTag, string> = {
  Hypothesis: "bg-primary",
  Critic: "bg-ink",
  Revision: "bg-glow",
  Tool: "bg-ink-muted",
  Score: "bg-ink-muted",
};

function LogRowContent({
  step,
  knownDocIds,
  open,
  onToggle,
}: {
  step: ReasoningStepOut;
  knownDocIds: ReadonlySet<string>;
  open: boolean;
  onToggle: () => void;
}) {
  const tag = stepTag(step);
  const hasTiming = step.latency_ms !== null || !!step.tokens;

  return (
    <div className="min-w-0">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-start justify-between gap-2 text-left"
      >
        <span className="min-w-0">
          <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="text-xs font-semibold uppercase tracking-wide text-ink">{tag}</span>
            <span className="text-xs text-ink-muted">Step {step.step_index + 1}</span>
          </span>
          {/* T13.5c plan, Batch 0.9: the developer's note explicitly asks
              for this one-line headline in title case, overriding
              titleCase.ts's own general "never on interpolated data"
              guidance — checked safe against titleCase's preservation
              rules (hyphenated/digit-bearing/mixed-case tokens like
              document IDs or "C2a" survive untouched). Scoped to this
              exact render site only — StepDetail/ToolStep (details, tool
              arguments, results) are untouched. */}
          <span className="mt-0.5 block text-sm text-ink-muted">{titleCase(stepActionLine(step))}</span>
        </span>
        <ChevronDown
          aria-hidden
          size={16}
          className={`mt-0.5 shrink-0 text-ink-muted transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>
      <div
        className={`grid transition-[grid-template-rows] duration-200 ease-out motion-reduce:transition-none ${
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
        }`}
      >
        <div className={`min-h-0 overflow-hidden transition-opacity duration-200 ${open ? "opacity-100" : "opacity-0"}`}>
          <div className="mt-2 pb-1">
            <StepDetail step={step} knownDocIds={knownDocIds} />
            {hasTiming ? (
              <p className="mt-1 text-[11px] text-ink-muted">
                {step.latency_ms !== null ? `${Math.round(step.latency_ms)} ms` : null}
                {step.tokens && Object.values(step.tokens).some((v) => v !== null)
                  ? ` · ${Object.entries(step.tokens)
                      .filter(([, v]) => v !== null)
                      .map(([k, v]) => `${k} ${v}`)
                      .join(", ")}`
                  : null}
              </p>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function LogRow({
  step,
  knownDocIds,
  animateIn,
  open,
  onToggle,
}: {
  step: ReasoningStepOut;
  knownDocIds: ReadonlySet<string>;
  animateIn: boolean;
  open: boolean;
  onToggle: () => void;
}) {
  const tag = stepTag(step);
  const content = <LogRowContent step={step} knownDocIds={knownDocIds} open={open} onToggle={onToggle} />;

  return (
    <li className="relative pb-5 pl-6 last:pb-0">
      {/* T13.5c plan, Audit Batch 3: the 1px line is centered exactly on
          the 10px dot's own center (dot at left-0, width 2.5 = 10px, so
          center = 5px; a 1px-wide line needs its own left edge at 4.5px,
          not 5px, so its center lands on 5px too — the previous left-
          [5px] put the line's visible center half a pixel right of the
          dot's). */}
      <span aria-hidden className="absolute bottom-0 left-[4.5px] top-4 w-px bg-border last:hidden" />
      <span aria-hidden className={`absolute left-0 top-1 h-2.5 w-2.5 rounded-full ${TAG_DOT[tag]}`} />
      {/* Mount-time animation only (no AnimatePresence at the list level —
          steps are only ever appended, never removed, so there's nothing
          to exit-animate; a stable key means an already-rendered row never
          replays this on re-render). AnimatedListItem is Magic UI's
          vendored per-item spring — reused here as the inner wrapper,
          inside the <li>, not wrapping it, so the DOM stays valid
          (<li><div>...) rather than a <div> landing directly under <ol>. */}
      {animateIn ? <AnimatedListItem>{content}</AnimatedListItem> : content}
    </li>
  );
}

export type ReasoningLogHandle = {
  expandAll: () => void;
  collapseAll: () => void;
};

export const ReasoningLog = forwardRef<
  ReasoningLogHandle,
  {
    steps: ReasoningStepOut[];
    knownDocIds: ReadonlySet<string>;
    isLive?: boolean;
  }
>(function ReasoningLog({ steps, knownDocIds, isLive = false }, ref) {
  const reducedMotion = usePrefersReducedMotion();
  const [openIndexes, setOpenIndexes] = useState<ReadonlySet<number>>(() => new Set());

  useImperativeHandle(
    ref,
    () => ({
      expandAll: () => setOpenIndexes(new Set(steps.map((s) => s.step_index))),
      collapseAll: () => setOpenIndexes(new Set()),
    }),
    [steps],
  );

  if (steps.length === 0) {
    return <p className="text-sm text-ink-muted">No agent run has happened for this processor yet.</p>;
  }

  const newestFirst = [...steps].reverse();

  function toggle(stepIndex: number) {
    setOpenIndexes((prev) => {
      const next = new Set(prev);
      if (next.has(stepIndex)) {
        next.delete(stepIndex);
      } else {
        next.add(stepIndex);
      }
      return next;
    });
  }

  return (
    <ol>
      {newestFirst.map((step) => (
        <LogRow
          key={step.step_index}
          step={step}
          knownDocIds={knownDocIds}
          animateIn={isLive && !reducedMotion}
          open={openIndexes.has(step.step_index)}
          onToggle={() => toggle(step.step_index)}
        />
      ))}
    </ol>
  );
});
