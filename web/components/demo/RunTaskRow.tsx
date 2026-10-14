"use client";

import { Check, ChevronDown, OctagonAlert } from "lucide-react";
import type { RunRow } from "@/lib/runRows";
import { AILoadingSpinner } from "@/components/ui/AILoadingSpinner";

/** One pill-shaped task row in the live-run panel (T16b).
 *
 * Anatomy, left to right: status icon, stage title (truncated), a short
 * muted detail, a status tag once terminal, and a chevron. The chevron
 * becomes interactive when the rows gain their expandable bodies; this
 * item renders the row's resting appearance only.
 *
 * **Every state's icon occupies the same 20px box**, deliberately: the
 * spinner is sized to match the completed tick so a row does not shift
 * sideways the instant its stage finishes. That is the one thing a viewer
 * is looking straight at when it happens.
 *
 * Icon colours are picked for contrast in both themes rather than by
 * name. The tick is `text-primary-foreground`, which is white in light
 * and navy in dark — a white tick on dark's lighter `--color-risk-low`
 * (#4ade80) measures 1.7:1 and would be nearly invisible, where navy on
 * it measures 9.4:1. Colour is never the only signal: each state also has
 * a distinct icon shape, and the terminal states carry a text tag. */

// The /5 tint, not /10, and the same pairing RiskBadge already uses: at
// /10 the light-theme Completed tag measured 4.37:1, just under AA's
// 4.5:1 floor for text this size. /5 leaves a lighter background and
// clears it. Measured on the painted pixel, not assumed.
const TAG_STYLE: Record<NonNullable<RunRow["tag"]>, string> = {
  Completed: "bg-risk-low/5 text-risk-low",
  Failed: "bg-risk-high/5 text-risk-high",
};

function StatusIcon({ row }: { row: RunRow }) {
  if (row.state === "done") {
    return (
      <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-risk-low text-primary-foreground">
        <Check aria-hidden size={13} strokeWidth={3} />
      </span>
    );
  }
  if (row.state === "failed") {
    return <OctagonAlert aria-hidden size={20} className="size-5 shrink-0 text-risk-high" />;
  }
  if (row.state === "in_progress") {
    return <AILoadingSpinner className="size-5 shrink-0" />;
  }
  return (
    <span className="flex size-5 shrink-0 items-center justify-center rounded-full border border-border text-[11px] font-medium tabular-nums text-ink-muted">
      {row.index}
    </span>
  );
}

export function RunTaskRow({ row }: { row: RunRow }) {
  return (
    <li className="flex min-h-11 items-center gap-3 rounded-full bg-surface px-3 py-2 shadow-resting">
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

      <ChevronDown aria-hidden size={16} className="shrink-0 text-ink-muted" />
    </li>
  );
}
