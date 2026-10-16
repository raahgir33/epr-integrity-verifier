"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useMotionValueEvent, useScroll } from "motion/react";
import { Menu, X } from "lucide-react";
import { PageContainer } from "@/components/ui/PageContainer";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/evaluation", label: "Evaluation" },
  { href: "/method", label: "Method" },
  { href: "/api-docs", label: "API Docs" },
];

const SOLID_SCROLL_THRESHOLD_PX = 40;

/** T13.6b plan, Part 3: Nav now overlays the landing page's full-bleed
 * hero — fixed instead of sticky, transparent over the hero until the
 * page scrolls past a small threshold (or on every other route, where
 * there's no hero to sit over). Publishes its own rendered height as
 * `--nav-h` on the document root via ResizeObserver, so layout.tsx's
 * <main> and the landing page's hero (its own negative-margin cancel)
 * both read one source of truth instead of a hardcoded guess that would
 * drift the moment Nav's own padding changes. */
/** T16b: the hero's text-column scrim is gone (see HeroScene.tsx), and
 * the nav sits transparent over the sky on the home page. Measured after
 * the scrim came out, the brand fell to 2.52:1 against the brightest
 * cloud behind it, under its 3.0 large-text floor; `drop-shadow-sm`
 * (0 1px 1px at 5% alpha) was never doing real work there. This matches
 * the 45 degree cast and intensity the hero copy now uses, so the nav and
 * the headline below it read as one light source. Applied ONLY in the
 * transparent state — on every other page the nav sits on a solid
 * surface and needs nothing. */
const OVER_HERO_TEXT_SHADOW = "1px 1px 2px rgb(6 16 40 / 0.78), 2px 2px 12px rgb(6 16 40 / 0.63)";

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [scrollYValue, setScrollYValue] = useState(0);
  const headerRef = useRef<HTMLElement>(null);

  const isHome = pathname === "/";
  // Plain scroll-position state, not a "solid" boolean reset per route —
  // `transparent` below derives straight from isHome + the current
  // value, so there's no second effect needed just to reset state when
  // the route changes (avoids react-hooks/set-state-in-effect: setState
  // inside this callback is the subscribe-to-an-external-system case the
  // rule itself calls out as fine, not a plain effect body).
  const { scrollY } = useScroll();
  useMotionValueEvent(scrollY, "change", setScrollYValue);

  useEffect(() => {
    const el = headerRef.current;
    if (!el) return;
    const setVar = () => document.documentElement.style.setProperty("--nav-h", `${el.offsetHeight}px`);
    setVar();
    const observer = new ResizeObserver(setVar);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const transparent = isHome && scrollYValue <= SOLID_SCROLL_THRESHOLD_PX;

  return (
    <header
      ref={headerRef}
      className={`fixed inset-x-0 top-0 z-40 transition-colors duration-200 ${
        transparent ? "border-b border-transparent bg-transparent" : "border-b border-border bg-surface"
      }`}
    >
      <PageContainer className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-4">
        <Link
          href="/"
          style={transparent ? { textShadow: OVER_HERO_TEXT_SHADOW } : undefined}
          className={`font-display text-xl font-bold tracking-tight whitespace-nowrap outline-none focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 ${
            transparent
              ? "text-white focus-visible:outline-white"
              : "text-primary focus-visible:outline-primary"
          }`}
        >
          EPR Integrity Verifier
        </Link>

        <div className="hidden items-center gap-5 sm:flex">
          <nav aria-label="Primary" className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
            {LINKS.map((link) => {
              const active = link.href === "/" ? pathname === "/" : pathname?.startsWith(link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  style={transparent ? { textShadow: OVER_HERO_TEXT_SHADOW } : undefined}
                  className={`outline-none focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 ${
                    transparent
                      ? `focus-visible:outline-white ${
                          active ? "font-medium text-white underline decoration-2 underline-offset-4" : "text-white/80 hover:text-white"
                        }`
                      : `focus-visible:outline-primary ${
                          active
                            ? "font-medium text-primary underline decoration-2 underline-offset-4"
                            : "text-ink-muted hover:text-ink"
                        }`
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
          <ThemeToggle variant={transparent ? "overlay" : "default"} />
        </div>

        <div className="flex items-center gap-2 sm:hidden">
          <ThemeToggle variant={transparent ? "overlay" : "default"} />
          <button
            type="button"
            aria-expanded={open}
            aria-controls="primary-nav-mobile"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((v) => !v)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setOpen(false);
            }}
            className={`flex h-10 w-10 items-center justify-center rounded-md border outline-none transition-transform duration-150 focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 motion-safe:active:scale-[0.96] ${
              transparent
                ? "border-white/40 text-white focus-visible:outline-white"
                : "border-border text-ink focus-visible:outline-primary"
            }`}
          >
            {/* T13.5c plan, Audit Batch 1: Lucide Menu/X, cross-faded per
                the make-interfaces-feel-better skill's exact contextual
                icon-animation spec — replacing the raw unicode glyphs. */}
            <AnimatePresence initial={false} mode="popLayout">
              <motion.span
                key={open ? "close" : "open"}
                initial={{ opacity: 0, scale: 0.25, filter: "blur(4px)" }}
                animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
                exit={{ opacity: 0, scale: 0.25, filter: "blur(4px)" }}
                transition={{ type: "spring", duration: 0.3, bounce: 0 }}
                className="flex"
              >
                {open ? <X aria-hidden size={16} /> : <Menu aria-hidden size={16} />}
              </motion.span>
            </AnimatePresence>
          </button>
        </div>
      </PageContainer>

      {open ? (
        // Always solid regardless of `transparent` — this is a dropdown
        // overlay sitting on top of whatever's behind it, not the bar
        // itself, so it needs its own legible background either way.
        <nav
          id="primary-nav-mobile"
          aria-label="Primary"
          className="border-t border-border bg-surface sm:hidden"
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
          }}
        >
          <PageContainer className="flex flex-col gap-1 py-3 text-sm">
            {LINKS.map((link) => {
              const active = link.href === "/" ? pathname === "/" : pathname?.startsWith(link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  onClick={() => setOpen(false)}
                  className={`outline-none focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                    active
                      ? "rounded px-2 py-2 font-medium text-primary bg-surface-sunk"
                      : "rounded px-2 py-2 text-ink-muted hover:bg-surface-sunk hover:text-ink"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </PageContainer>
        </nav>
      ) : null}
    </header>
  );
}
