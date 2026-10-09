"use client";

import * as RadixAccordion from "@radix-ui/react-accordion";
import type { ReactNode } from "react";

export type AccordionItemData = {
  id: string;
  trigger: ReactNode;
  content: ReactNode;
};

/** Styled Radix accordion (T13.5 plan, Part 2) — single-open by default.
 * Pass type="multiple" items individually if a future caller needs more
 * than one section open at once; not needed by anything built so far. */
export function Accordion({
  items,
  defaultValue,
}: {
  items: AccordionItemData[];
  defaultValue?: string;
}) {
  return (
    <RadixAccordion.Root
      type="single"
      collapsible
      defaultValue={defaultValue}
      className="divide-y divide-border"
    >
      {items.map((item) => (
        <RadixAccordion.Item key={item.id} value={item.id}>
          <RadixAccordion.Header>
            <RadixAccordion.Trigger className="group flex w-full items-center justify-between gap-4 py-4 text-left text-sm font-medium text-ink hover:text-primary">
              {item.trigger}
              <svg
                viewBox="0 0 16 16"
                aria-hidden
                className="h-4 w-4 shrink-0 text-ink-muted transition-transform duration-200 group-data-[state=open]:rotate-180"
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
            </RadixAccordion.Trigger>
          </RadixAccordion.Header>
          <RadixAccordion.Content className="accordion-content text-sm text-ink-muted">
            <div className="pb-4">{item.content}</div>
          </RadixAccordion.Content>
        </RadixAccordion.Item>
      ))}
    </RadixAccordion.Root>
  );
}
