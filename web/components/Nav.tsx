"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/evaluation", label: "Evaluation" },
  { href: "/method", label: "Method" },
];

export function Nav() {
  const pathname = usePathname();

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-4 sm:px-6 xl:max-w-7xl xl:px-8">
        <Link href="/" className="font-display text-lg font-semibold tracking-tight text-slate-900">
          EPR Integrity Verifier
        </Link>
        <nav aria-label="Primary" className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
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
      </div>
    </header>
  );
}
