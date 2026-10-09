import type { AnchorHTMLAttributes, ReactNode } from "react";

/** Glow button (T13.5b plan, Part 5) — built from scratch (Unlumen ban).
 * Reserved for HeroScene's single primary CTA only; every other button in
 * the app stays a plain Button/link. A static luminous-green halo (via
 * globals.css's `.glow-pulse`, which is itself reduced-motion gated) plus
 * a thin glow-colored border — never the sole carrier of required
 * contrast, since the button's own background/foreground pairing already
 * meets AA independently of the glow. Colors are hard-coded, not the
 * theme's --color-primary/-foreground tokens: this button only ever sits
 * on HeroScene's own deliberately theme-invariant dark band (see
 * HeroScene's comment), so it needs the same fixed pairing, not one that
 * would flip (and stop contrasting) with the viewer's chosen theme. */
export function GlowButton({
  children,
  className = "",
  ...rest
}: {
  children: ReactNode;
  className?: string;
} & AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a
      {...rest}
      className={`glow-pulse rounded-md border border-glow/40 bg-[#faf7f1] px-4 py-2 text-sm font-medium text-[#15301f] transition-transform duration-150 hover:scale-[1.02] hover:opacity-90 ${className}`}
    >
      {children}
    </a>
  );
}
