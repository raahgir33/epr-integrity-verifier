import Link from "next/link";
import { RiskBadge } from "@/components/RiskBadge";
import { StatCard } from "@/components/StatCard";
import { Heading } from "@/components/ui/Heading";
import { getBrands, getPortfolio } from "@/lib/api";
import { formatMonth, formatTonnes } from "@/lib/format";

export default async function PortfolioPage({
  searchParams,
}: {
  searchParams: Promise<{ brand?: string }>;
}) {
  const { brand: brandParam } = await searchParams;

  const { brands } = await getBrands();
  const activeBrandId = brandParam && brands.some((b) => b.brand_id === brandParam)
    ? brandParam
    : brands[0]?.brand_id;

  if (!activeBrandId) {
    return <p className="text-sm text-ink-muted">No brands in this dataset.</p>;
  }

  const portfolio = await getPortfolio(activeBrandId);

  return (
    <div className="space-y-6">
      <div>
        <Heading>Brand portfolio</Heading>
        <p className="mt-1 max-w-[70ch] text-pretty text-sm text-ink-muted">
          Certificates a brand holds across processors, and the share that is verifiable — apportioned
          from each processor&apos;s own verifiable ratio, not a per-certificate traced figure.
        </p>
      </div>

      <nav aria-label="Brand" className="flex flex-wrap gap-2 border-b border-border text-sm">
        {brands.map((b) => (
          <Link
            key={b.brand_id}
            href={`/portfolio?brand=${encodeURIComponent(b.brand_id)}`}
            className={
              b.brand_id === activeBrandId
                ? "border-b-2 border-primary px-3 py-2.5 font-medium text-primary"
                : "border-b-2 border-transparent px-3 py-2.5 text-ink-muted hover:text-ink"
            }
          >
            {b.name}
          </Link>
        ))}
      </nav>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <StatCard label="Total certified" value={formatTonnes(portfolio.total_certified_t)} />
        <StatCard label="Total verifiable (apportioned)" value={formatTonnes(portfolio.total_verifiable_t)} />
      </div>

      <div className="card overflow-x-auto p-4">
        <table className="w-full min-w-[36rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-ink-muted">
              <th className="py-2 pr-4 font-medium">Certificate</th>
              <th className="py-2 pr-4 font-medium">Processor</th>
              <th className="py-2 pr-4 font-medium">Category</th>
              <th className="py-2 pr-4 font-medium">Period</th>
              <th className="py-2 pr-4 font-medium">Quantity</th>
              <th className="py-2 font-medium">Processor risk</th>
            </tr>
          </thead>
          <tbody>
            {portfolio.certificates.map((c) => (
              <tr key={c.certificate_id} className="border-b border-border last:border-0">
                <td className="py-2 pr-4 font-mono text-xs text-ink">{c.certificate_id}</td>
                <td className="py-2 pr-4">
                  <Link
                    href={`/processors/${encodeURIComponent(c.processor_id)}`}
                    className="text-ink underline decoration-dotted hover:text-primary"
                  >
                    {c.processor_id}
                  </Link>
                </td>
                <td className="py-2 pr-4 text-ink-muted">{c.category}</td>
                <td className="py-2 pr-4 text-ink-muted">{formatMonth(c.period_month)}</td>
                <td className="num-cell py-2 pr-4 tabular-nums">{formatTonnes(c.quantity_t)}</td>
                <td className="py-2">{c.processor_risk_band ? <RiskBadge band={c.processor_risk_band} /> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
