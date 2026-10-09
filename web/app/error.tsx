"use client";

import { useEffect } from "react";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
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
        className="mt-6 rounded-md border border-border bg-surface px-4 py-2.5 text-sm font-medium text-ink hover:bg-surface-sunk"
      >
        Try again
      </button>
    </div>
  );
}
