"use client";

import { useRef, type PointerEvent, type ReactNode } from "react";
import { useIsFinePointer } from "@/lib/useIsFinePointer";
import { usePrefersReducedMotion } from "@/lib/usePrefersReducedMotion";

/** Mouse-effect card (T13.5b plan, Kokonut addendum — built from scratch;
 * see THIRD_PARTY_NOTICES.md). A lighter cousin of SpotlightCard's "glow"
 * variant: the same cursor-following radial highlight, no tilt, no group
 * dimming — used on the landing page's Who It's For panels and portfolio
 * preview cards. Off for `prefers-reduced-motion` and on anything but a
 * fine, hover-capable pointer, checked in JS so the listener is never
 * even attached on a device that could never show the effect. */
export function MouseEffectCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const reducedMotion = usePrefersReducedMotion();
  const isFinePointer = useIsFinePointer();
  const active = isFinePointer && !reducedMotion;

  function handlePointerMove(e: PointerEvent<HTMLDivElement>) {
    if (!active) return;
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    ref.current!.style.setProperty("--spot-x", `${e.clientX - rect.left}px`);
    ref.current!.style.setProperty("--spot-y", `${e.clientY - rect.top}px`);
  }

  return (
    <div
      ref={ref}
      onPointerMove={handlePointerMove}
      className={`${active ? "spotlight-card spotlight-card-glow" : ""} ${className}`}
    >
      {children}
    </div>
  );
}
