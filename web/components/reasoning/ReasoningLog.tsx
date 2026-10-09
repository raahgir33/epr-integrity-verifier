"use client";

import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { AnimatedListItem } from "@/components/magicui/animated-list";
import { StepDetail } from "@/components/reasoning/StepDetail";
import type { ReasoningStepOut } from "@/lib/api";
import { stepActionLine, stepTag, type StepTag } from "@/lib/reasoning";

/** T13.5b plan, Part 4 — a log-style reasoning panel, newest entry on
 * top, replacing the old numbered timeline. Each entry: a colored dot on
 * a connecting vertical line, an agent tag, "Step N" (no timestamp field
 * exists on ReasoningStepOut today — see lib/reasoning.ts), a one-line
 * action, and an expand toggle whose detail panel animates (200ms; 0ms
 * under reduced motion, via motion's own useReducedMotion rather than a
 * CSS media query, since this is a JS height animation). */

const TAG_DOT: Record<StepTag, string> = {
  Hypothesis: "bg-primary",
  Critic: "bg-accent",
  Revision: "bg-glow",
  Tool: "bg-ink-muted",
  Score: "bg-ink-muted",
};

function LogRowContent({
  step,
  knownDocIds,
}: {
  step: ReasoningStepOut;
  knownDocIds: ReadonlySet<string>;
}) {
  const [open, setOpen] = useState(false);
  const reducedMotion = useReducedMotion();
  const tag = stepTag(step);
  const hasTiming = step.latency_ms !== null || !!step.tokens;

  return (
    <div className="min-w-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-start justify-between gap-2 text-left"
      >
        <span className="min-w-0">
          <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="text-xs font-semibold uppercase tracking-wide text-ink">{tag}</span>
            <span className="text-xs text-ink-muted">Step {step.step_index + 1}</span>
          </span>
          <span className="mt-0.5 block text-sm text-ink-muted">{stepActionLine(step)}</span>
        </span>
        <svg
          viewBox="0 0 16 16"
          aria-hidden
          className={`mt-0.5 h-4 w-4 shrink-0 text-ink-muted transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        >
          <path
            d="M4 6l4 4 4-4"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: reducedMotion ? 0 : 0.2 }}
            className="overflow-hidden"
          >
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
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function LogRow({
  step,
  knownDocIds,
  animateIn,
}: {
  step: ReasoningStepOut;
  knownDocIds: ReadonlySet<string>;
  animateIn: boolean;
}) {
  const tag = stepTag(step);
  const content = <LogRowContent step={step} knownDocIds={knownDocIds} />;

  return (
    <li className="relative pb-5 pl-6 last:pb-0">
      <span aria-hidden className="absolute bottom-0 left-[5px] top-4 w-px bg-border last:hidden" />
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

export function ReasoningLog({
  steps,
  knownDocIds,
  isLive = false,
}: {
  steps: ReasoningStepOut[];
  knownDocIds: ReadonlySet<string>;
  isLive?: boolean;
}) {
  const reducedMotion = useReducedMotion();

  if (steps.length === 0) {
    return <p className="text-sm text-ink-muted">No agent run has happened for this processor yet.</p>;
  }

  const newestFirst = [...steps].reverse();

  return (
    <ol>
      {newestFirst.map((step) => (
        <LogRow
          key={step.step_index}
          step={step}
          knownDocIds={knownDocIds}
          animateIn={isLive && !reducedMotion}
        />
      ))}
    </ol>
  );
}
