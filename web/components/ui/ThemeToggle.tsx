"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";

/** Light/dark switch (T13.5b plan, Part 2) — built from scratch, not
 * pulled from any third-party registry (the task's Unlumen ban covers
 * this control specifically; only next-themes' hook/provider logic is a
 * vendored package). Renders a neutral placeholder until mounted so the
 * server-rendered icon (always "light", since defaultTheme is "light")
 * never mismatches a client that resolves to dark before hydration. */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  // Standard next-themes hydration guard: the server always renders the
  // placeholder (theme is unknown before hydration), and this flips it
  // once mounted — there's no way to derive "has mounted" outside an effect.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setMounted(true), []);

  const isDark = mounted && resolvedTheme === "dark";

  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      aria-pressed={isDark}
      className={`flex h-9 w-9 items-center justify-center rounded-md border border-border text-ink-muted transition-colors duration-150 hover:bg-surface-sunk hover:text-ink ${className}`}
    >
      {mounted ? (
        isDark ? (
          <svg viewBox="0 0 16 16" aria-hidden className="h-4 w-4">
            <path
              d="M14 9.5A6 6 0 0 1 6.5 2a6 6 0 1 0 7.5 7.5Z"
              fill="currentColor"
            />
          </svg>
        ) : (
          <svg viewBox="0 0 16 16" aria-hidden className="h-4 w-4">
            <circle cx="8" cy="8" r="3.2" fill="currentColor" />
            <g stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
              <path d="M8 1v1.6M8 13.4V15M15 8h-1.6M2.6 8H1M12.7 3.3l-1.1 1.1M4.4 11.6l-1.1 1.1M12.7 12.7l-1.1-1.1M4.4 4.4 3.3 3.3" />
            </g>
          </svg>
        )
      ) : (
        <span className="h-4 w-4" aria-hidden />
      )}
    </button>
  );
}
