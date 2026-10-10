import Link from "next/link";
import { PageContainer } from "@/components/ui/PageContainer";

export function Footer() {
  return (
    <footer className="mt-12 border-t border-border bg-surface">
      <PageContainer className="py-6 text-footer text-ink-muted">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <p className="max-w-[75ch] text-pretty">
            <strong className="font-medium text-ink">SYNTHETIC DATA.</strong> Every processor, brand,
            document and certificate shown here is fictional, generated for demonstration. No real company,
            recycler or brand is represented or implicated.
          </p>
          <nav aria-label="Footer" className="flex shrink-0 gap-4 pt-0.5 font-medium">
            <Link href="/method" className="outline-none hover:text-ink focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
              Method
            </Link>
            <Link href="/evaluation" className="outline-none hover:text-ink focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
              Evaluation
            </Link>
          </nav>
        </div>
        <p className="mt-2 text-pretty">Hero imagery generated with Google Flow.</p>
      </PageContainer>
    </footer>
  );
}
