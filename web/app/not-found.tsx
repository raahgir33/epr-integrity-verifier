import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-lg py-20 text-center">
      <h1 className="font-display text-2xl font-semibold text-balance text-ink">Not found</h1>
      <p className="mt-3 text-pretty text-ink-muted">There&apos;s no processor or page at this address.</p>
      <Link
        href="/"
        className="mt-6 inline-block rounded-md border border-border bg-surface px-4 py-2.5 text-sm font-medium text-ink hover:bg-surface-sunk"
      >
        Back to Overview
      </Link>
    </div>
  );
}
