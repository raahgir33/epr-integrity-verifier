import Link from "next/link";
import { PageContainer } from "@/components/ui/PageContainer";

export function Footer() {
  return (
    <footer className="mt-12 border-t border-border bg-surface">
      <PageContainer className="flex flex-wrap items-center justify-between gap-3 py-6 text-xs text-ink-muted">
        <p className="max-w-[60ch]">
          <strong className="font-medium text-ink">SYNTHETIC DATA</strong> — every processor, brand,
          document and certificate shown here is fictional, generated for demonstration. No real company,
          recycler or brand is represented or implicated.
        </p>
        <nav aria-label="Footer" className="flex shrink-0 gap-4 font-medium">
          <Link href="/method" className="hover:text-ink">
            Method
          </Link>
          <Link href="/evaluation" className="hover:text-ink">
            Evaluation
          </Link>
        </nav>
      </PageContainer>
    </footer>
  );
}
