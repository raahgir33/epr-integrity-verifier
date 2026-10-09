"use client";

import { useState } from "react";
import Link from "next/link";
import { Tabs } from "@/components/ui/Tabs";

const AUDIENCES = [
  {
    value: "brands",
    label: "Brand owners",
    body: "See the share of your certified tonnes that is independently verifiable, apportioned across every processor you hold certificates with.",
    linkHref: "/portfolio",
    linkLabel: "View your portfolio",
  },
  {
    value: "processors",
    label: "Processors",
    body: "Every finding comes with its evidence — see exactly what was checked, what the agents found, and what a clarification request would ask for before it's sent.",
    linkHref: "/method",
    linkLabel: "Read the method",
  },
  {
    value: "auditors",
    label: "Auditors & regulators",
    body: "Cross-processor checks, a full reasoning trail per certificate batch, and a measured accuracy report against a seeded, held-out test set.",
    linkHref: "/evaluation",
    linkLabel: "See the evaluation",
  },
];

export function AudienceTabs() {
  const [value, setValue] = useState("brands");

  return (
    <Tabs
      value={value}
      onValueChange={setValue}
      items={AUDIENCES.map((a) => ({
        value: a.value,
        label: a.label,
        content: (
          <div className="card p-5">
            <p className="max-w-[60ch] text-sm text-ink-muted">{a.body}</p>
            <Link
              href={a.linkHref}
              className="mt-3 inline-block text-sm font-medium text-primary underline decoration-dotted hover:text-accent"
            >
              {a.linkLabel} →
            </Link>
          </div>
        ),
      }))}
    />
  );
}
