"use client";

import * as RadixTabs from "@radix-ui/react-tabs";
import type { ReactNode } from "react";
import { titleCase } from "@/lib/titleCase";

export type TabItem = {
  value: string;
  label: string;
  content: ReactNode;
};

/** Styled Radix tabs (T13.5 plan, Part 2). Purely presentational — value
 * is always controlled by the caller, so a page that needs to sync the
 * active tab to a URL query param (processor page, Part 4) owns that
 * logic itself rather than this component reaching into next/navigation. */
export function Tabs({
  items,
  value,
  onValueChange,
  listClassName = "",
}: {
  items: TabItem[];
  value: string;
  onValueChange: (value: string) => void;
  listClassName?: string;
}) {
  return (
    <RadixTabs.Root value={value} onValueChange={onValueChange}>
      <RadixTabs.List
        aria-label="Sections"
        className={`flex flex-wrap gap-x-1 gap-y-1 overflow-x-auto border-b border-border ${listClassName}`}
      >
        {items.map((item) => (
          <RadixTabs.Trigger
            key={item.value}
            value={item.value}
            className="whitespace-nowrap border-b-2 border-transparent px-3 py-2.5 text-sm font-medium text-ink-muted outline-none transition-colors duration-150 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary data-[state=active]:border-primary data-[state=active]:text-primary"
          >
            {titleCase(item.label)}
          </RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
      {items.map((item) => (
        <RadixTabs.Content
          key={item.value}
          value={item.value}
          className="pt-4 outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          {item.content}
        </RadixTabs.Content>
      ))}
    </RadixTabs.Root>
  );
}
