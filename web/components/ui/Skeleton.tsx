/** Loading skeleton (T13.5 plan, Part 2). Pulse animation is wrapped in
 * motion-safe: so prefers-reduced-motion viewers get a static block
 * instead — still a usable loading cue, just not an animated one. */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`motion-safe:animate-pulse rounded bg-surface-sunk ${className}`} />;
}
