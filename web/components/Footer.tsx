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
          {/* T16b: replaces the Method and Evaluation links at the
              developer's request. Neither route loses its way in — both
              are still in the primary nav.

              The label started at the hero's "Scroll to Discover" type
              (11px) and was scaled up at the developer's request — 11px
              read far smaller than the footer's own ~14px body copy
              beside it. It keeps that line's treatment (semibold,
              uppercase, widest tracking) but carries no shadow: the hero
              one sits on photography and needs the shadow to survive a
              bright cloud, this sits on a solid surface and does not.

              The asset is trimmed to its own ink before export — the
              original carried ~9% transparent padding top and bottom,
              which would have made the mark sit optically high and small
              inside its box next to the label. */}
          <div className="flex shrink-0 items-center gap-3 pt-0.5">
            <span className="text-[13px] font-semibold uppercase tracking-widest">Built By</span>
            {/* eslint-disable-next-line @next/next/no-img-element -- a fixed-size
                static mark; this file's sibling imagery (HeroScene) uses the
                same plain <img>, and next/image is not used anywhere here. */}
            <img
              src="/auromake-logo.png"
              alt="Auromake"
              width={482}
              height={100}
              decoding="async"
              className="h-7 w-auto"
            />
          </div>
        </div>
        <p className="mt-2 text-pretty">Hero imagery generated with Google Flow.</p>
      </PageContainer>
    </footer>
  );
}
