"use client";
// Required, not optional — see WhatWeCheck.tsx's identical comment:
// Accordion's `items` prop carries React elements, and building that
// array in a Server Component passed across the RSC boundary into a
// Client Component produced a spurious "missing key" dev warning.

import { Accordion } from "@/components/ui/Accordion";

const FAQS = [
  {
    id: "errors",
    q: "What happens when extraction or a check fails for a document?",
    a: "It's recorded and shown as \"could not verify\" rather than hidden. A failed or missing step never silently counts as a pass, and a slow or failed live call never breaks a page, since every page reads results we've already computed.",
  },
  {
    id: "two-agents",
    q: "Why two AI agents instead of one?",
    a: "A Hypothesis agent argues a certificate batch is or isn't supported. A Critic agent then attacks that argument with its own tools and evidence. A finding only becomes a deduction once both agree, so one agent's claim alone is never enough, and a disagreement becomes a visible review flag instead of a silent deduction.",
  },
  {
    id: "synthetic",
    q: "Is this real data?",
    a: "No. Every processor, document, brand and certificate shown here is synthetic and fictional, generated purely for demonstration. No real company, recycler or brand is represented or implicated.",
  },
  {
    id: "unverifiable",
    q: "What does \"unverifiable\" mean?",
    a: "It means a certified tonne couldn't be traced to a plausible, consistent, physically possible material flow. It doesn't mean fraud. Findings are described as unverifiable, inconsistent or implausible, never as fraud.",
  },
];

export function Faq() {
  return (
    <Accordion
      items={FAQS.map((f) => ({ id: f.id, trigger: <span className="text-ink">{f.q}</span>, content: <p>{f.a}</p> }))}
    />
  );
}
