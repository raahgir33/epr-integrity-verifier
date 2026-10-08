import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-lg py-20 text-center">
      <h1 className="font-display text-2xl font-semibold text-slate-900">Not found</h1>
      <p className="mt-3 text-slate-600">There&apos;s no processor or page at this address.</p>
      <Link
        href="/"
        className="mt-6 inline-block rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        Back to Overview
      </Link>
    </div>
  );
}
