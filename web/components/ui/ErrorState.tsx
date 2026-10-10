"use client";

import { useEffect } from "react";

/** Shared route-segment error boundary content (T13.8) — every segment's
 * error.tsx renders this instead of duplicating the same markup. A single
 * message, not a per-cause one: nearly everything this app renders comes
 * from the API, and Next.js redacts a Server Component error's real
 * message in production (sending only a generic placeholder + digest —
 * see node_modules/next/dist/docs/01-app/03-api-reference/03-file-
 * conventions/error.md), so a client-visible distinction based on
 * `error.message` would silently stop working outside `next dev`. */
export function ErrorState({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Logged for local debugging only — never shown to the viewer.
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto max-w-lg py-20 text-center">
      <h1 className="font-display text-2xl font-semibold text-balance text-ink">Data service unavailable</h1>
      <p className="mt-3 text-pretty text-ink-muted">
        The verification API could not be reached. This page will work again once it&apos;s back.
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 rounded-md border border-border bg-surface px-4 py-2.5 text-sm font-medium text-ink outline-none transition-[background-color,scale] duration-150 hover:bg-surface-sunk focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary motion-safe:active:scale-[0.96]"
      >
        Try again
      </button>
    </div>
  );
}
