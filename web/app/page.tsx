import type { Metadata } from "next";
import { AlertBanner } from "@/components/demo/AlertBanner";
import { RunLiveVerification } from "@/components/demo/RunLiveVerification";
import { AudienceTabs } from "@/components/landing/AudienceTabs";
import { CloudStrip } from "@/components/landing/CloudStrip";
import { Faq } from "@/components/landing/Faq";
import { HeroScene } from "@/components/landing/HeroScene";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { PortfolioPreview } from "@/components/landing/PortfolioPreview";
import { ProofStrip } from "@/components/landing/ProofStrip";
import { WhatWeCheck } from "@/components/landing/WhatWeCheck";
import { FullBleed } from "@/components/ui/FullBleed";
import { SectionTitle } from "@/components/ui/SectionTitle";
import { TextReveal } from "@/components/ui/TextReveal";
import { getAlerts, getDemoBatches, getProcessor, getProcessors } from "@/lib/api";
import { buildCheckCatalog, getLandingFigures, pickRealExamples } from "@/lib/landing";

export const metadata: Metadata = {
  title: "EPR Integrity Verifier",
  description:
    "See how many certified recycling tonnes are independently verifiable, with evidence for every finding.",
};

export default async function LandingPage() {
  const [{ processors }, { batches }, { alerts }] = await Promise.all([
    getProcessors(),
    getDemoBatches(),
    getAlerts(),
  ]);

  const processorIds = processors.map((p) => p.processor_id);
  const details = await Promise.all(processorIds.map((id) => getProcessor(id)));

  const [figures, examples] = await Promise.all([
    getLandingFigures(),
    pickRealExamples(processorIds, details),
  ]);
  const checkCatalog = buildCheckCatalog(details);

  return (
    <div className="space-y-16">
      {/* T13.6b plan, Part 3: full-bleed 100svh hero tucks directly under
          the fixed, transparent-over-hero Nav (Nav.tsx publishes
          --nav-h; the fallback here matches Nav's own fixed ~64px height
          for the brief instant before that CSS var is set). No .band/
          padding — HeroScene owns its own full background now. Cancels
          BOTH main's --nav-h top padding AND PageContainer's own py-8
          (2rem) top padding — missing the second one left a real,
          measured 32px gap above the hero in T13.6b's own verification
          pass (main's padding + PageContainer's py-8 - FullBleed's
          margin != 0 with only --nav-h cancelled). */}
      <FullBleed contained={false} className="-mt-[calc(var(--nav-h,4rem)+2rem)]">
        <HeroScene figures={figures} />
      </FullBleed>

      <div id="live-verification" className="scroll-mt-16">
        <RunLiveVerification batches={batches} />
      </div>
      <AlertBanner alerts={alerts} />

      <ProofStrip figures={figures} />

      <section id="how-it-works" className="scroll-mt-20">
        <TextReveal>
          <SectionTitle className="text-xl">How it works</SectionTitle>
        </TextReveal>
        <p className="mt-1 max-w-[70ch] text-pretty text-sm text-ink-muted">
          Four stages, each shown with a real example from the dataset.
        </p>
        <div className="mt-5">
          <HowItWorks examples={examples} />
        </div>
      </section>

      <section>
        <TextReveal>
          <SectionTitle className="text-xl">Who it&apos;s for</SectionTitle>
        </TextReveal>
        <div className="mt-5">
          <AudienceTabs details={details} examples={examples} />
        </div>
      </section>

      <section id="portfolio-preview" className="scroll-mt-20">
        <TextReveal>
          <SectionTitle className="text-xl">Processors</SectionTitle>
        </TextReveal>
        <p className="mt-1 max-w-[70ch] text-pretty text-sm text-ink-muted">
          Every processor in the dataset, with its risk band and headline finding.
        </p>
        <div className="mt-5">
          <PortfolioPreview details={details} />
        </div>
      </section>

      <FullBleed className="band py-12">
        <section>
          <TextReveal>
            <SectionTitle className="text-xl">What we check</SectionTitle>
          </TextReveal>
          <p className="mt-1 max-w-[70ch] text-pretty text-sm text-ink-muted">
            Every threshold lives in <code>app/checks/params.py</code>, cited to a rule or marked an
            explicit assumption. See <a href="/method" className="underline decoration-dotted hover:text-primary">Method</a> for the full detail.
          </p>
          <div className="mt-5">
            <WhatWeCheck catalog={checkCatalog} />
          </div>
        </section>

        <section className="mt-12">
          <CloudStrip />
        </section>
      </FullBleed>

      <section>
        <TextReveal>
          <SectionTitle className="text-center text-xl">Frequently asked</SectionTitle>
        </TextReveal>
        <div className="card mx-auto mt-5 w-full max-w-[70%] p-4">
          <Faq />
        </div>
      </section>
    </div>
  );
}
