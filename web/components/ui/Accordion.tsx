"use client";

import * as RadixAccordion from "@radix-ui/react-accordion";
import type { ReactNode } from "react";

export type AccordionItemData = {
  id: string;
  trigger: ReactNode;
  content: ReactNode;
};

const ITEM_CLASSNAME = "group flex w-full items-center justify-between gap-4 py-4 text-left text-sm font-medium text-ink hover:text-primary";

function AccordionItems({ items }: { items: AccordionItemData[] }) {
  return (
    <>
      {items.map((item) => (
        <RadixAccordion.Item key={item.id} value={item.id}>
          <RadixAccordion.Header>
            <RadixAccordion.Trigger className={ITEM_CLASSNAME}>
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
    </>
  );
}

/** Styled Radix accordion (T13.5 plan, Part 2) — single-open by default.
 * `type="multiple"` (T13.5b plan, Part 5 — DocumentsTable's grouped-by-
 * type sections, each independently toggleable) takes `defaultValue` as
 * an array instead of a string; Radix's own types require branching on
 * `type` rather than passing one prop shape through to either variant. */
export function Accordion(
  props:
    | { type?: "single"; items: AccordionItemData[]; defaultValue?: string }
    | { type: "multiple"; items: AccordionItemData[]; defaultValue?: string[] },
) {
  if (props.type === "multiple") {
    return (
      <RadixAccordion.Root type="multiple" defaultValue={props.defaultValue} className="divide-y divide-border">
        <AccordionItems items={props.items} />
      </RadixAccordion.Root>
    );
  }
  return (
    <RadixAccordion.Root
      type="single"
      collapsible
      defaultValue={props.defaultValue}
      className="divide-y divide-border"
    >
      <AccordionItems items={props.items} />
    </RadixAccordion.Root>
  );
}
