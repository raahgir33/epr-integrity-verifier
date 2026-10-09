"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Menu, X } from "lucide-react";
import { PageContainer } from "@/components/ui/PageContainer";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/evaluation", label: "Evaluation" },
  { href: "/method", label: "Method" },
];

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-surface">
      <PageContainer className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-4">
        <Link
          href="/"
          className="font-display text-xl font-bold tracking-tight text-primary whitespace-nowrap outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
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
                  className={`outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                    active
                      ? "font-medium text-primary underline decoration-2 underline-offset-4"
                      : "text-ink-muted hover:text-ink"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
          <ThemeToggle />
        </div>

        <div className="flex items-center gap-2 sm:hidden">
          <ThemeToggle />
          <button
            type="button"
            aria-expanded={open}
            aria-controls="primary-nav-mobile"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((v) => !v)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setOpen(false);
            }}
            className="flex h-10 w-10 items-center justify-center rounded-md border border-border text-ink outline-none transition-transform duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary motion-safe:active:scale-[0.96]"
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
                  className={`outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
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
