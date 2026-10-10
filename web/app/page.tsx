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
      <FullBleed className="band -mt-8 pb-10 pt-8 sm:-mt-10 sm:pb-14 sm:pt-10">
        <HeroScene figures={figures} />
      </FullBleed>

      <AlertBanner alerts={alerts} />
      <div id="live-verification" className="scroll-mt-20">
        <RunLiveVerification batches={batches} />
      </div>

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
