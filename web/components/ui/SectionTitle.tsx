import type { ReactNode } from "react";
import { titleCase } from "@/lib/titleCase";

/** Section-level heading (T13.5b plan, Part 2) — h2 by default, h3 for a
 * nested card title (e.g. a How It Works step). Callers supply their own
 * size classes (section headings and card titles use different text
 * sizes today); this component only owns the tag + weight + title-case
 * behavior, same string-only rule as Heading. */
export function SectionTitle({
  children,
  as = "h2",
  className = "",
}: {
  children: ReactNode;
  as?: "h2" | "h3";
  className?: string;
}) {
  const Tag = as;
  return (
    <Tag className={`font-display font-semibold text-balance text-ink ${className}`}>
      {typeof children === "string" ? titleCase(children) : children}
    </Tag>
  );
}
