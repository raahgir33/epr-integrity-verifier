import { PageContainer } from "@/components/ui/PageContainer";

export function Footer() {
  return (
    <footer className="mt-12 border-t border-border bg-surface">
      <PageContainer className="py-6 text-xs text-ink-muted">
        <p>
          <strong className="font-medium text-ink">SYNTHETIC DATA</strong> — every processor, brand,
          document and certificate shown here is fictional, generated for demonstration. No real company,
          recycler or brand is represented or implicated.
        </p>
      </PageContainer>
    </footer>
  );
}
