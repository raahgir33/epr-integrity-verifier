/** Amendment 6 (T12 plan): C8's evidence_ids is literally
 * site_assessments.thumbnail_gcs_path (e.g. "gs://.../site/PWP-05.png" or
 * "seed-42/site/PWP-05.png" — see api/app/geo/site.py's
 * site_assessment_to_check_result). That's an internal storage path, never
 * a document to open — resolve it to the on-page site panel anchor instead
 * of showing the raw path or trying to open it as a file. */
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
    return { kind: "site", href: "#site", label: "Site imagery" };
  }
  return { kind: "plain", label: evidenceId };
}
