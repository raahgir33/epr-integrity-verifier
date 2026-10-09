"use client";

import * as RadixAccordion from "@radix-ui/react-accordion";
import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";

export type AccordionItemData = {
  id: string;
  trigger: ReactNode;
  content: ReactNode;
};

const ITEM_CLASSNAME =
  "group flex w-full items-center justify-between gap-4 py-4 text-left text-sm font-medium text-ink outline-none transition-colors duration-150 hover:text-primary focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

function AccordionItems({ items }: { items: AccordionItemData[] }) {
  return (
    <>
      {items.map((item) => (
        <RadixAccordion.Item key={item.id} value={item.id}>
          <RadixAccordion.Header>
            <RadixAccordion.Trigger className={ITEM_CLASSNAME}>
              {item.trigger}
              <ChevronDown
                aria-hidden
                size={16}
                className="shrink-0 text-ink-muted transition-transform duration-200 group-data-[state=open]:rotate-180"
              />
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
