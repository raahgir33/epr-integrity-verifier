import { AlertBanner } from "@/components/demo/AlertBanner";
import { RunLiveVerification } from "@/components/demo/RunLiveVerification";
import { ProcessorsTable } from "@/components/ProcessorsTable";
import { StatCard } from "@/components/StatCard";
import { getAlerts, getDemoBatches, getProcessors } from "@/lib/api";
import { formatSignedTonnes, formatTonnes } from "@/lib/format";

export default async function OverviewPage() {
  const [{ processors }, { batches }, { alerts }] = await Promise.all([
    getProcessors(),
    getDemoBatches(),
    getAlerts(),
  ]);

  const totalCertified = processors.reduce((sum, p) => sum + p.checks_only.certified_t, 0);
  const totalChecksOnly = processors.reduce((sum, p) => sum + p.checks_only.verifiable_t, 0);
  const totalWithAgents = processors.reduce(
    (sum, p) => sum + (p.full ? p.full.verifiable_t : p.checks_only.verifiable_t),
    0,
  );
  const delta = totalWithAgents - totalChecksOnly;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-2xl font-semibold text-slate-900">Portfolio overview</h1>
        <p className="mt-1 text-sm text-slate-600">
          Certified EPR tonnes across all processors, and the share that is independently verifiable —
          checks-only, and with the agent loop&apos;s own findings folded in.
        </p>
      </div>

      <AlertBanner alerts={alerts} />
      <RunLiveVerification batches={batches} />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        <StatCard label="Certified" value={formatTonnes(totalCertified)} />
        <StatCard label="Checks-only verifiable" value={formatTonnes(totalChecksOnly)} />
        <StatCard label="With agents verifiable" value={formatTonnes(totalWithAgents)} />
        <StatCard
          label="Agents' own contribution"
          value={formatSignedTonnes(delta)}
          sub={delta > 0 ? "additional tonnes confirmed unverifiable" : undefined}
        />
      </div>

      <div>
        <h2 className="font-display text-lg font-semibold text-slate-900">Processors</h2>
        <div className="mt-3">
          <ProcessorsTable processors={processors} />
        </div>
      </div>
    </div>
  );
}
