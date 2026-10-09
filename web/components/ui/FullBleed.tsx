import type { ReactNode } from "react";
import { PageContainer } from "@/components/ui/PageContainer";

/** Breaks a section out of the layout's PageContainer to span the full
 * viewport width (for a hero band or a darker rhythm band), using the
 * standard negative-margin breakout rather than restructuring the root
 * layout — every other page keeps a single always-contained body.
 * `contained` (default true) re-wraps the section's own children in a
 * PageContainer so their content still aligns with the rest of the
 * page; pass false for content that should itself run edge to edge. */
export function FullBleed({
  children,
  className = "",
  contained = true,
}: {
  children: ReactNode;
  className?: string;
  contained?: boolean;
}) {
  return (
    <div className={`relative left-1/2 w-screen -translate-x-1/2 ${className}`}>
      {contained ? <PageContainer>{children}</PageContainer> : children}
    </div>
  );
}
