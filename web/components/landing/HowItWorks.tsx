"use client";

import { useState } from "react";
import { classificationLabel } from "@/lib/findings";
import { STATUS_LABEL } from "@/lib/checks";
import { isClarificationMemo } from "@/lib/memo";
import type { RealExamples } from "@/lib/landing";

const STEPS = [
  {
    title: "Read the paper trail",
    body:
      "Gemini extracts invoices, e-way bills, weighbridge slips, consent permits and electricity bills — mixed formats, some in Hindi — into structured facts, values captured exactly as printed.",
  },
  {
    title: "Deterministic checks",
    body:
      "Capacity, mass balance, transport plausibility, cross-document consistency, duplicates, consent validity and energy use are tested by unit-tested Python, never by the model.",
  },
  {
    title: "Two AI agents must agree",
    body:
      "A Hypothesis agent argues each certificate batch is or isn't supported; a Critic agent attacks that argument with tools. A finding only becomes a deduction once both agree.",
  },
  {
    title: "Clarification memo",
    body:
      "A clean processor gets a verification statement; a flagged one gets a draft clarification request — in English or Hindi — citing the exact evidence behind every item.",
  },
];

function ExampleBlock({ step, examples }: { step: number; examples: RealExamples }) {
  if (step === 0) {
    const ex = examples.hindiDoc;
    if (!ex) return <p className="text-sm text-ink-muted">No example document available right now.</p>;
    const field = ex.facts.fields[0];
    return (
      <div className="text-sm">
        <p className="text-ink-muted">
          <span className="font-mono text-xs text-ink-muted">{ex.processorId}</span> — {ex.doc.doc_type} ({ex.doc.lang})
        </p>
        {field ? (
          <p className="mt-1 text-ink">
            <span className="text-ink-muted">{field.field_name}: </span>
            <span lang="hi">{field.printed_value}</span>
          </p>
        ) : null}
      </div>
    );
  }
  if (step === 1) {
    const ex = examples.failingCheck;
    if (!ex) return <p className="text-sm text-ink-muted">No example check result available right now.</p>;
    return (
      <div className="text-sm">
        <p className="text-ink-muted">
          <span className="font-mono text-xs text-ink-muted">{ex.processorId}</span> —{" "}
          <span className="font-mono font-medium text-ink">{ex.check.check_id}</span>{" "}
          {STATUS_LABEL[ex.check.status] ?? ex.check.status}
        </p>
        <p className="mt-1 text-ink">{ex.check.explanation}</p>
      </div>
    );
  }
  if (step === 2) {
    const ex = examples.finding;
    if (!ex) return <p className="text-sm text-ink-muted">No example finding available right now.</p>;
    return (
      <div className="text-sm">
        <p className="text-ink-muted">
          <span className="font-mono text-xs text-ink-muted">{ex.processorId}</span> — {classificationLabel(ex.finding)}
        </p>
        <p className="mt-1 text-ink">{ex.finding.explanation}</p>
      </div>
    );
  }
  const ex = examples.memo;
  if (!ex || !isClarificationMemo(ex.memo.doc_type, ex.memo.memo)) {
    return <p className="text-sm text-ink-muted">No example memo available right now.</p>;
  }
  const item = ex.memo.memo.items[0];
  return (
    <div className="text-sm">
      <p className="text-ink-muted">
        <span className="font-mono text-xs text-ink-muted">{ex.processorId}</span> — {ex.memo.memo.subject}
      </p>
      {item ? <p className="mt-1 text-ink">{item.what_we_observed}</p> : null}
    </div>
  );
}

export function HowItWorks({ examples }: { examples: RealExamples }) {
  // Independent per-card state, not a single "which one is open" value —
  // a reader comparing steps should be able to expand more than one at
  // once, and tying every card to one shared value made "open all four"
  // structurally impossible (opening card 2 always closed card 1).
  const [openSteps, setOpenSteps] = useState<ReadonlySet<number>>(new Set());

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {STEPS.map((step, i) => {
        const open = openSteps.has(i);
        return (
          <div key={step.title} className="card flex flex-col p-4">
            <span className="text-xs font-medium uppercase tracking-wide text-accent">Step {i + 1}</span>
            <h3 className="mt-1 font-display text-base font-semibold text-ink">{step.title}</h3>
            <p className="mt-1 flex-1 text-sm text-ink-muted">{step.body}</p>
            <button
              type="button"
              onClick={() =>
                setOpenSteps((prev) => {
                  const next = new Set(prev);
                  if (next.has(i)) next.delete(i);
                  else next.add(i);
                  return next;
                })
              }
              aria-expanded={open}
              className="mt-3 self-start text-xs font-medium text-primary underline decoration-dotted hover:text-accent"
            >
              {open ? "Hide example" : "See a real example"}
            </button>
            {open ? (
              <div className="mt-3 border-t border-border pt-3">
                <ExampleBlock step={i} examples={examples} />
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
