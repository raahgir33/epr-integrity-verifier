import type { ButtonHTMLAttributes, ReactNode } from "react";
import { titleCase } from "@/lib/titleCase";

const VARIANT = {
  primary: "bg-primary text-primary-foreground hover:opacity-90",
  secondary: "border border-border text-ink hover:bg-surface-sunk",
  ghost: "border border-border text-ink hover:bg-surface-sunk",
} as const;

const SIZE = {
  lg: "rounded-md px-5 py-3 text-base",
  sm: "rounded-md px-3 py-2.5 text-sm",
  // T13.5c plan, Audit Batch 6: xs stays visually compact (used for
  // tightly-packed toolbar rows — the memo letter's Copy/Print buttons,
  // gap-2 apart) but gets an invisible centered hit-area extension via
  // `relative` + `after:` instead of a direct padding bump, per
  // surfaces.md's small-control pattern. Sized to 32px (size-8), not the
  // usual 40px floor: at this row's 8px gap, a 40px box would overlap
  // the neighboring button's own extended hit area (surfaces.md's
  // collision rule — shrink rather than let two hit areas overlap);
  // 32px clears the gap with room to spare while still meaningfully
  // growing the ~24px visible target.
  xs: "relative rounded px-2 py-1 text-xs after:absolute after:left-1/2 after:top-1/2 after:size-8 after:-translate-x-1/2 after:-translate-y-1/2 after:content-['']",
} as const;

/** Shared CTA/toolbar button (T13.5b plan, Part 2) — a native <button>
 * carrying one of this app's existing visual styles, with Chicago title
 * case applied centrally to a plain-string label. Scoped to real
 * toolbar/CTA buttons (RunLiveVerification's actions, the memo letter's
 * EN/HI/Copy/Print controls) — NOT to inline prose links ("Read the
 * method →", evidence chips), which stay plain `<a>`/`<Link>` body-text
 * links, out of scope for title-casing. Next.js `Link`-based actions
 * (StickyHeader's "View Memo"/"Run Live Verification") call titleCase()
 * directly instead of this component, since Link isn't a <button>. */
export function Button({
  children,
  variant = "secondary",
  size = "sm",
  className = "",
  ...rest
}: {
  children: ReactNode;
  variant?: keyof typeof VARIANT;
  size?: keyof typeof SIZE;
  className?: string;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...rest}
      className={`font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50 ${SIZE[size]} ${VARIANT[variant]} ${className}`}
    >
      {typeof children === "string" ? titleCase(children) : children}
    </button>
  );
}
