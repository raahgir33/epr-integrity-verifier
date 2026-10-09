"use client";
// "use client" is required — see WhatWeCheck.tsx's identical comment:
// building the AUDIENCES-derived array of React elements in a Server
// Component and passing it across the RSC boundary reliably produced a
// spurious "missing key" dev warning.

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { RiskBadge } from "@/components/RiskBadge";
import { STATUS_LABEL } from "@/lib/checks";
import { classificationLabel } from "@/lib/findings";
import { formatTonnes } from "@/lib/format";
import type { ProcessorDetailResponse } from "@/lib/api";
import type { RealExamples } from "@/lib/landing";

function BrandIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className="h-6 w-6">
      <path
        d="M4 20V9l8-5 8 5v11M4 20h16M9 20v-6h6v6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ProcessorIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className="h-6 w-6">
      <path
        d="M4 20V11l4 3v-3l4 3v-3l4 3V6l4-2v16H4Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function AuditorIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className="h-6 w-6">
      <circle cx="10.5" cy="10.5" r="6" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M15.2 15.2 20 20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

type Audience = {
  value: string;
  label: string;
  Icon: () => ReactNode;
  benefits: string[];
  linkHref: string;
  linkLabel: string;
};

const AUDIENCES: Audience[] = [
  {
    value: "brands",
    label: "Brand owners",
    Icon: BrandIcon,
    benefits: [
      "See the share of your certified tonnes that is independently verifiable, not just purchased.",
      "Apportioned across every processor you hold certificates with, from each processor's own verifiable ratio.",
      "A risk band per processor, so you know where to ask questions before an audit does.",
    ],
    linkHref: "/portfolio",
    linkLabel: "View your portfolio",
  },
  {
    value: "processors",
    label: "Processors",
    Icon: ProcessorIcon,
    benefits: [
      "Every finding comes with its evidence — see exactly what was checked and why.",
      "A finding only becomes a deduction once two independent agents agree on it.",
      "See what a clarification request would ask for before it's ever sent to you.",
    ],
    linkHref: "/method",
    linkLabel: "Read the method",
  },
  {
    value: "auditors",
    label: "Auditors & regulators",
    Icon: AuditorIcon,
    benefits: [
      "Cross-processor checks against the same deterministic thresholds, every time.",
      "A full reasoning trail per certificate batch — nothing the agents concluded is hidden.",
      "A measured accuracy report against a seeded, held-out test set, not a self-reported claim.",
    ],
    linkHref: "/evaluation",
    linkLabel: "See the evaluation",
  },
];

function ExampleCard({ audience, details, examples }: { audience: string; details: ProcessorDetailResponse[]; examples: RealExamples }) {
  if (audience === "brands") {
    const detail = details[0];
    if (!detail) return null;
    const stage = detail.full ?? detail.checks_only;
    return (
      <Link href="/portfolio" className="card block p-4 transition-colors duration-150 hover:border-primary">
        <div className="flex items-start justify-between gap-2">
          <p className="font-mono text-xs text-ink-muted">{detail.profile.processor_id}</p>
          <RiskBadge band={stage.risk_band} />
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
          <dt className="text-ink-muted">Certified</dt>
          <dd className="num-cell text-ink">{formatTonnes(detail.checks_only.certified_t)}</dd>
          <dt className="text-ink-muted">Verifiable</dt>
          <dd className="num-cell text-ink">{formatTonnes(stage.verifiable_t)}</dd>
        </dl>
        <p className="mt-3 text-xs font-medium text-primary">See the full portfolio →</p>
      </Link>
    );
  }

  if (audience === "processors") {
    const ex = examples.finding;
    if (!ex) return null;
    return (
      <Link
        href={`/processors/${encodeURIComponent(ex.processorId)}`}
        className="card block p-4 transition-colors duration-150 hover:border-primary"
      >
        <p className="font-mono text-xs text-ink-muted">{ex.processorId}</p>
        <p className="mt-2 text-sm font-medium text-ink">{ex.finding.finding_type}</p>
        <p className="mt-1 text-sm text-ink-muted">{ex.finding.explanation}</p>
        <p className="mt-2 text-xs font-medium text-ink-muted">{classificationLabel(ex.finding)}</p>
        <p className="mt-3 text-xs font-medium text-primary">Open this processor →</p>
      </Link>
    );
  }

  const ex = examples.failingCheck;
  if (!ex) return null;
  return (
    <Link href="/evaluation" className="card block p-4 transition-colors duration-150 hover:border-primary">
      <p className="font-mono text-xs text-ink-muted">{ex.processorId}</p>
      <p className="mt-2 text-sm">
        <span className="font-mono font-medium text-ink">{ex.check.check_id}</span>{" "}
        <span className="text-ink-muted">{STATUS_LABEL[ex.check.status] ?? ex.check.status}</span>
      </p>
      <p className="mt-1 text-sm text-ink-muted">{ex.check.explanation}</p>
      <p className="mt-3 text-xs font-medium text-primary">See the evaluation protocol →</p>
    </Link>
  );
}

/** Who It's For (T13.5b plan, Part 5) — large icon tab buttons, each
 * opening a two-column panel: a benefits list and a live example card
 * built from data app/page.tsx already fetched (no new API calls). */
export function AudienceTabs({
  details,
  examples,
}: {
  details: ProcessorDetailResponse[];
  examples: RealExamples;
}) {
  const [value, setValue] = useState(AUDIENCES[0].value);
  const active = AUDIENCES.find((a) => a.value === value) ?? AUDIENCES[0];

  return (
    <div>
      <div role="tablist" aria-label="Audience" className="flex flex-wrap gap-3">
        {AUDIENCES.map((a) => {
          const isActive = a.value === value;
          return (
            <button
              key={a.value}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setValue(a.value)}
              className={`flex items-center gap-3 rounded-xl border px-5 py-4 text-left transition-colors duration-150 ${
                isActive
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-surface text-ink hover:bg-surface-sunk"
              }`}
            >
              <a.Icon />
              <span className="font-display text-base font-semibold">{a.label}</span>
            </button>
          );
        })}
      </div>

      <div className="card mt-5 grid grid-cols-1 gap-6 p-6 lg:grid-cols-2">
        <div>
          <ul className="space-y-4">
            {active.benefits.map((benefit) => (
              <li key={benefit} className="flex gap-3 text-base text-ink">
                <svg viewBox="0 0 16 16" aria-hidden className="mt-1 h-4 w-4 shrink-0 text-primary">
                  <path
                    d="M3 8.5 6.2 11.5 13 4.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span>{benefit}</span>
              </li>
            ))}
          </ul>
          <Link
            href={active.linkHref}
            className="mt-5 inline-block text-sm font-medium text-primary underline decoration-dotted hover:opacity-80"
          >
            {active.linkLabel} →
          </Link>
        </div>
        <ExampleCard audience={active.value} details={details} examples={examples} />
      </div>
    </div>
  );
}
