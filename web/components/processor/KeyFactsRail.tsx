import type { FindingOut, ProcessorProfile } from "@/lib/api";
import { formatTonnes } from "@/lib/format";

const CONFIRMED = new Set(["deductible", "concurs_with_check"]);
const REVIEW = new Set(["systemic", "no_own_evidence", "review_flag"]);

/** Right-hand rail (T13.5 plan, Part 4) — key facts, confirmed findings
 * and review flags, visible alongside the tabs at lg and above. Sticky
 * top offset (top-40 = 10rem) approximates Nav (~4rem) + StickyHeader
 * (~6rem) stacked above it, so it starts just below both rather than
 * overlapping either. */
export function KeyFactsRail({
  profile,
  findings,
}: {
  profile: ProcessorProfile;
  findings: FindingOut[];
}) {
  const confirmedCount = findings.filter((f) => CONFIRMED.has(f.classification)).length;
  const reviewCount = findings.filter((f) => REVIEW.has(f.classification)).length;

  return (
    <aside className="hidden lg:block lg:self-start lg:sticky lg:top-40">
      <div className="card space-y-4 p-4 text-sm">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">Key facts</p>
          <dl className="mt-2 space-y-1.5">
            <div className="flex justify-between gap-2">
              <dt className="text-ink-muted">Type</dt>
              <dd className="text-ink">{profile.type}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-ink-muted">Capacity</dt>
              <dd className="num-cell text-ink">{formatTonnes(profile.capacity_t_per_year)}/yr</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-ink-muted">Consent window</dt>
              <dd className="text-right text-ink">
                {profile.consent_valid_from} – {profile.consent_valid_to}
              </dd>
            </div>
          </dl>
        </div>

        <div className="border-t border-border pt-3">
          <div className="flex items-center justify-between">
            <span className="text-ink-muted">Confirmed findings</span>
            <span className="num-cell font-semibold text-ink">{confirmedCount}</span>
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between">
            <span className="text-ink-muted">Review flags</span>
            <span className="num-cell font-semibold text-ink">{reviewCount}</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
