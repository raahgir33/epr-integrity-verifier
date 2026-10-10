"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { AnimatePresence, motion } from "motion/react";
import { Moon, Sun } from "lucide-react";

/** Light/dark switch (T13.5b plan, Part 2) — built from scratch, not
 * pulled from any third-party registry (the task's Unlumen ban covers
 * this control specifically; only next-themes' hook/provider logic is a
 * vendored package). Renders a neutral placeholder until mounted so the
 * server-rendered icon (always "light", since defaultTheme is "light")
 * never mismatches a client that resolves to dark before hydration.
 *
 * Icons (T13.5c plan, Audit Batch 1) are Lucide Sun/Moon, cross-faded on
 * toggle per the make-interfaces-feel-better skill's exact contextual
 * icon-animation spec: scale 0.25->1, opacity 0->1, blur 4px->0px,
 * {type:"spring", duration:0.3, bounce:0}. initial={false} so the
 * mount/hydration transition itself doesn't animate — only a real click.
 *
 * `variant="overlay"` (T13.6b plan, Part 3: Nav transparent over the
 * hero) swaps the border/text colour set outright rather than appending
 * an overriding className — this file's own lib/utils.ts documents that
 * `cn()` is plain clsx, no tailwind-merge, specifically because this
 * app's components never pass conflicting Tailwind classes into a
 * className prop; a trailing override here would fight that convention
 * and depend on unstable stylesheet-order luck. */
const VARIANT_CLASSES = {
  default: "border-border text-ink-muted hover:bg-surface-sunk hover:text-ink focus-visible:outline-primary",
  overlay: "border-white/40 text-white hover:bg-white/10 hover:text-white focus-visible:outline-white",
} as const;

export function ThemeToggle({
  className = "",
  variant = "default",
}: {
  className?: string;
  variant?: keyof typeof VARIANT_CLASSES;
}) {
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
      className={`flex h-10 w-10 items-center justify-center rounded-md border outline-none transition-[color,background-color,scale] duration-150 focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 motion-safe:active:scale-[0.96] ${VARIANT_CLASSES[variant]} ${className}`}
    >
      {mounted ? (
        <AnimatePresence initial={false} mode="popLayout">
          <motion.span
            key={isDark ? "dark" : "light"}
            initial={{ opacity: 0, scale: 0.25, filter: "blur(4px)" }}
            animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, scale: 0.25, filter: "blur(4px)" }}
            transition={{ type: "spring", duration: 0.3, bounce: 0 }}
            className="flex"
          >
            {isDark ? <Moon aria-hidden size={16} /> : <Sun aria-hidden size={16} />}
          </motion.span>
        </AnimatePresence>
      ) : (
        <span className="h-4 w-4" aria-hidden />
      )}
    </button>
  );
}
