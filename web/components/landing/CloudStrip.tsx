const SERVICES = [
  "Gemini on Vertex AI",
  "Cloud Run",
  "BigQuery",
  "Cloud Storage",
  "Pub/Sub",
  "Earth Engine",
];

export function CloudStrip() {
  return (
    <div className="text-center">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">Built on Google Cloud</p>
      <p className="mx-auto mt-2 max-w-3xl text-sm text-ink-muted">{SERVICES.join(" · ")}</p>
    </div>
  );
}
