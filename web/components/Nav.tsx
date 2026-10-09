"use client";

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { PageContainer } from "@/components/ui/PageContainer";

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
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
      <PageContainer className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-4">
        <Link href="/" className="font-display text-lg font-semibold tracking-tight text-slate-900">
          EPR Integrity Verifier
        </Link>

        <nav aria-label="Primary" className="hidden flex-wrap gap-x-5 gap-y-1 text-sm sm:flex">
          {LINKS.map((link) => {
            const active = link.href === "/" ? pathname === "/" : pathname?.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={
                  active
                    ? "font-medium text-slate-900 underline decoration-2 underline-offset-4"
                    : "text-slate-600 hover:text-slate-900"
                }
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <button
          type="button"
          aria-expanded={open}
          aria-controls="primary-nav-mobile"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((v) => !v)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
          }}
          className="flex h-9 w-9 items-center justify-center rounded-md border border-slate-300 text-slate-700 sm:hidden"
        >
          <span aria-hidden className="text-base leading-none">
            {open ? "✕" : "☰"}
          </span>
        </button>
      </PageContainer>

      {open ? (
        <nav
          id="primary-nav-mobile"
          aria-label="Primary"
          className="border-t border-slate-200 bg-white sm:hidden"
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
                  className={
                    active
                      ? "rounded px-2 py-2 font-medium text-slate-900 bg-slate-50"
                      : "rounded px-2 py-2 text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }
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
