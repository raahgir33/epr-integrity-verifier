/** Amendment 6 (T12 plan): C8's evidence_ids is literally
 * site_assessments.thumbnail_gcs_path (e.g. "gs://.../site/PWP-05.png" or
 * "seed-42/site/PWP-05.png" — see api/app/geo/site.py's
 * site_assessment_to_check_result). That's an internal storage path, never
 * a document to open — resolve it to the Site evidence tab instead of
 * showing the raw path or trying to open it as a file. T13.5 plan,
 * Amendment C: the processor page moved from an in-page #site anchor to a
 * ?tab=site query param, so this href is a relative query string — it
 * resolves against whatever page renders it (only ever the processor
 * page today), and ProcessorTabs reads it on mount/change the same way
 * it reads a direct ?tab= link. */
const STORAGE_PATH_PATTERN = /gs:\/\/|\/site\/|\.(png|jpe?g)$/i;

export type EvidenceResolution =
  | { kind: "document"; href: string; label: string }
  | { kind: "site"; href: string; label: string }
  | { kind: "plain"; label: string };

export function resolveEvidence(evidenceId: string, knownDocIds: ReadonlySet<string>): EvidenceResolution {
  if (knownDocIds.has(evidenceId)) {
    return { kind: "document", href: `/files/${encodeURIComponent(evidenceId)}`, label: evidenceId };
  }
  if (STORAGE_PATH_PATTERN.test(evidenceId)) {
    return { kind: "site", href: "?tab=site", label: "Site imagery" };
  }
  return { kind: "plain", label: evidenceId };
}
