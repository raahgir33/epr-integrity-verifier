import { clsx, type ClassValue } from "clsx";

/** The `cn` helper the vendored Magic UI components (components/magicui/)
 * import from "@/lib/utils" by convention. Deliberately clsx-only, no
 * tailwind-merge — this app's own components never pass conflicting
 * Tailwind classes into these props, so clsx's plain concatenation is
 * sufficient and avoids adding a dependency beyond the task's allowed
 * list (motion, next-themes). */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}
