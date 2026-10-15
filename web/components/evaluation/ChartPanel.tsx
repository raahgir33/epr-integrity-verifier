"use client";

import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";

/** Shared frame for /evaluation's charts: a titled card, a caption, the
 * chart, and a disclosure revealing the same data as a real table.
 *
 * The toggle exists because a mark's value label is rounded for legibility
 * and a bar's height is not a number anyone can read off precisely — the
 * table carries each figure as stored. It is also the non-visual route to
 * every chart on this page. */
export function ChartPanel({
  title,
  caption,
  children,
  figures,
}: {
  title: string;
  caption: string;
  children: React.ReactNode;
  figures: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const figuresId = useId();

  return (
    <section className="card p-4">
      <h3 className="text-xs font-medium uppercase tracking-wide text-ink-muted">{title}</h3>
      <p className="mt-1 max-w-[80ch] text-pretty text-xs leading-relaxed text-ink-muted">
        {caption}
      </p>
      <div className="mt-3">{children}</div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={figuresId}
        onClick={() => setOpen((isOpen) => !isOpen)}
        className="mt-3 inline-flex min-h-11 items-center gap-1.5 rounded-sm px-1 text-xs font-medium text-ink-muted transition-colors duration-150 ease-out hover:text-primary"
      >
        <ChevronDown
          aria-hidden="true"
          strokeWidth={1.5}
          className={`size-3.5 transition-transform duration-150 ease-out ${open ? "rotate-180" : ""}`}
        />
        {open ? "Hide figures" : "Show figures"}
      </button>
      {/* Scrolls sideways on a narrow screen, so it is focusable and
          named: a keyboard user has no other way to reach the columns
          past the right edge. Hidden while collapsed, which also keeps
          it out of the tab order. */}
      <div
        id={figuresId}
        hidden={!open}
        className="mt-1 overflow-x-auto"
        role="region"
        aria-label={`${title}, figures`}
        tabIndex={0}
      >
        {figures}
      </div>
    </section>
  );
}

/** A figures table. The caption names the table for a screen reader; it is
 * visible too, since the disclosure button alone does not say what the
 * table holds. */
export function FiguresTable({
  caption,
  headers,
  children,
}: {
  caption: string;
  headers: string[];
  children: React.ReactNode;
}) {
  return (
    <table className="w-full border-collapse text-left text-xs">
      <caption className="pb-2 text-left text-xs text-ink-muted">{caption}</caption>
      <thead>
        <tr className="border-b border-border">
          {headers.map((header, index) => (
            <th
              key={header}
              scope="col"
              className={`py-1.5 pr-3 font-medium text-ink-muted ${index > 0 ? "text-right" : ""}`}
            >
              {header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  );
}

export function FiguresRow({
  header,
  values,
}: {
  header: string;
  values: (string | null)[];
}) {
  return (
    <tr className="border-b border-border/60 last:border-0">
      <th scope="row" className="py-1.5 pr-3 font-normal text-ink">
        {header}
      </th>
      {values.map((value, index) => (
        <td key={index} className="py-1.5 pr-3 text-right tabular-nums text-ink-muted">
          {value ?? "—"}
        </td>
      ))}
    </tr>
  );
}
