import { Skeleton } from "@/components/ui/Skeleton";

/** Generic route-segment loading placeholder (T13.8) — a title bar plus a
 * few content blocks, shown by every segment's loading.tsx while its
 * Server Component data fetch is in flight. Not a pixel match for any one
 * page's final layout; just enough shape that navigation never shows a
 * blank page. */
export function PageSkeleton() {
  return (
    <div className="space-y-6 py-8">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-full max-w-md" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
      <Skeleton className="h-64 w-full" />
    </div>
  );
}
