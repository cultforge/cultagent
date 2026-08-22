/** Shared UI primitives for a standard ops dashboard. */

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-md bg-card-2 ${className}`}
      aria-hidden
    />
  );
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-label="Loading dashboard">
      <div className="flex items-end justify-between gap-3">
        <div className="space-y-2">
          <Skeleton className="h-7 w-40" />
          <Skeleton className="h-4 w-64" />
        </div>
        <Skeleton className="h-9 w-28" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="cf-panel space-y-3 p-4">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-8 w-24" />
            <Skeleton className="h-1 w-full" />
          </div>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[1.4fr_0.85fr]">
        <div className="cf-panel space-y-4 p-5">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-72" />
          <Skeleton className="h-9 w-56" />
          <div className="grid grid-cols-3 gap-4 pt-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        </div>
        <div className="cf-panel space-y-3 p-5">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      </div>
      <div className="cf-panel p-4">
        <Skeleton className="mb-3 h-4 w-32" />
        <Skeleton className="h-40 w-full" />
      </div>
    </div>
  );
}
