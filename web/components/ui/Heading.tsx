import type { ReactNode } from "react";
import { titleCase } from "@/lib/titleCase";

/** Page-level h1 (T13.5b plan, Part 2) — applies Chicago title case
 * centrally, but only when `children` is a plain string: a heading that
 * interpolates a data value (a processor name, a count) passes a JSX
 * fragment instead and is rendered verbatim, never title-cased. */
export function Heading({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <h1 className={`font-display text-2xl font-semibold text-balance text-ink ${className}`}>
      {typeof children === "string" ? titleCase(children) : children}
    </h1>
  );
}
