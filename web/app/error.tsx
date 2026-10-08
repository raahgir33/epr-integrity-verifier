"use client";

import { useEffect } from "react";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Logged for local debugging only — never shown to the viewer.
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto max-w-lg py-20 text-center">
      <h1 className="font-display text-2xl font-semibold text-slate-900">Data service unavailable</h1>
      <p className="mt-3 text-slate-600">
        The verification API could not be reached. This page will work again once it&apos;s back.
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        Try again
      </button>
    </div>
  );
}
