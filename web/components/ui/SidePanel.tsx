"use client";

import * as RadixDialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";
import { X } from "lucide-react";

/** Slide-over side panel (T13.5 plan, Part 2), built on Radix Dialog —
 * used to show a document's image + extracted fields, or a finding's
 * full evidence, without leaving the current tab/scroll position. */
export function SidePanel({
  open,
  onOpenChange,
  title,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: ReactNode;
}) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="side-panel-overlay fixed inset-0 z-40 bg-ink/40" />
        <RadixDialog.Content
          className="side-panel-content fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-surface shadow-xl focus:outline-none sm:max-w-lg"
          aria-describedby={undefined}
        >
          <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-4">
            <RadixDialog.Title className="font-display text-base font-semibold text-ink">
              {title}
            </RadixDialog.Title>
            <RadixDialog.Close
              aria-label="Close panel"
              className="flex h-8 w-8 items-center justify-center rounded-md text-ink-muted hover:bg-surface-sunk hover:text-ink"
            >
              <X aria-hidden size={16} />
            </RadixDialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
