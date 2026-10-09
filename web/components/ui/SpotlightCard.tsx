"use client";

import { useRef, type PointerEvent, type ReactNode } from "react";
import { useIsFinePointer } from "@/lib/useIsFinePointer";
import { usePrefersReducedMotion } from "@/lib/usePrefersReducedMotion";
import { useSpotlightGroup } from "@/components/ui/SpotlightGroup";

/** Spotlight card (T13.5b plan, Kokonut addendum — built from scratch;
 * see THIRD_PARTY_NOTICES.md for why Kokonut's own version wasn't
 * vendored) — two variants:
 *
 * - `"full"` (landing feature cards — How It Works' 4 step cards): glow
 *   that follows the cursor, a subtle tilt, and dims sibling cards within
 *   the same SpotlightGroup while one is hovered.
 * - `"glow"` (processor metric tiles): the cursor-following glow only —
 *   no tilt, no dimming of neighbours, the numbers inside never move.
 *
 * Off entirely for `prefers-reduced-motion` and on anything but a fine,
 * hover-capable pointer — both checked in JS (not just CSS) so a touch
 * device never even attaches the listener for an effect it could never
 * show. `index`/`group` only matter for the "full" variant's dimming. */
export function SpotlightCard({
  children,
  variant = "full",
  index,
  className = "",
}: {
  children: ReactNode;
  variant?: "full" | "glow";
  index?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reducedMotion = usePrefersReducedMotion();
  const isFinePointer = useIsFinePointer();
  const group = useSpotlightGroup();
  const active = isFinePointer && !reducedMotion;

  function handlePointerMove(e: PointerEvent<HTMLDivElement>) {
    if (!active) return;
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    ref.current!.style.setProperty("--spot-x", `${x}px`);
    ref.current!.style.setProperty("--spot-y", `${y}px`);
    if (variant === "full") {
      ref.current!.style.setProperty("--spot-rotate-x", `${((y / rect.height - 0.5) * -6).toFixed(2)}deg`);
      ref.current!.style.setProperty("--spot-rotate-y", `${((x / rect.width - 0.5) * 6).toFixed(2)}deg`);
    }
  }

  function handlePointerEnter() {
    if (active && variant === "full" && group && index !== undefined) group.setHovered(index);
  }

  function handlePointerLeave() {
    if (variant === "full" && group && index !== undefined) group.setHovered(null);
    ref.current?.style.removeProperty("--spot-rotate-x");
    ref.current?.style.removeProperty("--spot-rotate-y");
  }

  const dimmed =
    active && variant === "full" && group?.hovered !== null && group?.hovered !== undefined && group.hovered !== index;

  return (
    <div
      ref={ref}
      onPointerMove={handlePointerMove}
      onPointerEnter={handlePointerEnter}
      onPointerLeave={handlePointerLeave}
      className={`${active ? `spotlight-card spotlight-card-${variant}` : ""} ${dimmed ? "spotlight-card-dimmed" : ""} ${className}`}
    >
      {children}
    </div>
  );
}
