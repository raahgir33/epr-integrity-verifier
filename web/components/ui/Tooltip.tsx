"use client";

import * as RadixTooltip from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";

/** Styled Radix tooltip (T13.5 plan, Part 2) — used for unit/threshold
 * explanations. Fade transition lives in globals.css's .tooltip-content
 * rule, guarded by prefers-reduced-motion there. */
export function TooltipProvider({ children }: { children: ReactNode }) {
  return <RadixTooltip.Provider delayDuration={200}>{children}</RadixTooltip.Provider>;
}

export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <RadixTooltip.Root>
      <RadixTooltip.Trigger asChild>
        <span
          tabIndex={0}
          className="cursor-help underline decoration-dotted decoration-ink-muted outline-none focus-visible:rounded-sm focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          {children}
        </span>
      </RadixTooltip.Trigger>
      <RadixTooltip.Portal>
        <RadixTooltip.Content
          side="top"
          sideOffset={6}
          className="tooltip-content z-50 max-w-xs rounded-md bg-ink px-2.5 py-1.5 text-xs text-primary-foreground shadow-overlay"
        >
          {label}
          <RadixTooltip.Arrow className="fill-ink" />
        </RadixTooltip.Content>
      </RadixTooltip.Portal>
    </RadixTooltip.Root>
  );
}
