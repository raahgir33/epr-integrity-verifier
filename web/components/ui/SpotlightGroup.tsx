"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

/** Coordinates the "others dim" half of SpotlightCard's full variant
 * (T13.5b plan, Kokonut addendum) across a set of sibling cards — a
 * single card can't know its siblings exist on its own. Wrap a grid of
 * `<SpotlightCard variant="full" index={i}>` in this; the glow-only
 * variant (processor metric tiles) never needs a group at all. */
const SpotlightGroupContext = createContext<{
  hovered: number | null;
  setHovered: (index: number | null) => void;
} | null>(null);

export function SpotlightGroup({ children }: { children: ReactNode }) {
  const [hovered, setHovered] = useState<number | null>(null);
  return (
    <SpotlightGroupContext.Provider value={{ hovered, setHovered }}>{children}</SpotlightGroupContext.Provider>
  );
}

export function useSpotlightGroup() {
  return useContext(SpotlightGroupContext);
}
