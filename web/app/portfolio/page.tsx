import Link from "next/link";
import { RiskBadge } from "@/components/RiskBadge";
import { StatCard } from "@/components/StatCard";
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
    return <p className="text-sm text-slate-500">No brands in this dataset.</p>;
  }

  const portfolio = await getPortfolio(activeBrandId);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold text-slate-900">Brand portfolio</h1>
        <p className="mt-1 text-sm text-slate-600">
          Certificates a brand holds across processors, and the share that is verifiable — apportioned
          from each processor&apos;s own verifiable ratio, not a per-certificate traced figure.
        </p>
      </div>

      <nav aria-label="Brand" className="flex flex-wrap gap-2 border-b border-slate-200 text-sm">
        {brands.map((b) => (
          <Link
            key={b.brand_id}
            href={`/portfolio?brand=${encodeURIComponent(b.brand_id)}`}
            className={
              b.brand_id === activeBrandId
                ? "border-b-2 border-slate-900 px-3 py-2 font-medium text-slate-900"
                : "border-b-2 border-transparent px-3 py-2 text-slate-500 hover:text-slate-900"
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

      <div className="overflow-x-auto">
        <table className="w-full min-w-[36rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
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
              <tr key={c.certificate_id} className="border-b border-slate-100 last:border-0">
                <td className="py-2 pr-4 font-mono text-xs text-slate-700">{c.certificate_id}</td>
                <td className="py-2 pr-4">
                  <Link
                    href={`/processors/${encodeURIComponent(c.processor_id)}`}
                    className="text-slate-900 underline decoration-dotted hover:text-slate-700"
                  >
                    {c.processor_id}
                  </Link>
                </td>
                <td className="py-2 pr-4 text-slate-600">{c.category}</td>
                <td className="py-2 pr-4 text-slate-600">{formatMonth(c.period_month)}</td>
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
